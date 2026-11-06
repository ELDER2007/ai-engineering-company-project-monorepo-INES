"""The weekly performance pipeline (Prefect flow) end to end, and the /reporting endpoints.

The flow runs for real against throw-away SQLite databases, inside Prefect's test harness, on telemetry in the real shape.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone

import pytest
from conftest import BOB, headers_for
from fastapi.testclient import TestClient
from prefect.testing.utilities import prefect_test_harness
from sqlalchemy import func, select

from data.pipelines.pipeline import weekly_office_performance_flow
from data.pipelines.weekly_office_performance import interface, repository, storage
from data.pipelines.weekly_office_performance.seed_telemetry import seed_telemetry
from main import app
from reporting.database import get_reporting_engine, get_telemetry_engine

WEEK = date(2026, 10, 26)
PERF = storage.weekly_performance


@pytest.fixture(scope="session", autouse=True)
def prefect_harness():
    with prefect_test_harness():
        yield


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    """The raw and eval files of the tests go to a temp folder, never to the repo's data/."""
    monkeypatch.setenv("PIPELINE_DATA_DIR", str(tmp_path / "data"))
    return tmp_path / "data"


@pytest.fixture()
def engines(tmp_path):
    source = storage.build_engine(f"sqlite:///{tmp_path / 'telemetry.sqlite'}")
    target = storage.build_engine(f"sqlite:///{tmp_path / 'reporting.sqlite'}")
    seed_telemetry(source)
    storage.create_reporting_schema(target)
    yield source, target
    source.dispose()
    target.dispose()


def run(engines, week=WEEK, **kwargs):
    """Fresh data by default (``refresh``): the data tests change the source between runs. The cache has its own tests."""
    source, target = engines
    kwargs.setdefault("refresh", True)
    return weekly_office_performance_flow(week_start=week, source_engine=source, target_engine=target, **kwargs)


def rows(target):
    with target.connect() as connection:
        return connection.execute(select(PERF).order_by(PERF.c.office, PERF.c.programme_id)).mappings().all()


def add_event(source, event_type, tags, when=datetime(2026, 10, 28, 12, tzinfo=timezone.utc), environment="production"):
    with source.begin() as connection:
        connection.execute(
            storage.telemetry_events.insert().values(
                event_id=str(uuid.uuid4()), event_type=event_type, timestamp=when, service="inventory_api",
                environment=environment, tags=tags,
            )
        )


# ---------------------------------------------------------------- the flow: happy path


def test_the_flow_loads_one_row_per_office_and_programme_with_the_right_kpis(engines):
    summary = run(engines)
    assert summary.state == "Completed"
    loaded = rows(engines[1])
    assert len(loaded) == 5 and all(r["week_start"] == WEEK for r in loaded)
    assert {r["currency"] for r in loaded if r["office"] == "valencia"} == {"EUR"}
    assert {r["currency"] for r in loaded if r["office"] == "miami"} == {"USD"}
    assert sum(r["shortage_events_count"] for r in loaded) == 2
    assert sum(r["cost_variance_events_count"] for r in loaded) == 1
    assert sum(r["kits_delivered_count"] for r in loaded) == 7  # the seeded outbound orders of that week


def test_only_the_requested_environment_is_reported(engines):
    source, _ = engines
    add_event(source, "outbound_order_created", {"office": "valencia", "programme_id": "ventas-b2b", "currency": "EUR", "order_id": "dev-1"}, environment="development")
    kits_before = sum(r["kits_delivered_count"] for r in rows(engines[1]))
    run(engines)
    assert sum(r["kits_delivered_count"] for r in rows(engines[1])) == kits_before + 7  # the development event is left out


def test_the_run_leaves_its_raw_events_and_a_validation_report(engines, data_dir):
    summary = run(engines)
    snapshot = data_dir / "raw" / f"weekly_events_{WEEK}_production.jsonl"
    assert len(snapshot.read_text().splitlines()) == 17
    report = json.loads(next((data_dir / "eval").glob(f"run_{WEEK}_*.json")).read_text())
    assert report["run_id"] == summary.run_id and report["state"] == "Completed" and report["reconciliation"]["ok"]
    assert report["counts"]["events_read"] == 17 and len(report["kpis"]) == 5


def test_the_execution_log_has_what_an_audit_needs(engines):
    summary = run(engines, trigger="scheduled")
    log = repository.get_run(engines[1], summary.run_id)
    assert (log.state, log.trigger, log.week_start, log.environment) == ("Completed", "scheduled", WEEK, "production")
    assert log.events_read == 17 and log.window_events_total == 18  # the extra one is a navigation event: proof of life
    assert (log.rejected_count, log.rows_written, log.rows_changed, log.rows_deleted) == (0, 5, 0, 0)
    assert log.started_at <= log.finished_at and log.error is None and log.prefect_flow_run_id


# ---------------------------------------------------------------- the flow: idempotency


def test_running_twice_updates_in_place_without_duplicates_or_changes(engines):
    run(engines)
    first = {(r["office"], r["programme_id"]): (r["id"], r["total_material_cost"]) for r in rows(engines[1])}
    second_run = run(engines)
    assert {(r["office"], r["programme_id"]): (r["id"], r["total_material_cost"]) for r in rows(engines[1])} == first
    assert repository.get_run(engines[1], second_run.run_id).rows_changed == 0


def test_a_late_event_corrects_the_week_in_place_and_the_log_says_so(engines):
    source, target = engines
    run(engines)
    before = sum(r["kits_delivered_count"] for r in rows(target))
    add_event(source, "outbound_order_created", {"office": "valencia", "programme_id": "ventas-b2b", "currency": "EUR", "order_id": "late-1"})
    again = run(engines)
    assert sum(r["kits_delivered_count"] for r in rows(target)) == before + 1
    assert repository.get_run(target, again.run_id).rows_changed == 1  # the audit trail of the correction


