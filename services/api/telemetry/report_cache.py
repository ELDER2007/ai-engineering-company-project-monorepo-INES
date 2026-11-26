"""In-memory TTL cache for the technical report.

Building the report reads every event of the window and aggregates it, which is wasted work when the same window is asked
twice within seconds (a dashboard that refreshes, several admins). An entry lives ``TTL_SECONDS`` and is also dropped as soon as
this process stores a new event (``invalidate``, called by ``store.save``), so a report never hides an event the API itself
just received.

Limits, on purpose and in the open: it is per process and non-persistent. A second API worker has its own cache and does not see
the other's invalidations, so there the TTL is the only bound on staleness (at most ``TTL_SECONDS``); a restart empties it. The
number of entries is bounded because the key comes from the caller (any ``since``/``until``).
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Hashable
from typing import Any

TTL_SECONDS = 60
MAX_ENTRIES = 32


class TTLCache:
    def __init__(self, ttl_seconds: float = TTL_SECONDS, max_entries: int = MAX_ENTRIES, clock: Callable[[], float] = time.monotonic):
        self._ttl = ttl_seconds
        self._max = max_entries
        self._clock = clock  # injectable so tests move time without sleeping
        self._entries: OrderedDict[Hashable, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()  # the endpoint is sync, so FastAPI runs it on several threads

    def get(self, key: Hashable) -> tuple[Any, float] | None:
        """``(value, age in seconds)`` of a live entry, or ``None`` when absent or expired (an expired one is removed)."""
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            stored_at, value = entry
            age = self._clock() - stored_at
            if age >= self._ttl:
                del self._entries[key]
                return None
            self._entries.move_to_end(key)
            return value, age

    def set(self, key: Hashable, value: Any) -> None:
        with self._lock:
            self._entries[key] = (self._clock(), value)
            self._entries.move_to_end(key)
            while len(self._entries) > self._max:
                self._entries.popitem(last=False)  # the least recently used

    def invalidate(self) -> None:
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


report_cache = TTLCache()
