"""Telemetry storage: what the receiver keeps, how retries and failures behave, immutability, the eight columns and three indexes, and that the tags keep the plan's allowlists and the briefing's dimensions."""

from __future__ import annotations

import copy
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, select

from conftest import ALICE, headers_for, uuid_of
from telemetry import contract, store
from telemetry.models import TelemetryEventRow
from test_telemetry_receiver import EXAMPLES, SCHEMA, browser_event, inventory_event, post

pytestmark = [pytest.mark.anyio, pytest.mark.usefixtures("telemetry_db")]

ROOT = Path(__file__).resolve().parents[3]
PLAN = (ROOT / "docs" / "telemetry" / "telemetry-plan.md").read_text(encoding="utf-8")
BRIEFING = (ROOT / "nexova-BRIEFING.es.md").read_text(encoding="utf-8")
INVENTORY_TYPES = sorted(SCHEMA["allOf"][0]["if"]["properties"]["event_type"]["enum"])
BRIEFING_INVENTORY_FIELDS = ("office", "product_id", "product_category", "programme_id", "quantity", "currency")
MANDATORY = ("inbound_order_created", "outbound_order_created", "stock_threshold_triggered", "direct_stock_edit_rejected", "kit_cost_variance_detected")


def rows(engine) -> list[TelemetryEventRow]:
    with Session(engine) as session:
        return list(session.exec(select(TelemetryEventRow).order_by(TelemetryEventRow.timestamp)).all())


def plan_dictionary_keys() -> set[str]:
    """The property keys the plan documents: the dictionary of section 15 plus the keys that section 17 (contract 2.1.0) adds."""
    section = PLAN.split("### Diccionario de propiedades del payload", 1)[1].split("\n### ", 1)[0]
    keys = set(re.findall(r"^\| `([a-z_]+)` \|", section, flags=re.MULTILINE))
    added = re.search(r"Claves nuevas del diccionario de la seccion 15: ([^.]*)\.", PLAN)
    return keys | set(re.findall(r"`([a-z_]+)`", added.group(1) if added else ""))


def references(node, target: str, seen: frozenset[str] = frozenset()) -> bool:
    """True when ``node`` reaches the definition ``target`` through its ``$ref`` chain (productPayload and inventoryFailure
    pull it in indirectly)."""
    if isinstance(node, list):
        return any(references(item, target, seen) for item in node)
    if not isinstance(node, dict):
        return False
    ref = node.get("$ref")
    if ref == target:
        return True
    if ref and ref not in seen:
        if references(SCHEMA["$defs"][ref.rsplit("/", 1)[1]], target, seen | {ref}):
            return True
    return any(references(value, target, seen) for key, value in node.items() if key != "$ref")


# --- what is stored ---------------------------------------------------------------------------------

async def test_a_valid_batch_is_stored_one_row_per_event_and_a_rejected_event_is_not(async_client, telemetry_db):
    bad = browser_event()
    bad["properties"]["email"] = "someone@example.com"
    good = [browser_event(), browser_event()]
    response = await post(async_client, [good[0], bad, good[1]])
    assert response.status_code == 200 and response.json()["accepted"] == 2
    assert {row.event_id for row in rows(telemetry_db)} == {good[0]["eventId"], good[1]["eventId"]}


async def test_the_envelope_and_the_properties_are_stored_unchanged(async_client, telemetry_db):
    event = browser_event(section="inventory", locale="es")
    await post(async_client, [event])
    (row,) = rows(telemetry_db)
    assert (row.event_id, row.event_type) == (event["eventId"], "section_viewed")
    assert (row.session_id, row.environment, row.service) == (event["sessionId"], "test", "backoffice")
    assert row.timestamp.replace(tzinfo=timezone.utc) == datetime(2026, 10, 27, 10, 0, tzinfo=timezone.utc)
    assert row.tags == {"section": "inventory", "locale": "es"}
    assert row.user_id is None


async def test_what_is_stored_is_what_the_server_stamped_not_what_the_browser_declared(async_client, telemetry_db):
    await post(async_client, [inventory_event(userId="a" * 64)], headers=headers_for(ALICE))
    (row,) = rows(telemetry_db)
    assert row.service == "inventory_api"  # the browser declared "backoffice"
    assert row.user_id == contract.pseudonym(str(uuid_of(ALICE)))
    assert re.fullmatch(r"[a-f0-9]{64}", row.user_id) and str(uuid_of(ALICE)) not in json.dumps(row.model_dump(mode="json"))


