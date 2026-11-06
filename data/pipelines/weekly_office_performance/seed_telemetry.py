"""Demo ``telemetry_events`` for LOCAL demos and tests only.

Creates a copy of the table with the real columns and fills it with events in the real shape of the telemetry contract
(``tags`` = the event's properties, money in minor units, ``order_id``, ``supplier_id``...), over two ISO weeks
(2026-10-19 and 2026-10-26). Deterministic: the same call gives the same rows. It is never used against the app's own
database: ``python -m data.pipelines.pipeline --demo`` works on a throw-away file.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete
from sqlalchemy.engine import Engine

from data.pipelines.weekly_office_performance.storage import source_metadata, telemetry_events

PROGRAMMES = ("ventas-b2b", "liderazgo-basico", "onboarding-soporte")
OFFICES = {"valencia": "EUR", "miami": "USD"}
SUPPLIERS = ("supplier-print-01", "supplier-cert-01", "supplier-hardware-01")
# (product_id, product_category)
PRODUCTS = [
    ("product-001", "training_kit"), ("product-002", "training_kit"), ("product-003", "training_kit"),
    ("product-004", "certification"), ("product-005", "certification"),
    ("product-006", "onboarding_equipment"), ("product-007", "onboarding_equipment"),
]
WEEKS = (datetime(2026, 10, 19, tzinfo=timezone.utc), datetime(2026, 10, 26, tzinfo=timezone.utc))
_NAMESPACE = uuid.UUID("5a1c2d3e-0000-4000-8000-000000000001")


def _row(event_type: str, week: int, day: int, hour: int, environment: str, key: str, **tags) -> dict:
    base = WEEKS[week]
    return {
        "event_id": str(uuid.uuid5(_NAMESPACE, f"{environment}:{key}")),
        "event_type": event_type,
        "timestamp": base.replace(day=base.day + day, hour=hour),
        "service": "inventory_api",
        "user_id": None,
        "session_id": str(uuid.uuid5(_NAMESPACE, f"session:{week}:{day}")),
        "environment": environment,
        "tags": tags,
    }


def build_events(environment: str = "production") -> list[dict]:
    events: list[dict] = []
    for i in range(14):  # inbound orders: cost in minor units
        office = "valencia" if i % 2 == 0 else "miami"
        product, category = PRODUCTS[i % len(PRODUCTS)]
        quantity, unit = 10 + (i % 5) * 5, 1150 + i * 100
        events.append(_row(
            "inbound_order_created", i % 2, i % 5, 9 + i % 6, environment, f"in-{i}",
            office=office, product_id=product, product_category=category, programme_id=PROGRAMMES[i % 3],
            quantity=quantity, currency=OFFICES[office], order_id=f"in-{i:03d}", supplier_id=SUPPLIERS[i % 3],
            unit_cost_minor=unit, total_cost_minor=quantity * unit,
        ))
    for i in range(14):  # outbound orders (kit / certificate deliveries)
        office = "miami" if i % 3 == 0 else "valencia"
        product, category = PRODUCTS[(i + 2) % len(PRODUCTS)]
        events.append(_row(
            "outbound_order_created", (i + 1) % 2, (i + 1) % 5, 10 + i % 6, environment, f"out-{i}",
            office=office, product_id=product, product_category=category, programme_id=PROGRAMMES[(i + 1) % 3],
            quantity=1 + i % 3, currency=OFFICES[office], order_id=f"out-{i:03d}", stock_before=30, stock_after=29,
        ))
    for n, (office, programme, product) in enumerate((("valencia", "ventas-b2b", "product-001"), ("miami", "liderazgo-basico", "product-004"))):
        events.append(_row(
            "stock_threshold_triggered", 1, 2, 15, environment, f"short-{n}",
            office=office, product_id=product, product_category="training_kit", programme_id=programme,
            quantity=2, currency=OFFICES[office], order_id=f"out-short-{n}", stock_before=9, stock_after=7, minimum_stock=8,
        ))
    events.append(_row(  # supplier price jump above 10 %
        "kit_cost_variance_detected", 1, 3, 11, environment, "var-0",
        office="miami", product_id="product-002", product_category="training_kit", programme_id="onboarding-soporte",
        quantity=1, currency="USD", order_id="in-var-0", supplier_id="supplier-print-01", unit_cost_minor=1800,
        reference_unit_cost_minor=1500, baseline_order_count=5, variance_percent=20, threshold_percent=10,
    ))
    # a non-business event of the same week: the liveness signal (window_events_total counts it)
    events.append(_row("section_viewed", 1, 1, 8, environment, "view-0", section="inventory", route="/inventory"))
    return events


def seed_telemetry(engine: Engine, environment: str = "production") -> int:
    """(Re)create ``telemetry_events`` locally and load the demo events. Returns how many."""
    source_metadata.create_all(engine)
    events = build_events(environment)
    with engine.begin() as connection:
        connection.execute(delete(telemetry_events))
        connection.execute(telemetry_events.insert(), events)
    return len(events)
