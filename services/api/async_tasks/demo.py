"""Tasks that only exist to SHOW the machinery (Flower, the retries, the dead-letter queue). They do nothing useful.

They are NOT loaded in production: ``services/celery_app.py`` imports this module only when the worker starts with ``CELERY_DEMO_TASKS=1``.
They go through the same base class as the real task, so what they show is what the real task does.

    demo_ok(seconds)          sleeps and succeeds (returns its pid) -> SUCCESS in Flower
    demo_fail()               always raises                    -> retries, then the dead-letter queue, FAILURE in Flower
    demo_flaky(fail_times)    fails ``fail_times`` times       -> retries, then SUCCESS
"""

from __future__ import annotations

import os
import time

from services.celery_app import app

from .base import MAX_RETRIES, ObservedTask, run_with_retries


@app.task(bind=True, base=ObservedTask, name="async_tasks.demo_ok", max_retries=MAX_RETRIES)
def demo_ok(self, seconds: float = 1.0) -> dict:
    time.sleep(seconds)
    return {"slept": seconds, "pid": os.getpid()}  # the pid: proof that it ran in the worker's process, not in the API's


@app.task(bind=True, base=ObservedTask, name="async_tasks.demo_fail", max_retries=MAX_RETRIES)
def demo_fail(self) -> None:
    def work() -> None:
        raise RuntimeError("demo: this task always fails (connect to postgresql://demo_user:demo_secret@db.example.com:5432/demo timed out)")

    return run_with_retries(self, work)


@app.task(bind=True, base=ObservedTask, name="async_tasks.demo_flaky", max_retries=MAX_RETRIES)
def demo_flaky(self, fail_times: int = 1) -> dict:
    def work() -> dict:
        if self.request.retries < fail_times:  # the attempt number decides: no state to keep between attempts
            raise RuntimeError(f"demo: attempt {self.request.retries + 1} fails on purpose")
        return {"attempts": self.request.retries + 1}

    return run_with_retries(self, work)
