"""The base class of every task: what is the same for all of them, so no task can forget it.

1. **One log line per execution** with ``task_id``, the attempt, the resulting status and the duration; a failure adds the complete error.
2. **Retries with a growing wait**: ``retry_delay`` (5 s, then 10 s, ...). Never immediately after a failure.
3. **The dead-letter queue** on the FINAL failure (``on_failure`` runs only then, not on every retry).
4. **Light messages**: a message in the queue carries identifiers and small parameters, never a payload of data.

The hooks of Celery are used (``before_start``, ``on_success``, ``on_retry``, ``on_failure``) and not ``__call__``: overriding ``__call__`` makes
Celery push a new request context, and the attempt number (``request.retries``) would be lost.

**How many attempts.** ``MAX_ATTEMPTS = 3`` executions in total: the first one and two retries. After the third failure the task goes to the
dead-letter queue, which is what the ticket asks ("after three consecutive failures"). In Celery's own words that is ``max_retries = 2``
(``MAX_RETRIES``): Celery counts retries, and the first execution is not one.
"""

from __future__ import annotations

import json
import logging
import os
import random
import time
import traceback
from typing import Any, Callable

from celery import Task

from core.redaction import strip_credentials

from . import dlq

logger = logging.getLogger("async_tasks")

MAX_ATTEMPTS = 3
MAX_RETRIES = MAX_ATTEMPTS - 1
DEFAULT_RETRY_BASE_SECONDS = 5.0
MAX_MESSAGE_BYTES = 1024  # a message is an id or a date, not data; this is generous for that and small for anything else
NON_RETRYABLE = (ValueError, TypeError)  # a wrong argument fails the same way every time: retrying it only delays the verdict


class MessageTooLarge(ValueError):
    """The arguments of a task are not light (they would travel through Redis)."""


def retry_base_seconds() -> float:
    try:
        return max(0.0, float(os.environ.get("ASYNC_RETRY_BASE_SECONDS", DEFAULT_RETRY_BASE_SECONDS)))
    except ValueError:
        return DEFAULT_RETRY_BASE_SECONDS


def retry_delay(retries: int) -> float:
    """Seconds to wait before the next attempt, after ``retries`` retries already made: 5, 10, 20... (exponential), plus up to 20 % of jitter.

    The jitter is only added, never subtracted: the wait of an attempt is always longer than the wait of the one before, and a burst of
    tasks that failed together does not come back all at the same second.
    """
    wait = retry_base_seconds() * (2 ** max(0, retries))
    return wait + random.uniform(0, wait * 0.2)


def check_light(args: Any, kwargs: Any) -> None:
    size = len(json.dumps([list(args or ()), dict(kwargs or {})], default=str))
    if size > MAX_MESSAGE_BYTES:
        raise MessageTooLarge(f"the arguments of a task must be light (identifiers, a date); this one is {size} bytes, the limit is {MAX_MESSAGE_BYTES}")


class TaskFailed(Exception):
    """The error of a task as TEXT and without credentials: what Celery keeps in Redis, what Flower shows and what the API returns.

    The original exception is never stored: the message of a database error can carry the URL it was using, user and password included.
    """


def run_with_retries(task: Task, work: Callable[[], Any]) -> Any:
    """Run ``work()``. If it fails: retry with the growing wait; a wrong argument, or the last attempt, fails for good (the dead-letter queue takes it).

    The error that leaves this function is always a ``TaskFailed`` with the message already cleaned, and it is raised OUTSIDE the ``except``
    block on purpose: raised inside it, Python chains it to the original error and the traceback that Celery stores would carry the
    original message (with its credentials) again.
    """
    try:
        return work()
    except Exception as exc:  # noqa: BLE001  (SoftTimeLimitExceeded is one too)
        error = exc
    clean = TaskFailed(describe(error))
    if isinstance(error, NON_RETRYABLE):
        raise clean
    raise task.retry(exc=clean, countdown=retry_delay(task.request.retries))


def _attempt(task: Task) -> int:
    return (getattr(task.request, "retries", 0) or 0) + 1


def _duration(task: Task) -> float:
    started = getattr(task.request, "_nexova_started", None)
    return time.perf_counter() - started if started is not None else 0.0


def describe(exc: BaseException) -> str:
    """``ErrorType: message`` of an error, without credentials. What the log, the dead letters and the API all say, so they say the same thing."""
    if isinstance(exc, TaskFailed):
        return str(exc)  # already "ErrorType: message", cleaned
    return strip_credentials(f"{type(exc).__name__}: {exc}")


class ObservedTask(Task):
    """Use as ``@app.task(bind=True, base=ObservedTask, max_retries=MAX_RETRIES)``."""

    abstract = True

    def apply_async(self, args=None, kwargs=None, **options):
        check_light(args, kwargs)  # before anything reaches Redis
        return super().apply_async(args, kwargs, **options)

    def before_start(self, task_id, args, kwargs):
        self.request._nexova_started = time.perf_counter()  # the clock of the duration

    def on_success(self, retval, task_id, args, kwargs):
        logger.info("task=%s task_id=%s attempt=%d status=success duration=%.3fs", self.name, task_id, _attempt(self), _duration(self))

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        cause = getattr(exc, "exc", None) or exc  # Retry wraps the error that caused it
        logger.warning("task=%s task_id=%s attempt=%d status=retry duration=%.3fs error=%s", self.name, task_id, _attempt(self), _duration(self), describe(cause))

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """The final failure: it is logged with the COMPLETE error, and it goes to the dead-letter queue."""
        attempt = _attempt(self)
        full = strip_credentials(str(getattr(einfo, "traceback", "") or "".join(traceback.format_exception(exc))))
        logger.error("task=%s task_id=%s attempt=%d status=failure duration=%.3fs error=%s\n%s", self.name, task_id, attempt, _duration(self), describe(exc), full)
        try:
            dlq.record(
                task_id=task_id,
                task_name=self.name,
                attempt=attempt,
                error=describe(exc),
                arguments=json.dumps({"args": list(args or ()), "kwargs": dict(kwargs or {})}, default=str),
            )
        except Exception as problem:  # the database is down: the failure must not disappear, so it stays in the log with everything
            logger.error("task=%s task_id=%s attempt=%d status=dead_letter_lost msg=the dead letter could NOT be written (%s) error=%s",
                         self.name, task_id, attempt, strip_credentials(str(problem)), describe(exc))
