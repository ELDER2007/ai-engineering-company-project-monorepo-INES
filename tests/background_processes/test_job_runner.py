"""The state machine of ``job_runs`` (services/api/job_runner/): its transitions, the lock that is the ``processing`` state itself, the
reference SQL, and that nothing in it needs FastAPI.

The tests with threads and with PostgreSQL are the ones that matter most: the lock has to hold when two runs ask at the same instant.
With a throw-away PostgreSQL:  NIGHTLY_TEST_ADMIN_URL=postgresql://postgres:...@localhost:PORT/postgres python -m pytest tests/background_processes
"""

from __future__ import annotations

import ast
import os
import re
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from job_runner import database, models, service

REPO = Path(__file__).resolve().parents[2]
JOB = "nightly_export"
DAY = date(2026, 10, 30)


@pytest.fixture()
def engine(tmp_path):
    engine = database.build_engine(f"sqlite:///{tmp_path / 'jobs.sqlite'}")
    database.ensure_table(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def session(engine):
    with Session(engine) as session:
        yield session


def rows(engine):
    with engine.connect() as connection:
        return connection.execute(text("select job_name, target_date, status, error_message from job_runs order by created_at")).all()


# ---------------------------------------------------------------- the table: the fields of the ticket, and the indexes


def test_the_table_has_the_fields_the_ticket_asks_for(engine):
    columns = {c["name"]: c for c in inspect(engine).get_columns("job_runs")}
    assert set(columns) >= {"id", "job_name", "target_date", "status", "started_at", "finished_at", "error_message", "created_at"}
    assert not columns["target_date"]["nullable"]  # mandatory: it is what makes the job idempotent per day
    assert not columns["status"]["nullable"] and not columns["job_name"]["nullable"] and not columns["created_at"]["nullable"]
    assert columns["started_at"]["nullable"] and columns["finished_at"]["nullable"] and columns["error_message"]["nullable"]


def test_the_table_is_called_job_runs_and_is_not_pipeline_runs():
    assert models.JobRunRow.__tablename__ == "job_runs" and models.JobRunRow.__table__.name == "job_runs"
    assert {t.name for t in models.SQLModel.metadata.sorted_tables if t.name.startswith(("job_", "pipeline_"))} == {"job_runs"}  # no pipeline_runs here


def test_there_is_an_index_on_job_name_and_target_date_and_it_is_not_unique(engine):
    indexes = {i["name"]: i for i in inspect(engine).get_indexes("job_runs")}
    index = indexes["ix_job_runs_job_name_target_date"]
    assert index["column_names"] == ["job_name", "target_date"] and not index["unique"]


def test_the_status_can_only_be_one_of_the_four_states(session):
    session.add(models.JobRunRow(job_name=JOB, target_date=DAY, status="zombie"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_a_new_run_is_pending_and_exists_before_any_work(session, engine):
    run = service.create_job_run(session, JOB, DAY)
    assert run.status == "pending" and run.started_at is None and run.finished_at is None and run.error_message is None
    assert rows(engine) == [(JOB, "2026-10-30", "pending", None)]


# ---------------------------------------------------------------- the transitions: pending -> processing -> completed | failed


def test_pending_to_processing_to_completed_and_the_timestamps_say_when(session):
    run = service.create_job_run(session, JOB, DAY)
    started = service.start_processing(session, run.id)
    assert started.status == "processing" and started.started_at is not None and started.finished_at is None
    done = service.complete(session, run.id)
    assert done.status == "completed" and done.finished_at >= done.started_at and done.error_message is None


def test_processing_to_failed_keeps_the_error_message(session):
    run = service.create_job_run(session, JOB, DAY)
    service.start_processing(session, run.id)
    assert service.fail(session, run.id, "ConnectionError: database unreachable") is True
    session.expire_all()
    row = session.get(models.JobRunRow, run.id)
    assert row.status == "failed" and row.error_message == "ConnectionError: database unreachable" and row.finished_at is not None


def test_a_pending_run_can_fail_too(session):
    run = service.create_job_run(session, JOB, DAY)
    assert service.fail(session, run.id, "never started") is True


def test_the_transitions_that_the_machine_does_not_have_are_refused(session):
    run = service.create_job_run(session, JOB, DAY)
    with pytest.raises(service.InvalidTransition):
        service.complete(session, run.id)  # pending -> completed: no, it has to be processing first
    service.start_processing(session, run.id)
    with pytest.raises(service.InvalidTransition):
        service.start_processing(session, run.id)  # processing -> processing
    service.complete(session, run.id)
    with pytest.raises(service.InvalidTransition):
        service.complete(session, run.id)  # completed -> completed
    assert service.fail(session, run.id, "too late") is False  # a finished run is never failed afterwards


def test_a_finished_run_never_changes_state_again(session):
    run = service.create_job_run(session, JOB, DAY)
    service.start_processing(session, run.id)
    service.fail(session, run.id, "first error")
    assert service.fail(session, run.id, "second error") is False
    session.expire_all()
    assert session.get(models.JobRunRow, run.id).error_message == "first error"


def test_the_error_message_never_holds_a_credential(session):
    run = service.create_job_run(session, JOB, DAY)
    service.start_processing(session, run.id)
    service.fail(session, run.id, "could not connect to postgresql://postgres.abc:Sup3rS3cret@aws-0-eu.pooler.supabase.com:6543/postgres: timeout")
    session.expire_all()
    message = session.get(models.JobRunRow, run.id).error_message
    assert "Sup3rS3cret" not in message and "postgres.abc" not in message and "timeout" in message and "aws-0-eu" in message


def test_a_very_long_error_message_is_cut(session):
    run = service.create_job_run(session, JOB, DAY)
    service.start_processing(session, run.id)
    service.fail(session, run.id, "x" * 50_000)
    session.expire_all()
    assert len(session.get(models.JobRunRow, run.id).error_message) == service.MAX_ERROR_LENGTH


# ---------------------------------------------------------------- the questions the script asks


def test_has_processing_lock_is_true_only_while_a_run_is_processing(session):
    assert service.has_processing_lock(session, JOB) is False
    run = service.create_job_run(session, JOB, DAY)
    assert service.has_processing_lock(session, JOB) is False  # pending is not a lock
    service.start_processing(session, run.id)
    assert service.has_processing_lock(session, JOB) is True and service.has_processing_lock(session, "another_job") is False
    service.complete(session, run.id)
    assert service.has_processing_lock(session, JOB) is False  # finishing releases the lock


def test_a_failed_run_releases_the_lock_too(session):
    run = service.create_job_run(session, JOB, DAY)
    service.start_processing(session, run.id)
    service.fail(session, run.id, "boom")
    assert service.has_processing_lock(session, JOB) is False


def test_has_completed_for_date_is_by_day_and_only_for_completed(session):
    run = service.create_job_run(session, JOB, DAY)
    assert service.has_completed_for_date(session, JOB, DAY) is False  # pending
    service.start_processing(session, run.id)
    assert service.has_completed_for_date(session, JOB, DAY) is False  # processing
    service.complete(session, run.id)
    assert service.has_completed_for_date(session, JOB, DAY) is True
    assert service.has_completed_for_date(session, JOB, DAY + timedelta(days=1)) is False  # the completed of one day says nothing of the next
    assert service.has_completed_for_date(session, "another_job", DAY) is False


def test_a_failed_day_is_not_done_and_can_be_tried_again(session):
    first = service.create_job_run(session, JOB, DAY)
    service.start_processing(session, first.id)
    service.fail(session, first.id, "boom")
    assert service.has_completed_for_date(session, JOB, DAY) is False
    second = service.create_job_run(session, JOB, DAY)  # the same day again: allowed, because the (job, day) index is not unique
    service.start_processing(session, second.id)
    service.complete(session, second.id)
    assert service.has_completed_for_date(session, JOB, DAY) is True


def test_every_execution_is_recorded_and_the_latest_comes_first(session):
    for day in (date(2026, 10, 28), date(2026, 10, 29), DAY):
        run = service.create_job_run(session, JOB, day)
        service.start_processing(session, run.id)
        service.complete(session, run.id)
    assert [r.target_date for r in service.list_runs(session, JOB)] == [DAY, date(2026, 10, 29), date(2026, 10, 28)]
    assert service.latest(session, JOB).target_date == DAY and service.latest(session, "nothing") is None


# ---------------------------------------------------------------- THE LOCK: the processing state itself, enforced by the database


def test_the_lock_has_no_table_column_or_file_of_its_own(engine):
    """There is no second mechanism: the only table is job_runs, and the lock is a constraint on its ``status`` column."""
    assert set(inspect(engine).get_table_names()) == {"job_runs"}
    assert {c["name"] for c in inspect(engine).get_columns("job_runs")} == {"id", "job_name", "target_date", "status", "started_at", "finished_at", "error_message", "created_at"}
    with engine.connect() as connection:
        (sql,) = connection.execute(text("select sql from sqlite_master where name = 'uq_job_runs_one_processing_per_job'")).one()
    assert "WHERE status = 'processing'" in sql and "UNIQUE" in sql.upper() and "job_name" in sql


def test_a_second_run_cannot_become_processing_while_the_first_is(session, engine):
    first = service.create_job_run(session, JOB, DAY)
    second = service.create_job_run(session, JOB, DAY)
    service.start_processing(session, first.id)
    with pytest.raises(service.JobAlreadyRunning):
        service.start_processing(session, second.id)
    assert [r[2] for r in rows(engine)] == ["processing", "pending"]  # the refused one did not change


def test_two_different_jobs_do_not_block_each_other(session):
    one = service.create_job_run(session, "nightly_export", DAY)
    other = service.create_job_run(session, "another_job", DAY)
    service.start_processing(session, one.id)
    service.start_processing(session, other.id)  # no error: the lock is per job


def test_releasing_the_lock_lets_the_next_run_in(session):
    first = service.create_job_run(session, JOB, DAY)
    second = service.create_job_run(session, JOB, DAY + timedelta(days=1))
    service.start_processing(session, first.id)
    service.complete(session, first.id)
    service.start_processing(session, second.id)  # no error


def test_the_instance_that_gives_up_leaves_no_trace(session, engine):
    run = service.create_job_run(session, JOB, DAY)
    assert service.discard_pending(session, run.id) is True
    assert rows(engine) == []
    held = service.create_job_run(session, JOB, DAY)
    service.start_processing(session, held.id)
    assert service.discard_pending(session, held.id) is False  # a run that is processing is never discarded
    assert [r[2] for r in rows(engine)] == ["processing"]


def race(make_session, run_ids):
    """Every thread asks to become ``processing`` at the same instant. Returns the outcomes."""
    barrier = threading.Barrier(len(run_ids))
    outcomes: list[str] = []

    def attempt(run_id):
        with make_session() as session:
            barrier.wait(timeout=10)
            try:
                service.start_processing(session, run_id)
                outcomes.append("won")
            except service.JobAlreadyRunning:
                outcomes.append("refused")

    threads = [threading.Thread(target=attempt, args=(run_id,)) for run_id in run_ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    return outcomes


@pytest.mark.parametrize("attempt", range(10))
def test_of_several_runs_that_start_at_the_same_instant_exactly_one_wins(tmp_path, attempt):
    """The case a check-then-act cannot survive: all of them look, all of them see nobody, all of them go. The database lets one in."""
    engine = database.build_engine(f"sqlite:///{tmp_path / f'race-{attempt}.sqlite'}")
    database.ensure_table(engine)
    with Session(engine) as setup:
        run_ids = [service.create_job_run(setup, JOB, DAY).id for _ in range(6)]
    outcomes = race(lambda: Session(engine), run_ids)
    assert sorted(outcomes) == ["refused"] * 5 + ["won"]
    assert [r[2] for r in rows(engine)].count("processing") == 1
    engine.dispose()


# ---------------------------------------------------------------- the zombie that no try/except can catch: a process that is killed


def make_row(engine, status, *, started=None, created=None):
    """A row as a killed process leaves it. Dates are written the way SQLAlchemy writes them in SQLite (UTC, no offset)."""
    def stored(value):
        return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f") if value else None

    run_id = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            text("insert into job_runs (id, job_name, target_date, status, started_at, created_at) values (:id, :job, :day, :status, :started, :created)"),
            {"id": run_id.hex, "job": JOB, "day": DAY.isoformat(), "status": status, "started": stored(started), "created": stored(created or datetime.now(timezone.utc))},
        )
    return run_id


def test_a_processing_run_that_is_too_old_is_closed_as_failed_so_it_cannot_block_every_night(session, engine):
    long_ago = datetime.now(timezone.utc) - timedelta(hours=5)
    make_row(engine, "processing", started=long_ago, created=long_ago)  # its process was killed: it will never write its own failed
    closed = service.mark_stale_as_failed(session, JOB, older_than=timedelta(hours=2))
    assert len(closed) == 1 and service.has_processing_lock(session, JOB) is False
    (_, _, status, message), = rows(engine)
    assert status == "failed" and message.startswith("stale:")


def test_a_recent_processing_run_is_alive_and_is_left_alone(session, engine):
    make_row(engine, "processing", started=datetime.now(timezone.utc) - timedelta(minutes=10))
    assert service.mark_stale_as_failed(session, JOB, older_than=timedelta(hours=2)) == []
    assert service.has_processing_lock(session, JOB) is True


def test_a_pending_run_that_never_started_is_closed_too(session, engine):
    make_row(engine, "pending", created=datetime.now(timezone.utc) - timedelta(hours=5))
    assert len(service.mark_stale_as_failed(session, JOB, older_than=timedelta(hours=2))) == 1
    assert [r[2] for r in rows(engine)] == ["failed"]


def test_the_stale_rule_only_touches_the_job_it_is_asked_about(session, engine):
    long_ago = datetime.now(timezone.utc) - timedelta(hours=5)
    other = make_row(engine, "processing", started=long_ago)
    with engine.begin() as connection:
        connection.execute(text("update job_runs set job_name = 'another_job' where id = :id"), {"id": other.hex})
    assert service.mark_stale_as_failed(session, JOB, older_than=timedelta(hours=2)) == []


# ---------------------------------------------------------------- the reference SQL says the same as the model


SQL = (REPO / "services" / "api" / "job_runner" / "sql" / "001_job_runs.sql").read_text(encoding="utf-8")


def test_the_reference_sql_has_the_same_columns_constraint_and_indexes_as_the_model():
    for column in ("id uuid primary key", "job_name text not null", "target_date date not null", "status varchar(16) not null",
                   "started_at timestamptz", "finished_at timestamptz", "error_message text", "created_at timestamptz not null"):
        assert column in SQL, column
    assert "check (status in ('pending', 'processing', 'completed', 'failed'))" in SQL
    assert "create index if not exists ix_job_runs_job_name_target_date on job_runs (job_name, target_date)" in SQL
    assert "create unique index if not exists uq_job_runs_one_processing_per_job on job_runs (job_name) where status = 'processing'" in SQL
    assert tuple(re.findall(r"'(\w+)'", re.search(r"check \(status in \(([^)]*)\)", SQL).group(1))) == models.STATUSES


def test_the_sql_says_the_lock_is_the_state_and_that_this_is_not_pipeline_runs():
    assert "THIS STATE IS THE LOCK" in SQL and "NOT `reporting.pipeline_runs`" in SQL


# ---------------------------------------------------------------- nothing here needs FastAPI: a job is a process of its own


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    return found


@pytest.mark.parametrize("path", sorted((REPO / "services" / "api" / "job_runner").glob("*.py")) + [REPO / "scripts" / "nightly_export.py"], ids=lambda p: p.name)
def test_no_file_of_the_job_imports_fastapi_or_the_api_application(path):
    assert not (imported_modules(path) & {"fastapi", "starlette", "uvicorn", "main", "apscheduler"}), path


def test_importing_the_job_in_a_fresh_process_loads_no_fastapi():
    import subprocess
    import sys

    code = ("import sys, importlib.util;"
            f"sys.path[:0] = [{str(REPO)!r}, {str(REPO / 'services' / 'api')!r}];"
            f"spec = importlib.util.spec_from_file_location('nightly', {str(REPO / 'scripts' / 'nightly_export.py')!r});"
            "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m);"
            "import job_runner.service, job_runner.database;"
            "loaded = sorted(k for k in sys.modules if k.split('.')[0] in ('fastapi', 'starlette', 'uvicorn'));"
            "print('LOADED:' + ','.join(loaded))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, env={**os.environ, "DATABASE_URL": "sqlite:///x"}, check=False)
    assert out.returncode == 0, out.stderr[-500:]
    assert out.stdout.strip().endswith("LOADED:"), out.stdout


def test_the_api_does_not_start_the_job_in_any_way():
    """The job is started from outside. Nothing in the API runs it, schedules it, or imports it."""
    for path in (REPO / "services" / "api").rglob("*.py"):
        if "job_runner" in path.parts or "tests" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        assert "nightly_export" not in source and "APScheduler" not in source and "repeat_every" not in source, path


# ---------------------------------------------------------------- the same, against a real PostgreSQL (the database of production)

ADMIN = os.environ.get("NIGHTLY_TEST_ADMIN_URL")
needs_postgres = pytest.mark.skipif(not ADMIN, reason="needs a throw-away PostgreSQL: NIGHTLY_TEST_ADMIN_URL=postgresql://postgres:...@localhost:PORT/postgres")


@pytest.fixture()
def postgres():
    from sqlalchemy.engine import make_url

    server = create_engine(make_url(ADMIN.replace("postgresql://", "postgresql+psycopg2://", 1)), isolation_level="AUTOCOMMIT")
    name = f"job_runs_{uuid.uuid4().hex[:8]}"
    with server.connect() as connection:
        connection.execute(text(f"create database {name}"))
    engine = database.build_engine(make_url(server.url).set(database=name).render_as_string(hide_password=False))
    yield engine
    engine.dispose()
    with server.connect() as connection:
        connection.execute(text(f"drop database {name} with (force)"))
    server.dispose()


@needs_postgres
def test_postgres_the_model_creates_the_table_and_the_partial_unique_index(postgres):
    database.ensure_table(postgres)
    database.ensure_table(postgres)  # idempotent
    with postgres.connect() as connection:
        definition = connection.execute(text("select indexdef from pg_indexes where indexname = 'uq_job_runs_one_processing_per_job'")).scalar_one()
    assert "UNIQUE" in definition and "(job_name)" in definition and "status" in definition and "processing" in definition


@needs_postgres
def test_postgres_the_reference_sql_runs_and_gives_a_table_that_the_service_can_use(postgres):
    with postgres.begin() as connection:
        connection.exec_driver_sql(SQL)
        connection.exec_driver_sql(SQL)  # idempotent
    with Session(postgres) as session:
        run = service.create_job_run(session, JOB, DAY)
        service.start_processing(session, run.id)
        other = service.create_job_run(session, JOB, DAY)
        with pytest.raises(service.JobAlreadyRunning):
            service.start_processing(session, other.id)
        service.complete(session, run.id)
        assert service.has_completed_for_date(session, JOB, DAY)


@needs_postgres
@pytest.mark.parametrize("attempt", range(5))
def test_postgres_of_several_runs_that_start_at_the_same_instant_exactly_one_wins(postgres, attempt):
    database.ensure_table(postgres)
    with Session(postgres) as setup:
        run_ids = [service.create_job_run(setup, JOB, DAY).id for _ in range(8)]
    outcomes = race(lambda: Session(postgres), run_ids)
    assert sorted(outcomes) == ["refused"] * 7 + ["won"]
    assert [r[2] for r in rows(postgres)].count("processing") == 1
    with postgres.begin() as connection:
        connection.execute(text("delete from job_runs"))
