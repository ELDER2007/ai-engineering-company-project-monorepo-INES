"""What the infrastructure of the task queue says (ticket DEV-55): ``docker-compose.yml``, the Dockerfile, the dependencies and the docs.

Static: it reads files, it needs no Docker and no Redis. The same stack RUNNING is tested in ``test_integration_redis.py``.

Run:  python -m pytest tests/async_tasks/test_infrastructure.py
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
COMPOSE = yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))
SERVICES = COMPOSE["services"]
DOCKERFILE = (REPO / "services" / "Dockerfile").read_text(encoding="utf-8")
REQUIREMENTS = (REPO / "services" / "api" / "requirements.txt").read_text(encoding="utf-8")
PYPROJECT = (REPO / "services" / "api" / "pyproject.toml").read_text(encoding="utf-8")
README = (REPO / "README.md").read_text(encoding="utf-8")
README_ES = (REPO / "README.es.md").read_text(encoding="utf-8")
ENV_EXAMPLE = (REPO / ".env.example").read_text(encoding="utf-8")


def command_of(service: str) -> list[str]:
    return [str(part) for part in SERVICES[service]["command"]]


# ---------------------------------------------------------------- Redis


def test_redis_is_the_official_image_on_the_standard_port_exposed_to_this_machine_only():
    redis = SERVICES["redis"]
    assert re.fullmatch(r"redis:\d+(\.\d+)*(-alpine)?", redis["image"])  # the official image, a pinned version: never ``latest``
    (port,) = redis["ports"]
    assert port.endswith(":6379") and port.startswith("127.0.0.1:")  # 6379, and not reachable from outside: Redis has no password here


def test_redis_has_a_fixed_memory_and_refuses_writes_instead_of_deleting_queued_tasks():
    command = command_of("redis")
    assert command[command.index("--maxmemory-policy") + 1] == "noeviction"
    assert command[command.index("--maxmemory") + 1] != "0" and "--maxmemory" in command  # ``noeviction`` without a limit never refuses anything
    assert command[command.index("--appendonly") + 1] == "yes"  # the queue survives a restart of Redis


def test_redis_keeps_its_data_in_a_volume_and_has_a_healthcheck():
    assert "redis-data:/data" in SERVICES["redis"]["volumes"] and "redis-data" in COMPOSE["volumes"]
    assert SERVICES["redis"]["healthcheck"]["test"] == ["CMD", "redis-cli", "ping"]


# ---------------------------------------------------------------- REDIS_URL: one variable, the same Redis for everyone


def test_the_api_the_worker_and_flower_connect_to_the_same_redis_through_REDIS_URL():
    urls = {name: SERVICES[name]["environment"]["REDIS_URL"] for name in ("api", "worker", "flower")}
    assert len(set(urls.values())) == 1  # one value, not three that can drift apart
    assert "redis://redis:6379/0" in urls["api"]  # by service name inside the network, never localhost


def test_no_url_of_redis_is_written_in_the_code_of_the_tasks():
    for path in [REPO / "services" / "celery_app.py", *(REPO / "services" / "api" / "async_tasks").glob("*.py")]:
        text = path.read_text(encoding="utf-8")
        urls = re.findall(r"redis://[^\s\"')]+", text)
        assert all(url.startswith("redis://localhost") or "host" in url or "queue.internal" in url or "results.internal" in url for url in urls), (path, urls)


# ---------------------------------------------------------------- the worker: a process of its own


def test_the_worker_is_a_service_of_its_own_that_runs_celery_and_not_uvicorn():
    worker = SERVICES["worker"]
    command = command_of("worker")
    assert command[:4] == ["celery", "-A", "services.celery_app", "worker"]
    assert not any("uvicorn" in part for part in command)  # not inside the process of FastAPI
    assert "-E" in command and any(part.startswith("--loglevel") for part in command)  # events for Flower; INFO for the log lines
    assert worker["working_dir"] == "/app"


def test_the_worker_waits_for_redis_but_the_api_does_not():
    assert SERVICES["worker"]["depends_on"]["redis"]["condition"] == "service_healthy"
    assert "redis" not in SERVICES["api"].get("depends_on", {})  # the API starts, and serves everything else, without Redis
    assert "worker" not in SERVICES["api"].get("depends_on", {}) and "api" not in SERVICES["worker"].get("depends_on", {})  # independent lifecycles


def test_the_worker_finishes_the_task_it_is_running_when_it_is_stopped():
    assert SERVICES["worker"]["stop_grace_period"] in ("2m", "120s")  # SIGTERM = warm shutdown; Docker would kill at 10 s otherwise
    assert SERVICES["worker"]["healthcheck"]["test"][1].startswith("celery -A services.celery_app inspect ping")


def test_the_worker_runs_one_task_at_a_time_by_default():
    """Each pipeline run starts its own Prefect server: two at once in one container choke each other (measured)."""
    assert "${CELERY_CONCURRENCY:-1}" in " ".join(command_of("worker"))


def test_the_demo_tasks_are_off_by_default():
    assert SERVICES["worker"]["environment"]["CELERY_DEMO_TASKS"] == "${CELERY_DEMO_TASKS:-0}"


# ---------------------------------------------------------------- Flower


def test_flower_is_on_port_5555_behind_a_login_and_reachable_from_this_machine_only():
    flower = SERVICES["flower"]
    assert flower["ports"] == ["127.0.0.1:${FLOWER_PORT:-5555}:5555"]
    assert command_of("flower") == ["celery", "-A", "services.celery_app", "flower", "--port=5555"]
    assert "FLOWER_BASIC_AUTH" in flower["environment"]  # without it anyone who reaches the port could see (and revoke) every task


def test_flower_shares_the_image_with_the_worker_and_waits_for_redis():
    assert SERVICES["flower"]["build"] == SERVICES["worker"]["build"] == SERVICES["api"]["build"]
    assert SERVICES["flower"]["depends_on"]["redis"]["condition"] == "service_healthy"


# ---------------------------------------------------------------- the image and the dependencies


def test_the_image_carries_the_celery_module_that_the_worker_runs():
    assert "COPY celery_app.py /app/services/celery_app.py" in DOCKERFILE  # ``celery -A services.celery_app`` from /app
    assert DOCKERFILE.index("COPY api .") < DOCKERFILE.index("COPY celery_app.py")


def test_celery_redis_and_flower_are_declared_where_docker_installs_them_and_where_uv_does():
    """Docker installs from requirements.txt, uv from pyproject.toml: they have to say the same (they already drifted once, with Prefect)."""
    for text in (REQUIREMENTS, PYPROJECT):
        assert re.search(r"celery\[redis\]>=5\.\d", text) and re.search(r"flower>=2", text)


def test_bcrypt_is_declared_on_its_own_because_libpass_no_longer_installs_it():
    """libpass 1.9.5.post0 requires only passlib: its ``[bcrypt]`` extra stopped pulling bcrypt. The Docker image installs from requirements.txt (not from the
    lock, which pins bcrypt 5.0.0), so a fresh build got no bcrypt and the API died at import (``passlib.exc.MissingBackendError: bcrypt: no backends available``)."""
    for text in (REQUIREMENTS, PYPROJECT):
        assert re.search(r"(?m)^\s*\"?bcrypt>=4", text), "bcrypt must be a direct dependency"


def test_the_lock_file_knows_the_new_dependencies():
    lock = (REPO / "services" / "api" / "uv.lock").read_text(encoding="utf-8")
    for package in ("celery", "flower", "redis", "kombu"):
        assert f'name = "{package}"' in lock


# ---------------------------------------------------------------- the environment and the documentation


def test_the_variables_are_documented_in_the_env_example():
    for name in ("REDIS_URL", "REDIS_PORT", "FLOWER_BASIC_AUTH", "FLOWER_PORT", "REDIS_MAXMEMORY", "CELERY_CONCURRENCY"):
        assert name in ENV_EXAMPLE
    assert "REDIS_URL=redis://localhost:6379/0" in ENV_EXAMPLE  # for a developer who runs the API outside Docker


@pytest.mark.parametrize("readme", [README, README_ES], ids=["README.md", "README.es.md"])
def test_the_readme_of_the_monorepo_says_how_to_start_and_stop_the_worker(readme):
    assert "celery -A services.celery_app worker" in readme
    assert "docker compose up -d redis worker flower" in readme and "docker compose stop worker" in readme
    assert "5555" in readme and "6379" in readme
    assert "inspect ping" in readme  # how to know that it is alive


def test_the_readme_explains_what_happens_when_the_worker_is_stopped_or_killed():
    for word in ("Warm shutdown", "acks_late", "idempotent"):
        assert word in README, word


def test_the_pr_checklist_documents_the_two_decisions_that_differ_from_the_obvious_reading():
    text = (REPO / "services" / "api" / "async_tasks" / "README.md").read_text(encoding="utf-8")
    assert "three attempts" in text.lower() and "max_retries=2" in text  # "three failures -> dead-letter queue" is what the ticket evaluates
    assert "/tasks/pipeline-runs" in text and "POST /reporting/pipeline-runs" in text  # the new endpoint, and why the old one stays


# ---------------------------------------------------------------- compose itself (needs the docker CLI)


@pytest.mark.skipif(shutil.which("docker") is None, reason="needs the docker CLI")
def test_compose_accepts_the_file_and_lists_the_task_queue_with_the_rest():
    out = subprocess.run(["docker", "compose", "config", "--services"], cwd=REPO, capture_output=True, text=True, timeout=60, check=False)
    assert out.returncode == 0, out.stderr[-400:]
    assert {"api", "uis", "redis", "worker", "flower"} <= set(out.stdout.split())


@pytest.mark.skipif(shutil.which("docker") is None, reason="needs the docker CLI")
def test_without_any_env_file_compose_resolves_every_value_it_needs():
    """``docker compose up`` has to work with nothing configured: no variable without a default."""
    out = subprocess.run(["docker", "compose", "config"], cwd=REPO, capture_output=True, text=True, timeout=60, check=False, env={"PATH": __import__("os").environ["PATH"]})
    assert out.returncode == 0 and "variable is not set" not in out.stderr
    resolved = yaml.safe_load(out.stdout)["services"]
    assert resolved["worker"]["environment"]["REDIS_URL"] == "redis://redis:6379/0"
    assert resolved["flower"]["environment"]["FLOWER_BASIC_AUTH"] == "admin:admin"
    assert "256mb" in resolved["redis"]["command"]
