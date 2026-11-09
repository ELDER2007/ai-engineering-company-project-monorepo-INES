"""``python data/pipelines/serve_demo.py``: the API on the pipeline's demo database, so ``/reporting`` shows numbers on a clean clone.

The last test starts it for real, as a reviewer would: a new process, no PYTHONPATH, no pytest. It never creates a user (the API's user store lives
in the repository folder) and it never touches a real database: every database variable of the child is the demo file.
"""

from __future__ import annotations

import os
import signal
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from data.pipelines import serve_demo
from data.pipelines.weekly_office_performance import storage

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "data" / "pipelines" / "serve_demo.py"
DEMO = "sqlite:////tmp/some/demo.sqlite"


# ---------------------------------------------------------------- the environment of the API: nothing real can be reached


def test_every_database_variable_of_the_api_points_at_the_demo_file_even_if_the_environment_had_a_real_one():
    real = {"DATABASE_URL": "postgresql://postgres:secret@db.example.com:5432/postgres", "TELEMETRY_DATABASE_URL": "postgresql://reader@x/y", "OTHER": "kept"}
    env = serve_demo.build_environment(real, DEMO)
    assert env["DATABASE_URL"] == env["REPORTING_DATABASE_URL"] == env["TELEMETRY_DATABASE_URL"] == DEMO
    assert env["OTHER"] == "kept" and real["DATABASE_URL"].startswith("postgresql://")  # the caller's mapping is not modified


def test_the_demo_login_is_set_unless_the_person_chose_another_one():
    assert serve_demo.build_environment({}, DEMO)["AUTH_INITIAL_EMAIL"] == serve_demo.DEMO_EMAIL
    chosen = serve_demo.build_environment({"AUTH_INITIAL_EMAIL": "me@example.com", "AUTH_INITIAL_PASSWORD": "my-own-password-1"}, DEMO)
    assert (chosen["AUTH_INITIAL_EMAIL"], chosen["AUTH_INITIAL_PASSWORD"]) == ("me@example.com", "my-own-password-1")


def test_an_empty_login_is_respected_so_no_user_is_created():
    env = serve_demo.build_environment({"AUTH_INITIAL_EMAIL": "", "AUTH_INITIAL_PASSWORD": ""}, DEMO)
    assert env["AUTH_INITIAL_EMAIL"] == "" and "use an account that already exists" in serve_demo.banner(env, "127.0.0.1", 8000)


def test_the_banner_says_where_to_go_how_to_log_in_and_what_to_expect():
    text = serve_demo.banner(serve_demo.build_environment({}, DEMO), "127.0.0.1", 8010)
    assert "http://127.0.0.1:8010/docs" in text and "demo@example.com / demo-password-123" in text
    assert "five rows" in text and "2026-10-26" in text and "no real database is used" in text


# ---------------------------------------------------------------- is there a computed week already?


def test_a_database_that_does_not_exist_has_no_computed_week_and_asking_creates_nothing(tmp_path):
    url = f"sqlite:///{tmp_path / 'demo.sqlite'}"
    assert serve_demo.has_computed_week(url) is False
    assert not (tmp_path / "demo.sqlite").exists() and not (tmp_path / "demo.sqlite.reporting").exists()  # SQLite would have created them had it connected


def test_a_database_with_a_computed_week_is_recognised(tmp_path):
    url = f"sqlite:///{tmp_path / 'demo.sqlite'}"
    engine = storage.build_engine(url)
    storage.create_reporting_schema(engine)
    assert serve_demo.has_computed_week(url) is False  # the tables exist, but empty
    with engine.begin() as connection:
        connection.execute(storage.weekly_performance.insert(), {
            "id": uuid4(), "office": "valencia", "programme_id": "ventas-b2b", "week_start": date(2026, 10, 26), "total_material_cost": Decimal("1.00"),
            "kits_delivered_count": 1, "shortage_events_count": 0, "cost_variance_events_count": 0, "currency": "EUR", "computed_at": datetime.now(timezone.utc)})
    engine.dispose()
    assert serve_demo.has_computed_week(url) is True


