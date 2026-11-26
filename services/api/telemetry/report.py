"""The technical report as a service: run the analysis pipeline (``analysis.py``) once per window and cache the result (``report_cache.py``).

The router only parses the query and calls ``get_report``; nothing here knows about HTTP, and nothing is computed per request when a
cached entry is alive.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlmodel import Session

from . import analysis
from .report_cache import report_cache


def _utc(moment: datetime | None) -> datetime | None:
    """Naive datetimes are taken as UTC (the table stores UTC); aware ones are converted to it."""
    if moment is None:
        return None
    return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment.astimezone(timezone.utc)


DEFAULT_WINDOW_DAYS = 7


def resolve_window(start_date: datetime | None, end_date: datetime | None, now: datetime | None = None) -> tuple[datetime, datetime]:
    """The ``[start, end)`` period of a request, in UTC, resolved once: ``end_date`` defaults to now and ``start_date`` to 7 days before
    ``end_date``. Both bounds are always returned, so every analysis function receives the same window and applies it once, in SQL
    (none has a default of its own)."""
    end = _utc(end_date) or _utc(now) or datetime.now(timezone.utc)
    start = _utc(start_date) or end - timedelta(days=DEFAULT_WINDOW_DAYS)
    return start, end


def get_report(
    session: Session, start_date: datetime | None = None, end_date: datetime | None = None, environment: str | None = None, refresh: bool = False
) -> dict[str, Any]:
    """The report for the requested period, from the cache when a live entry exists (unless ``refresh``): nothing is recomputed within the
    TTL. The cache key is what was ASKED (``start_date``/``end_date``, ``None`` when omitted), not the resolved window: a default request
    resolves "now" to a different instant every time, and keying on it would make the cache useless exactly for the default call. The
    answer says whether it came from the cache and how old it is, so a reader never mistakes a cached figure for a fresh one."""
    key = (_utc(start_date), _utc(end_date), environment)
    if not refresh and (hit := report_cache.get(key)) is not None:
        payload, age = hit
        return {**payload, "cached": True, "cache_age_seconds": round(age, 1)}
    start, end = resolve_window(start_date, end_date)
    built = analysis.build_report(session, start, end, environment)
    payload = {
        "period": {"from": start.isoformat(), "to": end.isoformat()},
        "metrics": built["metrics"],
        "findings": built["findings"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": environment,
        "truncated": built["truncated"],
    }
    report_cache.set(key, payload)
    return {**payload, "cached": False, "cache_age_seconds": 0.0}
