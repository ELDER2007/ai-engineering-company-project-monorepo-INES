"""A REAL Redis (in Docker) and a REAL worker (a process of its own): the acceptance criteria of ticket DEV-55, one by one.

Skipped when Docker is not available. It never touches docker-compose's Redis (its own container, on a free port) nor any real database (the worker
writes to a SQLite file of this test).

Run:  python -m pytest tests/async_tasks/test_integration_redis.py
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import redis
import yaml

REPO = Path(__file__).resolve().parents[2]
REDIS_PORT = urlsplit(os.environ["REDIS_URL"]).port  # set by the conftest next to this file, to a free port, before anything is imported

pytestmark = pytest.mark.skipif(shutil.which("docker") is None, reason="needs the docker CLI")

REDIS_IMAGE = yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))["services"]["redis"]["image"]
CONTAINER = f"nexova-async-tests-{os.getpid()}"
LOG_TIME = re.compile(r"\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),(\d{3}):")


def docker(*args: str, check: bool = True, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=check, timeout=timeout)


def wait_for(predicate, timeout: float = 60, interval: float = 0.1, what: str = "the condition"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    raise AssertionError(f"timed out waiting for {what}")


def redis_client(db: int = 0) -> redis.Redis:
    return redis.Redis(host="127.0.0.1", port=REDIS_PORT, db=db, socket_timeout=5)


class Stack:
    """The Redis container and the worker process of these tests."""

    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.db_path = tmp / "worker.sqlite"
        self.db_url = f"sqlite:///{self.db_path}"
        self.log_path = tmp / "worker.log"
        self.worker: subprocess.Popen | None = None

    # -- redis
    def start_redis(self) -> None:
        docker("rm", "-f", CONTAINER, check=False)
        docker("run", "-d", "--name", CONTAINER, "-p", f"127.0.0.1:{REDIS_PORT}:6379", REDIS_IMAGE,
               "redis-server", "--maxmemory", "64mb", "--maxmemory-policy", "noeviction", "--appendonly", "yes")
        self.wait_redis()

    def wait_redis(self) -> None:
        def ping() -> bool:
            try:
                return redis_client().ping()
            except redis.RedisError:
                return False

        wait_for(ping, 30, what="Redis to answer")

    def stop_redis(self) -> None:
        docker("stop", CONTAINER)

    def restart_redis(self) -> None:
        docker("restart", CONTAINER)
        self.wait_redis()

    def start_stopped_redis(self) -> None:
        docker("start", CONTAINER)
        self.wait_redis()

    # -- worker
    def start_worker(self) -> None:
        env = {
            **os.environ,
            "DATABASE_URL": self.db_url,
            "TELEMETRY_DATABASE_URL": "",
            "REPORTING_DATABASE_URL": "",
            "PIPELINE_ENV_FILE": "/nonexistent/.env",
            "PIPELINE_RETRIES": "0",
            "PIPELINE_DATA_DIR": str(self.tmp / "data"),
            "CELERY_DEMO_TASKS": "1",
            "ASYNC_RETRY_BASE_SECONDS": "0.5",
            "PYTHONPATH": f"{REPO}:{REPO / 'services' / 'api'}",
        }
        self.worker = subprocess.Popen(
            [sys.executable, "-m", "celery", "-A", "services.celery_app", "worker", "--loglevel=INFO", "-E", "--concurrency=1"],
            cwd=REPO, env=env, stdout=open(self.log_path, "ab"), stderr=subprocess.STDOUT,
        )
        offset = len(self.log())
        wait_for(lambda: " ready." in self.log()[offset:], 90, 0.3, "the worker to be ready")

    def stop_worker(self, sig: int = signal.SIGTERM, timeout: int = 90) -> int | None:
        if self.worker is None or self.worker.poll() is not None:
            return None if self.worker is None else self.worker.returncode
        self.worker.send_signal(sig)
        try:
            return self.worker.wait(timeout)
        except subprocess.TimeoutExpired:
            self.worker.kill()
            return self.worker.wait()

    def log(self) -> str:
        return self.log_path.read_text(encoding="utf-8", errors="replace") if self.log_path.exists() else ""

    def task_lines(self, task_id: str) -> list[str]:
        return [line for line in self.log().splitlines() if f"task_id={task_id}" in line and "status=" in line]

    def dead_letters(self):
        from async_tasks import dlq
        from async_tasks.dlq import build_engine

        return dlq.list_dead_letters(engine=build_engine(self.db_url))


@pytest.fixture(scope="module")
def stack(tmp_path_factory):
    probe = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=60, check=False)
    if probe.returncode != 0:
        pytest.skip("the docker daemon is not reachable")
    from services.celery_app import app

    if urlsplit(app.conf.broker_url).port != REDIS_PORT:  # another module created the app first, with another REDIS_URL: it would talk to the WRONG Redis
        pytest.skip(f"the Celery app points at {urlsplit(app.conf.broker_url).netloc}, not at this test's Redis: run this file on its own")
    stack = Stack(tmp_path_factory.mktemp("async-stack"))
    try:
        stack.start_redis()
        stack.start_worker()
        yield stack
    finally:
        stack.stop_worker()
        docker("rm", "-f", CONTAINER, check=False)


@pytest.fixture(autouse=True)
def _running(stack):
    """Every test starts with Redis up and a worker running, whatever the one before did."""
    if docker("inspect", "-f", "{{.State.Running}}", CONTAINER, check=False).stdout.strip() != "true":
        stack.start_stopped_redis()
    if stack.worker is None or stack.worker.poll() is not None:
        stack.start_worker()
    yield


@pytest.fixture()
def api():
    """The API in this process, logged in as an administrator, talking to the REAL Redis. No lifespan: nothing but the routes under test."""
    from fastapi.testclient import TestClient

    from auth.dependencies import get_current_user
    from main import app
    from users.schemas import Role, User

    admin = User(id=uuid.uuid4(), email="admin@example.com", hashed_password="x", role=Role.admin)
    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def outcome(task, timeout: float = 60):
    """The result of a task, read the way the API reads it: a plain query of its state. NOT ``task.get()``, which subscribes to Redis (pubsub) and gives up
    for good if Redis is away for a few seconds: the API never uses it."""
    wait_for(lambda: task.state in ("SUCCESS", "FAILURE"), timeout, 0.1, "the task to end")
    return task.result


def demos():
    from async_tasks import demo

    return demo


def status_of(api, task_id: str) -> dict:
    return api.get(f"/tasks/{task_id}").json()


def clock(line: str) -> datetime:
    day, millis = LOG_TIME.search(line).groups()
    return datetime.strptime(day, "%Y-%m-%d %H:%M:%S").replace(microsecond=int(millis) * 1000)


# ---------------------------------------------------------------- the worker is a process of its own


def test_the_task_runs_in_a_different_process_than_the_one_that_sent_it(stack):
    result = outcome(demos().demo_ok.apply_async(kwargs={"seconds": 0.1}))
    assert result["pid"] != os.getpid()  # not inside the process of the API
    assert stack.worker.pid != os.getpid() and stack.worker.poll() is None


def test_redis_is_the_broker_and_the_result_backend_of_the_app():
    from services.celery_app import app

    with app.connection_for_read() as connection:
        assert connection.transport_cls == "redis" and connection.as_uri().startswith("redis://")
    assert type(app.backend).__name__ == "RedisBackend"
    assert redis_client(0).ping() and redis_client(1).ping()


# ---------------------------------------------------------------- GET /tasks/{id}: the right state in every phase


def test_the_endpoint_follows_a_task_from_pending_to_started_to_success(api):
    demo = demos()
    blocker = demo.demo_ok.apply_async(kwargs={"seconds": 2.0})  # keeps the only process busy, so the next one WAITS in the queue
    wait_for(lambda: status_of(api, blocker.id)["status"] == "started", 30, 0.05, "the blocker to start")
    task = demo.demo_ok.apply_async(kwargs={"seconds": 1.0})
    seen: list[str] = []
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        body = status_of(api, task.id)
        if not seen or seen[-1] != body["status"]:
            seen.append(body["status"])
        if body["status"] == "success":
            break
        time.sleep(0.05)
    assert seen == ["pending", "started", "success"]
    assert body["task_id"] == task.id and body["result"]["slept"] == 1.0


def test_the_endpoint_shows_the_retries_and_the_final_failure_with_a_clean_error(api):
    task = demos().demo_fail.apply_async()
    seen: list[str] = []
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        body = status_of(api, task.id)
        if not seen or seen[-1] != body["status"]:
            seen.append(body["status"])
        if body["status"] == "failure":
            break
        time.sleep(0.05)
    assert "retry" in seen and seen[-1] == "failure"
    assert set(seen) <= {"pending", "started", "retry", "failure"}
    assert body["result"]["error"].startswith("RuntimeError: demo: this task always fails")
    assert "demo_secret" not in json.dumps(body)


# ---------------------------------------------------------------- retries with a growing wait, then the dead-letter queue


def test_three_failures_back_off_and_end_in_the_dead_letter_queue(stack):
    task = demos().demo_fail.apply_async()
    wait_for(lambda: any("status=failure" in line for line in stack.task_lines(task.id)), 60, 0.2, "the final failure")
    lines = stack.task_lines(task.id)
    assert [re.search(r"attempt=(\d)", line).group(1) for line in lines if "dead_letter" not in line] == ["1", "2", "3"]
    assert [re.search(r"status=(\w+)", line).group(1) for line in lines if "dead_letter" not in line] == ["retry", "retry", "failure"]
    first, second, third = (clock(line) for line in lines if "dead_letter" not in line)
    wait_1, wait_2 = (second - first).total_seconds(), (third - second).total_seconds()
    assert wait_1 >= 0.5 and wait_2 >= 1.0 and wait_2 > wait_1  # not immediate, and growing (0.5 s, then 1 s, plus jitter)
    (row,) = [r for r in stack.dead_letters() if r.task_id == task.id]
    assert row.attempt == 3 and row.task_name == "async_tasks.demo_fail" and "RuntimeError" in row.error and "demo_secret" not in row.error


def test_a_task_that_fails_once_succeeds_on_the_second_attempt_and_leaves_no_dead_letter(stack):
    task = demos().demo_flaky.apply_async(kwargs={"fail_times": 1})
    assert outcome(task) == {"attempts": 2}
    assert [re.search(r"status=(\w+)", line).group(1) for line in stack.task_lines(task.id)] == ["retry", "success"]
    assert task.id not in {row.task_id for row in stack.dead_letters()}


def test_every_execution_line_has_task_id_attempt_status_and_duration(stack):
    task = demos().demo_ok.apply_async(kwargs={"seconds": 0.2})
    outcome(task)
    (line,) = [line for line in stack.task_lines(task.id)]
    assert re.search(rf"task=async_tasks\.demo_ok task_id={task.id} attempt=1 status=success duration=\d+\.\d{{3}}s", line)


# ---------------------------------------------------------------- what is in Redis: light, expiring, without credentials


def test_a_message_in_the_queue_carries_only_the_week_not_data():
    from async_tasks.tasks import run_weekly_pipeline

    queue = f"inspect-{uuid.uuid4().hex[:8]}"  # a queue that no worker reads: the message stays there to be looked at
    run_weekly_pipeline.apply_async(kwargs={"week_start": "2026-10-26"}, queue=queue)
    (raw,) = redis_client(0).lrange(queue, 0, -1)
    message = json.loads(raw)
    arguments = json.loads(base64.b64decode(message["body"]))
    assert arguments[0] == [] and arguments[1] == {"week_start": "2026-10-26"}  # the whole payload: one date
    assert len(raw) < 1500  # the envelope, the headers and the date: bytes, not data
    redis_client(0).delete(queue)


def test_a_message_with_data_is_refused_before_it_reaches_redis():
    from async_tasks.base import MessageTooLarge

    queue = f"inspect-{uuid.uuid4().hex[:8]}"
    heavy = {"events": [{"event_id": str(uuid.uuid4()), "payload": "x" * 50} for _ in range(100)]}
    with pytest.raises(MessageTooLarge):
        demos().demo_ok.apply_async(kwargs=heavy, queue=queue)
    assert redis_client(0).llen(queue) == 0


def test_the_outcomes_expire_and_no_key_of_redis_ever_holds_the_password(stack):
    task = demos().demo_fail.apply_async()
    wait_for(lambda: task.state == "FAILURE", 60, 0.2, "the failure")
    ttl = redis_client(1).ttl(f"celery-task-meta-{task.id}")
    assert 0 < ttl <= 24 * 3600  # the outcome is kept for a day, not forever
    everything = b""
    for db in (0, 1):
        client = redis_client(db)
        for key in client.scan_iter("*"):
            kind = client.type(key)
            value = {b"string": lambda: client.get(key), b"list": lambda: b"".join(client.lrange(key, 0, -1)), b"hash": lambda: str(client.hgetall(key)).encode(),
                     b"set": lambda: b"".join(client.smembers(key)), b"zset": lambda: str(client.zrange(key, 0, -1)).encode()}.get(kind, lambda: b"")()
            everything += key + (value or b"")
    assert b"demo_secret" not in everything and b"demo_user" not in everything


# ---------------------------------------------------------------- 202 in under 200 ms, whatever the task takes


def test_the_post_answers_202_in_under_200_ms_while_the_worker_is_busy(api, stack):
    blocker = demos().demo_ok.apply_async(kwargs={"seconds": 6.0})  # a slow task holds the worker the whole time
    wait_for(lambda: blocker.state == "STARTED", 30, 0.1, "the blocker to start")
    api.post("/tasks/pipeline-runs", json={"week_start": "2026-10-26"})  # the first request opens the connection: not what is measured
    times = []
    for _ in range(8):
        started = time.perf_counter()
        answer = api.post("/tasks/pipeline-runs", json={"week_start": "2026-10-26"})
        times.append(time.perf_counter() - started)
        assert answer.status_code == 202 and set(answer.json()) == {"task_id"} and answer.headers["location"] == f"/tasks/{answer.json()['task_id']}"
    assert max(times) < 0.2, f"slowest: {max(times):.3f}s"
    from services.celery_app import app

    app.control.purge()  # the pipeline runs queued here are not what this test is about: they must not keep the worker busy
    outcome(blocker)


# ---------------------------------------------------------------- the real pipeline, through the queue


def test_the_real_pipeline_runs_in_the_worker_and_the_endpoint_returns_its_run(api, stack):
    from data.pipelines.weekly_office_performance.seed_telemetry import seed_telemetry
    from async_tasks.dlq import build_engine

    assert stack.db_url.startswith("sqlite:///") and "supabase" not in stack.db_url
    seed_telemetry(build_engine(stack.db_url))  # demo telemetry, in the throw-away file the worker reads
    answer = api.post("/tasks/pipeline-runs", json={"week_start": "2026-10-26"})
    assert answer.status_code == 202
    task_id = answer.json()["task_id"]
    body = wait_for(lambda: (b := status_of(api, task_id))["status"] in ("success", "failure") and b, 180, 0.5, "the pipeline task to end")
    assert body["status"] == "success", body
    assert body["result"]["state"] == "Completed" and body["result"]["rows_written"] == 5 and body["result"]["week_start"] == "2026-10-26"


# ---------------------------------------------------------------- the API stops, the worker does not; nothing is lost


def test_the_process_that_sent_the_tasks_can_end_and_the_worker_still_does_them(stack):
    """The 'API' is another process that enqueues three tasks and exits at once."""
    sender = (
        "import services.celery_app; from async_tasks.demo import demo_ok;"
        "print(','.join(demo_ok.apply_async(kwargs={'seconds': 0.3}).id for _ in range(3)))"
    )
    out = subprocess.run([sys.executable, "-c", sender], cwd=REPO, capture_output=True, text=True, check=True, env={**os.environ, "PYTHONPATH": f"{REPO}:{REPO / 'services' / 'api'}"})
    ids = out.stdout.strip().split(",")
    from services.celery_app import app

    wait_for(lambda: all(app.AsyncResult(i).state == "SUCCESS" for i in ids), 60, 0.2, "the three tasks")


def test_the_queue_survives_a_restart_of_redis(stack):
    stack.stop_worker()  # nobody takes the messages: they sit in the queue
    ids = [demos().demo_ok.apply_async(kwargs={"seconds": 0.2}).id for _ in range(3)]
    assert redis_client(0).llen("celery") == 3
    stack.restart_redis()  # ``appendonly yes``: the queue is rebuilt from the file
    assert redis_client(0).llen("celery") == 3
    stack.start_worker()
    from services.celery_app import app

    wait_for(lambda: all(app.AsyncResult(i).state == "SUCCESS" for i in ids), 60, 0.2, "the three tasks after the restart")


def test_stopping_the_worker_in_the_middle_of_a_task_lets_it_finish(stack):
    """``docker compose stop`` sends SIGTERM: a Warm shutdown. The task that is running ends; the process exits with code 0."""
    task = demos().demo_ok.apply_async(kwargs={"seconds": 4.0})
    wait_for(lambda: task.state == "STARTED", 30, 0.1, "the task to start")
    assert stack.stop_worker(signal.SIGTERM) == 0
    assert task.state == "SUCCESS" and task.result["slept"] == 4.0
    assert "Warm shutdown" in stack.log()


# ---------------------------------------------------------------- Redis down, Redis full: the API answers 503 and keeps living


def test_if_redis_is_full_the_post_answers_503_and_nothing_is_lost(api):
    client = redis_client()
    used = client.info("memory")["used_memory"]
    client.config_set("maxmemory", max(1, used - 200_000))  # below what it holds: every write is refused (``noeviction``)
    try:
        started = time.perf_counter()
        answer = api.post("/tasks/pipeline-runs", json={})
        assert answer.status_code == 503 and "not available" in answer.json()["detail"]
        assert time.perf_counter() - started < 1.0
        assert api.get("/health").status_code == 200
    finally:
        client.config_set("maxmemory", "64mb")
    assert api.post("/tasks/pipeline-runs", json={"week_start": "2026-10-26"}).status_code == 202  # accepted again
    from services.celery_app import app

    app.control.purge()


def test_if_redis_is_down_the_post_and_the_get_answer_503_fast_and_everything_recovers(api, stack):
    stack.stop_redis()
    try:
        for _ in range(3):
            started = time.perf_counter()
            assert api.post("/tasks/pipeline-runs", json={}).status_code == 503
            assert time.perf_counter() - started < 2.0  # it fails fast: it does not hang the request
        assert api.get(f"/tasks/{uuid.uuid4()}").status_code == 503
        assert api.get("/health").status_code == 200
    finally:
        stack.start_stopped_redis()
    task = demos().demo_ok.apply_async(kwargs={"seconds": 0.1})  # the same worker, which was never restarted, reconnects by itself
    assert outcome(task)["slept"] == 0.1
    assert api.post("/tasks/pipeline-runs", json={"week_start": "2026-10-26"}).status_code == 202
    from services.celery_app import app

    app.control.purge()
