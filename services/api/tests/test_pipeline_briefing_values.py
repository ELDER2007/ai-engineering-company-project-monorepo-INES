"""The KPI values are the ones the briefing defines ("KPIs a medir", section 4), not a reinterpretation of them.

The expected numbers are computed here, with plain loops that follow the briefing's own sentences, from the company's
official telemetry fixture (docs/telemetry/seed-data.json: 8 products, 3 programmes, 15 inbound and 15 outbound orders in
Valencia and Miami). The pipeline, run on the same events, must give exactly the same table."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from prefect.testing.utilities import prefect_test_harness
from sqlalchemy import select

from data.pipelines.pipeline import weekly_office_performance_flow
from data.pipelines.weekly_office_performance import storage

FIXTURE = Path(__file__).resolve().parents[3] / "docs" / "telemetry" / "seed-data.json"
pytestmark = pytest.mark.skipif(not FIXTURE.exists(), reason="the telemetry seed fixture is not in the repository")


@pytest.fixture(scope="module", autouse=True)
def prefect_harness():
    with prefect_test_harness():
        yield


def monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def at(created_at: str) -> datetime:
    return datetime.fromisoformat(created_at.replace("Z", "+00:00")).astimezone(timezone.utc)


def load():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    products = {p["product_id"]: p for p in fixture["products"]}
    events = []  # (event_type, timestamp, tags)

    def tags(order, product, **extra):
        return {"office": order["office"], "programme_id": product["programme_id"], "currency": order["currency"],
                "product_id": product["product_id"], "product_category": product["product_category"],
                "quantity": order["quantity"], "order_id": order["order_id"], **extra}

    by_id = {}
    for o in fixture["inbound_orders"]:
        by_id[o["order_id"]] = o
        events.append(("inbound_order_created", at(o["created_at"]), tags(o, products[o["product_id"]], supplier_id=o["supplier_id"],
                       unit_cost_minor=o["unit_cost_minor"], total_cost_minor=o["total_cost_minor"])))
    for o in fixture["outbound_orders"]:
        by_id[o["order_id"]] = o
        events.append(("outbound_order_created", at(o["created_at"]), tags(o, products[o["product_id"]])))
    derived = fixture["expected_derived_events"]
    for crossing in derived["stock_threshold_triggered"]:  # a threshold event happens with the outbound order that crossed it
        order = by_id[crossing["order_id"]]
        events.append(("stock_threshold_triggered", at(order["created_at"]),
                       tags(order, products[crossing["product_id"]], stock_before=crossing["stock_before"],
                            stock_after=crossing["stock_after"], minimum_stock=crossing["minimum_stock"])))
    variance = derived["kit_cost_variance_detected"]
    order = by_id[variance["order_id"]]
    events.append(("kit_cost_variance_detected", at(order["created_at"]), tags(order, products[variance["product_id"]], supplier_id=variance["supplier_id"])))
    return events, derived


def expected_by_the_briefing(events):
    """The four definitions of the briefing, one sentence each, applied with plain loops. Key: (office, programme, week)."""
    expected = defaultdict(lambda: {"cost": Decimal(0), "kits": 0, "short": 0, "var": 0, "currency": None})
    for event_type, when, t in events:
        row = expected[(t["office"], t["programme_id"], monday(when.date()))]
        row["currency"] = t["currency"]
        if event_type == "inbound_order_created":  # cost = "suma de los costos de inbound_order_created de la semana"
            row["cost"] += Decimal(t["total_cost_minor"]) / 100
        elif event_type == "outbound_order_created":  # kits = "conteo de outbound_order_created de la semana"
            row["kits"] += 1
        elif event_type == "stock_threshold_triggered":  # shortage = "conteo de stock_threshold_triggered de la semana"
            row["short"] += 1
        elif event_type == "kit_cost_variance_detected":  # variance = "conteo de kit_cost_variance_detected de la semana"
            row["var"] += 1
    return dict(expected)


@pytest.fixture()
def company_week_table(tmp_path):
    events, derived = load()
    source = storage.build_engine(f"sqlite:///{tmp_path / 'telemetry.sqlite'}")
    target = storage.build_engine(f"sqlite:///{tmp_path / 'reporting.sqlite'}")
    storage.source_metadata.create_all(source)
    with source.begin() as connection:
        connection.execute(storage.telemetry_events.insert(), [
            {"event_id": f"{i:08d}-0000-4000-8000-000000000000", "event_type": et, "timestamp": when, "service": "inventory_api",
             "environment": "production", "tags": tags} for i, (et, when, tags) in enumerate(events)])
    weeks = sorted({monday(when.date()) for _, when, _ in events})
    for week in weeks:
        weekly_office_performance_flow(week_start=week, refresh=True, source_engine=source, target_engine=target)
    with target.connect() as connection:
        table = {(r["office"], r["programme_id"], r["week_start"]): r
                 for r in connection.execute(select(storage.weekly_performance)).mappings()}
    yield events, derived, table
    source.dispose()
    target.dispose()


def test_the_fixture_is_the_one_the_plan_describes():
    events, derived = load()
    kinds = defaultdict(int)
    for et, _, _ in events:
        kinds[et] += 1
    assert kinds["inbound_order_created"] == derived["inbound_order_created_count"] == 15
    assert kinds["outbound_order_created"] == derived["outbound_order_created_count"] == 15
    assert kinds["stock_threshold_triggered"] == len(derived["stock_threshold_triggered"]) == 3
    assert kinds["kit_cost_variance_detected"] == 1


def test_every_cell_of_the_table_equals_what_the_briefing_definitions_give(company_week_table):
    events, _, table = company_week_table
    expected = expected_by_the_briefing(events)
    assert set(table) == set(expected)  # the same office / programme / week combinations, no more, no fewer
    for key, want in expected.items():
        got = table[key]
        assert Decimal(got["total_material_cost"]) == want["cost"], key  # "Costo de material por oficina/programa"
        assert got["kits_delivered_count"] == want["kits"], key  # "Kits entregados"
        assert got["shortage_events_count"] == want["short"], key  # "Frecuencia de escasez"
        assert got["cost_variance_events_count"] == want["var"], key  # "Frecuencia de variación de costo"
        assert got["currency"] == want["currency"], key


def test_the_totals_add_up_to_the_company_fixture(company_week_table):
    events, derived, table = company_week_table
    rows = list(table.values())
    assert sum(r["kits_delivered_count"] for r in rows) == derived["outbound_order_created_count"]
    assert sum(r["shortage_events_count"] for r in rows) == len(derived["stock_threshold_triggered"])
    assert sum(r["cost_variance_events_count"] for r in rows) == 1
    inbound_cost = sum(Decimal(t["total_cost_minor"]) / 100 for et, _, t in events if et == "inbound_order_created")
    assert sum(Decimal(r["total_material_cost"]) for r in rows) == inbound_cost


def test_euros_and_dollars_are_never_added_together(company_week_table):
    events, _, table = company_week_table
    by_currency = defaultdict(Decimal)
    for et, _, t in events:
        if et == "inbound_order_created":
            by_currency[t["currency"]] += Decimal(t["total_cost_minor"]) / 100
    for currency, total in by_currency.items():
        assert sum(Decimal(r["total_material_cost"]) for r in table.values() if r["currency"] == currency) == total
    assert {r["currency"] for r in table.values() if r["office"] == "valencia"} == {"EUR"}
    assert {r["currency"] for r in table.values() if r["office"] == "miami"} == {"USD"}


def test_a_kit_is_counted_per_delivery_order_as_the_briefing_says_not_per_unit(company_week_table):
    """The briefing: kits_delivered_count = "conteo de outbound_order_created". An order of 24 units is one."""
    events, _, table = company_week_table
    units = sum(t["quantity"] for et, _, t in events if et == "outbound_order_created")
    orders = sum(1 for et, _, _ in events if et == "outbound_order_created")
    assert units > orders  # the fixture has orders of several units, so the two readings differ
    assert sum(r["kits_delivered_count"] for r in table.values()) == orders
