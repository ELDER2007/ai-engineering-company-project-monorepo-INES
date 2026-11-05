"""Demo ``telemetry_events`` for LOCAL development only.

The real table is owned by the telemetry domain; this creates a minimal copy of it (and
fills it) so the pipeline can run end to end without it. Deterministic, idempotent
(``seed_telemetry`` replaces the demo rows). Follows the seed targets of the telemetry
BRIEFING: 7 materials over the 3 categories, 3 programmes, 14 inbound + 14 outbound orders,
2 stock-threshold events and 1 cost-variance event, over two ISO weeks.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete
from sqlalchemy.engine import Engine

from data.pipelines.weekly_office_performance.storage import source_metadata, telemetry_events

PROGRAMMES = ("b2b-sales", "onboarding-agents", "consultant-cert")
OFFICES = {"valencia": "EUR", "miami": "USD"}

# (product_id, product_category)
PRODUCTS = [
    ("KIT-SALES-01", "training_kit"),
    ("KIT-ONBRD-01", "training_kit"),
    ("KIT-CONSULT-01", "training_kit"),
    ("CERT-B2B-01", "certification"),
    ("CERT-CONSULT-01", "certification"),
    ("EQ-LAPTOP-BAG", "onboarding_equipment"),
    ("EQ-WELCOME-PACK", "onboarding_equipment"),
]
# Mondays of the two seeded weeks.
WEEKS = (datetime(2026, 10, 19, tzinfo=timezone.utc), datetime(2026, 10, 26, tzinfo=timezone.utc))


def _event(event_type: str, week: int, day: int, hour: int, **props):
    base = WEEKS[week]
    return {
        "event_type": event_type,
        "occurred_at": base.replace(day=base.day + day, hour=hour),
        "properties": props,
    }


def build_events() -> list[dict]:
    events: list[dict] = []
    for i in range(14):  # inbound orders
        office = "valencia" if i % 2 == 0 else "miami"
        product, category = PRODUCTS[i % len(PRODUCTS)]
        quantity = 10 + (i % 5) * 5
        events.append(
            _event(
                "inbound_order_created", i % 2, i % 5, 9 + i % 6,
                office=office, product_id=product, product_category=category,
                programme_id=PROGRAMMES[i % 3], quantity=quantity,
                total_cost=round(quantity * (11.5 + i), 2), currency=OFFICES[office],
            )
        )
    for i in range(14):  # outbound orders (kit / certificate deliveries)
        office = "miami" if i % 3 == 0 else "valencia"
        product, category = PRODUCTS[(i + 2) % len(PRODUCTS)]
        events.append(
            _event(
                "outbound_order_created", (i + 1) % 2, (i + 1) % 5, 10 + i % 6,
                office=office, product_id=product, product_category=category,
                programme_id=PROGRAMMES[(i + 1) % 3], quantity=1 + i % 3, currency=OFFICES[office],
            )
        )
    for office, programme, product in (("valencia", "b2b-sales", "KIT-SALES-01"), ("miami", "consultant-cert", "CERT-CONSULT-01")):
        events.append(
            _event(
                "stock_threshold_triggered", 1, 2, 15,
                office=office, product_id=product, product_category="training_kit",
                programme_id=programme, quantity=2, currency=OFFICES[office],
            )
        )
    events.append(  # supplier price jump > 10 %
        _event(
            "kit_cost_variance_detected", 1, 3, 11,
            office="miami", product_id="KIT-ONBRD-01", product_category="training_kit",
            programme_id="onboarding-agents", quantity=1, currency="USD",
        )
    )
    return events


def seed_telemetry(engine: Engine) -> int:
    """(Re)create ``telemetry_events`` locally and load the demo events. Returns the count."""
    source_metadata.create_all(engine)
    events = build_events()
    with engine.begin() as connection:
        connection.execute(delete(telemetry_events))
        connection.execute(telemetry_events.insert(), events)
    return len(events)
