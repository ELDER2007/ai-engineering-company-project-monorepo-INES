"""The HTTP side of the asynchronous tasks (ticket DEV-55): ``POST /tasks/pipeline-runs`` and ``GET /tasks/{task_id}``.

No Redis here: what the API asks Celery is replaced by stand-ins, so every state and every failure of Redis can be produced on demand. The same
endpoints against a REAL Redis and a REAL worker are in ``tests/async_tasks/test_integration_redis.py``.
"""

from __future__ import annotations

import os

import pytest
from celery import Celery
from conftest import BOB, headers_for
from fastapi.testclient import TestClient
from kombu.exceptions import OperationalError
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import OutOfMemoryError

import async_tasks.router as router_module
from async_tasks import dlq
from main import app

SECRET_URL = "postgresql://pipeline_writer:hunter2-the-password@db.example.supabase.co:6543/postgres"
TASK_ID = "6f1c2d3e-4a5b-4c6d-8e7f-0a1b2c3d4e5f"


@pytest.fixture(autouse=True)
def _throw_away_database(monkeypatch, tmp_path):
    """The dead-letter queue lives in the API's database, and the reporting endpoints read two more: always files of this test, NEVER the real ones.

    ``services/api/.env`` may hold the real Supabase (``core.config`` loads it when it is imported), including the two least-privilege role URLs of the
    pipeline. They are SET to empty here, not removed: ``load_dotenv`` never overrides a variable that exists."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'tasks.sqlite'}")
    monkeypatch.setenv("TELEMETRY_DATABASE_URL", "")
    monkeypatch.setenv("REPORTING_DATABASE_URL", "")
    from core.config import get_database_url

    assert get_database_url().startswith("sqlite:///")
    for name in ("DATABASE_URL", "TELEMETRY_DATABASE_URL", "REPORTING_DATABASE_URL"):
        value = os.environ.get(name, "")
        assert value == "" or value.startswith("sqlite:///"), f"{name} points at a real database: a test must never touch it"


@pytest.fixture()
def client(auth_headers) -> TestClient:
    return TestClient(app, headers=auth_headers)  # alice: an administrator


@pytest.fixture()
def user_client() -> TestClient:
    return TestClient(app, headers=headers_for(BOB))  # bob: not an administrator


class Sent:
    """Stands in for ``run_weekly_pipeline.apply_async``: it records what the API put in the message."""

    def __init__(self, monkeypatch, *, raises: Exception | None = None):
        self.calls: list[dict] = []
        self.raises = raises
        monkeypatch.setattr(router_module.run_weekly_pipeline, "apply_async", self)

    def __call__(self, args=None, kwargs=None, **options):
        self.calls.append({"args": args, "kwargs": kwargs, **options})
        if self.raises:
            raise self.raises
        return type("Result", (), {"id": TASK_ID})()


class FakeResult:
    """Stands in for ``celery_app.AsyncResult(task_id)``: the state and the result that Redis would hold."""

    def __init__(self, state, result=None, raises: Exception | None = None):
        self._state, self._result, self._raises = state, result, raises

    @property
    def state(self):
        if self._raises:
            raise self._raises
        return self._state

    @property
    def result(self):
        return self._result


def task_in_state(monkeypatch, state, result=None, raises=None):
    monkeypatch.setattr(router_module.celery_app, "AsyncResult", lambda task_id: FakeResult(state, result, raises))


# ---------------------------------------------------------------- POST: 202 and a task_id, at once


def test_the_post_answers_202_with_the_task_id_and_a_location(client, monkeypatch):
    sent = Sent(monkeypatch)
    answer = client.post("/tasks/pipeline-runs", json={"week_start": "2026-10-28"})
    assert answer.status_code == 202
    assert answer.json() == {"task_id": TASK_ID}
    assert answer.headers["location"] == f"/tasks/{TASK_ID}"
    assert sent.calls == [{"args": None, "kwargs": {"week_start": "2026-10-28"}}]  # ONE light parameter: the data is read by the worker


def test_without_a_body_it_asks_for_the_last_complete_week(client, monkeypatch):
    sent = Sent(monkeypatch)
    assert client.post("/tasks/pipeline-runs").status_code == 202
    assert sent.calls[0]["kwargs"] == {"week_start": None}


def test_the_post_does_not_run_the_pipeline_itself(client, monkeypatch):
    """The whole point: the request only queues. If the pipeline were called here, the answer would take seconds."""
    from data.pipelines.weekly_office_performance import interface

    def forbidden(**_):
        raise AssertionError("the API must not run the pipeline")

    monkeypatch.setattr(interface, "run_weekly_office_performance", forbidden)
    Sent(monkeypatch)
    assert client.post("/tasks/pipeline-runs", json={}).status_code == 202


def test_a_bad_date_is_refused_before_anything_is_queued(client, monkeypatch):
    sent = Sent(monkeypatch)
    assert client.post("/tasks/pipeline-runs", json={"week_start": "soon"}).status_code == 422
    assert sent.calls == []


def test_only_an_administrator_can_start_a_run_and_a_login_is_required(user_client, monkeypatch):
    sent = Sent(monkeypatch)
    assert TestClient(app).post("/tasks/pipeline-runs").status_code == 401
    assert user_client.post("/tasks/pipeline-runs").status_code == 403
    assert sent.calls == []


def test_the_synchronous_endpoint_is_still_there_and_unchanged():
    paths = app.openapi()["paths"]
    assert "post" in paths["/reporting/pipeline-runs"] and "201" in paths["/reporting/pipeline-runs"]["post"]["responses"]
    assert "202" in paths["/tasks/pipeline-runs"]["post"]["responses"]


# ---------------------------------------------------------------- POST: when Redis is not there


@pytest.mark.parametrize(
    "problem",
    [
        OperationalError("Error 111 connecting to redis:6379. Connection refused."),
        RedisConnectionError("Connection refused"),
        OutOfMemoryError("OOM command not allowed when used memory > 'maxmemory'."),  # Redis full, with ``noeviction``
        ConnectionRefusedError("nobody is listening"),
    ],
    ids=["kombu", "redis-connection", "redis-full", "os-error"],
)
def test_if_the_queue_is_unavailable_the_post_answers_503_not_a_stack_trace(client, monkeypatch, problem):
    Sent(monkeypatch, raises=problem)
    answer = client.post("/tasks/pipeline-runs", json={})
    assert answer.status_code == 503
    assert answer.json() == {"detail": "The task queue (Redis) is not available right now. Try again in a moment."}
    assert "location" not in answer.headers


def test_the_rest_of_the_api_keeps_working_while_the_queue_is_down(client, monkeypatch):
    Sent(monkeypatch, raises=OperationalError("down"))
    assert client.post("/tasks/pipeline-runs").status_code == 503
    assert client.get("/health").status_code == 200
    assert client.get("/auth/me").status_code == 200  # a logged-in endpoint that answers from its own store: no Redis involved


def test_the_api_does_not_need_redis_to_start_and_the_warm_up_does_not_delay_it(monkeypatch):
    """Importing the app opened no connection (this module imported it). The only thing at startup that touches Redis is the warm-up, in a background
    thread: even if it hangs, ``warm_up()`` returns at once."""
    import inspect
    import time

    import main

    assert "warm_up_task_queue()" in inspect.getsource(main.lifespan)  # it is called at startup...
    monkeypatch.setattr(router_module, "_open_queue_connections", lambda: time.sleep(3))  # ...and a hanging Redis...
    started = time.perf_counter()
    router_module.warm_up()
    assert time.perf_counter() - started < 0.5  # ...does not hold the start


def test_the_api_does_not_subscribe_to_the_results_of_the_tasks_it_publishes():
    """A subscription that the API never uses, and that turns a Redis outage into a 5 s wait and a RuntimeError (a 500) instead of an immediate 503."""
    router_module._use_publish_only()
    assert router_module.celery_app.backend.on_task_call is router_module._publish_only  # on the backend of THIS thread: Celery keeps one per thread


def test_the_post_applies_it_on_the_thread_that_publishes(client, monkeypatch):
    """FastAPI runs the endpoint in a pool of threads, not in the one that imported the module: it is checked from inside the request."""
    seen = {}

    def publish(args=None, kwargs=None, **options):
        seen["replaced"] = router_module.celery_app.backend.on_task_call is router_module._publish_only
        return type("Result", (), {"id": TASK_ID})()

    monkeypatch.setattr(router_module.run_weekly_pipeline, "apply_async", publish)
    assert client.post("/tasks/pipeline-runs").status_code == 202
    assert seen == {"replaced": True}


def test_the_warm_up_never_breaks_the_start_when_redis_is_absent(monkeypatch):
    def refuse(*_a, **_k):
        raise RedisConnectionError("no Redis here")

    pool = type("Pool", (), {"acquire": staticmethod(refuse)})()
    monkeypatch.setattr(router_module, "celery_app", type("App", (), {"producer_pool": pool})())
    router_module._open_queue_connections()  # logs a warning, raises nothing


# ---------------------------------------------------------------- GET /tasks/{task_id}: the real states of Celery


@pytest.mark.parametrize("celery_state, expected", [("PENDING", "pending"), ("STARTED", "started"), ("RETRY", "retry"), ("REVOKED", "revoked")])
def test_the_status_is_the_state_of_celery_in_lowercase_and_the_result_is_null_until_it_ends(client, monkeypatch, celery_state, expected):
    task_in_state(monkeypatch, celery_state, result=RuntimeError("not a result yet"))
    answer = client.get(f"/tasks/{TASK_ID}")
    assert answer.status_code == 200
    assert answer.json() == {"task_id": TASK_ID, "status": expected, "result": None}


def test_a_successful_task_returns_what_it_returned(client, monkeypatch):
    run = {"state": "Completed", "week_start": "2026-10-26", "rows_written": 5}
    task_in_state(monkeypatch, "SUCCESS", result=run)
    assert client.get(f"/tasks/{TASK_ID}").json() == {"task_id": TASK_ID, "status": "success", "result": run}


def test_a_failed_task_returns_its_error_without_credentials(client, monkeypatch):
    task_in_state(monkeypatch, "FAILURE", result=RuntimeError(f"cannot connect to {SECRET_URL}"))
    body = client.get(f"/tasks/{TASK_ID}").json()
    assert body["status"] == "failure"
    assert body["result"] == {"error": "RuntimeError: cannot connect to postgresql://***@db.example.supabase.co:6543/postgres"}
    assert "hunter2" not in str(body)


def test_the_error_of_a_task_that_failed_for_good_is_not_prefixed_twice(client, monkeypatch):
    """A task leaves Redis with a ``TaskFailed`` whose message already says ``ErrorType: message``: the API must not add the type again."""
    from async_tasks.base import TaskFailed

    task_in_state(monkeypatch, "FAILURE", result=TaskFailed("RuntimeError: cannot connect to postgresql://***@db.example.supabase.co/postgres"))
    assert client.get(f"/tasks/{TASK_ID}").json()["result"] == {"error": "RuntimeError: cannot connect to postgresql://***@db.example.supabase.co/postgres"}


def test_an_unknown_id_is_pending_because_celery_cannot_tell_it_from_a_queued_one(client, monkeypatch):
    """Documented behaviour of Celery, not of this API: there is no record of a task until a worker touches it. A REAL ``AsyncResult``, on an empty
    in-memory backend, so the answer does not depend on whether the machine that runs the tests has a Redis."""
    empty = Celery("unknown-ids", broker="memory://", backend="cache+memory://")
    monkeypatch.setattr(router_module.celery_app, "AsyncResult", empty.AsyncResult)
    answer = client.get("/tasks/an-id-nobody-ever-sent")
    assert answer.status_code == 200 and answer.json() == {"task_id": "an-id-nobody-ever-sent", "status": "pending", "result": None}


def test_the_get_answers_503_if_redis_is_not_there(client, monkeypatch):
    task_in_state(monkeypatch, None, raises=RedisConnectionError("Connection refused"))
    assert client.get(f"/tasks/{TASK_ID}").status_code == 503


def test_any_logged_in_user_can_ask_for_a_task_but_nobody_without_a_login(user_client, monkeypatch):
    task_in_state(monkeypatch, "PENDING")
    assert user_client.get(f"/tasks/{TASK_ID}").status_code == 200
    assert TestClient(app).get(f"/tasks/{TASK_ID}").status_code == 401


# ---------------------------------------------------------------- GET /tasks/dead-letters


def test_the_dead_letters_are_listed_newest_first_for_an_administrator(client):
    dlq.record(task_id="first", task_name="async_tasks.run_weekly_pipeline", attempt=3, error="RuntimeError: one")
    dlq.record(task_id="second", task_name="async_tasks.run_weekly_pipeline", attempt=3, error="RuntimeError: two", arguments='{"args": [], "kwargs": {"week_start": "2026-10-26"}}')
    rows = client.get("/tasks/dead-letters").json()
    assert [row["task_id"] for row in rows] == ["second", "first"]
    assert set(rows[0]) == {"id", "task_id", "task_name", "attempt", "error", "arguments", "failed_at"}
    assert rows[0]["attempt"] == 3 and rows[0]["error"] == "RuntimeError: two"


def test_the_dead_letters_are_for_administrators_only(user_client):
    assert user_client.get("/tasks/dead-letters").status_code == 403
    assert TestClient(app).get("/tasks/dead-letters").status_code == 401


def test_dead_letters_is_not_mistaken_for_a_task_id(client, monkeypatch):
    task_in_state(monkeypatch, "PENDING")
    assert client.get("/tasks/dead-letters").json() == []  # the list, not {"task_id": "dead-letters", ...}


def test_the_new_endpoints_are_documented_with_their_answers():
    paths = app.openapi()["paths"]
    assert set(paths["/tasks/{task_id}"]["get"]["responses"]) >= {"200", "503"}
    assert "503" in paths["/tasks/pipeline-runs"]["post"]["responses"]