async def test_no_token_and_no_operational_id_are_ever_stored(async_client, telemetry_db):
    headers = headers_for(ALICE)
    await post(async_client, [inventory_event(), browser_event()], headers=headers)
    stored = json.dumps([row.model_dump(mode="json") for row in rows(telemetry_db)])
    assert headers["Authorization"].split()[1] not in stored and str(uuid_of(ALICE)) not in stored


async def test_every_example_of_the_contract_is_stored(async_client, telemetry_db):
    events = [copy.deepcopy(e) | {"userId": None, "source": "backoffice"} for e in SCHEMA["examples"] if e["source"] != "worker"]
    response = await post(async_client, events, headers=headers_for(ALICE))
    assert response.json()["rejected"] == []
    assert len(rows(telemetry_db)) == len(events)


# --- retries and failures ---------------------------------------------------------------------------

async def test_a_retried_batch_is_acknowledged_again_and_stored_once(async_client, telemetry_db):
    batch = [browser_event(), browser_event()]
    first, second = await post(async_client, batch), await post(async_client, batch)
    assert first.json() == {"received": 2, "accepted": 2, "stored": 2, "rejected": []}
    assert second.json() == {"received": 2, "accepted": 2, "stored": 0, "rejected": []}  # nothing new was written
    assert len(rows(telemetry_db)) == 2


async def test_an_event_repeated_inside_one_batch_is_stored_once(async_client, telemetry_db):
    event = browser_event()
    assert (await post(async_client, [event, event, browser_event()])).json()["accepted"] == 3
    assert len(rows(telemetry_db)) == 2


async def test_a_batch_that_partly_repeats_stores_only_the_new_events(async_client, telemetry_db):
    old, new = browser_event(), browser_event()
    await post(async_client, [old])
    await post(async_client, [old, new])
    assert {row.event_id for row in rows(telemetry_db)} == {old["eventId"], new["eventId"]}


async def test_when_the_database_fails_the_answer_is_503_and_a_retry_stores_the_batch(async_client, telemetry_db, monkeypatch):
    batch = [browser_event(), browser_event()]
    real_save = store.save

    def broken(session, events):
        raise OperationalError("INSERT", {}, Exception("connection lost"))

    monkeypatch.setattr(store, "save", broken)
    assert (await post(async_client, batch)).status_code == 503  # the frontend retries on 5xx
    assert rows(telemetry_db) == []
    monkeypatch.setattr(store, "save", real_save)
    assert (await post(async_client, batch)).json()["accepted"] == 2
    assert len(rows(telemetry_db)) == 2


async def test_a_batch_with_only_rejected_events_stores_nothing_and_still_answers_200(async_client, telemetry_db):
    response = await post(async_client, [{**browser_event(), "schemaVersion": "1.0.0"}])
    assert response.status_code == 200 and response.json()["accepted"] == 0
    assert rows(telemetry_db) == []


# --- time -------------------------------------------------------------------------------------------

def test_the_timestamp_is_stored_in_utc():
    row = store.to_row(browser_event() | {"timestamp": "2026-10-27T10:00:00.250Z"})
    assert row["timestamp"] == datetime(2026, 10, 27, 10, 0, 0, 250000, tzinfo=timezone.utc)


def test_the_telemetry_code_has_no_update_or_delete_logic():
    """The events are immutable facts: the package only ever INSERTs."""
    source = "\n".join(path.read_text(encoding="utf-8") for path in (Path(store.__file__).parent).glob("*.py"))
    code = re.sub(r'"""(?:.|\n)*?"""|#.*', "", source)  # docstrings and comments may talk about it
    assert not re.search(r"\b(delete|update)\s*\(|\.(delete|merge)\(|\bDELETE\b|\bUPDATE\b", code)


# --- tags -------------------------------------------------------------------------------------------

