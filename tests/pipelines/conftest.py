"""Fixtures of the pipeline's own tests. They do not need the API: only ``data/``.

Run them from the repository root:      python -m pytest tests/pipelines
or from services/api (its pytest setup): python -m pytest ../../tests/pipelines
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Set before anything imports the pipeline: no retry waits in tests, and never read a developer's real services/api/.env.
os.environ.setdefault("PIPELINE_RETRIES", "0")
os.environ.setdefault("PIPELINE_ENV_FILE", "/nonexistent/.env")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # the repository root, so `data.` can be imported

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _prefect(tmp_path_factory):
    """Prefect's own throw-away database, and its cached results in a folder of this session (its test harness isolates the
    database but not the result storage, which would otherwise be ``~/.prefect/storage`` and leak between sessions)."""
    from prefect.settings import PREFECT_LOCAL_STORAGE_PATH, temporary_settings
    from prefect.testing.utilities import prefect_test_harness

    with temporary_settings({PREFECT_LOCAL_STORAGE_PATH: str(tmp_path_factory.mktemp("prefect-results"))}):
        with prefect_test_harness():
            yield


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    """The raw and eval files of the tests go to a temp folder, never to the repo's data/."""
    monkeypatch.setenv("PIPELINE_DATA_DIR", str(tmp_path / "data"))
    return tmp_path / "data"


@pytest.fixture()
def engines(tmp_path):
    """``(source, target)``: a database with demo ``telemetry_events`` and one for the ``reporting`` schema, both throw-away."""
    from data.pipelines.weekly_office_performance import storage
    from data.pipelines.weekly_office_performance.seed_telemetry import seed_telemetry

    source = storage.build_engine(f"sqlite:///{tmp_path / 'telemetry.sqlite'}")
    target = storage.build_engine(f"sqlite:///{tmp_path / 'reporting.sqlite'}")
    seed_telemetry(source)
    storage.create_reporting_schema(target)
    yield source, target
    source.dispose()
    target.dispose()
