"""In-memory sliding-window counters, used to slow down abuse of public endpoints.

Like TinyDB, this is single-process state: a second API worker would keep its own counters,
and a restart forgets them. Behind a reverse proxy the client address is the proxy's unless
the server trusts the forwarded headers (``uvicorn --proxy-headers``); see the README.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable
from threading import Lock

from fastapi import Request


class SlidingWindowLimiter:
    """At most ``limit`` events per key inside the last ``window_seconds``."""

    def __init__(self, limit: int, window_seconds: int, clock: Callable[[], float] = time.monotonic):
        self.limit = limit
        self.window = window_seconds
        self._clock = clock
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        events = self._events[key]
        while events and now - events[0] >= self.window:
            events.popleft()
        if not events:
            self._events.pop(key, None)  # keys that went quiet do not pile up in memory
        return events

    def retry_after(self, key: str) -> int:
        """Seconds until ``key`` may act again; 0 when it is under the limit."""
        with self._lock:
            now = self._clock()
            events = self._prune(key, now)
            if len(events) < self.limit:
                return 0
            return max(1, int(events[0] + self.window - now) + 1)

    def record(self, key: str) -> None:
        with self._lock:
            now = self._clock()
            self._prune(key, now)
            self._events[key].append(now)

    def clear(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


def client_host(request: Request) -> str:
    return request.client.host if request.client else "unknown"
