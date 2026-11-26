"""The logic of the asynchronous tasks (ticket DEV-55), in-process: no Redis, no worker. ``task.apply()`` runs a task like a worker does.

What the evaluation looks at, and where it is checked here:
* automatic retries with back-off, never immediately         -> ``test_the_wait_before_a_retry_*``
* after three consecutive failures: the dead-letter queue     -> ``test_three_failures_*``
* every execution logs task_id, attempt, status and duration  -> ``test_every_execution_logs_*``
* messages carry only identifiers                             -> ``test_a_message_*``

Run:  python -m pytest tests/async_tasks/test_tasks.py
"""

from __future__ import annotations

import inspect
import logging
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from celery.exceptions import Retry

import services.celery_app as celery_app_module
from async_tasks import base, dlq
from async_tasks.base import MAX_ATTEMPTS, MAX_RETRIES, ObservedTask, TaskFailed, retry_delay, run_with_retries
from services.celery_app import app

REPO = Path(__file__).resolve().parents[2]
SECRET_URL = "postgresql://pipeline_writer:hunter2-the-password@db.example.supabase.co:6543/postgres"

EXECUTIONS: list[int] = []  # the attempt number of every execution of ``always_fails``


@app.task(bind=True, base=ObservedTask, name="tests.always_fails", max_retries=MAX_RETRIES)
def always_fails(self, tag: str = "x") -> None:
    EXECUTIONS.append(self.request.retries + 1)

    def work() -> None:
        raise RuntimeError(f"cannot connect to {SECRET_URL}")

    return run_with_retries(self, work)


@app.task(bind=True, base=ObservedTask, name="tests.bad_argument", max_retries=MAX_RETRIES)
def bad_argument(self) -> None:
    EXECUTIONS.append(self.request.retries + 1)

    def work() -> None:
        raise ValueError("week_start must be a date")

    return run_with_retries(self, work)


@app.task(bind=True, base=ObservedTask, name="tests.works", max_retries=MAX_RETRIES)
def works(self) -> str:
    return "done"


@pytest.fixture(autouse=True)
def _clean():
    EXECUTIONS.clear()


def dead_letters():
    return dlq.list_dead_letters()


class FakeTask:
    """The part of a Celery task that ``run_with_retries`` uses: it records the ``countdown`` it was asked to wait."""

    def __init__(self, retries: int = 0):
        self.request = type("Request", (), {"retries": retries})()
        self.countdowns: list[float] = []

    def retry(self, exc=None, countdown=None, **_):
        if self.request.retries >= MAX_RETRIES:  # what Celery does on the last attempt: it raises the error instead of retrying
            raise exc
        self.countdowns.append(countdown)
        return Retry("retry", exc, countdown)


# ---------------------------------------------------------------- how many attempts: three, then the dead-letter queue


def test_a_task_gets_three_attempts_in_total_which_is_two_retries_for_celery():
    assert MAX_ATTEMPTS == 3 and MAX_RETRIES == 2
    assert always_fails.max_retries == MAX_RETRIES


def test_three_failures_end_in_the_dead_letter_queue_with_task_id_attempt_and_error():
    task_id = str(uuid.uuid4())
    result = always_fails.apply(kwargs={"tag": "x"}, task_id=task_id, throw=False)
    assert result.failed()
    assert EXECUTIONS == [1, 2, 3]  # the first execution and two retries: not a fourth
    (row,) = dead_letters()
    assert (row.task_id, row.attempt, row.task_name) == (task_id, 3, "tests.always_fails")
    assert "RuntimeError" in row.error and "cannot connect" in row.error
    assert row.failed_at is not None and row.arguments == '{"args": [], "kwargs": {"tag": "x"}}'


def test_one_row_per_task_not_one_per_failed_attempt():
    always_fails.apply(throw=False)
    assert len(dead_letters()) == 1  # on_failure runs on the FINAL failure only; the two retries wrote nothing


def test_a_task_that_succeeds_leaves_nothing_in_the_dead_letter_queue():
    assert works.apply().get() == "done"
    assert dead_letters() == []


def test_a_wrong_argument_is_not_retried_but_it_is_recorded_at_once():
    bad_argument.apply(throw=False)
    assert EXECUTIONS == [1]  # it would fail the same way every time
    (row,) = dead_letters()
    assert row.attempt == 1 and "ValueError" in row.error


