"""Fixtures of the tests of the background job (``scripts/nightly_export.py`` and ``services/api/job_runner/``).

Run them from the repository root:      python -m pytest tests/background_processes
"""

from __future__ import annotations

import importlib.util
import logging
import os
import signal
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# Set BEFORE anything imports the API's config: ``core.config`` reads services/api/.env when it is imported, and that file may hold the
# REAL database of whoever runs the tests. With DATABASE_URL already set, the file does not override it. No test can reach a real database.
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp(prefix='nightly-tests-')}/never-used.sqlite"
os.environ["PIPELINE_ENV_FILE"] = "/nonexistent/.env"  # the pipeline (a subprocess of some tests) must not read it either
# The pipeline reads its two own variables before DATABASE_URL, and ``services/api/.env`` may define them (the least-privilege roles of the
# real database). Removing them is NOT enough: ``core.config`` would load them from the file when it is imported. They must be SET, to
# empty (``load_dotenv`` never overrides a variable that exists, and the pipeline reads an empty one as "not set").
for _name in ("TELEMETRY_DATABASE_URL", "REPORTING_DATABASE_URL"):
    os.environ[_name] = ""
for _name in ("TARGET_DATE", "NIGHTLY_PIPELINE_COMMAND"):
    os.environ.pop(_name, None)
sys.path[:0] = [str(REPO), str(REPO / "services" / "api")]

import pytest  # noqa: E402


def load_script():
    """``scripts/nightly_export.py`` as a module (``scripts/`` is a folder of scripts, not a package)."""
    spec = importlib.util.spec_from_file_location("nightly_export_under_test", REPO / "scripts" / "nightly_export.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def script():
    return load_script()


DATABASE_VARIABLES = ("DATABASE_URL", "TELEMETRY_DATABASE_URL", "REPORTING_DATABASE_URL")


def assert_no_real_database() -> None:
    """The guard. If any variable that a job or the pipeline would read points at something that is not a throw-away SQLite file, the
    test stops BEFORE it can touch it. (The tests of PostgreSQL pass their own URL explicitly and never through these variables.)"""
    for name in DATABASE_VARIABLES:
        value = os.environ.get(name, "")
        assert value == "" or value.startswith("sqlite:///"), f"{name} points at a real database: a test must never touch it"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    """Every test: its own database file, its own data folder, and the logger as the script leaves it by default."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'app.sqlite'}")
    monkeypatch.setenv("PIPELINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TELEMETRY_DATABASE_URL", "")
    monkeypatch.setenv("REPORTING_DATABASE_URL", "")
    assert_no_real_database()
    monkeypatch.delenv("TARGET_DATE", raising=False)
    monkeypatch.delenv("NIGHTLY_PIPELINE_COMMAND", raising=False)
    sigterm = signal.getsignal(signal.SIGTERM)  # main() installs its own handler: do not leave it in the test process
    yield
    signal.signal(signal.SIGTERM, sigterm)
    logger = logging.getLogger("nightly_export")  # a test that called main() configured it: put it back for caplog
    logger.handlers[:] = []
    logger.propagate = True
    logger.setLevel(logging.NOTSET)
