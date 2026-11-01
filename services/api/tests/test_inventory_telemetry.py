"""What the inventory computes for the telemetry (docs/telemetry/telemetry-plan.md, sections 3, 5 and 9): the stock
before/after of every order, the minimum-stock crossing, the cost variance against a 5-entry baseline, the opaque
supplier id, the explicit refusal of a direct stock write, and the additive migration of an older database."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel

from conftest import headers_for, ALICE
from inventory import models, service
from inventory.database import add_missing_columns, build_engine, get_db
from main import app

OFFICE = "Valencia"
SUPPLIER = "Imprenta Levante S.L."


@pytest.fixture()
def engine(tmp_path):
    engine = build_engine(f"sqlite:///{tmp_path / 'inventory.sqlite'}")
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def client(engine, auth_headers):
    def _session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = _session
    yield TestClient(app, headers=auth_headers)
    app.dependency_overrides.pop(get_db, None)


def asset(client, **overrides) -> dict:
    body = {
        "name": "Kit de ventas B2B", "sku": "NXV-KIT-1", "category": "training_materials", "office": OFFICE,
        "programme_id": "ventas-b2b", "product_category": "training_kit", "minimum_stock": 10, **overrides,
    }
    response = client.post("/inventory/products", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def inbound(client, asset_id, quantity=10, cost=1000, supplier=SUPPLIER, office=OFFICE):
    body = {"asset_id": asset_id, "quantity": quantity, "supplier": supplier, "office": office}
    if cost is not None:
        body["unit_cost_minor"] = cost
    response = client.post("/inventory/orders/inbound", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def outbound(client, asset_id, quantity):
    body = {"asset_id": asset_id, "quantity": quantity, "exit_type": "consumption", "assigned_to": None, "office": OFFICE}
    response = client.post("/inventory/orders/outbound", json=body)
    assert response.status_code == 201, response.text
    return response.json()


# --- classification travels with the asset -----------------------------------------------------------------

def test_the_classification_of_an_asset_is_stored_and_returned_with_the_asset_and_its_orders(client):
    created = asset(client)
    assert (created["programme_id"], created["product_category"], created["minimum_stock"]) == ("ventas-b2b", "training_kit", 10)
    order = inbound(client, created["id"])
    assert order["asset"]["programme_id"] == "ventas-b2b" and order["asset"]["product_category"] == "training_kit"


@pytest.mark.parametrize("change", [
    {"product_category": "training_materials"},  # a legacy category is not a business category
    {"programme_id": "Ventas B2B"}, {"programme_id": "ventas b2b; drop"}, {"minimum_stock": -1},
])
def test_an_invalid_classification_is_refused(client, change):
    body = {"name": "X", "sku": "NXV-X", "category": "hardware", "office": OFFICE, **change}
    assert client.post("/inventory/products", json=body).status_code == 422


# --- stock before / after and the minimum-stock crossing ----------------------------------------------------

def test_every_order_reports_the_stock_before_and_after_it(client):
    created = asset(client)
    first = inbound(client, created["id"], quantity=12)
    assert first["effects"]["stock_before"] == 0 and first["effects"]["stock_after"] == 12
    out = outbound(client, created["id"], 5)
    assert (out["effects"]["stock_before"], out["effects"]["stock_after"], out["effects"]["minimum_stock"]) == (12, 7, 10)


def test_effects_are_only_in_the_response_that_creates_the_order(client):
    created = asset(client)
    inbound(client, created["id"])
    assert all(order["effects"] is None for order in client.get("/inventory/orders").json())


def test_the_threshold_alert_is_strict_and_not_repeated(client):
    """Plan, section 9: 12 -> 10 (min 10): none; 10 -> 9: one; 9 -> 8: none."""
    created = asset(client)
    inbound(client, created["id"], quantity=12)
    crossings = [outbound(client, created["id"], q)["effects"]["threshold_crossed"] for q in (2, 1, 1)]
    assert crossings == [False, True, False]


def test_restocking_rearms_the_threshold(client):
    """8 -> restock to 12 (an inbound never alerts) -> out 3 -> 9 < 10: a new alert."""
    created = asset(client)
    inbound(client, created["id"], quantity=8)
    assert inbound(client, created["id"], quantity=4)["effects"]["threshold_crossed"] is False
    assert outbound(client, created["id"], 3)["effects"]["threshold_crossed"] is True


def test_a_minimum_of_zero_switches_the_alert_off(client):
    created = asset(client, minimum_stock=0)
    inbound(client, created["id"], quantity=5)
    assert outbound(client, created["id"], 5)["effects"]["threshold_crossed"] is False


# --- cost variance ---------------------------------------------------------------------------------------------

def test_a_20_percent_rise_against_a_clean_baseline(client):
    created = asset(client)
    for _ in range(5):
        inbound(client, created["id"], cost=1000)
    variance = inbound(client, created["id"], cost=1200)["effects"]["cost_variance"]
    assert variance == {"reference_unit_cost_minor": 1000, "baseline_order_count": 5, "variance_percent": 20.0, "threshold_percent": 10}


def test_a_20_percent_drop_is_an_anomaly_too(client):
    created = asset(client)
    for _ in range(5):
        inbound(client, created["id"], cost=1000)
    assert inbound(client, created["id"], cost=800)["effects"]["cost_variance"]["variance_percent"] == 20.0


def test_exactly_10_percent_is_not_an_anomaly(client):
    created = asset(client)
    for _ in range(5):
        inbound(client, created["id"], cost=1000)
    assert inbound(client, created["id"], cost=1100)["effects"]["cost_variance"] is None


def test_the_reference_is_the_quantity_weighted_mean_rounded_half_up(client):
    created = asset(client)
    for quantity, cost in ((1, 1000), (1, 1000), (1, 1000), (1, 1000), (4, 1001)):  # (4000 + 4004) / 8 = 1000.5
        inbound(client, created["id"], quantity=quantity, cost=cost)
    variance = inbound(client, created["id"], cost=2000)["effects"]["cost_variance"]
    assert variance["reference_unit_cost_minor"] == 1001  # HALF_UP, not banker's rounding (which gives 1000)


def test_fewer_than_five_prior_entries_never_invent_a_baseline(client):
    created = asset(client)
    for _ in range(4):
        inbound(client, created["id"], cost=1000)
    assert inbound(client, created["id"], cost=5000)["effects"]["cost_variance"] is None


def test_the_baseline_is_per_supplier(client):
    created = asset(client)
    for _ in range(5):
        inbound(client, created["id"], cost=1000, supplier="Proveedor A")
    assert inbound(client, created["id"], cost=5000, supplier="Proveedor B")["effects"]["cost_variance"] is None
    assert inbound(client, created["id"], cost=5000, supplier="Proveedor A")["effects"]["cost_variance"] is not None


def test_entries_without_a_cost_do_not_count_towards_the_baseline(client):
    created = asset(client)
    for _ in range(3):
        inbound(client, created["id"], cost=1000)
    for _ in range(3):
        inbound(client, created["id"], cost=None)
    assert inbound(client, created["id"], cost=5000)["effects"]["cost_variance"] is None


def test_an_entry_without_cost_has_no_variance_and_is_still_stored(client):
    created = asset(client)
    order = inbound(client, created["id"], cost=None)
    assert order["unit_cost_minor"] is None and order["effects"]["cost_variance"] is None


def test_a_negative_cost_is_refused(client):
    created = asset(client)
    body = {"asset_id": created["id"], "quantity": 1, "supplier": SUPPLIER, "office": OFFICE, "unit_cost_minor": -1}
    assert client.post("/inventory/orders/inbound", json=body).status_code == 422


def test_the_currency_follows_the_office(client):
    miami = asset(client, sku="NXV-MIA", office="Miami")
    body = {"asset_id": miami["id"], "quantity": 1, "supplier": SUPPLIER, "office": "Miami", "unit_cost_minor": 100}
    assert client.post("/inventory/orders/inbound", json=body).json()["currency"] == "USD"
    assert inbound(client, asset(client, sku="NXV-VAL")["id"])["currency"] == "EUR"


# --- the supplier id --------------------------------------------------------------------------------------------

def test_the_supplier_id_is_opaque_stable_and_ignores_case_and_spacing():
    one = service.supplier_id_for("Imprenta  Levante S.L.")
    assert one == service.supplier_id_for(" imprenta levante s.l. ")
    assert one != service.supplier_id_for("Otra imprenta")
    assert "levante" not in one.lower() and one.startswith("sup-") and len(one) == 16


def test_an_inbound_order_stores_and_returns_the_supplier_id(client):
    order = inbound(client, asset(client)["id"])
    assert order["supplier_id"] == service.supplier_id_for(SUPPLIER)
    assert order["supplier"] == SUPPLIER  # the name stays in the operational record


# --- a direct stock write -------------------------------------------------------------------------------------------

@pytest.mark.parametrize("field", ["stock", "current_stock"])
def test_a_stock_field_in_an_order_is_refused_with_its_own_code_and_writes_nothing(client, field):
    created = asset(client)
    body = {"asset_id": created["id"], "quantity": 5, "supplier": SUPPLIER, "office": OFFICE, field: 999}
    response = client.post("/inventory/orders/inbound", json=body)
    assert response.status_code == 422
    assert response.json()["detail"] == {
        "code": "direct_stock_write_forbidden", "field": field,
        "message": "Stock cannot be written directly: register an inbound or outbound order.",
    }
    assert client.get("/inventory/orders").json() == []
    assert client.get(f"/inventory/products/{created['id']}").json()["current_stock"] == 0


def test_the_direct_write_is_refused_on_outbound_orders_too(client):
    created = asset(client)
    inbound(client, created["id"], quantity=5)
    body = {"asset_id": created["id"], "quantity": 1, "exit_type": "consumption", "office": OFFICE, "current_stock": 1}
    assert client.post("/inventory/orders/outbound", json=body).json()["detail"]["code"] == "direct_stock_write_forbidden"
    assert client.get(f"/inventory/products/{created['id']}").json()["current_stock"] == 5


def test_a_null_stock_field_still_counts_as_an_attempt(client):
    created = asset(client)
    body = {"asset_id": created["id"], "quantity": 1, "supplier": SUPPLIER, "office": OFFICE, "stock": None}
    assert client.post("/inventory/orders/inbound", json=body).status_code == 422


# --- the additive migration -----------------------------------------------------------------------------------------

def test_a_database_created_before_the_telemetry_columns_gets_them_without_losing_rows(tmp_path):
    engine = build_engine(f"sqlite:///{tmp_path / 'old.sqlite'}")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE assets (id INTEGER PRIMARY KEY, name VARCHAR NOT NULL, sku VARCHAR NOT NULL UNIQUE, "
            "category VARCHAR NOT NULL, office VARCHAR NOT NULL)"
        ))
        connection.execute(text(
            "CREATE TABLE asset_entries (id INTEGER PRIMARY KEY, asset_id INTEGER NOT NULL REFERENCES assets(id), "
            "quantity INTEGER NOT NULL, supplier VARCHAR NOT NULL, office VARCHAR NOT NULL, created_at DATETIME NOT NULL, "
            "user_uuid VARCHAR NOT NULL)"
        ))
        connection.execute(text("INSERT INTO assets VALUES (1, 'Portátil', 'SKU-1', 'hardware', 'Valencia')"))

    added = add_missing_columns(engine)

    assert {"assets.programme_id", "assets.product_category", "assets.minimum_stock",
            "asset_entries.supplier_id", "asset_entries.unit_cost_minor"} <= set(added)
    with Session(engine) as session:
        legacy = session.get(models.Asset, 1)
        assert (legacy.name, legacy.programme_id, legacy.product_category, legacy.minimum_stock) == ("Portátil", None, None, 0)
    assert add_missing_columns(engine) == []  # idempotent
    assert "minimum_stock" in {column["name"] for column in inspect(engine).get_columns("assets")}
    engine.dispose()


def test_the_seed_classifies_what_is_obvious_and_leaves_the_paper_unclassified():
    by_sku = {data["sku"]: data for data in __import__("inventory.seeding", fromlist=["ASSETS"]).ASSETS}
    assert by_sku["NXV-TRN-001"]["programme_id"] == "liderazgo-basico"
    assert by_sku["NXV-IT-001"]["product_category"] == "onboarding_equipment"
    assert "programme_id" not in by_sku["NXV-OFF-001"] and "product_category" not in by_sku["NXV-OFF-001"]