# ---------------------------------------------------------------- the wait: growing, never zero


def test_the_wait_before_a_retry_grows_and_is_never_immediate(monkeypatch):
    monkeypatch.delenv("ASYNC_RETRY_BASE_SECONDS", raising=False)  # the production default: 5 s
    for _ in range(50):  # the jitter is random: many draws
        first, second, third = retry_delay(0), retry_delay(1), retry_delay(2)
        assert 5 <= first <= 6 and 10 <= second <= 12 and 20 <= third <= 24
        assert 0 < first < second < third  # exponential: every wait is longer than the one before, with the jitter in


def test_the_task_asks_celery_for_that_wait(monkeypatch):
    monkeypatch.delenv("ASYNC_RETRY_BASE_SECONDS", raising=False)
    waits = []
    for retries in range(MAX_RETRIES):
        task = FakeTask(retries)
        with pytest.raises(Retry):
            run_with_retries(task, lambda: (_ for _ in ()).throw(RuntimeError("down")))
        waits.extend(task.countdowns)
    assert len(waits) == 2 and all(w > 0 for w in waits) and waits[0] < waits[1]  # a countdown: never "retry now"


def test_the_base_wait_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("ASYNC_RETRY_BASE_SECONDS", "2")
    assert 2 <= retry_delay(0) <= 2.4
    monkeypatch.setenv("ASYNC_RETRY_BASE_SECONDS", "not a number")
    assert retry_delay(0) >= base.DEFAULT_RETRY_BASE_SECONDS  # a typo does not stop the retries


# ---------------------------------------------------------------- the error that is kept never carries credentials


def test_the_error_that_leaves_a_task_is_text_without_the_password_and_without_the_original_in_its_chain():
    with pytest.raises(TaskFailed) as raised:
        run_with_retries(FakeTask(retries=MAX_RETRIES), lambda: (_ for _ in ()).throw(RuntimeError(f"cannot connect to {SECRET_URL}")))
    error = raised.value
    assert "hunter2" not in str(error) and "pipeline_writer" not in str(error) and str(error).startswith("RuntimeError: cannot connect")
    # Raised inside the ``except`` it would be chained to the original, and the traceback that Celery stores would print the original message again.
    assert error.__cause__ is None and error.__context__ is None


def test_the_dead_letter_and_the_log_never_carry_the_password(caplog):
    caplog.set_level(logging.INFO, logger="async_tasks")
    always_fails.apply(throw=False)
    (row,) = dead_letters()
    assert "hunter2" not in row.error and "hunter2" not in row.arguments
    assert "hunter2" not in caplog.text and "pipeline_writer" not in caplog.text
    assert "postgresql://***@db.example.supabase.co" in row.error


# ---------------------------------------------------------------- the log: one line per execution


def test_every_execution_logs_task_id_attempt_status_and_duration(caplog):
    caplog.set_level(logging.INFO, logger="async_tasks")
    task_id = str(uuid.uuid4())
    always_fails.apply(task_id=task_id, throw=False)
    lines = [r.getMessage() for r in caplog.records if r.name == "async_tasks" and "status=" in r.getMessage() and "dead_letter" not in r.getMessage()]
    assert len(lines) == 3  # one per execution
    for attempt, (line, status) in enumerate(zip(lines, ("retry", "retry", "failure")), start=1):
        assert f"task_id={task_id}" in line and f"attempt={attempt}" in line and f"status={status}" in line
        assert "duration=" in line and line.split("duration=")[1].split("s")[0].replace(".", "").isdigit()


def test_a_success_logs_its_line_too(caplog):
    caplog.set_level(logging.INFO, logger="async_tasks")
    task_id = str(uuid.uuid4())
    works.apply(task_id=task_id)
    (line,) = [r.getMessage() for r in caplog.records if "status=success" in r.getMessage()]
    assert f"task_id={task_id} attempt=1 status=success duration=" in line


