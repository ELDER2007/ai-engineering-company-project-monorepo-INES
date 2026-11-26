"""The HTTP side of the asynchronous tasks (ticket DEV-55).

* ``POST /tasks/pipeline-runs``  enqueue the weekly pipeline and answer ``202 Accepted`` + ``{"task_id": ...}`` at once. Admins only,
  like the synchronous ``POST /reporting/pipeline-runs``, which is untouched.
* ``GET /tasks/{task_id}``                 the state of a task, read from Redis: ``{"task_id", "status", "result"}``.
* ``GET /tasks/dead-letters``              the tasks that failed for good (admins only).

The API never runs the pipeline here: it validates, leaves a light message in Redis and answers. If Redis cannot be reached (or is full), the
answer is ``503``, not a stack trace; the rest of the API does not depend on Redis and keeps working.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import asdict
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from kombu.exceptions import KombuError
from pydantic import BaseModel
from redis.exceptions import RedisError

from auth.dependencies import admin_only, get_current_user
from reporting.schemas import PipelineRunCreate
from services.celery_app import app as celery_app

from . import dlq
from .base import describe
from .tasks import run_weekly_pipeline

logger = logging.getLogger("async_tasks")

router = APIRouter()


def _publish_only(producer, task_id) -> None:
    """Celery, when a process PUBLISHES a task, also subscribes (pubsub) to the channel where its result will arrive, so that ``AsyncResult.get()`` can wait for it.
    The API never waits: it answers ``202`` and later reads the state with a plain query (``AsyncResult.state``). The subscription only does harm here: when
    Redis goes away for more than a second, the next publish hangs for 5 s and then raises ``RuntimeError: ... The Celery application must be restarted``, which
    would be a ``500`` after a long wait instead of the immediate ``503``. (Measured: 5.01 s and a RuntimeError against 0.00 s and ``OperationalError``.)"""


def _use_publish_only() -> None:
    """Celery keeps ONE backend PER THREAD, and FastAPI runs the endpoints in a pool of threads: the replacement has to be made on the thread that is about to
    publish, every time (it is an attribute assignment). Done once at import it would only reach the thread that imported this module. The worker is another
    process and is untouched."""
    celery_app.backend.on_task_call = _publish_only


QUEUE_UNAVAILABLE = "The task queue (Redis) is not available right now. Try again in a moment."


class TaskAccepted(BaseModel):
    task_id: str


class TaskState(BaseModel):
    task_id: str
    status: str  # pending | started | success | failure (+ retry, revoked)
    result: Any | None = None  # the value the task returned (success), {"error": ...} (failure), null while it has not ended


class DeadLetterOut(BaseModel):
    id: int
    task_id: str
    task_name: str
    attempt: int
    error: str
    arguments: str | None
    failed_at: datetime


def _open_queue_connections() -> None:
    try:
        with celery_app.producer_pool.acquire(block=True, timeout=5) as producer:  # the connection the first POST would otherwise open
            producer.connection.ensure_connection(max_retries=1)
            producer.maybe_declare(celery_app.amqp.queues[celery_app.conf.task_default_queue])  # and the queue: the first publish declares it
        celery_app.backend.client.ping()  # the connection the first GET /tasks/{id} would otherwise open
    except Exception as problem:  # noqa: BLE001  Redis may simply not be there: the API does not need it to start
        logger.warning("task queue: not warmed up (%s); the first request will open the connection itself", type(problem).__name__)


def warm_up() -> None:
    """Open the connections to Redis at startup, in the background (Redis down must not delay or break the start).

    The first publish after the API starts costs 150-280 ms (a new connection, the declaration of the queue): more than the 200 ms that
    ``POST /tasks/pipeline-runs`` has to answer in. Opened here, the first request is as fast as the rest (a few milliseconds).
    """
    threading.Thread(target=_open_queue_connections, name="queue-warm-up", daemon=True).start()


def _unavailable(problem: Exception) -> HTTPException:
    logger.error("the task queue is not available: %s", type(problem).__name__)
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, QUEUE_UNAVAILABLE)


@router.post(
    "/tasks/pipeline-runs",
    response_model=TaskAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["tasks"],
    dependencies=[Depends(admin_only)],
    summary="Enqueue a pipeline run and answer at once (admins only)",
    description="Same work as `POST /reporting/pipeline-runs`, but it does not wait for it: the run is queued for a worker and the answer is "
    "`202 Accepted` with the `task_id`. Ask `GET /tasks/{task_id}` how it goes. `week_start` is any day of the week (default: the last complete ISO week).",
    responses={403: {"description": "Not an administrator"}, 503: {"description": "The task queue (Redis) is not available"}},
)
def enqueue_pipeline_run(response: Response, body: Annotated[PipelineRunCreate, Body()] = PipelineRunCreate()) -> TaskAccepted:
    _use_publish_only()
    try:
        result = run_weekly_pipeline.apply_async(kwargs={"week_start": body.week_start.isoformat() if body.week_start else None})
    except (KombuError, RedisError, OSError) as problem:  # Redis down, unreachable or full (``noeviction``): nothing was queued
        raise _unavailable(problem) from problem
    response.headers["Location"] = f"/tasks/{result.id}"
    return TaskAccepted(task_id=result.id)


# Declared BEFORE ``/tasks/{task_id}``: otherwise "dead-letters" would be read as a task id.
@router.get(
    "/tasks/dead-letters",
    response_model=list[DeadLetterOut],
    tags=["tasks"],
    dependencies=[Depends(admin_only)],
    summary="Tasks that failed for good (admins only)",
    description="The dead-letter queue: every task that used all its attempts, with its `task_id`, the attempt that failed last, the error and the moment. Newest first.",
)
def dead_letters(limit: Annotated[int, Query(ge=1, le=200)] = 50) -> list[DeadLetterOut]:
    return [DeadLetterOut(**asdict(row)) for row in dlq.list_dead_letters(limit)]


@router.get(
    "/tasks/{task_id}",
    response_model=TaskState,
    tags=["tasks"],
    dependencies=[Depends(get_current_user)],
    summary="State of an asynchronous task",
    description="`status` is the real state of the task in Celery: `pending` (queued, or an id Celery does not know: it cannot tell them apart), "
    "`started`, `success`, `failure`; also `retry` while it waits for its next attempt. `result` is what the task returned when it succeeded, "
    "`{\"error\": ...}` when it failed, and `null` before. The outcome is kept for one day.",
    responses={503: {"description": "The task queue (Redis) is not available"}},
)
def task_state(task_id: str) -> TaskState:
    try:
        outcome = celery_app.AsyncResult(task_id)
        state = outcome.state  # the one read from Redis
        value = outcome.result if state in ("SUCCESS", "FAILURE") else None
    except (KombuError, RedisError, OSError) as problem:
        raise _unavailable(problem) from problem
    result: Any = value
    if state == "FAILURE":  # the error of a database can carry the URL it was using: never to the client
        result = {"error": describe(value)}
    return TaskState(task_id=task_id, status=state.lower(), result=result)