async def test_the_tags_of_an_inventory_event_keep_the_dimensions_of_the_briefing(async_client, telemetry_db):
    await post(async_client, [inventory_event()], headers=headers_for(ALICE))
    (row,) = rows(telemetry_db)
    expected = EXAMPLES["outbound_order_created"]["properties"]
    assert row.tags == expected  # intact: nothing dropped, nothing added
    assert set(BRIEFING_INVENTORY_FIELDS) <= set(row.tags)  # office, product_id, product_category, programme_id, quantity, currency


async def test_an_event_without_inventory_dimensions_has_only_its_own_tags(async_client, telemetry_db):
    await post(async_client, [browser_event(section="suppliers", locale="en")])
    (row,) = rows(telemetry_db)
    assert row.tags == {"section": "suppliers", "locale": "en"}


async def test_the_tags_of_every_stored_example_only_use_keys_of_the_plans_allowlist(async_client, telemetry_db):
    events = [copy.deepcopy(e) | {"userId": None, "source": "backoffice"} for e in SCHEMA["examples"] if e["source"] != "worker"]
    await post(async_client, events, headers=headers_for(ALICE))
    stored_keys = {key for row in rows(telemetry_db) for key in row.tags}
    assert stored_keys and stored_keys <= plan_dictionary_keys(), f"not in the plan: {stored_keys - plan_dictionary_keys()}"
    assert not {"email", "name", "supplier", "assigned_to", "user_id"} & stored_keys  # no personal data in the tags


@pytest.mark.parametrize("event_type", INVENTORY_TYPES)
def test_every_inventory_event_carries_the_six_fields_of_the_briefing(event_type):
    """Briefing, section 3: the inventory events require office, product_id, product_category, programme_id, quantity, currency.
    The schema states it once (``$defs/inventoryProperties``) and each inventory variant must reference it."""
    assert set(SCHEMA["$defs"]["inventoryProperties"]["required"]) == set(BRIEFING_INVENTORY_FIELDS)
    variant = next(v for v in SCHEMA["oneOf"] if v["properties"]["event_type"]["const"] == event_type)
    assert references(variant, "#/$defs/inventoryProperties")


def test_the_five_mandatory_events_of_the_briefing_are_in_the_contract_and_in_the_plan():
    for event_type in MANDATORY:
        assert f"`{event_type}`" in BRIEFING and f"`{event_type}`" in PLAN
        assert event_type in INVENTORY_TYPES


def test_the_dimensions_of_the_briefing_are_documented_in_the_plan():
    assert set(BRIEFING_INVENTORY_FIELDS) <= plan_dictionary_keys()
    assert "por oficina y por programa" in BRIEFING  # what office and programme_id exist for


@pytest.mark.parametrize("office, currency", [("valencia", "USD"), ("miami", "EUR")])
async def test_a_currency_that_is_not_the_one_of_the_office_is_rejected_by_the_contract(async_client, telemetry_db, office, currency):
    event = inventory_event()
    event["properties"] = event["properties"] | {"office": office, "currency": currency}
    response = (await post(async_client, [event], headers=headers_for(ALICE))).json()
    assert (response["accepted"], response["stored"]) == (0, 0)
    assert rows(telemetry_db) == []


def test_the_table_has_eight_columns_and_three_indexes(tmp_path, monkeypatch):
    from sqlalchemy import inspect

    from inventory import database

    engine = database.build_engine(f"sqlite:///{tmp_path / 'fresh.sqlite'}")
    monkeypatch.setattr(database, "get_tinydb", lambda: None)
    monkeypatch.setattr(database, "get_engine", lambda: engine)
    database.init_db()  # creates the table the way the API does at startup
    inspector = inspect(engine)
    assert {c["name"] for c in inspector.get_columns("telemetry_events")} == {
        "event_id", "event_type", "timestamp", "service", "user_id", "session_id", "environment", "tags",
    }
    assert {tuple(i["column_names"]) for i in inspector.get_indexes("telemetry_events")} == {("timestamp",), ("event_type",)}  # + GIN on tags (PostgreSQL)
    ddl = (ROOT / "docs" / "telemetry" / "telemetry_events.sql").read_text(encoding="utf-8")
    assert ddl.count("CREATE INDEX") == 3 and "USING GIN (tags)" in ddl and "tags JSONB NOT NULL" in ddl