def test_a_failure_logs_the_complete_error_with_its_traceback(caplog):
    caplog.set_level(logging.INFO, logger="async_tasks")
    always_fails.apply(throw=False)
    failure = next(r for r in caplog.records if "status=failure" in r.getMessage())
    message = failure.getMessage()
    assert "RuntimeError: cannot connect to postgresql://***@" in message  # the whole message
    assert "Traceback (most recent call last)" in message  # and where it came from


def test_if_the_dead_letter_cannot_be_written_the_failure_is_still_in_the_log_and_nothing_is_raised(monkeypatch, caplog):
    def broken(**_):
        raise RuntimeError(f"the database is down: {SECRET_URL}")

    monkeypatch.setattr(dlq, "record", broken)
    caplog.set_level(logging.INFO, logger="async_tasks")
    always_fails.apply(throw=False)  # must not raise from inside on_failure
    lost = next(r.getMessage() for r in caplog.records if "dead_letter_lost" in r.getMessage())
    assert "could NOT be written" in lost and "RuntimeError: cannot connect" in lost  # the failure is not lost
    assert "hunter2" not in lost


# ---------------------------------------------------------------- the dead-letter table


def test_the_table_is_created_by_itself_and_lists_the_newest_first():
    for number in range(3):
        dlq.record(task_id=f"id-{number}", task_name="t", attempt=3, error="boom")
    assert [row.task_id for row in dlq.list_dead_letters()] == ["id-2", "id-1", "id-0"]
    assert [row.task_id for row in dlq.list_dead_letters(limit=1)] == ["id-2"]


def test_cleaning_the_credentials_of_a_huge_message_takes_milliseconds_not_minutes():
    """It was quadratic: 40 000 letters took 10 s. The message of a database error can be that long (it lists the parameters of the query)."""
    import time

    from core.redaction import strip_credentials

    started = time.perf_counter()
    strip_credentials("e" * 400_000)
    strip_credentials("a.b-c+" * 70_000)
    assert time.perf_counter() - started < 1.0
    assert strip_credentials("x https://u:p@a.com and ftp://v:w@b.org") == "x https://***@a.com and ftp://***@b.org"  # and it still finds them


def test_an_enormous_error_is_cut_to_what_the_column_holds():
    row = dlq.record(task_id="x", task_name="t", attempt=3, error="e" * 100_000)
    assert len(row.error) <= dlq.MAX_ERROR_LENGTH


def test_the_reference_sql_matches_the_model():
    sql = (REPO / "services" / "api" / "async_tasks" / "sql" / "001_task_dead_letters.sql").read_text(encoding="utf-8")
    for column in ("task_id", "task_name", "attempt", "error", "arguments", "failed_at"):
        assert column in sql
    assert set(dlq.dead_letters.columns.keys()) == {"id", "task_id", "task_name", "attempt", "error", "arguments", "failed_at"}


# ---------------------------------------------------------------- the messages are light


def test_a_message_with_light_parameters_is_accepted():
    base.check_light([], {"week_start": "2026-10-26"})
    base.check_light(["a-uuid-4-style-identifier-0000-0000"], {})


def test_a_message_carrying_data_is_refused_before_it_reaches_redis():
    heavy = {"events": [{"event_id": str(uuid.uuid4()), "payload": "x" * 50} for _ in range(100)]}
    with pytest.raises(base.MessageTooLarge, match="must be light"):
        base.check_light([], heavy)
    with pytest.raises(base.MessageTooLarge):
        works.apply_async(kwargs=heavy)  # through the real entry point of a task: nothing is sent


def test_the_pipeline_task_takes_one_parameter_a_date_and_nothing_else():
    from async_tasks.tasks import run_weekly_pipeline

    assert list(inspect.signature(run_weekly_pipeline.run).parameters) == ["week_start"]  # a date as text: the data is read by the worker


# ---------------------------------------------------------------- the pipeline task


def test_the_pipeline_task_returns_the_run_it_recorded(monkeypatch):
    from async_tasks import tasks

    fake_run = _fake_run()
    seen = {}
    monkeypatch.setattr(tasks, "ensure_reporting_schema", lambda: None)
    monkeypatch.setattr(tasks.interface, "reporting_engine", lambda: "target")
    monkeypatch.setattr(tasks.interface, "telemetry_engine", lambda: "source")
    monkeypatch.setattr(tasks.interface, "run_weekly_office_performance", lambda **kw: seen.update(kw) or fake_run)
    result = tasks.run_weekly_pipeline.apply(kwargs={"week_start": "2026-10-28"}).get()
    assert seen["week_start"].isoformat() == "2026-10-28" and seen["target_engine"] == "target"
    assert result["state"] == "Completed" and result["rows_written"] == 5 and result["week_start"] == "2026-10-26"


