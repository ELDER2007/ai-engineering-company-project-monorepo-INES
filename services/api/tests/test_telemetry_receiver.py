"""The telemetry receiver: batch in, per-event verdict out (what is stored is tested in test_telemetry_storage.py). See telemetry/router.py."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from uuid import uuid4

import pytest

from conftest import ALICE, headers_for
from telemetry import contract

pytestmark = [pytest.mark.anyio, pytest.mark.usefixtures("telemetry_db")]

SCHEMA = json.loads((Path(__file__).resolve().parents[3] / "docs" / "telemetry" / "event-schemas.json").read_text(encoding="utf-8"))
EXAMPLES = {example["event_type"]: example for example in SCHEMA["examples"]}


def browser_event(event_type: str = "section_viewed", **properties) -> dict:
    """A well-formed event as the backoffice builds it (userId null: the browser never knows the pseudonym)."""
    return {
        "eventId": str(uuid4()), "event_type": event_type, "schemaVersion": "2.0.0",
        "timestamp": "2026-10-27T10:00:00.000Z", "userId": None, "sessionId": str(uuid4()),
        "requestId": str(uuid4()), "environment": "test", "source": "backoffice",
        "properties": properties or {"section": "inventory", "locale": "es"},
    }


def inventory_event(**overrides) -> dict:
    event = copy.deepcopy(EXAMPLES["outbound_order_created"])
    event.update({"userId": None, "source": "backoffice", "eventId": str(uuid4()), "requestId": str(uuid4()), **overrides})
    return event


async def post(client, events, **kwargs):
    return await client.post("/telemetry/events", json={"events": events}, **kwargs)


async def test_a_valid_batch_is_acknowledged_with_200(async_client):
    response = await post(async_client, [browser_event(), browser_event(), browser_event()])
    assert response.status_code == 200
    assert response.json() == {"received": 3, "accepted": 3, "stored": 3, "rejected": []}


async def test_an_empty_batch_is_fine(async_client):
    assert (await post(async_client, [])).json() == {"received": 0, "accepted": 0, "stored": 0, "rejected": []}


async def test_the_body_is_parsed_whatever_the_content_type_because_sendbeacon_sends_text_plain(async_client):
    body = json.dumps({"events": [browser_event()]})
    response = await async_client.post("/telemetry/events", content=body, headers={"content-type": "text/plain;charset=UTF-8"})
    assert response.status_code == 200 and response.json()["accepted"] == 1


@pytest.mark.parametrize("body", ["not json", "[]", '{"events": "x"}', '{"event": {}}', "42", "null"])
async def test_a_body_that_is_not_a_batch_is_refused_as_a_whole(async_client, body):
    response = await async_client.post("/telemetry/events", content=body, headers={"content-type": "application/json"})
    assert response.status_code == 422


async def test_a_batch_is_capped_at_100_events_and_256_kb(async_client):
    assert (await post(async_client, [browser_event() for _ in range(100)])).json()["accepted"] == 100
    assert (await post(async_client, [browser_event() for _ in range(101)])).status_code == 422
    assert (await async_client.post("/telemetry/events", content=b"x" * (256 * 1024 + 1))).status_code == 413


async def test_one_bad_event_does_not_cost_the_good_ones(async_client):
    bad = browser_event()
    bad["properties"]["email"] = "someone@example.com"
    response = (await post(async_client, [browser_event(), bad, browser_event()])).json()
    assert (response["received"], response["accepted"]) == (3, 2)
    assert [r["index"] for r in response["rejected"]] == [1]
    assert response["rejected"][0]["event_id"] == bad["eventId"]


async def test_a_rejection_names_the_field_and_never_quotes_the_value(async_client):
    secret = "maria.lopez@example.com"
    leaking = [
        browser_event(section="inventory", locale=secret),  # wrong value of an enum
        {**browser_event(), "timestamp": secret},  # wrong format
        {**browser_event(), "eventId": secret},
    ]
    extra = browser_event()
    extra["properties"]["email"] = secret
    response = await post(async_client, [*leaking, extra])
    assert response.status_code == 200
    assert secret not in response.text.replace("email", "")  # the key name may be echoed, the value never
    assert response.json()["accepted"] == 0


@pytest.mark.parametrize("change", [
    lambda e: e.update(schemaVersion="1.0.0"),
    lambda e: e.update(event_type="logout"),
    lambda e: e.pop("sessionId"),
    lambda e: e.update(sessionId=None),  # a browser event needs a session
    lambda e: e.update(timestamp="2026-10-27T10:00:00+02:00"),  # UTC, ending in Z
    lambda e: e.update(requestId="not-a-uuid"),
    lambda e: e.update(environment="prod"),
    lambda e: e.update(unexpected=1),
    lambda e: e["properties"].update(section="payroll"),
])
async def test_the_contract_is_enforced(async_client, change):
    event = browser_event()
    change(event)
    assert (await post(async_client, [event])).json()["accepted"] == 0


async def test_a_non_object_event_is_rejected_not_a_server_error(async_client):
    response = await post(async_client, ["text", 7, None, [1]])
    assert response.status_code == 200 and response.json()["accepted"] == 0


async def test_every_example_of_the_contract_is_accepted_when_the_browser_relays_it_with_a_session(async_client, users_db):
    events = []
    for example in SCHEMA["examples"]:
        if example["source"] == "worker":
            continue  # the worker is not a browser
        events.append(copy.deepcopy(example) | {"userId": None, "source": "backoffice"})  # what the browser declares
    response = await post(async_client, events, headers=headers_for(ALICE))
    assert response.json()["rejected"] == []
    assert response.json()["accepted"] == len(events) >= 8


# --- identity and source are the server's ---------------------------------------------------------

async def test_an_inventory_event_needs_a_verified_session(async_client):
    anonymous = (await post(async_client, [inventory_event()])).json()
    assert anonymous["accepted"] == 0 and anonymous["rejected"][0]["path"] == "/userId"
    signed_in = (await post(async_client, [inventory_event()], headers=headers_for(ALICE))).json()
    assert signed_in["accepted"] == 1


async def test_a_token_that_is_not_valid_counts_as_no_session(async_client):
    response = await post(async_client, [inventory_event()], headers={"Authorization": "Bearer nonsense"})
    assert response.json()["accepted"] == 0
    assert (await post(async_client, [browser_event()], headers={"Authorization": "Bearer nonsense"})).json()["accepted"] == 1


async def test_the_browser_cannot_choose_its_userid_or_the_source_of_an_inventory_event():
    spoofed = inventory_event(userId="a" * 64, source="website")
    stamped = contract.stamp(spoofed, None)
    assert stamped["userId"] is None and stamped["source"] == "inventory_api"
    assert spoofed["userId"] == "a" * 64  # the input is not mutated


async def test_a_source_that_is_not_the_events_is_still_refused():
    event = browser_event()
    event["source"] = "api"  # the browser claiming to be the API for a browser event
    assert contract.problem(contract.stamp(event, None))["path"] == "/source"


def test_an_event_type_outside_the_catalogue_is_reported_as_such():
    event = browser_event()
    event["event_type"] = "logout"
    assert contract.problem(event) == {"path": "/event_type", "rule": "enum", "detail": "violates 'enum'"}


def test_a_closed_payload_names_the_unexpected_key_without_its_value():
    event = browser_event()
    event["properties"]["email"] = "maria@example.com"
    found = contract.problem(event)
    assert found["path"] == "/properties" and "'email'" in found["detail"] and "maria" not in found["detail"]


def test_the_pseudonym_is_a_stable_64_hex_hmac_that_is_not_the_user_id():
    first = contract.pseudonym("5f1c4d2e-0000-4000-8000-000000000001")
    assert first == contract.pseudonym("5f1c4d2e-0000-4000-8000-000000000001")
    assert first != contract.pseudonym("5f1c4d2e-0000-4000-8000-000000000002")
    assert len(first) == 64 and all(c in "0123456789abcdef" for c in first) and "5f1c4d2e" not in first


def test_the_events_fixed_to_the_inventory_api_are_read_from_the_contract():
    assert contract.server_sourced_event_types() >= {
        "inbound_order_created", "outbound_order_created", "stock_threshold_triggered",
        "direct_stock_edit_rejected", "kit_cost_variance_detected",
    }
    assert "section_viewed" not in contract.server_sourced_event_types()


async def test_the_receiver_stores_nothing_and_has_no_get(async_client):
    assert (await async_client.get("/telemetry/events")).status_code == 405


async def test_cors_allows_the_backoffice_to_post_a_batch_directly(async_client):
    preflight = await async_client.options(
        "/telemetry/events",
        headers={"Origin": "http://localhost:5174", "Access-Control-Request-Method": "POST",
                 "Access-Control-Request-Headers": "content-type,authorization"},
    )
    assert preflight.status_code == 200 and preflight.headers["access-control-allow-origin"] == "http://localhost:5174"


# --- the receiver's log: how many events and the type of each ----------------------------------------

async def test_the_receiver_logs_how_many_events_arrived_and_the_type_of_each(async_client, caplog):
    caplog.set_level("INFO", logger="telemetry")
    await post(async_client, [browser_event("section_viewed"), browser_event("section_viewed"), inventory_event()], headers=headers_for(ALICE))
    assert "received 3 event(s): section_viewed, section_viewed, outbound_order_created" in caplog.text


async def test_an_empty_batch_is_logged_too(async_client, caplog):
    caplog.set_level("INFO", logger="telemetry")
    await post(async_client, [])
    assert "received 0 event(s): -" in caplog.text


async def test_the_log_never_carries_text_the_client_controls(async_client, caplog):
    caplog.set_level("INFO", logger="telemetry")
    forged = browser_event()
    forged["event_type"] = "x\nINFO: telemetry: admin logged in"
    await post(async_client, [forged, {"event_type": 42}, "text"])
    assert "received 3 event(s): <invalid>, <invalid>, <invalid>" in caplog.text
    assert "admin logged in" not in caplog.text.replace("rejected", "")


async def test_the_rejections_are_logged_without_values(async_client, caplog):
    caplog.set_level("INFO", logger="telemetry")
    bad = browser_event()
    bad["properties"]["email"] = "maria@example.com"
    await post(async_client, [bad])
    assert "rejected 1: #0 /properties (additionalProperties)" in caplog.text
    assert "maria" not in caplog.text


# --- the Pydantic envelope: defined once, reused by phase 3 -----------------------------------------

from pydantic import ValidationError  # noqa: E402

from telemetry.schemas import TelemetryBatch, TelemetryEvent  # noqa: E402


def test_the_model_accepts_a_well_formed_event_and_dumps_it_as_the_row_to_store():
    event = TelemetryEvent.model_validate(browser_event())
    row = event.model_dump(mode="json")
    assert set(row) == {"eventId", "event_type", "schemaVersion", "timestamp", "userId", "sessionId", "requestId", "environment", "source", "properties"}
    assert row["userId"] is None and isinstance(row["eventId"], str) and row["timestamp"].startswith("2026-10-27T10:00:00")


def test_the_model_covers_the_envelope_fields_of_the_plan():
    assert {"eventId", "timestamp", "sessionId", "userId", "event_type", "schemaVersion", "requestId", "properties"} <= set(TelemetryEvent.model_fields)


@pytest.mark.parametrize("field", ["eventId", "event_type", "schemaVersion", "timestamp", "userId", "sessionId", "requestId", "environment", "source", "properties"])
def test_every_field_is_required_and_null_is_not_absence(field):
    event = browser_event()
    del event[field]
    with pytest.raises(ValidationError):
        TelemetryEvent.model_validate(event)


@pytest.mark.parametrize("change", [
    {"eventId": "not-a-uuid"}, {"eventId": "10000000-0000-1000-8000-000000000001"},  # not a v4
    {"schemaVersion": "1.0.0"}, {"timestamp": "2026-10-27T10:00:00"},  # no time zone
    {"userId": "abc"}, {"environment": "prod"}, {"source": "mobile"}, {"event_type": "Login"}, {"properties": "x"}, {"extra": 1},
])
def test_the_model_refuses_what_breaks_the_envelope(change):
    with pytest.raises(ValidationError):
        TelemetryEvent.model_validate({**browser_event(), **change})


def test_the_batch_model_is_the_phase_3_request_body():
    assert len(TelemetryBatch.model_validate({"events": [browser_event(), browser_event()]}).events) == 2
    with pytest.raises(ValidationError):
        TelemetryBatch.model_validate({"events": [{"event_type": "section_viewed"}]})


async def test_an_envelope_failure_is_reported_by_field_and_rule_never_by_value(async_client):
    event = browser_event()
    event["eventId"] = "maria@example.com"
    response = (await post(async_client, [event])).json()
    assert response["rejected"][0]["path"] == "/eventId" and "maria" not in json.dumps(response)


# --- TELEMETRY_ENDPOINT: read from the start, not used yet ---------------------------------------------

def test_the_backend_reads_telemetry_endpoint_but_does_not_depend_on_it(monkeypatch):
    from core.config import get_telemetry_endpoint

    monkeypatch.delenv("TELEMETRY_ENDPOINT", raising=False)
    assert get_telemetry_endpoint() is None
    monkeypatch.setenv("TELEMETRY_ENDPOINT", "  http://collector.internal/events  ")
    assert get_telemetry_endpoint() == "http://collector.internal/events"
    monkeypatch.setenv("TELEMETRY_ENDPOINT", "   ")
    assert get_telemetry_endpoint() is None


async def test_setting_telemetry_endpoint_does_not_redirect_anything(async_client, monkeypatch):
    monkeypatch.setenv("TELEMETRY_ENDPOINT", "http://127.0.0.1:1/never-called")  # nothing listens there: a forward would fail
    response = await post(async_client, [browser_event()])
    assert response.status_code == 200 and response.json()["accepted"] == 1


# --- events the API decides: the server pins their source and their user rule ---------------------------

def auth_event(event_type, properties, **overrides):
    event = browser_event(event_type, **properties)
    event["source"] = "backoffice"  # what the browser says; the contract pins `api`
    return event | overrides


async def test_a_login_event_relayed_by_the_browser_is_sourced_api(async_client):
    events = [
        auth_event("login_attempted", {"method": "password", "duration_ms": 0}),
        auth_event("login_failed", {"method": "password", "duration_ms": 130, "reason": "invalid_credentials"}),
        auth_event("registration_failed", {"reason": "unavailable"}),
    ]
    response = (await post(async_client, events)).json()
    assert (response["accepted"], response["rejected"]) == (3, [])


async def test_attempts_and_failures_never_carry_a_user_even_when_the_batch_is_flushed_with_a_session(async_client):
    """login_attempted and login_succeeded travel in the same batch, flushed after the login: the token is there, the attempt still has no user."""
    events = [
        auth_event("login_attempted", {"method": "password", "duration_ms": 0}),
        auth_event("login_succeeded", {"method": "password", "duration_ms": 120}),
        auth_event("login_failed", {"method": "password", "duration_ms": 90, "reason": "internal_error"}),
    ]
    response = (await post(async_client, events, headers=headers_for(ALICE))).json()
    assert response["rejected"] == [] and response["accepted"] == 3
    assert contract.stamp(events[0], "u")["userId"] is None and contract.stamp(events[1], "u")["userId"] is not None


async def test_a_login_succeeded_needs_a_verified_session(async_client):
    response = (await post(async_client, [auth_event("login_succeeded", {"method": "password", "duration_ms": 90})])).json()
    assert response["accepted"] == 0 and response["rejected"][0]["path"] == "/userId"


@pytest.mark.parametrize("event_type, properties", [
    ("login_failed", {"method": "password", "duration_ms": 1, "reason": "network_error"}),  # not in the approved enum
    ("login_failed", {"method": "password", "duration_ms": 1, "reason": "invalid_credentials", "email": "a@b.c"}),
    ("registration_failed", {"reason": "email_taken"}),
    ("authorization_denied", {"route_id": "users", "status_code": 500}),
    ("supplier_created", {"supplier_id": "ana lópez"}),
    ("incident_status_changed", {"incident_id": "INC-1", "from_status": "closed", "to_status": "open"}),
    ("profile_updated", {"changed_field_count": 0}),
])
async def test_values_outside_the_approved_enums_and_extra_keys_are_rejected(async_client, event_type, properties):
    response = (await post(async_client, [auth_event(event_type, properties)], headers=headers_for(ALICE))).json()
    assert response["accepted"] == 0 and response["rejected"][0]["path"].startswith("/properties")


def test_the_events_whose_source_the_server_pins_are_read_from_the_schema():
    pinned = contract.server_sourced_event_types()
    assert {"login_failed", "supplier_created", "incident_analysis_failed", "authorization_denied", "inbound_order_created"} <= pinned
    assert not {"section_viewed", "web_vital_reported", "flow_started", "application_error_occurred"} & pinned  # these accept more than one source
    assert "logout_completed" in pinned  # pinned to the backoffice itself


# --- contract 2.1.0: web_vital_reported -----------------------------------------------------------------

def vital(**overrides):
    event = browser_event("web_vital_reported", metric="LCP", value=1840.5, rating="good", section="inventory")
    event["schemaVersion"] = "2.1.0"
    return event | overrides


async def test_a_web_vital_is_accepted(async_client):
    assert (await post(async_client, [vital()])).json()["accepted"] == 1


async def test_both_contract_versions_are_accepted_for_the_forty_older_events_and_only_2_1_for_web_vitals(async_client):
    old, new = browser_event(), browser_event()
    new["schemaVersion"] = "2.1.0"
    assert (await post(async_client, [old, new])).json()["accepted"] == 2
    response = (await post(async_client, [vital(schemaVersion="2.0.0")])).json()
    assert response["accepted"] == 0 and response["rejected"][0]["path"] == "/schemaVersion"


@pytest.mark.parametrize("properties", [
    {"metric": "FID"}, {"metric": "lcp"}, {"value": -1}, {"value": "fast"}, {"rating": "ok"}, {"section": "payroll"}, {"route": "/inventory/products"},
])
async def test_a_web_vital_outside_its_allowlist_is_rejected(async_client, properties):
    event = vital()
    event["properties"] = {**event["properties"], **properties}
    assert (await post(async_client, [event])).json()["accepted"] == 0


async def test_a_web_vital_without_a_field_is_rejected(async_client):
    for field in ("metric", "value", "rating", "section"):
        event = vital()
        del event["properties"][field]
        assert (await post(async_client, [event])).json()["accepted"] == 0


def test_the_contract_has_41_variants_and_the_new_one_is_documented():
    assert len(SCHEMA["oneOf"]) == 41 and "v2.1.0" in SCHEMA["title"]
    assert EXAMPLES["web_vital_reported"]["schemaVersion"] == "2.1.0"
