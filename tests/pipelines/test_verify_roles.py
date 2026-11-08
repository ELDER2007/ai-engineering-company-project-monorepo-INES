"""``data/pipelines/verify_roles.py``: the check of the two least-privilege roles.

The pure tests need nothing. The ones against a real database need a throw-away PostgreSQL:
    PIPELINE_TEST_ADMIN_URL=postgresql://postgres:...@localhost:PORT/postgres python -m pytest tests/pipelines/test_verify_roles.py
(they create a database of their own inside it and drop it at the end).
"""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from data.pipelines import verify_roles as vr
from data.pipelines.weekly_office_performance import storage

REPO = Path(__file__).resolve().parents[2]
SQL = REPO / "data" / "pipelines" / "weekly_office_performance" / "sql"

# ---------------------------------------------------------------- building the URL of a role (pure)


def test_a_supabase_pooler_user_keeps_its_project_id():
    url = vr.role_url("postgresql://postgres.abcdefg:admin-pw@aws-0-eu.pooler.supabase.com:6543/postgres", "pipeline_reader", "r-pw")
    assert (url.username, url.password, url.host, url.port, url.database) == ("pipeline_reader.abcdefg", "r-pw", "aws-0-eu.pooler.supabase.com", 6543, "postgres")


def test_a_plain_user_gets_no_suffix():
    assert vr.role_url("postgresql://postgres:admin-pw@localhost:5432/postgres", "pipeline_writer", "w-pw").username == "pipeline_writer"


@pytest.mark.parametrize("password", ["a@b:c/d?e#f%g", "con espacios y ñ", "p'ass\"word"])
def test_any_character_of_a_password_survives_the_round_trip(password):
    """The password is data, not text glued into a URL: whatever the person chose works."""
    url = vr.role_url("postgresql://postgres.x:admin-pw@h:6543/postgres", "pipeline_reader", password)
    assert make_url(url.render_as_string(hide_password=False)).password == password


def test_the_administrators_password_is_never_reused():
    url = vr.role_url("postgresql://postgres.x:admin-pw@h:6543/postgres", "pipeline_reader", "r-pw")
    assert "admin-pw" not in url.render_as_string(hide_password=False)


def test_the_checks_never_write_anything():
    """Every statement the script sends is a select or a `delete ... where false`: nothing can change in the database."""
    source = (REPO / "data" / "pipelines" / "verify_roles.py").read_text(encoding="utf-8")
    statements = re.findall(r'f?"((?:select|delete|insert|update|drop|create|alter|truncate|grant)[^"]*)"', source, re.IGNORECASE)
    assert statements, "no statement found"
    for statement in statements:
        lowered = statement.lower()
        assert lowered.startswith("select") or lowered.endswith("where false"), statement


def test_without_a_postgresql_database_there_is_nothing_to_check(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("TELEMETRY_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'x.sqlite'}")
    assert vr.main([]) == 2
    assert "nothing to check" in capsys.readouterr().err


# ---------------------------------------------------------------- against a real PostgreSQL

ADMIN = os.environ.get("PIPELINE_TEST_ADMIN_URL")
needs_postgres = pytest.mark.skipif(not ADMIN, reason="needs a throw-away PostgreSQL: PIPELINE_TEST_ADMIN_URL=postgresql://postgres:...@localhost:PORT/postgres")


@pytest.fixture()
def database():
    """A database of its own, with the telemetry table and the reporting schema, and the roles of 002_roles.sql."""
    admin_server = create_engine(make_url(ADMIN.replace("postgresql://", "postgresql+psycopg2://", 1)), isolation_level="AUTOCOMMIT")
    name = f"verify_roles_{uuid.uuid4().hex[:8]}"
    with admin_server.connect() as connection:
        connection.execute(text(f"create database {name}"))
    url = make_url(admin_server.url).set(database=name)
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text("create table public.telemetry_events (event_id text primary key, event_type text)"))
        connection.execute(text("insert into public.telemetry_events values ('a', 'x'), ('b', 'y'), ('c', 'z')"))
    storage.create_reporting_schema(admin)
    script = (SQL / "002_roles.sql").read_text(encoding="utf-8").replace("CHANGE-ME-reader-password", "reader-pw").replace("CHANGE-ME-writer-password", "writer-pw")
    # roles are cluster-wide: unique names per test run keep tests apart
    suffix = uuid.uuid4().hex[:6]
    script = re.sub(r"\bpipeline_reader\b", f"pipeline_reader_{suffix}", script)  # \b: the policy name pipeline_reader_select stays as it is
    script = re.sub(r"\bpipeline_writer\b", f"pipeline_writer_{suffix}", script)
    with admin.connect() as connection:
        connection.exec_driver_sql(script)
    yield url, admin, suffix
    admin.dispose()
    with admin_server.connect() as connection:
        connection.execute(text(f"drop database {name} with (force)"))
        for role in (f"pipeline_reader_{suffix}", f"pipeline_writer_{suffix}"):
            connection.execute(text(f"drop role if exists {role}"))
    admin_server.dispose()


@pytest.fixture()
def roles(monkeypatch, database):
    """The checker uses the fixed role names; point them at this test's roles."""
    url, admin, suffix = database
    monkeypatch.setattr(vr, "READER", f"pipeline_reader_{suffix}")
    monkeypatch.setattr(vr, "WRITER", f"pipeline_writer_{suffix}")
    return url, admin


