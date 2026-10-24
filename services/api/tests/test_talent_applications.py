"""POST /talent-applications (public website form) and GET (admin-only list)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from tinydb import TinyDB

from main import app
from talent import service

from conftest import ALICE, BOB, headers_for

VALID = {
    "full_name": "Ana García",
    "email": "Ana@Example.com",
    "phone": "+34 612 345 678",
    "country": "spain",
    "experience_years": 5,
    "sector": "technology",
    "english_level": "advanced",
    "availability": "immediate",
    "linkedin_url": "https://www.linkedin.com/in/ana",
    "comments": "Hola",
    "consent": True,
}


@pytest.fixture()
def client(tmp_path, monkeypatch) -> TestClient:
    database = TinyDB(tmp_path / "talent-db.json")
    monkeypatch.setattr(service, "_db", database)
    yield TestClient(app)  # no auth headers: the form is public
    database.close()


def test_post_is_public_and_returns_only_a_receipt(client):
    response = client.post("/talent-applications", json=VALID)
    assert response.status_code == 201
    assert set(response.json()) == {"id", "created_at"}  # no personal data echoed back


def test_post_stores_the_application_with_a_lowercased_email(client):
    client.post("/talent-applications", json=VALID)
    stored = client.get("/talent-applications", headers=headers_for(ALICE)).json()
    assert len(stored) == 1
    assert stored[0]["email"] == "ana@example.com"
    assert stored[0]["consent"] is True


def test_optional_fields_may_be_omitted_or_blank(client):
    payload = {k: v for k, v in VALID.items() if k not in {"linkedin_url", "comments"}}
    assert client.post("/talent-applications", json=payload).status_code == 201
    assert client.post("/talent-applications", json={**payload, "linkedin_url": ""}).status_code == 201


@pytest.mark.parametrize(
    "change",
    [
        {"full_name": "Ana"},  # name and surname required
        {"email": "not-an-email"},
        {"phone": "612345678"},  # no country code
        {"country": "mars"},
        {"experience_years": -1},
        {"experience_years": 51},
        {"sector": "other-thing"},
        {"english_level": "fluent"},
        {"availability": "whenever"},
        {"linkedin_url": "linkedin.com/in/ana"},  # must be http(s)
        {"comments": "x" * 501},
        {"consent": False},
        {"unknown_field": 1},  # extra keys are refused
    ],
)
def test_invalid_payloads_are_rejected_with_422(client, change):
    assert client.post("/talent-applications", json={**VALID, **change}).status_code == 422


@pytest.mark.parametrize("missing", [k for k in VALID if k not in {"linkedin_url", "comments"}])
def test_every_required_field_is_required(client, missing):
    payload = {k: v for k, v in VALID.items() if k != missing}
    assert client.post("/talent-applications", json=payload).status_code == 422


def test_nothing_is_stored_when_the_payload_is_rejected(client):
    client.post("/talent-applications", json={**VALID, "consent": False})
    assert client.get("/talent-applications", headers=headers_for(ALICE)).json() == []


def test_list_requires_a_session(client):
    assert client.get("/talent-applications").status_code == 401


def test_list_is_admin_only(client):
    assert client.get("/talent-applications", headers=headers_for(BOB)).status_code == 403
    assert client.get("/talent-applications", headers=headers_for(ALICE)).status_code == 200


def test_a_client_that_floods_the_form_is_slowed_down(client):
    statuses = [client.post("/talent-applications", json=VALID).status_code for _ in range(11)]

    assert statuses == [201] * 10 + [429]
    blocked = client.post("/talent-applications", json=VALID)
    assert blocked.status_code == 429 and int(blocked.headers["Retry-After"]) > 0
    assert len(client.get("/talent-applications", headers=headers_for(ALICE)).json()) == 10  # nothing stored past the limit
