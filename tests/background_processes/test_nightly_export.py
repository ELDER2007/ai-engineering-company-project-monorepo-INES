"""``scripts/nightly_export.py`` (ticket DEV-53), one test group per thing the evaluation looks at:

 1. an independent process (no FastAPI)             6. the CSV, in data/raw, from telemetry_events
 2. the state machine, with target_date             7. job_runs and pipeline_runs side by side, not duplicated
 3. ``processing`` as the lock, TWO INSTANCES AT ONCE   8. logs with timestamp, job and status
 4. idempotent per target_date                      9. the trigger (see test_scheduler.py)
 5. no record left in ``processing`` after a failure  10. TARGET_DATE

The tests of the lock, the signals and the pipeline use REAL processes: the script is started the way cron starts it.

Run:  python -m pytest tests/background_processes
"""

from __future__ import annotations

import ast
import csv
import logging
import os
import re
import signal
import sqlite3
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlmodel import Session

from data.pipelines.weekly_office_performance.storage import telemetry_events
from job_runner import database, service

REPO = Path(__file__).resolve().parents[2]
SCRIPT_FILE = REPO / "scripts" / "nightly_export.py"
UTC = timezone.utc
DAY = date(2026, 10, 30)
JOB = "nightly_export"

FAKE_PIPELINE = """\
import os, sys, time
with open(os.environ["FAKE_PIPELINE_COUNTER"], "a") as handle:
    handle.write(f"{os.getpid()}\\n")
time.sleep(float(os.environ.get("FAKE_PIPELINE_SLEEP", "0")))
if os.environ.get("FAKE_PIPELINE_STDERR"):
    sys.stderr.write(os.environ["FAKE_PIPELINE_STDERR"])
sys.exit(int(os.environ.get("FAKE_PIPELINE_EXIT", "0")))
"""


# ---------------------------------------------------------------- the fixtures


@pytest.fixture()
def engine():
    engine = database.build_engine(os.environ["DATABASE_URL"])
    database.ensure_table(engine)
    telemetry_events.create(engine)
    yield engine
    engine.dispose()


class FakePipeline:
    """A pipeline that only counts how many times it was launched, and can sleep or fail on demand."""

    def __init__(self, tmp_path: Path, monkeypatch):
        path = tmp_path / "fake_pipeline.py"
        path.write_text(FAKE_PIPELINE, encoding="utf-8")
        self.command = [sys.executable, str(path)]
        self.counter = tmp_path / "launches.txt"
        monkeypatch.setenv("FAKE_PIPELINE_COUNTER", str(self.counter))
        monkeypatch.setenv("NIGHTLY_PIPELINE_COMMAND", " ".join(self.command))

    @property
    def launches(self) -> int:
        return len(self.counter.read_text().split()) if self.counter.exists() else 0

    @property
    def pids(self) -> list[int]:
        return [int(p) for p in self.counter.read_text().split()] if self.counter.exists() else []


@pytest.fixture()
def fake(tmp_path, monkeypatch):
    return FakePipeline(tmp_path, monkeypatch)


def event(engine, when: datetime, *, event_type="section_viewed", environment="production", tags=None, event_id=None):
    with engine.begin() as connection:
        connection.execute(telemetry_events.insert(), {
            "event_id": event_id or f"e-{when.isoformat()}-{environment}-{event_type}", "event_type": event_type, "timestamp": when, "service": "backoffice",
            "user_id": None, "session_id": "s-1", "environment": environment, "tags": tags or {"section": "inventory"}})


def go(script, engine, day=DAY, *, command, tmp_path, timeout=60, stale_hours=2):
    return script.run(engine, day, export_dir=tmp_path / "data" / "raw", command=command, timeout=timeout, stale_after=timedelta(hours=stale_hours))


def runs(engine):
    with engine.connect() as connection:
        return connection.execute(text("select target_date, status, error_message, started_at is not null, finished_at is not null from job_runs order by created_at")).all()


def statuses(engine):
    return [r[1] for r in runs(engine)]