# ---------------------------------------------------------------- the command line


def run_check(tmp_path: Path, cwd: Path) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "DATABASE_URL", "TELEMETRY_DATABASE_URL", "REPORTING_DATABASE_URL")}
    env["PIPELINE_DEMO_DB"] = str(tmp_path / "demo.sqlite")
    return subprocess.run([sys.executable, str(SCRIPT), "--check", "--port", "8123"], cwd=cwd, env=env, capture_output=True, text=True, timeout=120, check=False)


def test_check_says_what_it_would_do_from_any_folder_and_starts_and_writes_nothing(tmp_path):
    elsewhere = tmp_path / "somewhere" / "else"
    elsewhere.mkdir(parents=True)
    out = run_check(tmp_path, elsewhere)
    assert out.returncode == 0, out.stderr[-600:]
    assert "has none: it would run the pipeline with --demo first" in out.stdout and "--port 8123" in out.stdout
    assert "nothing else would be touched" in out.stdout
    assert not (tmp_path / "demo.sqlite").exists() and not (tmp_path / "demo.sqlite.reporting").exists()


def test_the_script_has_a_shebang_and_a_main_guard():
    source = SCRIPT.read_text(encoding="utf-8")
    assert source.startswith("#!/usr/bin/env python3") and 'if __name__ == "__main__":' in source


# ---------------------------------------------------------------- the real thing, started the way a reviewer starts it


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_started_for_real_it_computes_the_demo_week_and_the_api_serves_the_reporting_endpoints(tmp_path):
    port = free_port()
    demo = tmp_path / "demo.sqlite"
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "DATABASE_URL", "TELEMETRY_DATABASE_URL", "REPORTING_DATABASE_URL")}
    env.update(PIPELINE_DEMO_DB=str(demo), PIPELINE_RETRIES="0", PIPELINE_ENV_FILE="/nonexistent/.env", PREFECT_LOCAL_STORAGE_PATH=str(tmp_path / "prefect"),
               PIPELINE_DATA_DIR=str(tmp_path / "data"), AUTH_INITIAL_EMAIL="", AUTH_INITIAL_PASSWORD="")  # no user: this test must not write the user store
    process = subprocess.Popen([sys.executable, str(SCRIPT), "--port", str(port)], cwd=tmp_path, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                               start_new_session=True)
    try:
        deadline, up = time.monotonic() + 180, False
        while time.monotonic() < deadline and process.poll() is None and not up:
            try:
                up = urllib.request.urlopen(f"http://127.0.0.1:{port}/docs", timeout=2).status == 200
            except OSError:
                time.sleep(1)
        assert up, "the API did not come up"
        paths = urllib.request.urlopen(f"http://127.0.0.1:{port}/openapi.json", timeout=10).read().decode()
        assert "/reporting/weekly-office-program-performance" in paths and "/reporting/pipeline-runs/latest" in paths
        with sqlite3.connect(demo) as connection:  # the pipeline computed the week into the demo file, five rows, and nothing else was touched
            connection.execute(f"attach database '{demo}.reporting' as reporting")
            rows = connection.execute("select office, programme_id from reporting.weekly_office_program_performance order by 1, 2").fetchall()
            run = connection.execute("select state, trigger from reporting.pipeline_runs").fetchall()
        assert len(rows) == 5 and {office for office, _ in rows} == {"miami", "valencia"}
        assert run == [("Completed", "manual")]
        assert serve_demo.has_computed_week(f"sqlite:///{demo}") is True  # a second start would not compute it again
    finally:
        with_group = os.getpgid(process.pid)
        os.killpg(with_group, signal.SIGTERM)
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            os.killpg(with_group, signal.SIGKILL)
    assert process.poll() is not None
