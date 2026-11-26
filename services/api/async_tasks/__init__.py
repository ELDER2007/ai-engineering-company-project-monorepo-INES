"""Asynchronous tasks of the API (ticket DEV-55): the heavy work that a request must not wait for.

``services/celery_app.py`` is the Celery application; this package holds what runs inside a worker:

* ``base``     the base class of every task: ONE log line per execution, light messages, and the dead-letter queue on the final failure.
* ``dlq``      the dead-letter queue: the table ``task_dead_letters`` in the API's own database.
* ``tasks``    the tasks. Today: the weekly business-performance pipeline.
* ``router``   the HTTP side: ``POST /tasks/pipeline-runs`` (202 + ``task_id``) and ``GET /tasks/{task_id}``.
* ``demo``     tasks that only exist to show Flower and the dead-letter queue. Loaded only with ``CELERY_DEMO_TASKS=1``.

The tasks do NOT import FastAPI: a worker is a process of its own and does not need the web application. ``router`` is the only module here
that does, and the worker never imports it.
"""

from __future__ import annotations

import sys
from pathlib import Path

# ``services.celery_app`` lives next to ``services/api``: with the root of the repository on the path it is importable as ``services.celery_app``
# (a namespace package, ``services/`` has no ``__init__.py``) both from a worker and from the API. At the END, like reporting/__init__.py.
_REPO_ROOT = str(Path(__file__).resolve().parents[3])
if _REPO_ROOT not in sys.path:
    sys.path.append(_REPO_ROOT)
