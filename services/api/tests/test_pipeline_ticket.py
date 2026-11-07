"""The four requirements of the implementation ticket: partial failures, retries, command line, one-hour cache."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from conftest import ALICE  # noqa: F401
from prefect.cache_policies import NO_CACHE
from prefect.testing.utilities import prefect_test_harness

from data.pipelines import pipeline
from data.pipelines.weekly_office_performance import repository
from data.process import weekly_performance as wp
from test_reporting import WEEK, add_event, rows, run

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module", autouse=True)
def prefect_harness():
    with prefect_test_harness():
        yield


def spy(monkeypatch, owner, name):
    """Count the calls of ``owner.name`` while keeping its behaviour."""
    calls = []
    original = getattr(owner, name)

    def wrapper(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(owner, name, wrapper)
    return calls


def latest(target):
    return repository.get_latest_run(target)


# =============================================================== 1. partial failures: optional vs critical


def test_the_optional_and_the_critical_tasks_are_the_ones_the_design_says():
    optional = {"count_window_events", "save_raw_snapshot", "save_eval_report"}
    critical = {"start_pipeline_run", "resolve_week_window", "extract_events", "validate_events", "check_currency_consistency",
                "aggregate_by_office_programme", "reconcile", "load_weekly_performance", "finish_pipeline_run"}
    assert all(hasattr(pipeline, name) for name in optional | critical)
    assert optional.isdisjoint(critical)


def test_a_failing_optional_count_does_not_stop_the_run_and_is_recorded_as_unknown_not_zero(engines, monkeypatch):
    def broken(*_args, **_kwargs):
        raise ConnectionError("count timed out")

    monkeypatch.setattr(repository, "count_window_events", broken)
    summary = run(engines)
    assert summary.state == "Completed" and len(rows(engines[1])) == 5  # the report is complete and correct
    log = latest(engines[1])
    assert log.state == "Completed" and log.window_events_total is None  # unknown: NOT 0
    assert "count_window_events" in log.warnings and "count timed out" in log.warnings


def test_a_failing_raw_snapshot_does_not_stop_the_run(engines, monkeypatch):
    original = pipeline._dir

    def no_raw(name):
        if name == "raw":
            raise PermissionError("read-only disk")
        return original(name)

    monkeypatch.setattr(pipeline, "_dir", no_raw)
    assert run(engines).state == "Completed"
    assert len(rows(engines[1])) == 5 and "save_raw_snapshot" in latest(engines[1]).warnings


def test_a_failing_evaluation_report_does_not_stop_the_run(engines, monkeypatch):
    original = pipeline._dir

    def no_eval(name):
        if name == "eval":
            raise PermissionError("read-only disk")
        return original(name)

    monkeypatch.setattr(pipeline, "_dir", no_eval)
    assert run(engines).state == "Completed" and "save_eval_report" in latest(engines[1]).warnings


def test_several_optional_failures_are_all_recorded(engines, monkeypatch):
    monkeypatch.setattr(repository, "count_window_events", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("x")))
    original = pipeline._dir
    monkeypatch.setattr(pipeline, "_dir", lambda name: (_ for _ in ()).throw(OSError("full")) if name == "raw" else original(name))
    run(engines)
    warnings = latest(engines[1]).warnings
    assert "count_window_events" in warnings and "save_raw_snapshot" in warnings


def test_a_clean_run_has_no_warnings(engines):
    run(engines)
    assert latest(engines[1]).warnings is None


def test_a_failing_critical_task_stops_the_run_loads_nothing_and_is_logged(engines, monkeypatch):
    def broken(*_args, **_kwargs):
        raise ConnectionError("database unreachable")

    monkeypatch.setattr(repository, "extract", broken)
    with pytest.raises(ConnectionError):
        run(engines)
    assert rows(engines[1]) == []
    log = latest(engines[1])
    assert log.state == "Failed" and "database unreachable" in log.error and log.finished_at is not None


def test_the_warnings_reach_the_api_response(engines, monkeypatch, auth_headers):
    from fastapi.testclient import TestClient

    from main import app
    from reporting.database import get_reporting_engine, get_telemetry_engine

    monkeypatch.setattr(repository, "count_window_events", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("x")))
    app.dependency_overrides[get_telemetry_engine] = lambda: engines[0]
    app.dependency_overrides[get_reporting_engine] = lambda: engines[1]
    try:
        body = TestClient(app, headers=auth_headers).post("/reporting/pipeline-runs", json={"week_start": "2026-10-26"}).json()
    finally:
        app.dependency_overrides.clear()
    assert body["state"] == "Completed" and body["window_events_total"] is None and "count_window_events" in body["warnings"]


# =============================================================== 2. retries on the tasks that touch external services


def test_the_default_back_off_is_5_30_and_120_seconds(monkeypatch):
    monkeypatch.delenv("PIPELINE_RETRIES", raising=False)
    monkeypatch.delenv("PIPELINE_RETRY_DELAYS", raising=False)
    assert pipeline._retry_delays() == [5, 30, 120]
    monkeypatch.setenv("PIPELINE_RETRIES", "0")
    assert pipeline._retry_delays() == []


def test_every_task_that_touches_the_database_is_configured_with_retries():
    """Checked in a fresh interpreter, because the test suite switches retries off."""
    code = (
        "from data.pipelines import pipeline as p;"
        "t=[p.extract_events,p.load_weekly_performance,p.start_pipeline_run,p.finish_pipeline_run];"
        "print([x.retries for x in t], [x.retry_delay_seconds for x in t][0], p.count_window_events.retries,"
        " p.validate_events.retries, p.aggregate_by_office_programme.retries)"
    )
    env = {k: v for k, v in os.environ.items() if k != "PIPELINE_RETRIES"}
    out = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=env, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().splitlines()[-1] == "[3, 3, 3, 3] [5, 30, 120] 1 0 0"  # DB tasks retry; pure ones do not


def test_a_transient_failure_of_the_extraction_is_absorbed_by_the_retries(engines, monkeypatch):
    original, calls = repository.extract, []

    def flaky(*args, **kwargs):
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionError("pooler out of connections")
        return original(*args, **kwargs)

    monkeypatch.setattr(repository, "extract", flaky)
    monkeypatch.setattr(pipeline, "extract_events", pipeline.extract_events.with_options(retries=2, retry_delay_seconds=0))
    assert run(engines).state == "Completed" and len(calls) == 3 and len(rows(engines[1])) == 5


def test_a_transient_failure_of_the_load_is_retried_and_leaves_no_duplicates(engines, monkeypatch):
    original, calls = repository.load_week, []

    def flaky(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise ConnectionError("connection reset")
        return original(*args, **kwargs)

    monkeypatch.setattr(repository, "load_week", flaky)
    monkeypatch.setattr(pipeline, "load_weekly_performance", pipeline.load_weekly_performance.with_options(retries=1, retry_delay_seconds=0))
    assert run(engines).state == "Completed" and len(calls) == 2 and len(rows(engines[1])) == 5


def test_a_failure_that_never_recovers_ends_failed_after_using_every_retry(engines, monkeypatch):
    calls = []

    def always(*_args, **_kwargs):
        calls.append(1)
        raise ConnectionError("down")

    monkeypatch.setattr(repository, "extract", always)
    monkeypatch.setattr(pipeline, "extract_events", pipeline.extract_events.with_options(retries=2, retry_delay_seconds=0))
    with pytest.raises(ConnectionError):
        run(engines)
    assert len(calls) == 3 and latest(engines[1]).state == "Failed"


# =============================================================== 3. runs as a command-line script


def test_it_runs_as_a_script_from_the_command_line(tmp_path):
    env = {**os.environ, "PIPELINE_DEMO_DB": str(tmp_path / "demo.sqlite"), "PIPELINE_DATA_DIR": str(tmp_path / "data")}
    out = subprocess.run(
        [sys.executable, "data/pipelines/pipeline.py", "--demo", "--week-start", "2026-10-26"],
        cwd=REPO, env=env, capture_output=True, text=True, timeout=240,
    )
    assert out.returncode == 0, out.stderr[-800:]
    assert "RunSummary" in out.stdout and "state='Completed'" in out.stdout
    assert list((tmp_path / "data" / "eval").glob("run_2026-10-26_*.json"))  # it left its validation report


def test_the_script_documents_itself():
    out = subprocess.run([sys.executable, "data/pipelines/pipeline.py", "--help"], cwd=REPO, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0 and "--week-start" in out.stdout and "--refresh" in out.stdout and "--demo" in out.stdout


def test_main_returns_zero_when_it_works_and_one_when_it_fails(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PIPELINE_DEMO_DB", str(tmp_path / "demo.sqlite"))
    assert pipeline.main(["--demo", "--week-start", "2026-10-26"]) == 0

    monkeypatch.setattr(pipeline, "weekly_office_performance_flow", lambda **_: (_ for _ in ()).throw(RuntimeError("boom")))
    assert pipeline.main(["--demo", "--week-start", "2026-10-26"]) == 1
    assert "FAILED: RuntimeError: boom" in capsys.readouterr().err


# =============================================================== 4. a task that ran in the last hour is not repeated


def test_the_cache_lasts_one_hour_and_covers_only_the_tasks_that_can_safely_be_reused():
    assert pipeline.CACHE_TTL == timedelta(hours=1)
    assert pipeline.extract_events.cache_expiration == pipeline.CACHE_TTL
    assert pipeline.aggregate_by_office_programme.cache_expiration == pipeline.CACHE_TTL
    # the load and the log act on the world every time: they must never be skipped
    for never_cached in (pipeline.load_weekly_performance, pipeline.start_pipeline_run, pipeline.finish_pipeline_run,
                         pipeline.reconcile, pipeline.check_currency_consistency):
        assert never_cached.cache_policy is NO_CACHE


def test_a_second_run_within_the_hour_reuses_the_extraction_and_the_transformation_but_still_loads(engines, monkeypatch):
    extractions = spy(monkeypatch, repository, "extract")
    aggregations = spy(monkeypatch, wp, "aggregate_by_office_programme")
    loads = spy(monkeypatch, repository, "load_week")

    run(engines, refresh=False)
    extracted, aggregated = len(extractions), len(aggregations)
    assert extracted == 1  # (the aggregation may already be cached by an earlier test: same inputs, same result)
    run(engines, refresh=False)
    assert len(extractions) == extracted and len(aggregations) == aggregated  # the second run repeated neither
    assert len(loads) == 2  # but the load acted both times
    assert len(rows(engines[1])) == 5


def test_refresh_bypasses_the_cache(engines, monkeypatch):
    extractions = spy(monkeypatch, repository, "extract")
    run(engines, refresh=False)
    run(engines, refresh=True)
    assert len(extractions) == 2


def test_a_late_event_is_not_seen_inside_the_hour_unless_the_run_refreshes(engines):
    """The design tension, written down: the cache trades freshness for speed, and refresh is the way out."""
    source, target = engines
    run(engines, refresh=False)
    kits = lambda: sum(r["kits_delivered_count"] for r in rows(target))  # noqa: E731
    before = kits()
    add_event(source, "outbound_order_created", {"office": "valencia", "programme_id": "ventas-b2b", "currency": "EUR", "order_id": "late-9"})
    run(engines, refresh=False)
    assert kits() == before  # cached extraction: the late event is not there yet
    run(engines, refresh=True)
    assert kits() == before + 1


def test_after_a_failed_load_the_rerun_does_not_read_the_source_again_and_recovers(engines, monkeypatch):
    """The case the cache exists for: extraction succeeded, the load died; the retry skips the expensive part."""
    extractions = spy(monkeypatch, repository, "extract")
    original = repository.load_week
    state = {"first": True}

    def dies_once(*args, **kwargs):
        if state.pop("first", False):
            raise ConnectionError("lost the database during the load")
        return original(*args, **kwargs)

    monkeypatch.setattr(repository, "load_week", dies_once)
    with pytest.raises(ConnectionError):
        run(engines, refresh=False)
    assert rows(engines[1]) == []
    assert run(engines, refresh=False).state == "Completed"
    assert len(extractions) == 1 and len(rows(engines[1])) == 5


def test_a_failed_task_is_never_cached(engines, monkeypatch):
    calls, original = [], repository.extract

    def fails_first(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise ConnectionError("first read fails")
        return original(*args, **kwargs)

    monkeypatch.setattr(repository, "extract", fails_first)
    with pytest.raises(ConnectionError):
        run(engines, refresh=False)
    assert run(engines, refresh=False).state == "Completed" and len(calls) == 2


def test_the_cache_expires(engines, monkeypatch):
    import time

    extractions = spy(monkeypatch, repository, "extract")
    monkeypatch.setattr(pipeline, "extract_events", pipeline.extract_events.with_options(cache_expiration=timedelta(milliseconds=50)))
    run(engines, refresh=False)
    time.sleep(0.3)
    run(engines, refresh=False)
    assert len(extractions) == 2


def test_different_weeks_and_environments_do_not_share_a_cache_entry(engines, monkeypatch):
    extractions = spy(monkeypatch, repository, "extract")
    run(engines, week=WEEK, refresh=False)
    run(engines, week=date(2026, 10, 19), refresh=False)
    run(engines, week=WEEK, environment="staging", refresh=False)
    assert len(extractions) == 3
