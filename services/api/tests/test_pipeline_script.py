"""Phase 4: the pipeline is a command-line script. ``python data/pipelines/pipeline.py`` must run end to end, and the
reporting frequency and the command must be documented in the design document."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
PIPELINE = REPO / "data" / "pipelines" / "pipeline.py"
DESIGN = (REPO / "data" / "pipelines" / "PIPELINE_DESIGN.md").read_text(encoding="utf-8")


def clean_env(tmp_path, **extra):
    """A fresh checkout: no database configured, no local telemetry, outputs in a temp folder."""
    env = {k: v for k, v in os.environ.items() if k not in {"DATABASE_URL", "TELEMETRY_DATABASE_URL", "REPORTING_DATABASE_URL", "PIPELINE_ENVIRONMENT"}}
    env.update(PIPELINE_ENV_FILE=str(tmp_path / "no.env"), PIPELINE_LOCAL_DB=str(tmp_path / "no-such-app.sqlite"), PIPELINE_DEMO_DB=str(tmp_path / "demo.sqlite"),
               PIPELINE_DATA_DIR=str(tmp_path / "data"), **extra)
    return env


def run_script(env, *args, cwd=REPO):
    return subprocess.run([sys.executable, str(PIPELINE), *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=300)


def test_the_file_has_a_main_block_that_calls_the_command_line_entry_point():
    tree = ast.parse(PIPELINE.read_text(encoding="utf-8"))
    guard = next(n for n in tree.body if isinstance(n, ast.If) and "__name__" in ast.dump(n.test) and "__main__" in ast.dump(n.test))
    assert "main" in ast.dump(guard)  # `sys.exit(main())`


def test_the_exact_command_runs_without_errors_on_a_fresh_checkout(tmp_path):
    """`python data/pipelines/pipeline.py`, no arguments, nothing configured."""
    out = run_script(clean_env(tmp_path))
    assert out.returncode == 0, out.stderr[-1200:]
    assert "state='Completed'" in out.stdout
    assert "DEMO" in out.stderr  # it says it is on demo data, it does not do it silently
    assert not (tmp_path / "no-such-app.sqlite").exists()  # and asking for local telemetry created no file
    assert list((tmp_path / "data" / "eval").glob("run_*.json"))  # the run left its validation report


def test_the_exact_command_runs_from_any_folder(tmp_path):
    elsewhere = tmp_path / "somewhere" / "else"
    elsewhere.mkdir(parents=True)
    out = run_script(clean_env(tmp_path), cwd=elsewhere)
    assert out.returncode == 0, out.stderr[-1200:]


def test_with_a_database_configured_a_real_failure_is_not_hidden_behind_the_demo(tmp_path):
    """A configured database without telemetry is a real problem in production: exit 1, never the demo."""
    empty = tmp_path / "configured-but-empty.sqlite"
    out = run_script(clean_env(tmp_path, DATABASE_URL=f"sqlite:///{empty}"), "--week-start", "2026-10-26")
    assert out.returncode == 1
    assert "FAILED" in out.stderr and "DEMO" not in out.stderr


def test_a_local_database_that_already_has_telemetry_is_used_not_the_demo(tmp_path):

    from data.pipelines.weekly_office_performance import seed_telemetry, storage

    local = tmp_path / "app.sqlite"
    engine = storage.build_engine(f"sqlite:///{local}")
    seed_telemetry.seed_telemetry(engine)  # the API's own file now holds telemetry_events
    engine.dispose()
    env = clean_env(tmp_path)
    env["PIPELINE_LOCAL_DB"] = str(local)
    out = run_script(env, "--week-start", "2026-10-26")
    assert out.returncode == 0, out.stderr[-1200:]
    assert "DEMO" not in out.stderr and "demo:" not in out.stdout


def test_asking_whether_local_telemetry_exists_never_creates_the_file(tmp_path, monkeypatch):
    from data.pipelines.weekly_office_performance import storage

    monkeypatch.setenv("PIPELINE_LOCAL_DB", str(tmp_path / "ghost.sqlite"))
    assert storage.local_telemetry_available() is False
    assert not (tmp_path / "ghost.sqlite").exists()
    (tmp_path / "ghost.sqlite").write_bytes(b"")  # an empty file is not telemetry either
    assert storage.local_telemetry_available() is False


def test_the_database_counts_as_configured_only_through_the_environment(monkeypatch):
    from data.pipelines.weekly_office_performance import storage

    for name in ("DATABASE_URL", "TELEMETRY_DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    assert storage.database_configured() is False
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
    assert storage.database_configured() is True


# ---------------------------------------------------------------- documented in the design document


def test_the_design_document_states_the_weekly_frequency_and_the_cron_times():
    assert "Ciclo de reporting" in DESIGN and "semanal" in DESIGN.lower()
    assert "`0 5 * * 1`" in DESIGN and "lunes 05:00 UTC" in DESIGN  # the scheduled run
    assert "`0 5 * * 4`" in DESIGN and "jueves 05:00 UTC" in DESIGN  # the correction run


def test_the_design_document_gives_the_command_to_run_it():
    assert "python data/pipelines/pipeline.py" in DESIGN
    assert "python data/pipelines/pipeline.py --trigger scheduled" in DESIGN
    assert "pipeline.py" in PIPELINE.read_text(encoding="utf-8").split('"""')[1]  # and the script documents itself at the top
    assert "0 5 * * 1" in PIPELINE.read_text(encoding="utf-8").split('"""')[1]


def test_the_pipeline_reads_the_same_env_file_as_the_api(tmp_path, monkeypatch):
    """If services/api/.env holds the DATABASE_URL, the API uses that database: the pipeline must see it too, not silently run on the demo."""
    from data.pipelines.weekly_office_performance import storage

    env_file = tmp_path / "api.env"
    env_file.write_text("DATABASE_URL=postgresql://user:secret@db.example.com:6543/postgres\n")
    monkeypatch.setenv("PIPELINE_ENV_FILE", str(env_file))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TELEMETRY_DATABASE_URL", raising=False)
    storage.load_api_env.cache_clear()
    try:
        assert storage.database_configured() is True
        assert storage.database_url().startswith("postgresql+psycopg2://user:secret@db.example.com")
    finally:
        monkeypatch.delenv("DATABASE_URL", raising=False)  # what load_dotenv put into the process
        storage.load_api_env.cache_clear()


def test_a_variable_already_in_the_environment_wins_over_the_env_file(tmp_path, monkeypatch):
    from data.pipelines.weekly_office_performance import storage

    env_file = tmp_path / "api.env"
    env_file.write_text("DATABASE_URL=sqlite:///from-file.sqlite\n")
    monkeypatch.setenv("PIPELINE_ENV_FILE", str(env_file))
    monkeypatch.setenv("DATABASE_URL", "sqlite:///from-environment.sqlite")
    storage.load_api_env.cache_clear()
    try:
        assert storage.database_url() == "sqlite:///from-environment.sqlite"
    finally:
        storage.load_api_env.cache_clear()