def csv_file(tmp_path: Path, day: date = DAY) -> Path:
    return tmp_path / "data" / "raw" / f"telemetry_{day.isoformat()}.csv"


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def start_script(extra_env: dict | None = None, **kwargs) -> subprocess.Popen:
    """The script, started as cron starts it: a command line and an environment."""
    return subprocess.Popen([sys.executable, str(SCRIPT_FILE)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=REPO, env={**os.environ, **(extra_env or {})}, **kwargs)


def wait_until(condition, timeout=60.0, step=0.05):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(step)
    return False


def sqlite_rows(url: str, query: str):
    path = url.removeprefix("sqlite:///")
    with sqlite3.connect(path, timeout=30) as connection:
        return connection.execute(query).fetchall()


# ================================================================ 1. AN INDEPENDENT PROCESS


def test_the_script_starts_from_the_command_line_and_runs_to_the_end(engine, fake, tmp_path):
    process = start_script({"TARGET_DATE": "2026-10-30"})
    out, err = process.communicate(timeout=120)
    assert process.returncode == 0, err
    assert "status=completed" in out and statuses(engine) == ["completed"] and fake.launches == 1


def test_the_script_is_executable_with_a_shebang_and_a_main_guard():
    source = SCRIPT_FILE.read_text(encoding="utf-8")
    assert source.startswith("#!/usr/bin/env python3") and 'if __name__ == "__main__":' in source and "sys.exit(main())" in source


def test_the_script_imports_and_runs_no_fastapi_code():
    tree = ast.parse(SCRIPT_FILE.read_text(encoding="utf-8"))
    modules = {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module} | {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not (modules & {"fastapi", "starlette", "uvicorn", "main", "apscheduler", "threading", "asyncio"})
    source = SCRIPT_FILE.read_text(encoding="utf-8")
    assert "BackgroundTasks" not in source and "repeat_every" not in source and "lifespan" not in source


def test_the_script_runs_in_a_process_of_its_own_while_the_api_code_is_not_even_loaded(engine, fake, tmp_path):
    code = (f"import sys, os; sys.argv = ['nightly_export']; os.environ['TARGET_DATE'] = '2026-10-30';"
            f"import runpy; ns = runpy.run_path({str(SCRIPT_FILE)!r}, run_name='not_main');"
            "rc = ns['main']([]);"
            "api = sorted(k for k in sys.modules if k.split('.')[0] in ('fastapi', 'starlette', 'uvicorn'));"
            "print('RC=%s API=%s' % (rc, ','.join(api)))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, cwd=REPO, check=False)
    assert out.returncode == 0, out.stderr[-500:]
    assert "RC=0 API=" in out.stdout and out.stdout.strip().endswith("API=")


def test_the_pipeline_is_a_subprocess_not_code_run_in_this_process(engine, fake, tmp_path, script):
    go(script, engine, command=fake.command, tmp_path=tmp_path)
    assert fake.launches == 1 and fake.pids[0] != os.getpid()


# ================================================================ 2. THE STATE MACHINE, WITH target_date


def test_a_normal_night_goes_pending_processing_completed_and_the_record_says_what_day_and_when(engine, fake, tmp_path, script):
    seen: list[str] = []
    original = service.start_processing

    def spy(session, run_id):
        seen.append("pending:" + ",".join(statuses(engine)))
        result = original(session, run_id)
        seen.append("processing:" + ",".join(statuses(engine)))
        return result

    service.start_processing, service_real = spy, original
    try:
        assert go(script, engine, command=fake.command, tmp_path=tmp_path) == 0
    finally:
        service.start_processing = service_real
    assert seen == ["pending:pending", "processing:processing"]  # it existed as pending BEFORE it started, and became processing before any work
    ((target, status, error, started, finished),) = runs(engine)
    assert (target, status, error, started, finished) == ("2026-10-30", "completed", None, 1, 1)


def test_the_record_is_processing_while_the_work_is_going_on(engine, tmp_path, monkeypatch, script):
    fake_ = FakePipeline(tmp_path, monkeypatch)
    snapshot = {}
    original = script.run_pipeline

    def watch(command, timeout):
        snapshot["during"] = statuses(engine)
        return original(command, timeout)

    script.run_pipeline = watch
    try:
        go(script, engine, command=fake_.command, tmp_path=tmp_path)
    finally:
        script.run_pipeline = original
    assert snapshot["during"] == ["processing"] and statuses(engine) == ["completed"]


def test_a_failed_night_ends_failed_with_the_message_of_the_error(engine, fake, tmp_path, monkeypatch, script):
    monkeypatch.setenv("FAKE_PIPELINE_EXIT", "3")
    with pytest.raises(script.PipelineFailed):
        go(script, engine, command=fake.command, tmp_path=tmp_path)
    ((target, status, error, started, finished),) = runs(engine)
    assert (target, status, started, finished) == ("2026-10-30", "failed", 1, 1) and "PipelineFailed: the pipeline exited with code 3" in error


# ================================================================ 3. PROCESSING AS THE LOCK: TWO INSTANCES AT ONCE


def test_two_instances_started_at_the_same_time_only_one_works_and_the_other_leaves_in_silence(engine, tmp_path, monkeypatch):
    """The demonstration the evaluation asks for: two REAL processes, started together. One goes on; the other aborts silently."""
    fake_ = FakePipeline(tmp_path, monkeypatch)
    env = {"TARGET_DATE": "2026-10-30", "FAKE_PIPELINE_SLEEP": "4"}
    first, second = start_script(env), start_script(env)
    results = [first.communicate(timeout=180), second.communicate(timeout=180)]
    assert [first.returncode, second.returncode] == [0, 0]  # the one that left did not fail: it left in silence
    outputs = [out for out, _ in results]
    worked = [o for o in outputs if "status=completed" in o]
    left = [o for o in outputs if "status=skipped" in o]
    assert len(worked) == 1 and len(left) == 1
    assert "ERROR" not in "".join(outputs) and all(err.strip() == "" for _, err in results)  # nothing on stderr, no error line
    assert fake_.launches == 1  # the pipeline was launched ONCE
    assert statuses(engine) == ["completed"]  # and the one that left left no row behind (no zombie pending)
    assert csv_file(tmp_path).exists()


def test_a_second_instance_started_while_the_first_works_aborts_without_touching_anything(engine, tmp_path, monkeypatch):
    fake_ = FakePipeline(tmp_path, monkeypatch)
    first = start_script({"TARGET_DATE": "2026-10-30", "FAKE_PIPELINE_SLEEP": "6"})
    assert wait_until(lambda: statuses(engine) == ["processing"], timeout=90)  # the first holds the lock
    second = start_script({"TARGET_DATE": "2026-10-29"})  # another day: the lock is by job, not by day
    out, err = second.communicate(timeout=120)
    assert second.returncode == 0 and "status=skipped" in out and "another run is processing" in out and err.strip() == ""
    assert statuses(engine) == ["processing"]  # untouched: no second row, the first still going
    first.communicate(timeout=180)
    assert statuses(engine) == ["completed"] and fake_.launches == 1


def test_the_lock_is_released_when_the_run_ends_so_the_next_night_can_work(engine, fake, tmp_path, script):
    go(script, engine, DAY, command=fake.command, tmp_path=tmp_path)
    go(script, engine, DAY + timedelta(days=1), command=fake.command, tmp_path=tmp_path)
    assert statuses(engine) == ["completed", "completed"] and fake.launches == 2


def test_a_run_that_finds_the_lock_taken_before_it_asks_leaves_no_row_either(engine, fake, tmp_path, script, caplog):
    with Session(engine) as session:
        held = service.create_job_run(session, JOB, DAY - timedelta(days=1))
        service.start_processing(session, held.id)
    with caplog.at_level(logging.INFO, logger="nightly_export"):
        assert go(script, engine, command=fake.command, tmp_path=tmp_path) == 0
    assert statuses(engine) == ["processing"] and fake.launches == 0 and not csv_file(tmp_path).exists()
    assert [r.levelname for r in caplog.records] == ["INFO"] and caplog.records[0].status == "skipped"


def test_the_race_inside_the_script_when_the_check_passes_but_the_database_says_no(engine, fake, tmp_path, script, caplog):
    """Both look, nobody is processing, both go. Here the check passes and the other run slips in right after it: the DATABASE refuses."""
    original = service.has_processing_lock

    def lie(session, job_name):
        with Session(engine) as other:  # the other instance, getting in between the question and the start
            row = service.create_job_run(other, JOB, DAY - timedelta(days=1))
            service.start_processing(other, row.id)
        return False  # "nobody is processing" (it was true when it was asked)

    service.has_processing_lock = lie
    try:
        with caplog.at_level(logging.INFO, logger="nightly_export"):
            assert go(script, engine, command=fake.command, tmp_path=tmp_path) == 0
    finally:
        service.has_processing_lock = original
    assert statuses(engine) == ["processing"] and fake.launches == 0  # the late one was refused and removed its own pending row
    assert any(r.status == "skipped" for r in caplog.records)


# ================================================================ 4. IDEMPOTENT PER target_date


def test_running_twice_the_same_day_gives_what_running_once_gives(engine, fake, tmp_path, script):
    event(engine, datetime(2026, 10, 30, 10, tzinfo=UTC))
    go(script, engine, command=fake.command, tmp_path=tmp_path)
    first_bytes, first_mtime = csv_file(tmp_path).read_bytes(), csv_file(tmp_path).stat().st_mtime_ns
    assert go(script, engine, command=fake.command, tmp_path=tmp_path) == 0
    assert csv_file(tmp_path).read_bytes() == first_bytes and csv_file(tmp_path).stat().st_mtime_ns == first_mtime  # the CSV was not touched
    assert fake.launches == 1  # no second execution of the pipeline
    assert statuses(engine) == ["completed"]  # no second record: the skipped run is only a log line
    assert sorted(p.name for p in (tmp_path / "data" / "raw").iterdir()) == ["telemetry_2026-10-30.csv"]  # one CSV, no leftovers


def test_the_second_run_says_it_skipped_a_duplicate(engine, fake, tmp_path, script, caplog):
    go(script, engine, command=fake.command, tmp_path=tmp_path)
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="nightly_export"):
        go(script, engine, command=fake.command, tmp_path=tmp_path)
    (record,) = caplog.records
    assert (record.levelname, record.status, record.target_date) == ("INFO", "skipped", "2026-10-30") and "already completed" in record.getMessage()


def test_the_completed_of_one_day_does_not_stop_another_day(engine, fake, tmp_path, script):
    go(script, engine, DAY, command=fake.command, tmp_path=tmp_path)
    go(script, engine, DAY - timedelta(days=1), command=fake.command, tmp_path=tmp_path)
    assert fake.launches == 2 and csv_file(tmp_path, DAY).exists() and csv_file(tmp_path, DAY - timedelta(days=1)).exists()


def test_a_day_that_failed_after_exporting_is_retried_without_exporting_twice(engine, fake, tmp_path, script, monkeypatch):
    event(engine, datetime(2026, 10, 30, 10, tzinfo=UTC))
    monkeypatch.setenv("FAKE_PIPELINE_EXIT", "1")
    with pytest.raises(script.PipelineFailed):
        go(script, engine, command=fake.command, tmp_path=tmp_path)  # exported, then the pipeline failed
    exported = csv_file(tmp_path).stat().st_mtime_ns
    monkeypatch.setenv("FAKE_PIPELINE_EXIT", "0")
    assert go(script, engine, command=fake.command, tmp_path=tmp_path) == 0  # the day is not done, so it is tried again
    assert csv_file(tmp_path).stat().st_mtime_ns == exported  # but the CSV was not written again
    assert statuses(engine) == ["failed", "completed"] and fake.launches == 2


def test_the_csv_that_already_exists_is_never_written_again(engine, tmp_path, script):
    csv_file(tmp_path).parent.mkdir(parents=True)
    csv_file(tmp_path).write_text("a file that was already there", encoding="utf-8")
    path, rows = script.export_csv_if_missing(engine, DAY, tmp_path / "data" / "raw")
    assert rows is None and path.read_text(encoding="utf-8") == "a file that was already there"


# ================================================================ 5. NO RECORD LEFT IN processing AFTER A FAILURE


def test_the_failure_handling_is_a_try_except_finally_that_catches_everything():
    tree = ast.parse(SCRIPT_FILE.read_text(encoding="utf-8"))
    run = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "run")
    tries = [n for n in ast.walk(run) if isinstance(n, ast.Try)]
    work = next(t for t in tries if t.handlers and t.finalbody and t.orelse)
    assert [ast.unparse(h.type) for h in work.handlers] == ["BaseException"]  # not just Exception: Ctrl-C and SIGTERM too
    assert any(isinstance(n, ast.Raise) for n in ast.walk(work.handlers[0]))  # and the error is propagated, not swallowed


def test_a_failure_while_exporting_leaves_the_record_failed(engine, fake, tmp_path, script):
    def broken(*args, **kwargs):
        raise OSError("disk full")

    original = script.export_csv_if_missing
    script.export_csv_if_missing = broken
    try:
        with pytest.raises(OSError):
            go(script, engine, command=fake.command, tmp_path=tmp_path)
    finally:
        script.export_csv_if_missing = original
    assert statuses(engine) == ["failed"] and "OSError: disk full" in runs(engine)[0][2] and fake.launches == 0  # and the pipeline was never launched


@pytest.mark.parametrize("failure", [ValueError("a bug"), RuntimeError("boom"), KeyError("missing"), MemoryError(), KeyboardInterrupt(), SystemExit(3)])
def test_whatever_is_raised_while_working_the_record_never_stays_in_processing(engine, fake, tmp_path, script, failure):
    original = script.run_pipeline

    def explode(command, timeout):
        raise failure

    script.run_pipeline = explode
    try:
        with pytest.raises(BaseException):  # noqa: B017 - the error is propagated, whatever it is
            go(script, engine, command=fake.command, tmp_path=tmp_path)
    finally:
        script.run_pipeline = original
    assert statuses(engine) == ["failed"] and service.has_processing_lock(Session(engine), JOB) is False


def test_a_pipeline_that_does_not_end_in_time_is_stopped_and_the_record_is_failed(engine, fake, tmp_path, script, monkeypatch):
    monkeypatch.setenv("FAKE_PIPELINE_SLEEP", "30")
    started = time.monotonic()
    with pytest.raises(script.PipelineFailed, match="did not finish in 1 s"):
        go(script, engine, command=fake.command, tmp_path=tmp_path, timeout=1)
    assert time.monotonic() - started < 20 and statuses(engine) == ["failed"]


def test_if_closing_the_record_fails_at_first_it_is_tried_again(engine, fake, tmp_path, script, monkeypatch):
    monkeypatch.setenv("FAKE_PIPELINE_EXIT", "1")
    monkeypatch.setattr(script, "RETRY_SLEEP_SECONDS", 0)
    real, calls = service.fail, []

    def flaky(session, run_id, message):
        calls.append(1)
        if len(calls) <= 2:
            raise ConnectionError("the database blinked")
        return real(session, run_id, message)

    service.fail = flaky
    try:
        with pytest.raises(script.PipelineFailed):
            go(script, engine, command=fake.command, tmp_path=tmp_path)
    finally:
        service.fail = real
    assert statuses(engine) == ["failed"]


def test_if_the_run_ends_without_a_final_state_the_net_under_the_net_closes_it(engine, fake, tmp_path, script):
    """``complete`` itself fails (the database goes away right at the end): the ``finally`` must still leave the record failed."""
    real = service.complete

    def broken(session, run_id):
        raise ConnectionError("lost the database at the very end")

    service.complete = broken
    try:
        with pytest.raises(ConnectionError):
            go(script, engine, command=fake.command, tmp_path=tmp_path)
    finally:
        service.complete = real
    assert statuses(engine) == ["failed"] and "ended without recording its final state" in runs(engine)[0][2]


def test_sigterm_what_cron_or_docker_stop_send_ends_the_record_failed_and_stops_the_pipeline(engine, tmp_path, monkeypatch):
    fake_ = FakePipeline(tmp_path, monkeypatch)
    process = start_script({"TARGET_DATE": "2026-10-30", "FAKE_PIPELINE_SLEEP": "60"})
    assert wait_until(lambda: fake_.launches == 1 and statuses(engine) == ["processing"], timeout=90)  # it is in the middle of the pipeline
    process.send_signal(signal.SIGTERM)
    out, err = process.communicate(timeout=30)
    assert process.returncode == 130
    ((_, status, error, _, finished),) = runs(engine)
    assert status == "failed" and finished == 1 and "interrupted" in error  # not left in processing
    assert "ERROR" in out and "status=failed" in out
    assert wait_until(lambda: not pid_alive(fake_.pids[0]), timeout=10)  # the child pipeline was stopped too


def pid_alive(pid: int) -> bool:
    """Is the process still running? (A child that died and that nobody has waited for yet is not alive.)"""
    try:
        os.kill(pid, 0)
        return Path(f"/proc/{pid}/stat").read_text().split()[2] != "Z"
    except (ProcessLookupError, FileNotFoundError):
        return False


def test_kill_9_cannot_be_caught_so_the_next_run_closes_the_dead_record_and_goes_on(engine, tmp_path, monkeypatch):
    """The zombie that no try/except can stop: the process is killed outright. The record stays processing... until the next run."""
    fake_ = FakePipeline(tmp_path, monkeypatch)
    process = start_script({"TARGET_DATE": "2026-10-30", "FAKE_PIPELINE_SLEEP": "60"})
    assert wait_until(lambda: statuses(engine) == ["processing"] and fake_.launches == 1, timeout=90)
    process.kill()  # SIGKILL: no handler, no finally
    process.communicate(timeout=30)
    os.kill(fake_.pids[0], signal.SIGKILL)
    assert statuses(engine) == ["processing"]  # the zombie exists, and it blocks the lock

    blocked = start_script({"TARGET_DATE": "2026-10-30"})
    out, _ = blocked.communicate(timeout=120)
    assert blocked.returncode == 0 and "status=skipped" in out  # while it is recent, it is taken for a run that is still going
    with engine.begin() as connection:  # time passes: three hours
        old = (datetime.now(UTC) - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S.%f")
        connection.execute(text("update job_runs set started_at = :old, created_at = :old"), {"old": old})
    monkeypatch.setenv("FAKE_PIPELINE_SLEEP", "0")
    recovered = start_script({"TARGET_DATE": "2026-10-30"})
    out, err = recovered.communicate(timeout=120)
    assert recovered.returncode == 0, err
    assert "ERROR" in out and "closed as failed" in out and "status=completed" in out
    assert statuses(engine) == ["failed", "completed"] and "stale" in runs(engine)[0][2]


def test_the_stale_limit_is_always_longer_than_the_pipeline_timeout(engine, fake, tmp_path, monkeypatch, script):
    """A live run must never look dead: however small NIGHTLY_STALE_AFTER_MINUTES is, it never undercuts the timeout."""
    seen = {}
    monkeypatch.setenv("TARGET_DATE", "2026-10-30")
    monkeypatch.setenv("NIGHTLY_PIPELINE_TIMEOUT_SECONDS", "1800")
    monkeypatch.setenv("NIGHTLY_STALE_AFTER_MINUTES", "1")
    monkeypatch.setattr(script, "run", lambda *a, **k: seen.update(k) or 0)
    assert script.main([]) == 0
    assert seen["stale_after"] > timedelta(seconds=1800)


# ================================================================ 6. THE CSV: data/raw, from telemetry_events, for the target date


def test_the_csv_has_the_right_name_the_header_and_the_events_of_the_day_from_telemetry_events(engine, fake, tmp_path, script):
    event(engine, datetime(2026, 10, 30, 8, 15, tzinfo=UTC), event_type="section_viewed", tags={"section": "inventory"}, event_id="a")
    event(engine, datetime(2026, 10, 30, 9, 0, tzinfo=UTC), event_type="outbound_order_created", tags={"office": "miami", "total_cost_minor": 25000}, event_id="b")
    go(script, engine, command=fake.command, tmp_path=tmp_path)
    path = tmp_path / "data" / "raw" / "telemetry_2026-10-30.csv"
    assert path.exists() and path.name == "telemetry_2026-10-30.csv"
    assert path.read_text(encoding="utf-8").splitlines()[0] == "event_id,event_type,timestamp,service,user_id,session_id,environment,tags"
    a, b = read_csv(path)
    assert (a["event_id"], a["event_type"], a["timestamp"], a["service"], a["session_id"], a["environment"]) == ("a", "section_viewed", "2026-10-30T08:15:00+00:00", "backoffice", "s-1", "production")
    assert a["user_id"] == "" and b["event_id"] == "b"
    import json

    assert json.loads(b["tags"]) == {"office": "miami", "total_cost_minor": 25000}


def test_only_the_events_of_the_target_day_in_utc_go_in_and_the_edges_are_right(engine, tmp_path, script):
    edges = {"before": datetime(2026, 10, 29, 23, 59, 59, 999999, tzinfo=UTC), "first": datetime(2026, 10, 30, 0, 0, 0, tzinfo=UTC),
             "last": datetime(2026, 10, 30, 23, 59, 59, 999999, tzinfo=UTC), "after": datetime(2026, 10, 31, 0, 0, 0, tzinfo=UTC)}
    for name, when in edges.items():
        event(engine, when, event_id=name)
    path, rows = script.export_csv_if_missing(engine, DAY, tmp_path / "data" / "raw")
    assert rows == 2 and [r["event_id"] for r in read_csv(path)] == ["first", "last"]  # midnight starts a day and does not end the one before


def test_every_environment_is_exported_because_the_csv_is_a_backup_of_the_table(engine, tmp_path, script):
    for environment in ("production", "development", "test", "staging"):
        event(engine, datetime(2026, 10, 30, 12, tzinfo=UTC), environment=environment, event_id=environment)
    path, rows = script.export_csv_if_missing(engine, DAY, tmp_path / "data" / "raw")
    assert rows == 4 and {r["environment"] for r in read_csv(path)} == {"production", "development", "test", "staging"}


def test_the_csv_holds_exactly_what_the_table_holds_for_that_day(engine, tmp_path, script):
    for i in range(25):
        event(engine, datetime(2026, 10, 30, i % 24, i, tzinfo=UTC), event_type=f"type_{i % 3}", tags={"n": i, "text": "ñandú, \"quoted\"\nline"}, event_id=f"id-{i:02d}")
    with engine.connect() as connection:
        expected = connection.execute(text("select event_id, event_type from telemetry_events order by timestamp, event_id")).all()
    path, rows = script.export_csv_if_missing(engine, DAY, tmp_path / "data" / "raw")
    assert rows == 25 and [(r["event_id"], r["event_type"]) for r in read_csv(path)] == [tuple(r) for r in expected]
    assert all("ñandú" in r["tags"] and "\\n" in r["tags"] for r in read_csv(path))  # commas, quotes and newlines survive


def test_a_day_without_events_gives_a_csv_with_only_the_header_and_counts_as_done(engine, fake, tmp_path, script):
    assert go(script, engine, command=fake.command, tmp_path=tmp_path) == 0
    assert csv_file(tmp_path).read_text(encoding="utf-8").splitlines() == ["event_id,event_type,timestamp,service,user_id,session_id,environment,tags"]
    assert statuses(engine) == ["completed"]


def test_the_same_day_always_gives_the_same_file(engine, tmp_path, script):
    for i in range(10):
        event(engine, datetime(2026, 10, 30, 10, tzinfo=UTC), event_id=f"same-instant-{9 - i}")  # the same instant: the order must still be fixed
    one, _ = script.export_csv_if_missing(engine, DAY, tmp_path / "one")
    two, _ = script.export_csv_if_missing(engine, DAY, tmp_path / "two")
    assert one.read_bytes() == two.read_bytes()


def test_the_file_is_written_whole_or_not_at_all(engine, tmp_path, script, monkeypatch):
    """A run killed halfway must not leave a partial file under the final name: the next run would take it for done."""
    event(engine, datetime(2026, 10, 30, 10, tzinfo=UTC))
    real = script.csv.writer

    class Breaks:
        def __init__(self, handle):
            self.inner, self.n = real(handle), 0

        def writerow(self, row):
            self.n += 1
            if self.n == 2:
                raise OSError("disk full halfway")
            self.inner.writerow(row)

    monkeypatch.setattr(script.csv, "writer", Breaks)
    with pytest.raises(OSError):
        script.export_csv_if_missing(engine, DAY, tmp_path / "data" / "raw")
    assert list((tmp_path / "data" / "raw").iterdir()) == []  # no final file, no temporary leftover


def test_the_csv_is_a_backup_and_the_pipeline_is_not_told_about_it(script, fake, monkeypatch):
    """The pipeline reads telemetry_events from the database: no argument of its command is the exported file."""
    monkeypatch.delenv("NIGHTLY_PIPELINE_COMMAND", raising=False)
    for command in (script.pipeline_command(), fake.command):
        assert not any(argument.endswith(".csv") or "telemetry_20" in argument for argument in command)


def test_the_default_pipeline_command_is_the_pipelines_own_entry_point(script, monkeypatch):
    monkeypatch.delenv("NIGHTLY_PIPELINE_COMMAND", raising=False)
    command = script.pipeline_command()
    assert command[0] == sys.executable and command[1].endswith(str(Path("data") / "pipelines" / "pipeline.py")) and Path(command[1]).exists()
    assert "--no-prefect" not in command and "telemetry_kpi_daily" not in " ".join(command)  # the reference command of the text does not exist here


# ================================================================ 7. job_runs AND pipeline_runs: DIFFERENT LOGS, NOT DUPLICATED


def strings_without_docstrings(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {id(n.body[0].value) for n in ast.walk(tree) if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and n.body and isinstance(n.body[0], ast.Expr) and isinstance(getattr(n.body[0], "value", None), ast.Constant)}
    return [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings]


@pytest.mark.parametrize("path", [SCRIPT_FILE] + sorted((REPO / "services" / "api" / "job_runner").glob("*.py")), ids=lambda p: p.name)
def test_the_job_never_reads_or_writes_pipeline_runs_nor_the_reporting_schema(path):
    code = " ".join(strings_without_docstrings(path))
    assert "pipeline_runs" not in code and "reporting" not in code and "weekly_office" not in code


def test_the_pipeline_is_launched_not_imported_so_each_keeps_its_own_log():
    tree = ast.parse(SCRIPT_FILE.read_text(encoding="utf-8"))
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert not any(m.startswith("data.pipelines") and not m.endswith("storage") for m in imported)  # only the mirror of the SOURCE table, never the pipeline
    assert "subprocess" in {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}


def test_with_the_real_pipeline_both_logs_coexist_each_written_by_its_own_process(tmp_path, monkeypatch):
    """The real thing, no stand-in: the script launches the real pipeline. job_runs holds the night, pipeline_runs holds the phases."""
    from data.pipelines.weekly_office_performance import storage
    from data.pipelines.weekly_office_performance.seed_telemetry import seed_telemetry

    url = os.environ["DATABASE_URL"]
    source = storage.build_engine(url)
    seed_telemetry(source)  # the demo events (the week of 2026-10-26)
    source.dispose()
    monkeypatch.delenv("NIGHTLY_PIPELINE_COMMAND", raising=False)
    process = start_script({"TARGET_DATE": "2026-10-27", "PREFECT_LOCAL_STORAGE_PATH": str(tmp_path / "prefect"), "PIPELINE_RETRIES": "0", "NIGHTLY_PIPELINE_TIMEOUT_SECONDS": "280"})
    out, err = process.communicate(timeout=290)
    assert process.returncode == 0, (out[-800:], err[-800:])
    assert "exported 5 events" in out and "status=completed" in out
    assert [r[0] for r in sqlite_rows(url, "select status from job_runs")] == ["completed"]  # the night
    reporting = url.removeprefix("sqlite:///") + ".reporting"
    with sqlite3.connect(reporting) as connection:
        phases = connection.execute("select flow_name, trigger, state from pipeline_runs").fetchall()
    assert phases == [("weekly-office-performance", "scheduled", "Completed")]  # the pipeline wrote its own, as a scheduled run
    assert len(read_csv(tmp_path / "data" / "raw" / "telemetry_2026-10-27.csv")) == 5


# ================================================================ 8. LOGS: TIMESTAMP, JOB NAME AND STATUS IN EVERY RELEVANT EVENT


LINE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00 (INFO|ERROR) job=nightly_export target_date=(\d{4}-\d{2}-\d{2}|-) status=(processing|completed|failed|skipped) \S")


def render(script, records) -> list[str]:
    formatter = script.LogFormatter(script.LOG_FORMAT)
    return [formatter.format(r).splitlines()[0] for r in records]


def test_every_line_has_timestamp_job_and_status_and_the_normal_events_are_info(engine, fake, tmp_path, script, caplog):
    with caplog.at_level(logging.INFO, logger="nightly_export"):
        go(script, engine, command=fake.command, tmp_path=tmp_path)  # start, export, end
        go(script, engine, command=fake.command, tmp_path=tmp_path)  # skipped as a duplicate
    lines = render(script, caplog.records)
    assert len(lines) == 4 and all(LINE.match(line) for line in lines), lines
    assert {r.levelname for r in caplog.records} == {"INFO"}
    assert [r.status for r in caplog.records] == ["processing", "processing", "completed", "skipped"]
    assert all(r.job == "nightly_export" and r.target_date == "2026-10-30" for r in caplog.records)


def test_an_exception_is_an_error_line_with_the_failed_status_and_the_traceback(engine, fake, tmp_path, script, caplog, monkeypatch):
    monkeypatch.setenv("FAKE_PIPELINE_EXIT", "2")
    with caplog.at_level(logging.INFO, logger="nightly_export"), pytest.raises(script.PipelineFailed):
        go(script, engine, command=fake.command, tmp_path=tmp_path)
    error = [r for r in caplog.records if r.levelname == "ERROR"]
    assert len(error) == 1 and error[0].status == "failed" and error[0].exc_info is not None
    assert LINE.match(render(script, error)[0]) and "PipelineFailed" in script.LogFormatter(script.LOG_FORMAT).format(error[0])


def test_the_timestamp_is_utc_iso_8601(engine, fake, tmp_path, script, caplog):
    with caplog.at_level(logging.INFO, logger="nightly_export"):
        go(script, engine, command=fake.command, tmp_path=tmp_path)
    stamp = render(script, caplog.records)[0].split(" ")[0]
    parsed = datetime.fromisoformat(stamp)
    assert parsed.utcoffset() == timedelta(0) and abs((datetime.now(UTC) - parsed).total_seconds()) < 60


def test_a_credential_in_an_error_reaches_neither_the_record_nor_the_log(engine, fake, tmp_path, script, caplog, monkeypatch):
    monkeypatch.setenv("FAKE_PIPELINE_EXIT", "3")
    monkeypatch.setenv("FAKE_PIPELINE_STDERR", "could not connect to postgresql://admin:Sup3rS3cretPw@db.example.com:6543/postgres")
    with caplog.at_level(logging.INFO, logger="nightly_export"), pytest.raises(script.PipelineFailed):
        go(script, engine, command=fake.command, tmp_path=tmp_path)
    everything = "\n".join(script.LogFormatter(script.LOG_FORMAT).format(r) for r in caplog.records)
    assert "Sup3rS3cretPw" not in everything and "Sup3rS3cretPw" not in (runs(engine)[0][2] or "") and "db.example.com" in everything


def test_the_real_script_prints_its_lines_to_the_output(engine, fake, tmp_path):
    process = start_script({"TARGET_DATE": "2026-10-30"})
    out, _ = process.communicate(timeout=120)
    lines = out.strip().splitlines()
    assert len(lines) == 3 and all(LINE.match(line) for line in lines), lines


# ================================================================ 10. TARGET_DATE (and the exit codes of a wrong one)


def test_by_default_the_day_is_yesterday_in_utc(script):
    before = datetime.now(UTC).date() - timedelta(days=1)
    chosen = script.resolve_target_date(None)
    assert chosen in {before, datetime.now(UTC).date() - timedelta(days=1)}
    assert script.resolve_target_date("", today=date(2026, 11, 9)) == date(2026, 11, 8)
    assert script.resolve_target_date(None, today=date(2026, 3, 1)) == date(2026, 2, 28)  # across a month end


def test_target_date_chooses_the_day_with_no_change_in_the_code(script):
    assert script.resolve_target_date("2026-10-30", today=date(2026, 11, 9)) == date(2026, 10, 30)
    assert script.resolve_target_date(" 2025-01-15 ", today=date(2026, 11, 9)) == date(2025, 1, 15)
    assert script.resolve_target_date("2026-11-08", today=date(2026, 11, 9)) == date(2026, 11, 8)  # yesterday, said out loud


def test_two_different_days_run_from_the_same_code_give_two_files_and_two_records(engine, fake, tmp_path, monkeypatch, script):
    for day in ("2026-10-29", "2026-10-30"):
        monkeypatch.setenv("TARGET_DATE", day)
        assert script.main([]) == 0
    assert csv_file(tmp_path, date(2026, 10, 29)).exists() and csv_file(tmp_path, date(2026, 10, 30)).exists()
    assert [r[0] for r in runs(engine)] == ["2026-10-29", "2026-10-30"]


@pytest.mark.parametrize("bad", ["yesterday", "2026-13-01", "2026-02-30", "30-10-2026", "2026/10/30", "20261030", "2026-10-3", "--help"])
def test_a_wrong_target_date_is_refused_with_a_clear_message_and_nothing_is_started(bad, engine, fake, monkeypatch, script, capsys):
    monkeypatch.setenv("TARGET_DATE", bad)
    assert script.main([]) == 2
    assert "TARGET_DATE" in capsys.readouterr().err and runs(engine) == [] and fake.launches == 0


@pytest.mark.parametrize("offset", [0, 1, 30])
def test_a_day_that_has_not_ended_is_refused_because_its_csv_would_stay_incomplete_for_ever(offset, engine, fake, monkeypatch, script, capsys):
    monkeypatch.setenv("TARGET_DATE", (datetime.now(UTC).date() + timedelta(days=offset)).isoformat())
    assert script.main([]) == 2
    assert "has not ended yet" in capsys.readouterr().err and runs(engine) == []


# ================================================================ the same demonstration, on PostgreSQL (the database of production)

ADMIN = os.environ.get("NIGHTLY_TEST_ADMIN_URL")
needs_postgres = pytest.mark.skipif(not ADMIN, reason="needs a throw-away PostgreSQL: NIGHTLY_TEST_ADMIN_URL=postgresql://postgres:...@localhost:PORT/postgres")


@needs_postgres
def test_postgres_two_real_instances_at_the_same_time_only_one_works(tmp_path, monkeypatch):
    """Two real processes against a real PostgreSQL. The URL goes only to the children, never to this process's environment."""
    import uuid

    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url

    server = create_engine(make_url(ADMIN.replace("postgresql://", "postgresql+psycopg2://", 1)), isolation_level="AUTOCOMMIT")
    name = f"nightly_{uuid.uuid4().hex[:8]}"
    with server.connect() as connection:
        connection.execute(text(f"create database {name}"))
    url = make_url(server.url).set(database=name)
    pg = create_engine(url)
    try:
        telemetry_events.create(pg)
        database.ensure_table(pg)
        event(pg, datetime(2026, 10, 30, 10, tzinfo=UTC), event_id="e-1")  # PostgreSQL does enforce the 36 characters of event_id
        fake_ = FakePipeline(tmp_path, monkeypatch)
        env = {"DATABASE_URL": url.render_as_string(hide_password=False), "TARGET_DATE": "2026-10-30", "FAKE_PIPELINE_SLEEP": "4"}
        first, second = start_script(env), start_script(env)
        results = [first.communicate(timeout=180), second.communicate(timeout=180)]
        assert [first.returncode, second.returncode] == [0, 0], results
        outputs = [out for out, _ in results]
        assert sum("status=completed" in o for o in outputs) == 1 and sum("status=skipped" in o for o in outputs) == 1
        assert "ERROR" not in "".join(outputs) and all(err.strip() == "" for _, err in results)
        assert fake_.launches == 1 and statuses(pg) == ["completed"]
        assert len(read_csv(csv_file(tmp_path))) == 1
    finally:
        pg.dispose()
        with server.connect() as connection:
            connection.execute(text(f"drop database {name} with (force)"))
        server.dispose()


# ================================================================ the exit codes and the command line


def test_exit_codes_zero_when_done_or_skipped_one_when_it_fails(engine, fake, monkeypatch, script):
    monkeypatch.setenv("TARGET_DATE", "2026-10-30")
    assert script.main([]) == 0  # done
    assert script.main([]) == 0  # skipped as a duplicate: not an error
    monkeypatch.setenv("TARGET_DATE", "2026-10-29")
    monkeypatch.setenv("FAKE_PIPELINE_EXIT", "1")
    assert script.main([]) == 1  # failed


def test_a_database_that_cannot_be_reached_is_an_error_line_and_exit_code_one(tmp_path, fake, monkeypatch, script, caplog):
    monkeypatch.setattr(script, "configure_logging", lambda: None)  # main() would take the logger away from caplog
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'no-such-folder' / 'x.sqlite'}")
    monkeypatch.setenv("TARGET_DATE", "2026-10-30")
    with caplog.at_level(logging.INFO, logger="nightly_export"):
        assert script.main([]) == 1
    assert [r.levelname for r in caplog.records] == ["ERROR"] and fake.launches == 0


def test_the_script_restores_nothing_it_does_not_own_it_only_sets_the_sigterm_handler(script, monkeypatch, engine, fake):
    previous = signal.getsignal(signal.SIGTERM)
    monkeypatch.setenv("TARGET_DATE", "2026-10-30")
    try:
        script.main([])
        assert signal.getsignal(signal.SIGTERM) is script._on_sigterm
    finally:
        signal.signal(signal.SIGTERM, previous)
