#!/usr/bin/env python3
"""Nightly export of the telemetry (ticket DEV-53): export yesterday's events to a CSV, launch the data pipeline, and leave a record
in the database of what happened and when.

Usage (from the repository root):
    python scripts/nightly_export.py                          # yesterday, in UTC
    TARGET_DATE=2026-10-30 python scripts/nightly_export.py   # any past day, with no change in the code

It is a process of its OWN: it imports no FastAPI and never runs inside the API. Something outside (cron, the scheduler container:
see infra/scheduler/) starts it every night.

Each execution is a row of ``job_runs`` (services/api/job_runner/) in the state machine ``pending -> processing -> completed | failed``:

* LOCK. ``processing`` IS the lock: if another run of ``nightly_export`` is ``processing``, this one aborts silently (an INFO line in the
  log, exit code 0). The database enforces it, so two instances started at the same instant cannot both go on.
* IDEMPOTENT PER DAY. If the day already has a ``completed`` run, nothing is done again: no CSV, no pipeline. If the CSV of the day
  already exists it is not written again (a day that failed after exporting is retried without exporting twice).
* NO ZOMBIES. Whatever goes wrong (an exception, Ctrl-C, SIGTERM), the row ends ``failed`` with the message of the error. A process killed
  with ``kill -9`` cannot write it: the next run closes any row left ``processing`` for too long (``NIGHTLY_STALE_AFTER_MINUTES``).

The CSV (``data/raw/telemetry_YYYY-MM-DD.csv``) is a BACKUP for audit and recovery. The pipeline does not read it: it reads
``telemetry_events`` from the database. ``job_runs`` (this job) and ``reporting.pipeline_runs`` (the pipeline's phases) are different logs.

Environment (all optional):
    TARGET_DATE                       the day to export, YYYY-MM-DD; it must be a day that has ended (UTC). Default: yesterday.
    DATABASE_URL                      the API's database (also read from services/api/.env).
    PIPELINE_DATA_DIR                 where ``raw/`` is (default: <repo>/data).
    NIGHTLY_PIPELINE_COMMAND          the pipeline command (default: python data/pipelines/pipeline.py --trigger scheduled).
    NIGHTLY_PIPELINE_TIMEOUT_SECONDS  the pipeline is stopped after this long (default 1800).
    NIGHTLY_STALE_AFTER_MINUTES       a row ``processing`` for longer than this is a dead run (default 120; always longer than the timeout).
    NIGHTLY_REQUIRE_DATABASE_URL      set to 1 (the scheduler container does) to refuse to run without DATABASE_URL instead of using the local SQLite file.

Exit code: 0 done, or skipped (already done / another run is going); 1 the run failed; 2 bad usage (an invalid TARGET_DATE, or no database when one is required); 130 interrupted.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import shlex
import signal
import subprocess
import sys
import time
from contextlib import suppress
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "services" / "api"))  # the job_runner package (and the API's config) live there
sys.path.insert(0, str(REPO))  # ``data.`` : the mirror of the telemetry_events table the pipeline already uses

from sqlalchemy import select  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402
from sqlmodel import Session  # noqa: E402

from data.pipelines.weekly_office_performance.storage import telemetry_events  # noqa: E402
from job_runner import database, service  # noqa: E402

JOB_NAME = "nightly_export"
COLUMNS = ["event_id", "event_type", "timestamp", "service", "user_id", "session_id", "environment", "tags"]
DEFAULT_PIPELINE_TIMEOUT_SECONDS = 1800
DEFAULT_STALE_AFTER_MINUTES = 120
RECORD_FAILURE_ATTEMPTS = 3
RETRY_SLEEP_SECONDS = 1.0

# ------------------------------------------------------------------------------------------------ the log: timestamp, job and status in every line

LOG_FORMAT = "%(asctime)s %(levelname)s job=%(job)s target_date=%(target_date)s status=%(status)s %(message)s"
log = logging.getLogger("nightly_export")


class LogFormatter(logging.Formatter):
    """UTC timestamps, and never a credential: a database error can carry the URL it was connecting to, even in a traceback."""

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:  # noqa: N802
        return datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="seconds")

    def format(self, record: logging.LogRecord) -> str:
        return service.strip_credentials(super().format(record))


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(LogFormatter(LOG_FORMAT))
    log.handlers[:] = [handler]
    log.setLevel(logging.INFO)
    log.propagate = False


def event(level: int, status: str, message: str, target_date: date | None = None, **kwargs) -> None:
    """One line of the log. INFO for the normal events (start, end, skipped), ERROR for the exceptions."""
    log.log(level, message, extra={"job": JOB_NAME, "target_date": target_date.isoformat() if target_date else "-", "status": status}, **kwargs)


# ------------------------------------------------------------------------------------------------ the day


class UsageError(ValueError):
    """A wrong TARGET_DATE: nothing was started, so there is no row to close."""


def resolve_target_date(raw: str | None, today: date | None = None) -> date:
    """``TARGET_DATE`` or, by default, yesterday in UTC. It must be a day that has already ended: a CSV of a day still going would be
    written incomplete, and since an existing CSV is never written again, it would stay incomplete for ever."""
    today = today or datetime.now(timezone.utc).date()
    if raw is None or not raw.strip():
        return today - timedelta(days=1)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw.strip()):
        raise UsageError(f"TARGET_DATE must be YYYY-MM-DD, not {raw!r}")
    try:
        target = date.fromisoformat(raw.strip())
    except ValueError as error:
        raise UsageError(f"TARGET_DATE is not a real date: {raw!r}") from error
    if target >= today:
        raise UsageError(f"TARGET_DATE {target} has not ended yet (UTC today is {today}): only a past day can be exported")
    return target


# ------------------------------------------------------------------------------------------------ the CSV (a backup)


def csv_path(export_dir: Path, target_date: date) -> Path:
    return export_dir / f"telemetry_{target_date.isoformat()}.csv"


def _cell(column: str, value):
    if value is None:
        return ""
    if column == "timestamp":
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()
    if column == "tags":
        return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return value


def export_csv_if_missing(engine: Engine, target_date: date, export_dir: Path) -> tuple[Path, int | None]:
    """The events of ``target_date`` (the UTC day), from ``telemetry_events``, to ``telemetry_YYYY-MM-DD.csv``.

    ``(path, None)`` if the file already exists: it is not written again. Otherwise ``(path, rows)``. The rows go in a fixed order, so
    the same day always gives the same file. A day with no events gives a file with only the header.

    The file is written to a temporary name and renamed at the end: the final name only ever holds a COMPLETE file. Otherwise a run
    killed halfway would leave a partial file that the next run would take for done."""
    path = csv_path(export_dir, target_date)
    if path.exists():
        return path, None
    start = datetime.combine(target_date, dtime.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    export_dir.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    columns = [telemetry_events.c[name] for name in COLUMNS]
    query = select(*columns).where(telemetry_events.c.timestamp >= start, telemetry_events.c.timestamp < end).order_by(
        telemetry_events.c.timestamp, telemetry_events.c.event_id)
    rows = 0
    try:
        with engine.connect() as connection, temporary.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(COLUMNS)
            for row in connection.execution_options(stream_results=True).execute(query):
                writer.writerow([_cell(name, value) for name, value in zip(COLUMNS, row)])
                rows += 1
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path, rows


# ------------------------------------------------------------------------------------------------ the pipeline, as a process of its own


class PipelineFailed(RuntimeError):
    """The pipeline did not end well: its exit code or its timeout say so."""


def pipeline_command() -> list[str]:
    configured = os.environ.get("NIGHTLY_PIPELINE_COMMAND", "").strip()
    return shlex.split(configured) if configured else [sys.executable, str(REPO / "data" / "pipelines" / "pipeline.py"), "--trigger", "scheduled"]


def run_pipeline(command: list[str], timeout: int) -> None:
    """Launch the pipeline as a subprocess and wait for it. It writes its OWN log (``reporting.pipeline_runs``); this job only needs to know
    whether it ended well. If this process is interrupted while waiting, ``subprocess.run`` stops the child too."""
    try:
        done = subprocess.run(command, cwd=REPO, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as error:
        raise PipelineFailed(f"the pipeline did not finish in {timeout} s and was stopped") from error
    if done.returncode != 0:
        tail = (done.stderr or done.stdout or "").strip()[-600:]
        raise PipelineFailed(f"the pipeline exited with code {done.returncode}" + (f": {tail}" if tail else ""))


# ------------------------------------------------------------------------------------------------ one execution


def describe(error: BaseException) -> str:
    if isinstance(error, KeyboardInterrupt):
        return "interrupted before finishing (SIGTERM or Ctrl-C)"
    return f"{type(error).__name__}: {error}"


def record_failure(engine: Engine, run_id, message: str) -> bool:
    """Write ``failed`` and its message, trying again if the database is busy. If it cannot be written at all, the run is left for the
    next execution to close as stale: it is never left looking alive."""
    for attempt in range(RECORD_FAILURE_ATTEMPTS):
        try:
            with Session(engine) as session:
                service.fail(session, run_id, message)
            return True
        except Exception:  # noqa: BLE001 - whatever it was, try again, then give up loudly
            if attempt + 1 < RECORD_FAILURE_ATTEMPTS:
                time.sleep(RETRY_SLEEP_SECONDS)
    event(logging.ERROR, "failed", f"could not write the failure of run {run_id}: the next run will close it as stale")
    return False


def run(engine: Engine, target_date: date, *, export_dir: Path, command: list[str], timeout: int, stale_after: timedelta) -> int:
    """One execution for ``target_date``. Returns the exit code; raises (after recording ``failed``) if the work fails."""
    with Session(engine) as session:
        for dead in service.mark_stale_as_failed(session, JOB_NAME, stale_after):
            event(logging.ERROR, "failed", f"run {dead} was left unfinished by a process that died: closed as failed")
        if service.has_completed_for_date(session, JOB_NAME, target_date):
            event(logging.INFO, "skipped", "this day is already completed: nothing to do", target_date)
            return 0
        if service.has_processing_lock(session, JOB_NAME):
            event(logging.INFO, "skipped", "another run is processing: aborting", target_date)
            return 0
        run_id = service.create_job_run(session, JOB_NAME, target_date).id  # pending: it exists before doing any work
        try:
            service.start_processing(session, run_id)  # the lock: the database lets only one run in
        except service.JobAlreadyRunning:
            service.discard_pending(session, run_id)  # leave no trace: a pending row that nobody will finish would be a zombie
            event(logging.INFO, "skipped", "another run is processing: aborting", target_date)
            return 0

    event(logging.INFO, "processing", "started", target_date)
    started = time.monotonic()
    try:
        path, rows = export_csv_if_missing(engine, target_date, export_dir)
        event(logging.INFO, "processing", f"{path.name} already exists: not exported again" if rows is None else f"exported {rows} events to {path.name}", target_date)
        run_pipeline(command, timeout)
    except BaseException as error:  # noqa: BLE001 - ANY failure, Ctrl-C and SIGTERM included, must leave the row failed
        message = describe(error)
        record_failure(engine, run_id, message)
        event(logging.ERROR, "failed", message, target_date, exc_info=isinstance(error, Exception))
        with suppress(AttributeError):
            error.logged = True  # main() must not log it a second time
        raise
    else:
        with Session(engine) as session:
            service.complete(session, run_id)
        event(logging.INFO, "completed", f"finished in {time.monotonic() - started:.1f} s", target_date)
        return 0
    finally:
        # The net under the net: whatever happened above, this run must not stay pending or processing. It changes nothing if the run
        # already ended (``fail`` only touches an unfinished row), so on the normal path it does no harm.
        with suppress(Exception), Session(engine) as session:
            service.fail(session, run_id, "the run ended without recording its final state")


# ------------------------------------------------------------------------------------------------ the command line


def _on_sigterm(signum, frame) -> None:  # noqa: ARG001
    raise KeyboardInterrupt("SIGTERM")  # what cron or ``docker stop`` send: the same path as Ctrl-C, so the row ends failed


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description="Export yesterday's telemetry to a CSV, launch the data pipeline and record the run. "
                                        "See the top of this file; the day is chosen with the TARGET_DATE variable.").parse_args(argv)
    configure_logging()
    try:
        target_date = resolve_target_date(os.environ.get("TARGET_DATE"))
    except UsageError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if os.environ.get("NIGHTLY_REQUIRE_DATABASE_URL") and not os.environ.get("DATABASE_URL", "").strip():
        print("error: DATABASE_URL is not set, and NIGHTLY_REQUIRE_DATABASE_URL asks for a real database (not the local SQLite fallback)", file=sys.stderr)
        return 2
    signal.signal(signal.SIGTERM, _on_sigterm)

    export_dir = Path(os.environ.get("PIPELINE_DATA_DIR") or REPO / "data") / "raw"
    timeout = int(os.environ.get("NIGHTLY_PIPELINE_TIMEOUT_SECONDS", DEFAULT_PIPELINE_TIMEOUT_SECONDS))
    stale_after = max(timedelta(minutes=int(os.environ.get("NIGHTLY_STALE_AFTER_MINUTES", DEFAULT_STALE_AFTER_MINUTES))),
                      timedelta(seconds=timeout) + timedelta(minutes=5))  # a live run must never look dead
    try:
        engine = database.build_engine()
        database.ensure_table(engine)
        return run(engine, target_date, export_dir=export_dir, command=pipeline_command(), timeout=timeout, stale_after=stale_after)
    except KeyboardInterrupt:
        return 130
    except Exception as error:  # noqa: BLE001 - the run already recorded and logged its own failures; this is the rest
        if not getattr(error, "logged", False):
            event(logging.ERROR, "failed", describe(error), target_date, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
