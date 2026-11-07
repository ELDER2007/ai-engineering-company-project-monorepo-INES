"""Pure transformation logic of the weekly office/programme performance report.

No I/O and no Prefect here: the tasks of ``data/pipelines/pipeline.py`` call these functions, and the unit tests call
them directly with synthetic events.

It works on the real telemetry contract (``telemetry_events``: ``event_type``, ``timestamp`` and the ``tags`` JSON, which
is the event's ``properties``). One output row per ``office`` x ``programme_id`` x ISO week. Money arrives in minor units
(``total_cost_minor``, cents) and leaves in currency units. It is never converted between currencies: EUR (Valencia)
and USD (Miami) stay in separate rows.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Iterable, Mapping

INBOUND = "inbound_order_created"
OUTBOUND = "outbound_order_created"
SHORTAGE = "stock_threshold_triggered"
COST_VARIANCE = "kit_cost_variance_detected"
EVENT_TYPES: tuple[str, ...] = (INBOUND, OUTBOUND, SHORTAGE, COST_VARIANCE)

OFFICE_CURRENCY: dict[str, str] = {"valencia": "EUR", "miami": "USD"}
CENT = Decimal("0.01")


class CurrencyMismatchError(ValueError):
    """An event carries a currency that is not its office's currency (business rule)."""


class ReconciliationError(ValueError):
    """The aggregated numbers do not add up to the events they came from: the report must not be published."""


@dataclass(frozen=True)
class TelemetryEvent:
    event_type: str
    timestamp: datetime
    tags: Mapping[str, Any]
    event_id: str | None = None


@dataclass(frozen=True)
class RejectedEvent:
    event: TelemetryEvent
    reason: str


@dataclass(frozen=True)
class CleanEvent:
    event_type: str
    office: str
    programme_id: str
    currency: str
    order_id: str
    cost: Decimal  # currency units; only meaningful for INBOUND, zero otherwise


@dataclass(frozen=True)
class WeeklyRow:
    office: str
    programme_id: str
    week_start: date
    total_material_cost: Decimal
    kits_delivered_count: int
    shortage_events_count: int
    cost_variance_events_count: int
    currency: str


@dataclass
class ValidationResult:
    valid: list[CleanEvent] = field(default_factory=list)
    rejected: list[RejectedEvent] = field(default_factory=list)

    def rejected_by_reason(self) -> dict[str, int]:
        return dict(Counter(r.reason for r in self.rejected))


@dataclass
class Aggregation:
    """What the aggregation produced and the de-duplicated events it came from (reconciliation needs both)."""

    rows: list[WeeklyRow]
    events: list[CleanEvent]
    duplicates_removed: int


# --------------------------------------------------------------------------- week window


def week_start_of(day: date) -> date:
    """Monday of the ISO week containing ``day``."""
    return day - timedelta(days=day.weekday())


def resolve_week_window(
    week_start: date | None = None, today: date | None = None
) -> tuple[date, datetime, datetime]:
    """``(week_start, start, end)`` with ``[start, end)`` in UTC.

    ``week_start`` is snapped to its Monday. When omitted, the last *complete* ISO week before ``today`` (UTC).
    """
    if week_start is None:
        today = today or datetime.now(timezone.utc).date()
        week_start = week_start_of(today) - timedelta(days=7)
    else:
        week_start = week_start_of(week_start)
    start = datetime(week_start.year, week_start.month, week_start.day, tzinfo=timezone.utc)
    return week_start, start, start + timedelta(days=7)


def ensure_utc(value: datetime) -> datetime:
    """Naive datetimes (SQLite) are taken as UTC."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


# --------------------------------------------------------------------------- validation


def _minor_to_units(value: Any) -> Decimal | None:
    """An integer amount in minor units (cents) -> currency units. ``None`` when it is not a non-negative integer."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return (Decimal(value) / 100).quantize(CENT)


def material_cost(tags: Mapping[str, Any]) -> Decimal | None:
    """``total_cost_minor`` in currency units, or ``unit_cost_minor * quantity`` when only the unit cost is present."""
    if tags.get("total_cost_minor") is not None:
        return _minor_to_units(tags["total_cost_minor"])
    unit, quantity = tags.get("unit_cost_minor"), tags.get("quantity")
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0 or not isinstance(unit, int) or isinstance(unit, bool):
        return None
    return _minor_to_units(unit * quantity)


def validate_events(events: Iterable[TelemetryEvent]) -> ValidationResult:
    """Split events into clean ones and rejected ones (with the reason). Never raises."""
    result = ValidationResult()
    for event in events:
        reason = _reject_reason(event)
        if reason:
            result.rejected.append(RejectedEvent(event, reason))
            continue
        tags = event.tags
        result.valid.append(
            CleanEvent(
                event_type=event.event_type,
                office=str(tags["office"]).strip().lower(),
                programme_id=str(tags["programme_id"]).strip(),
                currency=str(tags["currency"]).strip().upper(),
                order_id=str(tags["order_id"]).strip(),
                cost=material_cost(tags) if event.event_type == INBOUND else Decimal(0),  # type: ignore[arg-type]
            )
        )
    return result


