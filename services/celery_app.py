"""The Celery application of the monorepo (ticket DEV-55): Redis as the broker AND as the result backend.

The API never runs the heavy work: it leaves a small message in Redis (the *broker*) and answers at once; a worker, a process of its own,
takes the message, does the work and leaves the outcome in Redis (the *result backend*), where ``GET /tasks/{task_id}`` reads it.

Start a worker (from the root of the repository)::

    celery -A services.celery_app worker --loglevel=INFO -E

Everything that can change between machines comes from the environment, never from the code:

* ``REDIS_URL``            the Redis of the broker, ``redis://host:6379/0``. The same one for the API and for every worker.
* ``REDIS_RESULT_URL``     optional: where the outcomes are kept. By default the same server, database ``/1``.
* ``ASYNC_RETRY_BASE_SECONDS``  the first wait before a retry (default 5); it doubles every time.
* ``CELERY_DEMO_TASKS=1``  also load ``async_tasks.demo`` (tasks that only exist to show Flower and the dead-letter queue). Off by default.

The tasks live in ``services/api/async_tasks/``: they need the API's own modules (the database, the pipeline), so that folder is put on
``sys.path`` here, and the root of the repository too (``data.pipelines``), exactly like ``reporting/__init__.py`` does for the API.
Importing this module opens no connection to Redis.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from celery import Celery

_SERVICES = Path(__file__).resolve().parent
_REPO_ROOT = _SERVICES.parent  # /app in the Docker image, the root of the clone on a developer's machine
for _path in (str(_SERVICES / "api"),):
    if _path not in sys.path:
        sys.path.insert(0, _path)
if str(_REPO_ROOT) not in sys.path:
    sys.path.append(_REPO_ROOT.as_posix())  # at the END: it must never shadow an installed package

DEFAULT_REDIS_URL = "redis://localhost:6379/0"  # only for a developer running Redis on the same machine; Docker sets REDIS_URL

# A task is cut off softly (it gets SoftTimeLimitExceeded and can clean up) and then hard (the process is killed). Every task has both:
# a task without a timeout can hold a worker forever. The pipeline has its own retries inside (waits of 5, 30 and 120 s), so the limits are
# generous: the soft one is longer than the pipeline's worst case.
SOFT_TIME_LIMIT_SECONDS = 600
HARD_TIME_LIMIT_SECONDS = 660
# Redis hands a message to another worker if nobody confirmed it within this time (a worker that died without confirming). It must be LONGER
# than any task plus any retry wait, or a task that is still running would be delivered a second time.
VISIBILITY_TIMEOUT_SECONDS = 900  # 15 min: longer than the hard limit (11 min) plus a retry wait, short enough to recover a task of a dead worker
RESULT_EXPIRES_SECONDS = 24 * 3600  # the outcomes are not kept forever: Redis has a fixed memory (see docker-compose.yml)


def broker_url() -> str:
    return os.environ.get("REDIS_URL", "").strip() or DEFAULT_REDIS_URL


def result_backend_url() -> str:
    """Where the outcomes are kept: ``REDIS_RESULT_URL``, or the broker's server with database ``/1`` (the queue is ``/0``)."""
    explicit = os.environ.get("REDIS_RESULT_URL", "").strip()
    if explicit:
        return explicit
    parts = urlsplit(broker_url())
    return urlunsplit(parts._replace(path="/1"))


def _demo_enabled() -> bool:
    return os.environ.get("CELERY_DEMO_TASKS", "").strip() == "1"


app = Celery(
    "nexova",
    broker=broker_url(),
    backend=result_backend_url(),
    include=["async_tasks.tasks"] + (["async_tasks.demo"] if _demo_enabled() else []),
)

app.conf.update(
    # What travels is JSON and light: identifiers and small parameters, never a payload of data (see async_tasks/base.py).
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # The states the API reports: without ``task_track_started`` a task goes from PENDING straight to SUCCESS and "started" never exists.
    task_track_started=True,
    # The message is confirmed AFTER the task ends, not when it starts: if the worker dies half way, Redis delivers the message again.
    # (The pipeline is idempotent: running a week twice rewrites the same rows.)
    task_acks_late=True,
    worker_prefetch_multiplier=1,  # one message at a time per process: a slow task never holds messages that another worker could take
    task_soft_time_limit=SOFT_TIME_LIMIT_SECONDS,
    task_time_limit=HARD_TIME_LIMIT_SECONDS,
    result_expires=RESULT_EXPIRES_SECONDS,
    # Redis
    broker_transport_options={"visibility_timeout": VISIBILITY_TIMEOUT_SECONDS, "socket_connect_timeout": 2, "socket_keepalive": True},
    result_backend_transport_options={"retry_policy": {"timeout": 5.0}},
    broker_connection_timeout=2,
    broker_connection_retry_on_startup=True,  # the worker waits for Redis instead of dying if it starts first
    # When the API publishes and Redis is down, fail fast (the endpoint answers 503) instead of retrying for many seconds.
    task_publish_retry=True,
    task_publish_retry_policy={"max_retries": 1, "interval_start": 0, "interval_step": 0.2, "interval_max": 0.5},
    # Flower needs events to show queued, running and finished tasks.
    worker_send_task_events=True,
    task_send_sent_event=True,
    timezone="UTC",
    enable_utc=True,
)
