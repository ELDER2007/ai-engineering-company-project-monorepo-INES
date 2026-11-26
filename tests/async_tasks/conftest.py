"""Fixtures of the tests of the asynchronous tasks (ticket DEV-55): ``services/celery_app.py`` and ``services/api/async_tasks/``.

Run them from the repository root:      python -m pytest tests/async_tasks

Three kinds of tests live here:
* ``test_tasks.py``               the logic of the tasks (retries, back-off, dead-letter queue, logs), in-process, no Redis.
* ``test_infrastructure.py``      what docker-compose.yml, the Dockerfile and the docs say (static, no Docker needed).
* ``test_integration_redis.py``   a REAL Redis in Docker and a REAL worker process. Skipped when Docker is not available.
The HTTP endpoints are tested in ``services/api/tests/test_async_tasks_api.py``, next to the other endpoint tests.
"""

from __future__ import annotations

import os
import socket
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


# Set BEFORE anything imports the API's config or the Celery app (both read the environment when they are imported). services/api/.env may hold
# the REAL database of whoever runs the tests: with DATABASE_URL already set, the file does not override it. No test can reach a real database.
REDIS_PORT = _free_port()  # the Redis of these tests (integration) lives on a free port: it never collides with the one of docker-compose
os.environ["REDIS_URL"] = f"redis://127.0.0.1:{REDIS_PORT}/0"
os.environ.pop("REDIS_RESULT_URL", None)
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp(prefix='async-tests-')}/never-used.sqlite"
os.environ["PIPELINE_ENV_FILE"] = "/nonexistent/.env"
for _name in ("TELEMETRY_DATABASE_URL", "REPORTING_DATABASE_URL"):
    os.environ[_name] = ""  # SET to empty, not removed: load_dotenv never overrides a variable that exists
os.environ["CELERY_DEMO_TASKS"] = "1"  # the tests use the demo tasks (they are the ones that fail and succeed on demand)
os.environ["ASYNC_RETRY_BASE_SECONDS"] = "0.2"
sys.path[:0] = [str(REPO), str(REPO / "services" / "api")]

import pytest  # noqa: E402

DATABASE_VARIABLES = ("DATABASE_URL", "TELEMETRY_DATABASE_URL", "REPORTING_DATABASE_URL")


def assert_no_real_database() -> None:
    for name in DATABASE_VARIABLES:
        value = os.environ.get(name, "")
        assert value == "" or value.startswith("sqlite:///"), f"{name} points at a real database: a test must never touch it"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    """Every test: its own database file (where the dead-letter queue is written)."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'app.sqlite'}")
    monkeypatch.setenv("PIPELINE_DATA_DIR", str(tmp_path / "data"))
    assert_no_real_database()
    yield