@needs_postgres
def test_the_roles_of_the_script_pass_every_check(roles):
    url, _ = roles
    checks = vr.check_roles(url, "reader-pw", "writer-pw")
    assert all(c.ok for c in checks), [str(c) for c in checks if not c.ok]
    assert any("3 events" in c.text for c in checks)  # the reader really reads the telemetry


@needs_postgres
def test_a_wrong_password_is_reported_and_nothing_else_is_assumed(roles):
    url, _ = roles
    checks = vr.check_roles(url, "not-the-password", "writer-pw")
    assert not all(c.ok for c in checks) and any("could not connect" in c.text for c in checks)


@needs_postgres
def test_a_writer_that_can_read_the_telemetry_is_caught(roles):
    url, admin = roles
    with admin.connect() as connection:
        connection.execute(text(f"grant select on public.telemetry_events to {vr.WRITER}"))
    failed = [c.text for c in vr.check_roles(url, "reader-pw", "writer-pw") if not c.ok]
    assert failed == [f"{vr.WRITER} CANNOT read the telemetry"]


@needs_postgres
def test_a_reader_that_can_write_is_caught(roles):
    url, admin = roles
    with admin.connect() as connection:
        connection.execute(text(f"grant delete on public.telemetry_events to {vr.READER}"))
    failed = [c.text for c in vr.check_roles(url, "reader-pw", "writer-pw") if not c.ok]
    assert failed == [f"{vr.READER} CANNOT write in the telemetry"]


@needs_postgres
def test_row_level_security_without_a_policy_is_caught_instead_of_reading_zero_rows_silently(roles):
    """The dangerous case: RLS on and no policy. The reader connects, reads... nothing, and gets no error."""
    url, admin = roles
    with admin.connect() as connection:
        connection.execute(text("alter table public.telemetry_events enable row level security"))
        connection.execute(text(f"drop policy pipeline_reader_select on public.telemetry_events"))
    checks = vr.check_roles(url, "reader-pw", "writer-pw")
    failed = [c.text for c in checks if not c.ok]
    assert len(failed) == 1 and "row level security is ON" in failed[0] and "WITHOUT a policy" in failed[0]
    assert any("0 events" in c.text for c in checks)  # and the 0 shows, which is exactly the silent failure


@needs_postgres
def test_with_row_level_security_and_the_policy_every_check_passes(roles):
    url, admin = roles
    with admin.connect() as connection:
        connection.execute(text("alter table public.telemetry_events enable row level security"))
    checks = vr.check_roles(url, "reader-pw", "writer-pw")
    assert all(c.ok for c in checks), [str(c) for c in checks if not c.ok]
    assert any("3 events" in c.text for c in checks) and any("has a policy" in c.text for c in checks)


@needs_postgres
@pytest.mark.usefixtures("prefect_runtime")
def test_run_runs_the_real_pipeline_with_the_two_roles_and_the_report_is_written(roles, monkeypatch, capsys):
    """The whole thing: the passwords are asked for, the roles are checked, and the pipeline reads with the reader and writes
    the report with the writer, in one process, with nothing exported."""
    from data.pipelines.weekly_office_performance.seed_telemetry import seed_telemetry

    url, admin = roles
    with admin.connect() as connection:
        connection.execute(text("drop table public.telemetry_events"))
    seed_telemetry(admin)  # the real table, with the demo events of the week 2026-10-26
    with admin.connect() as connection:
        connection.execute(text(f"grant select on public.telemetry_events to {vr.READER}"))
    monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
    for name in ("TELEMETRY_DATABASE_URL", "REPORTING_DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    asked = []
    monkeypatch.setattr(vr.getpass, "getpass", lambda prompt: asked.append(prompt) or ("reader-pw" if vr.READER in prompt else "writer-pw"))

    assert vr.main(["--run", "--week-start", "2026-10-26"]) == 0
    out = capsys.readouterr().out
    assert len(asked) == 2 and "All the checks passed" in out and "state='Completed'" in out
    assert "reader-pw" not in out and "writer-pw" not in out  # nothing secret is ever printed
    with admin.connect() as connection:
        assert connection.execute(text("select count(*) from reporting.weekly_office_program_performance")).scalar() == 5
        assert connection.execute(text("select state from reporting.pipeline_runs order by started_at desc limit 1")).scalar() == "Completed"
    for name in ("TELEMETRY_DATABASE_URL", "REPORTING_DATABASE_URL"):  # they were set for this process by the script: not our problem here
        monkeypatch.delenv(name, raising=False)


@needs_postgres
def test_run_does_not_run_the_pipeline_when_a_check_fails(roles, monkeypatch, capsys):
    url, admin = roles
    with admin.connect() as connection:
        connection.execute(text(f"grant select on public.telemetry_events to {vr.WRITER}"))  # the writer must not read telemetry
    monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
    monkeypatch.setattr(vr.getpass, "getpass", lambda prompt: "reader-pw" if vr.READER in prompt else "writer-pw")
    from data.pipelines import pipeline

    monkeypatch.setattr(pipeline, "main", lambda *a, **k: pytest.fail("the pipeline ran although a check failed"))
    assert vr.main(["--run"]) == 1
    assert "FALLA" in capsys.readouterr().out