def _reject_reason(event: TelemetryEvent) -> str | None:
    if event.event_type not in EVENT_TYPES:
        return "unsupported event_type"
    tags = event.tags or {}
    if str(tags.get("office") or "").strip().lower() not in OFFICE_CURRENCY:
        return "missing or unknown office"
    if not str(tags.get("programme_id") or "").strip():
        return "missing programme_id"
    if not str(tags.get("currency") or "").strip():
        return "missing currency"
    if not str(tags.get("order_id") or "").strip():
        return "missing order_id"
    if event.event_type == INBOUND and material_cost(tags) is None:
        return "inbound_order_created without a valid cost"
    return None


def check_currency_consistency(events: Iterable[CleanEvent]) -> None:
    """Fail when an event's currency is not its office's (EUR for valencia, USD for miami)."""
    bad = sorted({(e.office, e.currency) for e in events if e.currency != OFFICE_CURRENCY[e.office]})
    if bad:
        raise CurrencyMismatchError("currency does not match the office: " + ", ".join(f"{o}/{c}" for o, c in bad))


# --------------------------------------------------------------------------- aggregation


def dedupe_events(events: Iterable[CleanEvent]) -> tuple[list[CleanEvent], int]:
    """Count each (``event_type``, ``order_id``) once. The source already guarantees a unique ``event_id``; this is the
    second line of defence, for an order that arrived with two different event ids. Order-preserving."""
    events = list(events)
    seen: set[tuple[str, str]] = set()
    unique: list[CleanEvent] = []
    for event in events:
        key = (event.event_type, event.order_id)
        if key in seen:
            continue
        seen.add(key)
        unique.append(event)
    return unique, len(events) - len(unique)


def aggregate_by_office_programme(events: Iterable[CleanEvent], week_start: date) -> Aggregation:
    """De-duplicate, then compute the four KPIs per (office, programme_id). Sorted for deterministic output."""
    unique, duplicates = dedupe_events(list(events))
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for e in unique:
        b = buckets.setdefault(
            (e.office, e.programme_id),
            {"cost": Decimal(0), "kits": 0, "short": 0, "var": 0, "currency": OFFICE_CURRENCY[e.office]},
        )
        if e.event_type == INBOUND:
            b["cost"] += e.cost
        elif e.event_type == OUTBOUND:
            b["kits"] += 1
        elif e.event_type == SHORTAGE:
            b["short"] += 1
        elif e.event_type == COST_VARIANCE:
            b["var"] += 1
    rows = [
        WeeklyRow(
            office=office,
            programme_id=programme,
            week_start=week_start,
            total_material_cost=b["cost"],
            kits_delivered_count=b["kits"],
            shortage_events_count=b["short"],
            cost_variance_events_count=b["var"],
            currency=b["currency"],
        )
        for (office, programme), b in sorted(buckets.items())
    ]
    return Aggregation(rows=rows, events=unique, duplicates_removed=duplicates)


def reconcile(aggregation: Aggregation, *, events_read: int, rejected_count: int, valid_count: int) -> dict[str, Any]:
    """Prove the report adds up; raise ``ReconciliationError`` when it does not.

    1. every event read is either valid or rejected;
    2. valid = unique + duplicates removed;
    3. the per-row counts and costs sum to what the unique events contain, type by type.
    """
    problems: list[str] = []
    if events_read != valid_count + rejected_count:
        problems.append(f"events_read {events_read} != valid {valid_count} + rejected {rejected_count}")
    if valid_count != len(aggregation.events) + aggregation.duplicates_removed:
        problems.append("valid events != unique events + duplicates removed")
    expected = Counter(e.event_type for e in aggregation.events)
    got = {
        OUTBOUND: sum(r.kits_delivered_count for r in aggregation.rows),
        SHORTAGE: sum(r.shortage_events_count for r in aggregation.rows),
        COST_VARIANCE: sum(r.cost_variance_events_count for r in aggregation.rows),
    }
    for event_type, total in got.items():
        if total != expected.get(event_type, 0):
            problems.append(f"{event_type}: rows add up to {total}, events are {expected.get(event_type, 0)}")
    expected_cost = sum((e.cost for e in aggregation.events if e.event_type == INBOUND), Decimal(0))
    got_cost = sum((r.total_material_cost for r in aggregation.rows), Decimal(0))
    if got_cost != expected_cost:
        problems.append(f"total cost: rows add up to {got_cost}, events are {expected_cost}")
    if problems:
        raise ReconciliationError("; ".join(problems))
    return {"ok": True, "events_read": events_read, "valid": valid_count, "rejected": rejected_count,
            "unique": len(aggregation.events), "duplicates_removed": aggregation.duplicates_removed}