def test_without_a_week_it_runs_the_last_complete_week(monkeypatch):
    from async_tasks import tasks

    seen = {}
    monkeypatch.setattr(tasks, "ensure_reporting_schema", lambda: None)
    monkeypatch.setattr(tasks.interface, "reporting_engine", lambda: None)
    monkeypatch.setattr(tasks.interface, "telemetry_engine", lambda: None)
    monkeypatch.setattr(tasks.interface, "run_weekly_office_performance", lambda **kw: seen.update(kw) or _fake_run())
    tasks.run_weekly_pipeline.apply().get()
    assert seen["week_start"] is None


def test_a_duplicate_request_for_a_week_already_running_is_skipped_not_failed(monkeypatch):
    """The pipeline refuses to run a week twice at once. A duplicate is harmless: it must not be retried (a run outlasts the waits) nor end in the
    dead-letter queue as if something had broken."""
    from async_tasks import tasks

    def busy(**_):
        raise tasks.interface.PipelineBusyError("busy")

    monkeypatch.setattr(tasks, "ensure_reporting_schema", lambda: None)
    monkeypatch.setattr(tasks.interface, "reporting_engine", lambda: None)
    monkeypatch.setattr(tasks.interface, "telemetry_engine", lambda: None)
    monkeypatch.setattr(tasks.interface, "run_weekly_office_performance", busy)
    result = tasks.run_weekly_pipeline.apply(kwargs={"week_start": "2026-10-26"})
    assert result.successful() and result.get()["state"] == "Skipped" and "already running" in result.get()["detail"]
    assert dead_letters() == []


def test_a_malformed_week_fails_at_once_and_is_recorded(monkeypatch):
    from async_tasks import tasks

    result = tasks.run_weekly_pipeline.apply(kwargs={"week_start": "next tuesday"}, throw=False)
    assert result.failed()
    (row,) = dead_letters()
    assert row.attempt == 1 and "ValueError" in row.error


def test_a_failure_of_the_pipeline_is_retried_and_then_recorded(monkeypatch):
    from async_tasks import tasks

    calls = []

    def down(**_):
        calls.append(1)
        raise tasks.interface.PipelineRunFailed(f"Prefect could not start ({SECRET_URL})")

    monkeypatch.setattr(tasks, "ensure_reporting_schema", lambda: None)
    monkeypatch.setattr(tasks.interface, "reporting_engine", lambda: None)
    monkeypatch.setattr(tasks.interface, "telemetry_engine", lambda: None)
    monkeypatch.setattr(tasks.interface, "run_weekly_office_performance", down)
    tasks.run_weekly_pipeline.apply(kwargs={"week_start": "2026-10-26"}, throw=False)
    assert len(calls) == MAX_ATTEMPTS
    (row,) = dead_letters()
    assert row.attempt == 3 and "PipelineRunFailed" in row.error and "hunter2" not in row.error


def _fake_run():
    from datetime import date, datetime

    from data.pipelines.weekly_office_performance.interface import RunInfo  # noqa: F401  (the real type, so the field names are the real ones)
    import dataclasses

    values = dict(
        id="run-1", flow_name="weekly-office-performance", trigger="manual", prefect_flow_run_id=None, week_start=date(2026, 10, 26),
        environment="production", state="Completed", started_at=datetime(2026, 11, 2, 5, 0), finished_at=datetime(2026, 11, 2, 5, 1),
        events_read=17, window_events_total=18, rejected_count=0, rows_written=5, rows_changed=0, rows_deleted=0, error=None, warnings=None,
    )
    return RunInfo(**{f.name: values[f.name] for f in dataclasses.fields(RunInfo)})


# ---------------------------------------------------------------- the configuration of the app