def test_a_duplicated_order_under_another_event_id_is_counted_once(engines):
    source, _ = engines
    tags = {"office": "valencia", "programme_id": "ventas-b2b", "currency": "EUR", "order_id": "dup-1"}
    add_event(source, "outbound_order_created", tags)
    add_event(source, "outbound_order_created", tags)  # same order, different event_id
    run(engines)
    assert sum(r["kits_delivered_count"] for r in rows(engines[1])) == 8  # 7 seeded + 1, not + 2


def test_a_week_without_events_writes_nothing_and_still_completes(engines):
    summary = run(engines, week=date(2026, 1, 5))
    assert summary.state == "Completed" and rows(engines[1]) == []


def test_a_combination_that_no_longer_has_events_disappears_from_the_week(engines):
    source, target = engines
    add_event(source, "outbound_order_created", {"office": "miami", "programme_id": "solo-esta-semana", "currency": "USD", "order_id": "x-1"})
    run(engines)
    assert "solo-esta-semana" in {r["programme_id"] for r in rows(target)}
    with source.begin() as connection:  # the source changed: that event is gone
        connection.execute(storage.telemetry_events.delete().where(storage.telemetry_events.c.tags["order_id"].as_string() == "x-1"))
    again = run(engines)
    assert "solo-esta-semana" not in {r["programme_id"] for r in rows(target)}
    assert repository.get_run(target, again.run_id).rows_deleted == 1


def test_the_pipeline_never_writes_to_telemetry_events(engines):
    source, _ = engines
    with source.connect() as connection:
        before = connection.execute(select(func.count()).select_from(storage.telemetry_events)).scalar()
    run(engines)
    with source.connect() as connection:
        assert connection.execute(select(func.count()).select_from(storage.telemetry_events)).scalar() == before


# ---------------------------------------------------------------- the endpoints


@pytest.fixture()
def client(engines, auth_headers):
    source, target = engines
    app.dependency_overrides[get_telemetry_engine] = lambda: source
    app.dependency_overrides[get_reporting_engine] = lambda: target
    yield TestClient(app, headers=auth_headers)  # ALICE is an admin
    app.dependency_overrides.pop(get_telemetry_engine, None)
    app.dependency_overrides.pop(get_reporting_engine, None)


def test_before_any_run_the_report_and_the_latest_run_are_not_found(client):
    assert client.get("/reporting/weekly-office-program-performance").status_code == 404
    assert client.get("/reporting/pipeline-runs/latest").status_code == 404


def test_a_manual_run_fills_the_report_and_becomes_the_latest_run(client):
    created = client.post("/reporting/pipeline-runs", json={"week_start": "2026-10-28"})  # snapped to its Monday
    assert created.status_code == 201
    body = created.json()
    assert body["state"] == "Completed" and body["trigger"] == "manual" and body["week_start"] == "2026-10-26"
    assert body["events_read"] == 17 and body["rows_written"] == 5

    assert client.get("/reporting/pipeline-runs/latest").json()["id"] == body["id"]
    report = client.get("/reporting/weekly-office-program-performance").json()  # default: the latest week
    assert report["week_start"] == "2026-10-26" and len(report["entries"]) == 5
    assert set(report["entries"][0]) == {
        "office", "programme_id", "total_material_cost", "kits_delivered_count",
        "shortage_events_count", "cost_variance_events_count", "currency",
    }


def test_a_week_without_data_returns_an_empty_list_not_an_error(client):
    client.post("/reporting/pipeline-runs", json={"week_start": "2026-10-26"})
    answer = client.get("/reporting/weekly-office-program-performance", params={"week_start": "2025-01-06"})
    assert answer.status_code == 200 and answer.json() == {"week_start": "2025-01-06", "entries": []}


def test_a_failing_run_answers_500_and_is_the_latest_run(client, engines):
    add_event(engines[0], "outbound_order_created", {"office": "miami", "programme_id": "x", "currency": "EUR", "order_id": "bad-1"})
    assert client.post("/reporting/pipeline-runs", json={"week_start": "2026-10-26"}).status_code == 500
    latest = client.get("/reporting/pipeline-runs/latest").json()
    assert latest["state"] == "Failed" and "miami/EUR" in latest["error"]


def test_a_malformed_week_start_is_refused(client):
    assert client.get("/reporting/weekly-office-program-performance", params={"week_start": "soon"}).status_code == 422
    assert client.post("/reporting/pipeline-runs", json={"week_start": "soon"}).status_code == 422


def test_without_a_session_nothing_is_served():
    anonymous = TestClient(app)
    assert anonymous.get("/reporting/weekly-office-program-performance").status_code == 401
    assert anonymous.get("/reporting/pipeline-runs/latest").status_code == 401
    assert anonymous.post("/reporting/pipeline-runs").status_code == 401


def test_a_normal_user_can_read_the_report_but_not_trigger_a_run(client):
    client.post("/reporting/pipeline-runs", json={"week_start": "2026-10-26"})
    user = headers_for(BOB)
    assert client.get("/reporting/weekly-office-program-performance", headers=user).status_code == 200
    assert client.get("/reporting/pipeline-runs/latest", headers=user).status_code == 200
    assert client.post("/reporting/pipeline-runs", headers=user).status_code == 403


def test_the_interface_is_what_the_endpoints_call(engines):
    assert interface.get_latest_run(engines[1]) is None
    run = interface.run_weekly_office_performance(source_engine=engines[0], target_engine=engines[1], week_start=WEEK)
    assert run.state == "Completed" and interface.get_weekly_performance(engines[1]).week_start == WEEK
