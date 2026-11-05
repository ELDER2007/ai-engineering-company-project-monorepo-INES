"""Pure transformation logic of the weekly office/programme performance report.

No I/O and no Prefect here: the Prefect tasks in ``data/pipelines/weekly_office_performance``
call these functions, and the unit tests call them directly with synthetic events.

One output row per ``office`` x ``programme_id`` x ISO week (see PIPELINE_DESIGN.md, sections 2-4).
Money is never converted: EUR (Valencia) and USD (Miami) stay in separate rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

INBOUND = "inbound_order_created"
OUTBOUND = "outbound_order_created"
SHORTAGE = "stock_threshold_triggered"
COST_VARIANCE = "kit_cost_variance_detected"
EVENT_TYPES: tuple[str, ...] = (INBOUND, OUTBOUND, SHORTAGE, COST_VARIANCE)

OFFICE_CURRENCY: dict[str, str] = {"valencia": "EUR", "miami": "USD"}


class CurrencyMismatchError(ValueError):
    """An event carries a currency that is not its office's currency (business rule, section 7)."""


@dataclass(frozen=True)
class TelemetryEvent:
    event_type: str
    occurred_at: datetime
    properties: Mapping[str, Any]
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
    cost: Decimal  # only meaningful for INBOUND; zero otherwise


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


# --------------------------------------------------------------------------- week window


def week_start_of(day: date) -> date:
    """Monday of the ISO week containing ``day``."""
    return day - timedelta(days=day.weekday())


def resolve_week_window(
    week_start: date | None = None, today: date | None = None
) -> tuple[date, datetime, datetime]:
    """``(week_start, start, end)`` with ``[start, end)`` in UTC.

    ``week_start`` is snapped to its Monday. When omitted, the last *complete* ISO week
    before ``today`` (UTC) is used.
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


def _to_decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None
    return number if number.is_finite() and number >= 0 else None


def material_cost(properties: Mapping[str, Any]) -> Decimal | None:
    """``total_cost``, or ``unit_cost * quantity`` when only the unit cost is present."""
    if properties.get("total_cost") is not None:
        return _to_decimal(properties["total_cost"])
    unit, quantity = _to_decimal(properties.get("unit_cost")), _to_decimal(properties.get("quantity"))
    if unit is None or quantity is None:
        return None
    return unit * quantity


def validate_events(events: Iterable[TelemetryEvent]) -> ValidationResult:
    """Split events into clean ones and rejected ones (with the reason). Never raises."""
    result = ValidationResult()
    for event in events:
        reason = _reject_reason(event)
        if reason:
            result.rejected.append(RejectedEvent(event, reason))
            continue
        props = event.properties
        result.valid.append(
            CleanEvent(
                event_type=event.event_type,
                office=str(props["office"]).strip().lower(),
                programme_id=str(props["programme_id"]).strip(),
                currency=str(props["currency"]).strip().upper(),
                cost=material_cost(props) if event.event_type == INBOUND else Decimal(0),  # type: ignore[arg-type]
            )
        )
    return result


def _reject_reason(event: TelemetryEvent) -> str | None:
    if event.event_type not in EVENT_TYPES:
        return f"unsupported event_type {event.event_type!r}"
    props = event.properties or {}
    office = str(props.get("office") or "").strip().lower()
    if office not in OFFICE_CURRENCY:
        return "missing or unknown office"
    if not str(props.get("programme_id") or "").strip():
        return "missing programme_id"
    if not str(props.get("currency") or "").strip():
        return "missing currency"
    if event.event_type == INBOUND and material_cost(props) is None:
        return "inbound_order_created without a valid cost"
    return None


def check_currency_consistency(events: Iterable[CleanEvent]) -> None:
    """Fail when an event's currency is not its office's (EUR for valencia, USD for miami)."""
    bad = sorted({(e.office, e.currency) for e in events if e.currency != OFFICE_CURRENCY[e.office]})
    if bad:
        raise CurrencyMismatchError(
            "currency does not match the office: " + ", ".join(f"{o}/{c}" for o, c in bad)
        )


# --------------------------------------------------------------------------- aggregation


def aggregate_by_office_programme(events: Iterable[CleanEvent], week_start: date) -> list[WeeklyRow]:
    """Compute the four KPIs per (office, programme_id). Sorted for deterministic output."""
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for e in events:
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
    return [
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
