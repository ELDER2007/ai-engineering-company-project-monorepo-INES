"""GET /telemetry/report: access control, the window and environment filters, and the cache (hit, TTL, invalidation on ingest)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlmodel import Session

from conftest import ALICE, BOB, headers_for
from telemetry import analysis, report as report_module, store
from telemetry.models import TelemetryEventRow
from telemetry.report_cache import TTLCache, report_cache
from test_telemetry_receiver import browser_event, post

pytestmark = [pytest.mark.anyio, pytest.mark.usefixtures("telemetry_db")]


@pytest.fixture(autouse=True)
def clean_cache():
    report_cache.invalidate()
    yield
    report_cache.invalidate()


def add(engine, event_type: str, when: str | None = None, environment: str = "test", **tags) -> None:
    """One stored event; by default one hour ago, so it is inside the default window (last 7 days) whenever the test runs."""
    moment = datetime.fromisoformat(when) if when else datetime.now(timezone.utc) - timedelta(hours=1)
    with Session(engine) as session:
        session.add(TelemetryEventRow(event_id=str(uuid4()), event_type=event_type, timestamp=moment, service="backoffice", environment=environment, tags=tags))
        session.commit()


def total(body: dict) -> int:
    """All the events the report counted: the sum of its ``events_per_day`` series."""
    return sum(row["events"] for row in body["metrics"]["events_per_day"])


async def get(client, email=ALICE, **params):
    return await client.get("/telemetry/report", params=params, headers=headers_for(email))


# --- access -----------------------------------------------------------------------------------------


async def test_the_report_needs_a_session(async_client):
    assert (await async_client.get("/telemetry/report")).status_code == 401


async def test_the_report_is_for_admins_only(async_client):
    assert (await get(async_client, BOB)).status_code == 403


async def test_an_admin_gets_the_report_even_with_no_events(async_client):
    response = await get(async_client)
    assert response.status_code == 200
    body = response.json()
    assert total(body) == 0 and body["cached"] is False and body["truncated"] is False


# --- window and environment -------------------------------------------------------------------------


async def test_the_report_reflects_the_stored_events(async_client, telemetry_db):
    add(telemetry_db, "application_error_occurred", component="inventory", error_code="network_failed")
    add(telemetry_db, "login_failed", reason="invalid_credentials", duration_ms=120)
    report = (await get(async_client)).json()["metrics"]
    assert report["application_errors"] == [{"component": "inventory", "error_code": "network_failed", "errors": 1}]
    assert report["login_failures_by_reason"] == [{"reason": "invalid_credentials", "failures": 1}]


async def test_start_date_is_inclusive_and_end_date_exclusive(async_client, telemetry_db):
    add(telemetry_db, "section_viewed", "2026-10-27T10:00:00+00:00")
    add(telemetry_db, "section_viewed", "2026-10-27T11:00:00+00:00")
    add(telemetry_db, "section_viewed", "2026-10-27T12:00:00+00:00")
    body = (await get(async_client, start_date="2026-10-27T10:00:00Z", end_date="2026-10-27T12:00:00Z")).json()
    assert total(body) == 2


async def test_environment_filters_the_events(async_client, telemetry_db):
    add(telemetry_db, "section_viewed", environment="production")
    add(telemetry_db, "section_viewed", environment="test")
    assert total((await get(async_client, environment="production")).json()) == 1


async def test_bad_parameters_are_422(async_client):
    assert (await get(async_client, start_date="2026-10-28T00:00:00Z", end_date="2026-10-27T00:00:00Z")).status_code == 422
    assert (await get(async_client, start_date="yesterday")).status_code == 422
    assert (await get(async_client, environment="prod")).status_code == 422


async def test_a_window_with_more_rows_than_the_cap_is_marked_truncated(async_client, telemetry_db, monkeypatch):
    monkeypatch.setattr(analysis, "MAX_ROWS", 2)
    for _ in range(3):
        add(telemetry_db, "section_viewed")
    body = (await get(async_client)).json()
    assert body["truncated"] is True and total(body) == 2


# --- cache ------------------------------------------------------------------------------------------


async def test_the_second_request_is_served_from_the_cache_and_says_so(async_client, telemetry_db):
    add(telemetry_db, "section_viewed")
    first = (await get(async_client)).json()
    add(telemetry_db, "section_viewed")  # written behind the API's back (no invalidation): the cache must still answer
    second = (await get(async_client)).json()
    assert first["cached"] is False and second["cached"] is True
    assert total(second) == 1 and second["generated_at"] == first["generated_at"]


async def test_refresh_skips_the_cache(async_client, telemetry_db):
    add(telemetry_db, "section_viewed")
    await get(async_client)
    add(telemetry_db, "section_viewed")
    body = (await get(async_client, refresh=True)).json()
    assert body["cached"] is False and total(body) == 2


async def test_different_windows_do_not_share_an_entry(async_client, telemetry_db):
    add(telemetry_db, "section_viewed")
    await get(async_client)
    assert (await get(async_client, start_date="2026-10-28T00:00:00Z")).json()["cached"] is False


# --- default window ---------------------------------------------------------------------------------


async def test_without_parameters_the_period_is_the_last_seven_days_ending_now(async_client, telemetry_db):
    add(telemetry_db, "section_viewed", (datetime.now(timezone.utc) - timedelta(days=3)).isoformat())
    add(telemetry_db, "section_viewed", (datetime.now(timezone.utc) - timedelta(days=30)).isoformat())
    before = datetime.now(timezone.utc)
    body = (await get(async_client)).json()
    start, end = (datetime.fromisoformat(body["period"][key]) for key in ("from", "to"))
    assert total(body) == 1  # the 30-day-old event is outside the period, applied once in SQL
    assert end - start == timedelta(days=7) and before <= end <= datetime.now(timezone.utc) and end.utcoffset() == timedelta(0)


def test_resolve_window_defaults_each_missing_bound_in_utc():
    now = datetime(2026, 10, 31, 15, 30, tzinfo=timezone.utc)
    assert report_module.resolve_window(None, None, now) == (datetime(2026, 10, 24, 15, 30, tzinfo=timezone.utc), now)
    end = datetime(2026, 10, 20, tzinfo=timezone.utc)
    assert report_module.resolve_window(None, end, now) == (datetime(2026, 10, 13, tzinfo=timezone.utc), end)
    start = datetime(2026, 10, 1)  # naive: taken as UTC
    assert report_module.resolve_window(start, None, now) == (datetime(2026, 10, 1, tzinfo=timezone.utc), now)


async def test_the_response_has_the_period_and_the_two_required_metrics(async_client, telemetry_db):
    add(telemetry_db, "section_load_completed", section="home", duration_ms=10, outcome="error")
    body = (await get(async_client)).json()
    assert set(body["period"]) == {"from", "to"}
    stored_day = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%d")  # what ``add`` stores by default
    assert body["metrics"]["events_per_day"] == [{"day": stored_day, "events": 1}]
    assert body["metrics"]["error_rate_by_type"] == [{"event_type": "section_load_completed", "events": 1, "errors": 1, "error_rate": 1.0}]


async def test_the_response_has_auth_failure_rate_per_day(async_client, telemetry_db):
    add(telemetry_db, "login_failed", reason="invalid_credentials", duration_ms=5)
    add(telemetry_db, "login_succeeded", duration_ms=5)
    (day,) = (await get(async_client)).json()["metrics"]["auth_failure_rate"]
    assert (day["succeeded"], day["failed"], day["attempts"], day["failure_rate"]) == (1, 1, 2, 0.5)


async def test_a_default_request_is_cached_even_though_its_resolved_now_moves(async_client, telemetry_db):
    add(telemetry_db, "section_viewed")
    first = (await get(async_client)).json()
    second = (await get(async_client)).json()
    assert (first["cached"], second["cached"]) == (False, True)
    assert second["period"] == first["period"]  # the cached answer, not a recomputation


async def test_the_same_explicit_period_is_served_from_the_cache_within_the_ttl(async_client, telemetry_db):
    params = {"start_date": "2026-10-01T00:00:00Z", "end_date": "2026-10-31T00:00:00Z"}
    first = (await get(async_client, **params)).json()
    second = (await get(async_client, **params)).json()
    assert (first["cached"], second["cached"]) == (False, True) and second["cache_age_seconds"] >= 0


async def test_a_start_after_the_default_end_is_422(async_client):
    assert (await get(async_client, start_date="2999-01-01T00:00:00Z")).status_code == 422


async def test_storing_an_event_through_the_api_invalidates_the_cache(async_client, telemetry_db):
    await get(async_client)
    assert (await post(async_client, [browser_event()])).json()["stored"] == 1
    body = (await get(async_client)).json()
    assert body["cached"] is False and total(body) == 1


async def test_a_retried_batch_stores_nothing_and_keeps_the_cache(async_client):
    event = browser_event()
    await post(async_client, [event])
    await get(async_client)
    assert (await post(async_client, [event])).json()["stored"] == 0
    assert (await get(async_client)).json()["cached"] is True


def test_save_invalidates_only_when_something_was_inserted(telemetry_db):
    report_cache.set("k", 1)
    with Session(telemetry_db) as session:
        assert store.save(session, []) == 0
    assert report_cache.get("k") is not None


# --- TTLCache on its own ----------------------------------------------------------------------------


def test_an_entry_expires_after_the_ttl():
    now = [0.0]
    cache = TTLCache(ttl_seconds=60, clock=lambda: now[0])
    cache.set("k", "v")
    now[0] = 59.9
    assert cache.get("k") == ("v", pytest.approx(59.9))
    now[0] = 60
    assert cache.get("k") is None and len(cache) == 0


def test_the_cache_is_bounded_and_drops_the_least_recently_used():
    cache = TTLCache(max_entries=2)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.get("a")  # a is now the most recent
    cache.set("c", 3)
    assert cache.get("b") is None and cache.get("a") is not None and cache.get("c") is not None


def test_invalidate_empties_the_cache():
    cache = TTLCache()
    cache.set("a", 1)
    cache.invalidate()
    assert len(cache) == 0
