"""Resilience of the pipeline: what a failure does to the data, and how a rerun recovers (PIPELINE_DESIGN.md, section 5)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from prefect.testing.utilities import prefect_test_harness
from sqlalchemy import update

from data.pipelines.weekly_office_performance import interface, repository, storage
from main import app
from reporting.database import get_reporting_engine, get_telemetry_engine
from test_reporting import WEEK, add_event, rows, run

RUNS = storage.pipeline_runs


@pytest.fixture(scope="module", autouse=True)
def prefect_harness():
    with prefect_test_harness():
        yield


def snapshot(target):
    return [(r["office"], r["programme_id"], r["total_material_cost"], r["kits_delivered_count"], r["id"]) for r in rows(target)]


# ---------------------------------------------------------------- a failed load never corrupts and a rerun recovers


def test_a_failure_in_the_load_rolls_the_whole_week_back_and_a_rerun_gives_the_clean_result(engines, monkeypatch):
    source, target = engines
    run(engines)
    good = snapshot(target)

    # the data changes, and the next load dies AFTER writing: the verification step blows up
    add_event(source, "outbound_order_created", {"office": "valencia", "programme_id": "ventas-b2b", "currency": "EUR", "order_id": "new-1"})
    monkeypatch.setattr(repository, "_verify_load", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("connection lost")))
    with pytest.raises(RuntimeError, match="connection lost"):
        run(engines)
    assert snapshot(target) == good  # nothing half-written: the table is exactly what the last good load left

    failed = repository.get_latest_run(target)
    assert failed.state == "Failed" and "connection lost" in failed.error and failed.finished_at is not None

    monkeypatch.undo()
    run(engines)  # the rerun
    assert sum(r["kits_delivered_count"] for r in rows(target)) == sum(g[3] for g in good) + 1
    assert len(rows(target)) == len(good)  # same rows, no duplicates


def test_a_failure_before_the_load_leaves_the_previous_week_untouched(engines):
    source, target = engines
    run(engines)
    good = snapshot(target)
    add_event(source, "outbound_order_created", {"office": "miami", "programme_id": "x", "currency": "EUR", "order_id": "bad-1"})  # wrong currency
    with pytest.raises(Exception, match="miami/EUR"):
        run(engines)
    assert snapshot(target) == good


def test_a_report_that_does_not_reconcile_is_not_published(engines, monkeypatch):
    from data.process import weekly_performance as wp

    original = wp.build_weekly_rows

    def losing_a_row(*args, **kwargs):
        rows = original(*args, **kwargs)
        rows.pop()  # a bug that drops a combination
        return rows

    monkeypatch.setattr(wp, "build_weekly_rows", losing_a_row)
    with pytest.raises(wp.ReconciliationError):
        run(engines)
    assert rows(engines[1]) == []
    assert repository.get_latest_run(engines[1]).state == "Failed"


# ---------------------------------------------------------------- concurrent and dead runs


def start(target, week=WEEK):
    return repository.start_run(target, flow_name="weekly-office-performance", trigger="scheduled", week_start=week,
                                environment="production", prefect_flow_run_id=None)


def test_the_database_refuses_a_second_running_run_of_the_same_week(engines):
    _, target = engines
    first_id, first_ok = start(target)
    second_id, second_ok = start(target)
    assert first_ok and not second_ok and first_id != second_id
    states = {r.id: r.state for r in [repository.get_run(target, first_id), repository.get_run(target, second_id)]}
    assert states == {first_id: "Running", second_id: "Skipped"}
    assert start(target, week=date(2026, 10, 19))[1]  # another week is not blocked


def test_a_finished_run_does_not_block_the_next_one(engines):
    _, target = engines
    run_id, _ = start(target)
    repository.finish_run(target, run_id, state="Completed")
    assert start(target)[1]


def test_a_run_that_died_is_marked_crashed_and_does_not_lock_the_week(engines):
    _, target = engines
    dead_id, _ = start(target)
    with target.begin() as connection:  # it has been "running" for two hours
        connection.execute(update(RUNS).where(RUNS.c.id == uuid.UUID(dead_id)).values(started_at=datetime.now(timezone.utc) - timedelta(hours=2)))
    new_id, acquired = start(target)
    assert acquired and repository.get_run(target, dead_id).state == "Crashed"
    assert repository.get_run(target, new_id).state == "Running"


def test_the_flow_skips_when_the_week_is_already_running_and_the_endpoint_answers_409(engines, auth_headers):
    source, target = engines
    start(target)  # someone else holds the week
    summary = run(engines)
    assert summary.state == "Skipped" and rows(target) == []

    app.dependency_overrides[get_telemetry_engine] = lambda: source
    app.dependency_overrides[get_reporting_engine] = lambda: target
    try:
        answer = TestClient(app, headers=auth_headers).post("/reporting/pipeline-runs", json={"week_start": "2026-10-26"})
    finally:
        app.dependency_overrides.pop(get_telemetry_engine, None)
        app.dependency_overrides.pop(get_reporting_engine, None)
    assert answer.status_code == 409
    with pytest.raises(interface.PipelineBusyError):
        interface.run_weekly_office_performance(source_engine=source, target_engine=target, week_start=WEEK)


# ---------------------------------------------------------------- the architecture rules


def test_services_reporting_holds_no_sql_and_no_etl_logic():
    import re
    from pathlib import Path

    banned = re.compile(r"^\s*(from|import)\s+(sqlalchemy\.(sql|orm|dialects)|sqlmodel|pandas|prefect|data\.process)\b|\b(select|insert|update|delete)\(", re.M)
    for path in (Path(__file__).parents[1] / "reporting").glob("*.py"):
        assert not banned.search(path.read_text()), f"{path.name} has SQL or ETL logic"


def test_services_only_import_the_public_interface_of_the_pipelines():
    import re
    from pathlib import Path

    imports = set()
    for path in (Path(__file__).parents[1] / "reporting").glob("*.py"):
        imports |= set(re.findall(r"^from (data\.[\w.]+) import", path.read_text(), re.M))
    assert imports == {"data.pipelines.weekly_office_performance"}  # only `import interface`, never repository/storage/pipeline


def test_the_pipeline_does_not_import_from_services():
    import re
    from pathlib import Path

    root = Path(__file__).parents[3] / "data"
    for path in root.rglob("*.py"):
        assert not re.search(r"^\s*(from|import)\s+(services|reporting|telemetry|inventory|auth)\b", path.read_text(), re.M), path.name