def test_redis_is_the_broker_and_the_result_backend_taken_from_REDIS_URL():
    assert app.conf.broker_url == celery_app_module.broker_url()
    assert app.conf.result_backend.endswith("/1") and app.conf.broker_url.endswith("/0")  # the queue and the outcomes in separate databases
    assert urlsplit(app.conf.broker_url).netloc == urlsplit(app.conf.result_backend).netloc  # the same server


def test_the_result_backend_can_be_pointed_somewhere_else(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://queue.internal:6380/3")
    assert celery_app_module.result_backend_url() == "redis://queue.internal:6380/1"
    monkeypatch.setenv("REDIS_RESULT_URL", "redis://results.internal:6381/7")
    assert celery_app_module.result_backend_url() == "redis://results.internal:6381/7"


def test_a_message_is_confirmed_after_the_work_and_the_started_state_exists():
    assert app.conf.task_acks_late is True and app.conf.worker_prefetch_multiplier == 1
    assert app.conf.task_track_started is True  # without it "started" never exists
    assert app.conf.task_serializer == "json" and app.conf.accept_content == ["json"]


def test_every_task_has_a_timeout_a_soft_one_and_a_hard_one_and_the_queue_waits_longer_than_both():
    conf = app.conf
    assert 0 < conf.task_soft_time_limit < conf.task_time_limit
    assert conf.broker_transport_options["visibility_timeout"] > conf.task_time_limit  # or a running task would be delivered twice
    assert 0 < conf.result_expires <= 24 * 3600  # Redis has a fixed memory: the outcomes cannot stay forever
    for name in ("async_tasks.run_weekly_pipeline", "tests.always_fails"):
        task = app.tasks[name]
        assert task.soft_time_limit in (None, conf.task_soft_time_limit) and task.time_limit in (None, conf.task_time_limit)  # not switched off per task


def test_the_publishing_of_the_api_fails_fast_when_redis_is_not_there():
    policy = app.conf.task_publish_retry_policy
    assert app.conf.broker_connection_timeout <= 2 and policy["max_retries"] <= 1


def test_flower_gets_its_events():
    assert app.conf.worker_send_task_events is True and app.conf.task_send_sent_event is True


def test_the_tasks_registered_for_the_worker_are_the_pipeline_and_the_demos():
    import async_tasks.demo  # noqa: F401
    import async_tasks.tasks  # noqa: F401

    names = {n for n in app.tasks if n.startswith("async_tasks.")}
    assert names == {"async_tasks.run_weekly_pipeline", "async_tasks.demo_ok", "async_tasks.demo_fail", "async_tasks.demo_flaky"}
    assert all(isinstance(app.tasks[n], ObservedTask) for n in names)  # every one goes through the base class: no task can skip the log or the dead letters


def test_the_demo_tasks_are_not_loaded_unless_they_are_asked_for():
    code = "import os; os.environ.pop('CELERY_DEMO_TASKS', None); import services.celery_app as m; print(m.app.conf.include)"
    out = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True, check=True, env={**_env(), "CELERY_DEMO_TASKS": "0"}).stdout
    assert "async_tasks.tasks" in out and "demo" not in out


def test_importing_the_tasks_and_the_endpoints_registers_no_table_in_the_shared_metadata():
    """The inventory creates every table of SQLModel's metadata in its own database at startup (``init_db``), and its test says it has exactly its own.
    The dead-letter queue has a ``MetaData`` of its own, and nothing here imports ``job_runner`` (whose ``job_runs`` WOULD register itself)."""
    code = (
        "import services.celery_app, async_tasks.tasks, async_tasks.router, async_tasks.dlq, async_tasks.base;"
        "from sqlmodel import SQLModel;"
        "print(sorted(SQLModel.metadata.tables))"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True, check=True, env=_env()).stdout
    assert out.strip() == "[]"


def test_a_worker_does_not_need_the_web_application():
    """The tasks run in a process of their own: importing them must not import FastAPI's app nor the routers."""
    code = (
        "import sys, services.celery_app, async_tasks.tasks;"
        "print(sorted(m for m in ('main', 'async_tasks.router') if m in sys.modules))"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True, check=True, env=_env()).stdout
    assert out.strip() == "[]"


def _env() -> dict:
    import os

    return {**os.environ, "PYTHONPATH": f"{REPO}:{REPO / 'services' / 'api'}"}
