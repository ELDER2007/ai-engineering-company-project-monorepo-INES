"""Validate the synthetic telemetry acceptance fixture using only the standard library."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


FIXTURE_PATH = Path(__file__).resolve().parents[1] / "docs/telemetry/seed-data.json"
CURRENCY_BY_OFFICE = {"valencia": "EUR", "miami": "USD"}
FORBIDDEN_KEYS = {"assigned_to", "customer_email", "description", "email", "name", "phone"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def check_no_sensitive_keys(value: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            require(key.casefold() not in FORBIDDEN_KEYS, f"Sensitive key present: {key}")
            check_no_sensitive_keys(child)
    elif isinstance(value, list):
        for child in value:
            check_no_sensitive_keys(child)


def main() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text())
    products = {product["product_id"]: product for product in fixture["products"]}
    inbound = fixture["inbound_orders"]
    outbound = fixture["outbound_orders"]
    expected = fixture["expected_derived_events"]
    author_id = fixture["synthetic_author_user_id"]

    require(len(products) == 8, "Expected exactly 8 products")
    require(
        {product["product_category"] for product in products.values()}
        == {"training_kit", "certification", "onboarding_equipment"},
        "Products must cover all three categories",
    )
    require(len({product["programme_id"] for product in products.values()}) >= 3, "Expected at least 3 programmes")
    require(len(inbound) == 15, "Expected exactly 15 inbound orders")
    require(len(outbound) == 15, "Expected exactly 15 outbound orders")
    require(re.fullmatch(r"[a-f0-9]{64}", author_id) is not None, "Synthetic author must match the 64-character pseudonym format")
    check_no_sensitive_keys(fixture)

    orders = inbound + outbound
    order_ids = [order["order_id"] for order in orders]
    require(len(order_ids) == len(set(order_ids)), "Order IDs must be unique")
    timeline = []
    for kind, items in (("inbound", inbound), ("outbound", outbound)):
        for order in items:
            product = products.get(order["product_id"])
            require(product is not None, f"Unknown product in {order['order_id']}")
            require(order["quantity"] > 0, f"Non-positive quantity in {order['order_id']}")
            require(order["office"] == product["office"], f"Office mismatch in {order['order_id']}")
            require(order["currency"] == CURRENCY_BY_OFFICE[order["office"]], f"Currency mismatch in {order['order_id']}")
            require(order["userId"] == author_id, f"Unattributed order {order['order_id']}")
            timestamp = parse_timestamp(order["created_at"])
            if kind == "inbound":
                require(order["total_cost_minor"] == order["quantity"] * order["unit_cost_minor"], f"Cost mismatch in {order['order_id']}")
            timeline.append((timestamp, kind, order))

    stock = defaultdict(int)
    history = defaultdict(list)
    threshold_events = []
    variance_events = []
    for _, kind, order in sorted(timeline, key=lambda entry: entry[0]):
        product = products[order["product_id"]]
        if kind == "inbound":
            key = (order["product_id"], order["supplier_id"], order["office"], order["currency"])
            baseline = history[key][-5:]
            if len(baseline) == 5:
                reference = (
                    Decimal(sum(item["quantity"] * item["unit_cost_minor"] for item in baseline))
                    / sum(item["quantity"] for item in baseline)
                ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
                if reference > 0:
                    variance = Decimal(abs(order["unit_cost_minor"] - int(reference))) * 100 / reference
                    if variance > 10:
                        variance_events.append(
                            {
                                "order_id": order["order_id"],
                                "product_id": order["product_id"],
                                "supplier_id": order["supplier_id"],
                                "baseline_order_ids": [item["order_id"] for item in baseline],
                                "baseline_order_count": 5,
                                "reference_unit_cost_minor": int(reference),
                                "unit_cost_minor": order["unit_cost_minor"],
                                "variance_percent": float(variance),
                                "threshold_percent": 10,
                            }
                        )
            history[key].append(order)
            stock[order["product_id"]] += order["quantity"]
            continue

        before = stock[order["product_id"]]
        after = before - order["quantity"]
        require(after >= 0, f"Negative stock after {order['order_id']}")
        if before >= product["minimum_stock"] and after < product["minimum_stock"]:
            threshold_events.append(
                {
                    "order_id": order["order_id"],
                    "product_id": order["product_id"],
                    "stock_before": before,
                    "stock_after": after,
                    "minimum_stock": product["minimum_stock"],
                }
            )
        stock[order["product_id"]] = after

    require(threshold_events == expected["stock_threshold_triggered"], "Threshold events do not match expected crossings")
    require(len(threshold_events) >= 2, "Expected at least two stock threshold crossings")
    require(len(variance_events) == 1, "Expected exactly one cost variance event")
    require(variance_events[0] == expected["kit_cost_variance_detected"], "Cost variance does not match the five-order baseline")
    require(dict(stock) == expected["ending_stock_by_product"], "Ending stock does not match expected values")
    require(expected["inbound_order_created_count"] == len(inbound), "Inbound event count mismatch")
    require(expected["outbound_order_created_count"] == len(outbound), "Outbound event count mismatch")

    print("Telemetry fixture valid: 8 products, 15 inbound, 15 outbound")
    print(f"Derived events valid: {len(threshold_events)} stock crossings, {len(variance_events)} cost variance")
    print("All ending stock values are non-negative and match the fixture assertions.")


if __name__ == "__main__":
    main()