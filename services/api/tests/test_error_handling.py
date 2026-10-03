"""Error handling: what the API sends when something goes wrong, and what it keeps out of
its answers and its log.

Every error is JSON; a 500 is generic and carries an ``error_id``; a validation error never
echoes the rejected value; the data files failing is a 503; the customer's email is only shown
in full to an admin; a damaged document does not take the list down; one user cannot export
another's analysis; and a wrong first-user password is never written to the log.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pytest
from conftest import ALICE, BOB, headers_for, uuid_of
from fastapi.testclient import TestClient
from jose import jwt
from tinydb import TinyDB

from auth.security import decode_access_token, verify_password
from core import config, logging_config
from core.errors import INTERNAL_ERROR_MESSAGE, UNAVAILABLE_MESSAGE, DatabaseUnavailableError
from core.storage import open_database
from incidents import incident_store as store
from incidents import service as csv_service
from main import app
from profiles import service as profiles_service
from suppliers import service as suppliers_service
from users import service as users_service

NEW = {
    "title": "VPN drops",
    "description": "VPN drops every ten minutes",
    "category": "TECHNICAL",
    "origin": "customer",
    "branch": "central",
    "customer_email": "jane.doe@acme.com",
}
JSON = {"Content-Type": "application/json"}
HEADER = "ticket_id,date,client_company,category,description,agent_id,customer_email,status,satisfaction_score\n"
ROW = "NXV-000001,2024-01-18,ACME,TECHNICAL,Role permissions not updated,AGT-08,jane@acme.com,{status},\n"


@pytest.fixture()
def incidents_db(tmp_path, monkeypatch):
    database = TinyDB(tmp_path / "incidents.json")
    monkeypatch.setattr(store, "_db", database)
    yield database
    database.close()


@pytest.fixture()
def api(auth_headers) -> TestClient:
    return TestClient(app, headers=auth_headers, raise_server_exceptions=False)


@pytest.fixture()
def analyses(monkeypatch):
    monkeypatch.setattr(csv_service, "_results", {})


# --- every error is JSON ---------------------------------------------------------------------

def test_an_unexpected_error_is_a_generic_json_500_with_an_error_id_and_cors(api, monkeypatch):
    def boom(**_):
        raise RuntimeError("secret detail: hunter2")

    monkeypatch.setattr(suppliers_service, "list_suppliers", boom)
    response = api.get("/suppliers", headers={"Origin": "http://localhost:5174", **headers_for(ALICE)})
    assert response.status_code == 500
    body = response.json()
    assert body["detail"] == INTERNAL_ERROR_MESSAGE and len(body["error_id"]) == 8
    assert "hunter2" not in response.text
    assert response.headers["access-control-allow-origin"] == "http://localhost:5174"  # the browser can read it


def test_an_unexpected_error_is_logged_with_its_id_and_traceback(api, monkeypatch, caplog):
    def boom(**_):
        raise RuntimeError("secret detail: hunter2")

    monkeypatch.setattr(suppliers_service, "list_suppliers", boom)
    with caplog.at_level(logging.ERROR):
        error_id = api.get("/suppliers").json()["error_id"]
    # The traceback stays in the server log (that is where it is useful); only the client never sees it.
    assert error_id in caplog.text and "RuntimeError" in caplog.text and "boom" in caplog.text


@pytest.mark.parametrize("path,body", [
    ("/profiles/me", b'{"name": NaN}'),
    ("/suppliers", b'{"monthly_rate": NaN, "name": "x"}'),
    ("/suppliers/1", b'{"monthly_rate": Infinity}'),
    ("/suppliers/1/rate", b'{"monthly_rate": NaN}'),
    ("/suppliers/1/status", b'{"status": NaN}'),
])
def test_nan_or_infinity_in_a_body_is_a_422_not_a_500(api, path, body):
    method = "put" if path == "/profiles/me" else "post" if path == "/suppliers" else "patch"
    response = getattr(api, method)(path, content=body, headers=JSON)
    assert response.status_code == 422, response.text
    assert isinstance(response.json()["detail"], list)


def test_a_validation_error_never_echoes_the_rejected_value(api):
    response = api.put("/profiles/me", json={"name": "n" * 500, "phone": "+34 600 000 000"}, headers=JSON)
    assert response.status_code == 422
    for error in response.json()["detail"]:
        assert "input" not in error and "ctx" not in error
    assert "nnnnn" not in response.text

    broken = api.post("/suppliers", content="{bad", headers=JSON)
    assert broken.status_code == 422 and all("input" not in e and "ctx" not in e for e in broken.json()["detail"])


def test_unknown_routes_and_methods_are_json_too(api):
    for response in (api.get("/nope"), api.delete("/auth/me")):
        assert response.headers["content-type"].startswith("application/json")
        assert isinstance(response.json()["detail"], str)


# --- the data files ------------------------------------------------------------------------

def test_a_damaged_data_file_is_a_503_that_names_no_path(api, tmp_path, monkeypatch):
    damaged = tmp_path / "suppliers-db.json"
    damaged.write_text("{corrupt", encoding="utf-8")
    monkeypatch.setattr(suppliers_service, "_db", None)
    monkeypatch.setattr(suppliers_service, "get_suppliers_db_path", lambda: damaged)
    response = api.get("/suppliers")
    assert response.status_code == 503
    assert response.json() == {"detail": UNAVAILABLE_MESSAGE}
    assert str(tmp_path) not in response.text


def test_open_database_keeps_only_the_file_name_and_the_kind_of_error(tmp_path):
    damaged = tmp_path / "users-db.json"
    damaged.write_text("{corrupt", encoding="utf-8")
    with pytest.raises(DatabaseUnavailableError) as raised:
        open_database(damaged)
    assert "users-db.json" in str(raised.value) and "JSONDecodeError" in str(raised.value)
    assert str(tmp_path) not in str(raised.value)


def test_a_failed_open_is_tried_again_instead_of_being_remembered(tmp_path, monkeypatch):
    path = tmp_path / "suppliers-db.json"
    path.write_text("{corrupt", encoding="utf-8")
    monkeypatch.setattr(suppliers_service, "_db", None)
    monkeypatch.setattr(suppliers_service, "get_suppliers_db_path", lambda: path)
    with pytest.raises(DatabaseUnavailableError):
        suppliers_service.get_db()
    path.unlink()  # whoever looks after the server fixes the file
    assert len(suppliers_service.get_db()) > 0


# --- who sees which emails -------------------------------------------------------------------

def test_the_customer_email_and_the_staff_emails_are_only_shown_in_full_to_an_admin(incidents_db):
    admin = TestClient(app, headers=headers_for(ALICE))
    created = admin.post("/api/incidents", json=NEW)
    assert created.status_code == 201 and created.json()["customer_email"] == "jane.doe@acme.com"
    incident_id = created.json()["id"]

    seen_by_admin = admin.get(f"/api/incidents/{incident_id}").json()
    assert seen_by_admin["customer_email"] == "jane.doe@acme.com"
    assert seen_by_admin["history"][0]["actor"] == ALICE

    seen_by_user = TestClient(app, headers=headers_for(BOB)).get(f"/api/incidents/{incident_id}").json()
    assert seen_by_user["customer_email"] == "j***@acme.com"
    assert seen_by_user["history"][0]["actor"] == "a***@example.com"
    assert "jane.doe" not in str(seen_by_user) and "alice@" not in str(seen_by_user)


def test_what_a_non_admin_gets_back_from_an_edit_is_masked_too(incidents_db):
    incident_id = TestClient(app, headers=headers_for(ALICE)).post("/api/incidents", json=NEW).json()["id"]
    bob = TestClient(app, headers=headers_for(BOB))
    edited = bob.patch(f"/api/incidents/{incident_id}", json={"title": "VPN keeps dropping"}).json()
    assert edited["customer_email"] == "j***@acme.com"
    assert all("@" not in e["actor"] or "***" in e["actor"] for e in edited["history"])
    moved = bob.patch(f"/api/incidents/{incident_id}/status", json={"status": "in_progress"}).json()
    assert moved["customer_email"] == "j***@acme.com"


# --- a damaged document does not take the manager down ---------------------------------------

def test_a_document_that_cannot_be_read_is_skipped_and_logged(incidents_db, api, caplog):
    assert api.post("/api/incidents", json=NEW).status_code == 201
    store.insert({"id": "NXV-000777", "title": "left by an older data model"})  # most keys missing
    store.insert({"id": "weird", "status": "nonsense"})
    with caplog.at_level(logging.WARNING):
        listing = api.get("/api/incidents")
        summary = api.get("/api/incidents/summary")
        facets = api.get("/api/incidents/facets")
    assert (listing.status_code, summary.status_code, facets.status_code) == (200, 200, 200)
    assert listing.json()["total"] == 1 and summary.json()["total"] == 1
    assert "NXV-000777" in caplog.text
    assert api.post("/api/incidents", json=NEW).status_code == 201  # and new incidents can still be created


# --- uploading a CSV --------------------------------------------------------------------------

def analyze(client, content: bytes | str, name: str = "export.csv"):
    return client.post("/api/incidents/analyze", files={"file": (name, content)})


def test_a_row_with_a_status_nobody_defined_is_invalid_not_a_500(api, analyses):
    response = analyze(api, HEADER + ROW.format(status="PENDING") + ROW.format(status="OPEN"))
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["total_records"], body["valid_records"], body["invalid_records"]) == (2, 1, 1)


@pytest.mark.parametrize("content,name", [
    (b"hello", "notes.txt"),                        # not a .csv
    (b"\xff\xfe\x00bad", "export.csv"),             # not UTF-8
    (b"foo,bar\n1,2\n", "export.csv"),              # other columns
    (HEADER.encode(), "export.csv"),                # no rows
    ((HEADER + ROW.format(status="OPEN").replace("ACME", "x" * 200_000)).encode(), "export.csv"),  # a cell the parser refuses
])
def test_a_file_that_cannot_be_processed_is_always_a_422(api, analyses, content, name):
    response = analyze(api, content, name)
    assert response.status_code == 422, response.text
    assert isinstance(response.json()["detail"], str)


def test_a_file_over_the_limit_is_a_413(api, analyses, monkeypatch):
    monkeypatch.setattr(csv_service, "MAX_UPLOAD_BYTES", 100)
    response = analyze(api, HEADER + ROW.format(status="OPEN"))
    assert response.status_code == 413 and isinstance(response.json()["detail"], str)


def test_the_export_is_each_users_own_last_analysis(analyses):
    alice, bob = TestClient(app, headers=headers_for(ALICE)), TestClient(app, headers=headers_for(BOB))
    assert alice.get("/api/incidents/results/export").status_code == 404
    assert analyze(alice, HEADER + ROW.format(status="OPEN")).status_code == 200
    assert alice.get("/api/incidents/results/export").status_code == 200
    seen_by_bob = bob.get("/api/incidents/results/export")
    assert seen_by_bob.status_code == 404
    assert "POST" not in seen_by_bob.json()["detail"] and "/api/" not in seen_by_bob.json()["detail"]  # no endpoint in a user message
    assert analyze(bob, HEADER + ROW.format(status="OPEN") + ROW.format(status="CLOSED")).status_code == 200
    assert bob.get("/api/incidents/results/export").status_code == 200


def test_only_a_bounded_number_of_analyses_is_kept(monkeypatch):
    monkeypatch.setattr(csv_service, "_results", {})
    monkeypatch.setattr(csv_service, "MAX_KEPT_ANALYSES", 3)
    for owner in "abcd":
        csv_service.run_analysis(filename="a.csv", content=(HEADER + ROW.format(status="OPEN")).encode(), owner=owner)
    assert list(csv_service._results) == ["b", "c", "d"]


# --- the first user ------------------------------------------------------------------------

def test_a_first_user_password_that_is_not_valid_is_never_written_down(tmp_path, monkeypatch, caplog):
    database = TinyDB(tmp_path / "empty-users.json")
    monkeypatch.setattr(users_service, "_db", database)
    monkeypatch.setenv("AUTH_INITIAL_EMAIL", "admin@example.com")
    monkeypatch.setenv("AUTH_INITIAL_PASSWORD", "hunter2")  # too short
    with caplog.at_level(logging.DEBUG), pytest.raises(RuntimeError) as raised:
        users_service.bootstrap_first_user()
    assert "hunter2" not in str(raised.value) and "at least" in str(raised.value)
    assert raised.value.__cause__ is None and raised.value.__suppress_context__  # the original error quotes the password
    assert "hunter2" not in caplog.text
    database.close()


def test_a_valid_first_user_is_logged_by_id_not_by_email(tmp_path, monkeypatch, caplog):
    database = TinyDB(tmp_path / "empty-users.json")
    monkeypatch.setattr(users_service, "_db", database)
    monkeypatch.setenv("AUTH_INITIAL_EMAIL", "admin@example.com")
    monkeypatch.setenv("AUTH_INITIAL_PASSWORD", "a-long-enough-password")
    with caplog.at_level(logging.INFO):
        users_service.bootstrap_first_user()
    assert "Bootstrapped first user" in caplog.text and "admin@example.com" not in caplog.text
    database.close()


def test_an_email_that_is_already_taken_is_not_repeated_in_the_error(api):
    response = TestClient(app).post("/users", json={"email": ALICE, "password": "another-long-password"})
    assert response.status_code == 409
    assert ALICE not in response.text


# --- the log ---------------------------------------------------------------------------------

def test_the_access_log_keeps_the_path_and_drops_the_query_string():
    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:50000", "GET", "/api/incidents?q=maria.garcia&client_company=ACME", "1.1", 200), None,
    )
    assert logging_config._DropQueryString().filter(record) is True
    assert "maria" not in record.getMessage() and "/api/incidents" in record.getMessage()


def test_configure_logging_can_be_called_twice():
    logging_config.configure_logging()
    logging_config.configure_logging()
    filters = [f for f in logging.getLogger("uvicorn.access").filters if isinstance(f, logging_config._DropQueryString)]
    assert len(filters) == 1


def test_a_refused_token_is_logged_by_kind_and_never_quoted(caplog):
    secret = config.get_jwt_secret()
    expired = jwt.encode(
        {"user_id": str(uuid_of(ALICE)), "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        secret, algorithm=config.JWT_ALGORITHM,
    )
    forged = jwt.encode({"user_id": str(uuid_of(ALICE)), "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
                        "not-the-secret-not-the-secret-not-the-secret", algorithm=config.JWT_ALGORITHM)
    with caplog.at_level(logging.INFO):
        assert decode_access_token(expired) is None and decode_access_token(forged) is None
    assert "expired" in caplog.text and "invalid token" in caplog.text
    assert expired not in caplog.text and forged not in caplog.text


def test_a_malformed_stored_hash_is_logged_but_still_looks_like_a_wrong_password(caplog):
    with caplog.at_level(logging.WARNING):
        assert verify_password("whatever", "not-a-bcrypt-hash") is False
    assert "malformed" in caplog.text and "whatever" not in caplog.text


def test_a_failed_login_is_logged_without_the_email(caplog):
    with caplog.at_level(logging.WARNING):
        TestClient(app).post("/auth/login", data={"username": "someone@example.com", "password": "wrong-password-1"})
    assert "Failed login attempt" in caplog.text
    assert "someone@example.com" not in caplog.text and "wrong-password-1" not in caplog.text


# --- the repair of the profiles at start-up ---------------------------------------------------

def test_profiles_are_not_wiped_when_the_user_store_looks_empty(users_db, caplog):
    users_db.truncate()
    before = profiles_service.profile_user_ids()
    assert before
    with caplog.at_level(logging.WARNING):
        users_service.sync_profiles()
    assert profiles_service.profile_user_ids() == before
    assert "not deleting anything" in caplog.text


def test_an_orphan_profile_is_deleted_and_logged(caplog):
    orphan = "00000000-0000-0000-0000-00000000dead"
    profiles_service.ensure_profile(orphan, "ghost@example.com")
    with caplog.at_level(logging.INFO):
        users_service.sync_profiles()
    assert orphan not in profiles_service.profile_user_ids()
    assert orphan in caplog.text and "ghost@example.com" not in caplog.text
