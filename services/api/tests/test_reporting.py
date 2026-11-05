"""Weekly performance pipeline (Prefect flow) and the /reporting endpoints.

The flow runs for real against throw-away SQLite databases, inside Prefect's test harness.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from prefect.testing.utilities import prefect_test_harness
from sqlalchemy import func, select

from data.pipelines.weekly_office_performance import storage
from data.pipelines.weekly_office_performance.flow import weekly_office_performance_flow
from data.pipelines.weekly_office_performance.seed_telemetry import seed_telemetry
from main import app
from reporting import service
from reporting.database import get_reporting_engine, get_telemetry_engine

WEEK = date(2026, 10, 26)


@pytest.fixture(scope="session", autouse=True)
def prefect_harness():
    with prefect_test_harness():
        yield


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
    source, target = engines
    return weekly_office_performance_flow(week_start=week, source_engine=source, target_engine=target, **kwargs)


def rows(target):
    with target.connect() as connection:
        return connection.execute(select(storage.weekly_performance)).mappings().all()


# ---------------------------------------------------------------- the flow


def test_the_flow_loads_one_row_per_office_and_programme_with_the_right_kpis(engines):
    summary = run(engines)
    assert summary.state == "Completed" and summary.rejected_count == 0
    loaded = rows(engines[1])
    assert len(loaded) == summary.rows_written > 0
    assert {r["currency"] for r in loaded if r["office"] == "valencia"} == {"EUR"}
    assert {r["currency"] for r in loaded if r["office"] == "miami"} == {"USD"}
    # the seeded events of that week: 2 shortages, 1 cost variance, in total
    assert sum(r["shortage_events_count"] for r in loaded) == 2
    assert sum(r["cost_variance_events_count"] for r in loaded) == 1
    assert all(r["week_start"] == WEEK for r in loaded)


def test_running_twice_updates_in_place_without_duplicates(engines):
    run(engines)
    first = {(r["office"], r["programme_id"]): r["id"] for r in rows(engines[1])}
    run(engines)
    second = {(r["office"], r["programme_id"]): r["id"] for r in rows(engines[1])}
    assert first == second  # same rows, same ids: upserted, not re-inserted


def test_a_late_event_is_picked_up_by_the_next_run(engines):
    source, target = engines
    run(engines)
    before = sum(r["kits_delivered_count"] for r in rows(target))
    with source.begin() as connection:
        connection.execute(
            storage.telemetry_events.insert().values(
                event_type="outbound_order_created",
                occurred_at=datetime(2026, 10, 30, 9, tzinfo=timezone.utc),
                properties={"office": "valencia", "programme_id": "b2b-sales", "currency": "EUR"},
            )
        )
    run(engines)
    assert sum(r["kits_delivered_count"] for r in rows(target)) == before + 1


def test_a_week_without_events_writes_nothing_and_still_completes(engines):
    summary = run(engines, week=date(2026, 1, 5))
    assert summary.state == "Completed" and summary.rows_written == 0 and rows(engines[1]) == []


def test_invalid_events_are_counted_not_loaded_and_do_not_fail_the_run(engines):
    source, _ = engines
    with source.begin() as connection:
        connection.execute(
            storage.telemetry_events.insert().values(
                event_type="inbound_order_created",
                occurred_at=datetime(2026, 10, 28, tzinfo=timezone.utc),
                properties={"office": "valencia", "programme_id": "b2b-sales", "currency": "EUR"},  # no cost
            )
        )
    assert run(engines).rejected_count == 1


def test_mixed_currencies_fail_the_run_and_the_failure_is_recorded(engines):
    source, target = engines
    with source.begin() as connection:
        connection.execute(
            storage.telemetry_events.insert().values(
                event_type="outbound_order_created",
                occurred_at=datetime(2026, 10, 28, tzinfo=timezone.utc),
                properties={"office": "miami", "programme_id": "b2b-sales", "currency": "EUR"},
            )
        )
    with pytest.raises(Exception, match="miami/EUR"):
        run(engines)
    latest = service.get_latest_run(target)
    assert latest.state == "Failed" and "miami/EUR" in latest.error
    assert rows(target) == []  # nothing half-loaded


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
    yield TestClient(app, headers=auth_headers)
    app.dependency_overrides.pop(get_telemetry_engine, None)
    app.dependency_overrides.pop(get_reporting_engine, None)


def test_before_any_run_the_report_and_the_latest_run_are_not_found(client):
    assert client.get("/reporting/weekly-office-program-performance").status_code == 404
    assert client.get("/reporting/pipeline-runs/latest").status_code == 404


def test_a_manual_run_fills_the_report_and_becomes_the_latest_run(client):
    created = client.post("/reporting/pipeline-runs", json={"week_start": "2026-10-28"})  # snapped to Monday
    assert created.status_code == 201
    body = created.json()
    assert body["state"] == "Completed" and body["trigger"] == "manual" and body["week_start"] == "2026-10-26"

    assert client.get("/reporting/pipeline-runs/latest").json()["id"] == body["id"]

    report = client.get("/reporting/weekly-office-program-performance").json()  # default: latest week
    assert report["week_start"] == "2026-10-26" and len(report["entries"]) == body["rows_written"]
    assert set(report["entries"][0]) == {
        "office", "programme_id", "total_material_cost", "kits_delivered_count",
        "shortage_events_count", "cost_variance_events_count", "currency",
    }


def test_a_specific_week_without_data_returns_an_empty_list(client):
    client.post("/reporting/pipeline-runs", json={"week_start": "2026-10-26"})
    report = client.get("/reporting/weekly-office-program-performance", params={"week_start": "2025-01-06"})
    assert report.status_code == 200 and report.json() == {"week_start": "2025-01-06", "entries": []}


def test_a_failing_run_answers_500_and_is_the_latest_run(client, engines):
    with engines[0].begin() as connection:
        connection.execute(
            storage.telemetry_events.insert().values(
                event_type="outbound_order_created",
                occurred_at=datetime(2026, 10, 28, tzinfo=timezone.utc),
                properties={"office": "miami", "programme_id": "x", "currency": "EUR"},
            )
        )
    assert client.post("/reporting/pipeline-runs", json={"week_start": "2026-10-26"}).status_code == 500
    assert client.get("/reporting/pipeline-runs/latest").json()["state"] == "Failed"


def test_a_malformed_week_start_is_refused(client):
    assert client.get("/reporting/weekly-office-program-performance", params={"week_start": "soon"}).status_code == 422
    assert client.post("/reporting/pipeline-runs", json={"week_start": "soon"}).status_code == 422


def test_without_a_session_nothing_is_served():
    anonymous = TestClient(app)
    assert anonymous.get("/reporting/weekly-office-program-performance").status_code in (401, 403)
    assert anonymous.post("/reporting/pipeline-runs").status_code in (401, 403)
