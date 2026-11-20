"""Business logic of the inventory domain.

Rules enforced here (the CONTEXT's "Reglas de Negocio"):

1. ``current_stock = SUM(entries) - SUM(exits)``, computed on every read, never stored.
2. An outbound order that would exceed the stock is refused *before* anything is written.
5. Both offices share the same tables; ``office`` is a filter, not a partition.

Every read that needs related data fetches it in the same statement (a correlated aggregate
for the stock, a JOIN for the asset of an order), so the number of queries does not grow with
the number of rows: no N+1.
"""

from __future__ import annotations

import hashlib
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

from sqlmodel import Session, col, func, select

from .models import OFFICE_CURRENCY, Asset, AssetEntry, AssetExit
from .schemas import (
    AssetBrief,
    AssetCreate,
    AssetEntryCreate,
    AssetExitCreate,
    AssetOut,
    CostVariance,
    OrderEffects,
    OrderOut,
)

# Cost-variance rule of docs/telemetry/telemetry-plan.md, section 5: the new unit cost is compared with the
# weighted mean of the last BASELINE_ORDERS eligible entries (same asset, supplier and office/currency); strictly
# more than VARIANCE_THRESHOLD_PERCENT away, up or down, is an anomaly. Fewer entries than that: no baseline.
BASELINE_ORDERS = 5
VARIANCE_THRESHOLD_PERCENT = 10

# Correlated scalar subqueries: one SELECT returns every asset with its net stock. The sums
# are bounded by the partition key of the CONTEXT, ``office``: an asset's stock only counts
# the orders of its own office (the API refuses any other, see ``_check_office``).
_ENTERED = (
    select(func.coalesce(func.sum(AssetEntry.quantity), 0))
    .where(AssetEntry.asset_id == Asset.id, AssetEntry.office == Asset.office)
    .scalar_subquery()
)
_EXITED = (
    select(func.coalesce(func.sum(AssetExit.quantity), 0))
    .where(AssetExit.asset_id == Asset.id, AssetExit.office == Asset.office)
    .scalar_subquery()
)
_STOCK = (_ENTERED - _EXITED).label("current_stock")


class AssetNotFoundError(Exception):
    def __init__(self, asset_id: int):
        super().__init__(f"Asset {asset_id} not found")


class DuplicateSkuError(Exception):
    def __init__(self, sku: str):
        super().__init__(f"An asset with SKU '{sku}' already exists")


class OfficeMismatchError(Exception):
    def __init__(self, name: str, asset_office: str, order_office: str):
        super().__init__(
            f"Asset '{name}' belongs to the {asset_office} office: an order for it cannot be registered in {order_office}."
        )


class InsufficientStockError(Exception):
    def __init__(self, name: str, available: int, quantity: int):
        super().__init__(f"Insufficient stock for asset '{name}'. Available: {available}, requested: {quantity}.")


def supplier_id_for(name: str) -> str:
    """Opaque, stable id of a supplier from its name, ignoring case and spacing ("Acme  S.L." == "acme s.l.").

    Interim until the suppliers registry is the source of inventory suppliers: the commercial name must never
    reach telemetry (schema `id`, no free text), and a hash cannot be read back as one.
    """
    normalised = " ".join(name.casefold().split())
    return "sup-" + hashlib.sha256(normalised.encode("utf-8")).hexdigest()[:12]


def _asset_out(asset: Asset, stock: int) -> AssetOut:
    return AssetOut(
        id=asset.id,
        name=asset.name,
        sku=asset.sku,
        category=asset.category,
        office=asset.office,
        programme_id=asset.programme_id,
        product_category=asset.product_category,
        minimum_stock=asset.minimum_stock,
        current_stock=stock,
    )


def list_assets(session: Session, *, office: str | None = None, category: str | None = None) -> list[AssetOut]:
    statement = select(Asset, _STOCK).order_by(col(Asset.id))
    if office:
        statement = statement.where(Asset.office == office)
    if category:
        statement = statement.where(Asset.category == category)
    return [_asset_out(asset, int(stock)) for asset, stock in session.exec(statement)]


def get_asset(session: Session, asset_id: int) -> AssetOut:
    row = session.exec(select(Asset, _STOCK).where(Asset.id == asset_id)).first()
    if row is None:
        raise AssetNotFoundError(asset_id)
    return _asset_out(row[0], int(row[1]))


def _sku_exists(session: Session, sku: str) -> bool:
    return session.exec(select(Asset.id).where(Asset.sku == sku)).first() is not None


def create_asset(session: Session, payload: AssetCreate) -> AssetOut:
    """A new asset starts at 0 units: stock only arrives through an inbound order."""
    if _sku_exists(session, payload.sku):
        raise DuplicateSkuError(payload.sku)
    asset = Asset(
        name=payload.name,
        sku=payload.sku,
        category=payload.category.value,
        office=payload.office.value,
        programme_id=payload.programme_id,
        product_category=payload.product_category.value if payload.product_category else None,
        minimum_stock=payload.minimum_stock,
    )
    session.add(asset)
    try:
        session.commit()
    except Exception as exc:
        # The UNIQUE constraint on sku is the source of truth: if another request took the
        # SKU between the check above and this insert, it is the same conflict.
        session.rollback()
        if _sku_exists(session, payload.sku):
            raise DuplicateSkuError(payload.sku) from exc
        raise
    session.refresh(asset)
    return _asset_out(asset, 0)


def _brief(asset: Asset) -> AssetBrief:
    return AssetBrief(
        id=asset.id,
        name=asset.name,
        sku=asset.sku,
        category=asset.category,
        office=asset.office,
        programme_id=asset.programme_id,
        product_category=asset.product_category,
        minimum_stock=asset.minimum_stock,
    )


def _inbound_out(entry: AssetEntry, asset: Asset, effects: OrderEffects | None = None) -> OrderOut:
    return OrderOut(
        type="inbound",
        id=entry.id,
        asset=_brief(asset),
        quantity=entry.quantity,
        office=entry.office,
        created_at=entry.created_at,
        user_uuid=entry.user_uuid,
        supplier=entry.supplier,
        supplier_id=entry.supplier_id,
        unit_cost_minor=entry.unit_cost_minor,
        currency=OFFICE_CURRENCY[entry.office],
        effects=effects,
    )


def _outbound_out(exit_: AssetExit, asset: Asset, effects: OrderEffects | None = None) -> OrderOut:
    return OrderOut(
        type="outbound",
        id=exit_.id,
        asset=_brief(asset),
        quantity=exit_.quantity,
        office=exit_.office,
        created_at=exit_.created_at,
        user_uuid=exit_.user_uuid,
        currency=OFFICE_CURRENCY[exit_.office],
        exit_type=exit_.exit_type,
        assigned_to=exit_.assigned_to,
        effects=effects,
    )


def cost_variance(session: Session, asset: Asset, office: str, supplier_id: str, unit_cost_minor: int) -> CostVariance | None:
    """The variance of a new inbound unit cost against its baseline, or None when it is within the threshold or
    there is no baseline to compare with (never invented: fewer than BASELINE_ORDERS eligible entries, or a zero
    reference). Called before the new entry is inserted, so the baseline is the entries *prior* to it."""
    prior = session.exec(
        select(AssetEntry)
        .where(
            AssetEntry.asset_id == asset.id,
            AssetEntry.office == office,
            AssetEntry.supplier_id == supplier_id,
            col(AssetEntry.unit_cost_minor).is_not(None),
        )
        .order_by(col(AssetEntry.created_at).desc(), col(AssetEntry.id).desc())
        .limit(BASELINE_ORDERS)
    ).all()
    if len(prior) < BASELINE_ORDERS:
        return None
    units = sum(entry.quantity for entry in prior)
    weighted = Decimal(sum(entry.quantity * entry.unit_cost_minor for entry in prior)) / Decimal(units)
    reference = int(weighted.quantize(Decimal(1), rounding=ROUND_HALF_UP))
    if reference == 0:
        return None
    variance = Fraction(100 * abs(unit_cost_minor - reference), reference)  # exact: 10 % is not "more than 10 %"
    if variance <= VARIANCE_THRESHOLD_PERCENT:
        return None
    return CostVariance(
        reference_unit_cost_minor=reference,
        baseline_order_count=BASELINE_ORDERS,
        variance_percent=float(variance),
        threshold_percent=VARIANCE_THRESHOLD_PERCENT,
    )


def _check_office(asset: Asset, order_office: str) -> None:
    """Both offices share the tables, but each asset lives in one: an order must come from it,
    otherwise it would be stored and never counted in the stock."""
    if asset.office != order_office:
        raise OfficeMismatchError(asset.name, asset.office, order_office)


def register_inbound(session: Session, payload: AssetEntryCreate, user_uuid: str) -> OrderOut:
    # FOR UPDATE serialises concurrent entries of the same asset (PostgreSQL), so each one sees the others in
    # its cost baseline and in the stock it reports; SQLite ignores the clause and is single-writer anyway.
    row = session.exec(select(Asset, _STOCK).where(Asset.id == payload.asset_id).with_for_update(of=Asset)).first()
    if row is None:
        raise AssetNotFoundError(payload.asset_id)
    asset, stock_before = row[0], int(row[1])
    try:
        _check_office(asset, payload.office.value)
    except OfficeMismatchError:
        session.rollback()  # release the lock; nothing was written
        raise
    supplier_id = supplier_id_for(payload.supplier)
    variance = (
        cost_variance(session, asset, payload.office.value, supplier_id, payload.unit_cost_minor)
        if payload.unit_cost_minor is not None
        else None
    )
    entry = AssetEntry(
        asset_id=asset.id,
        quantity=payload.quantity,
        supplier=payload.supplier,
        supplier_id=supplier_id,
        unit_cost_minor=payload.unit_cost_minor,
        office=payload.office.value,
        user_uuid=user_uuid,
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    effects = OrderEffects(
        stock_before=stock_before,
        stock_after=stock_before + payload.quantity,
        minimum_stock=asset.minimum_stock,
        cost_variance=variance,
    )
    return _inbound_out(entry, asset, effects)


def register_outbound(session: Session, payload: AssetExitCreate, user_uuid: str) -> OrderOut:
    # FOR UPDATE locks the asset row on PostgreSQL until the commit, so two simultaneous
    # outbound orders cannot both pass the stock check and drive the stock negative.
    # (SQLite, the local fallback, ignores the clause and is single-writer anyway.)
    row = session.exec(select(Asset, _STOCK).where(Asset.id == payload.asset_id).with_for_update(of=Asset)).first()
    if row is None:
        raise AssetNotFoundError(payload.asset_id)
    asset, available = row[0], int(row[1])
    try:
        _check_office(asset, payload.office.value)
    except OfficeMismatchError:
        session.rollback()  # release the lock; nothing was written
        raise
    if payload.quantity > available:
        session.rollback()  # release the lock; nothing was written
        raise InsufficientStockError(asset.name, available, payload.quantity)
    exit_ = AssetExit(
        asset_id=asset.id,
        quantity=payload.quantity,
        exit_type=payload.exit_type.value,
        assigned_to=payload.assigned_to,
        office=payload.office.value,
        user_uuid=user_uuid,
    )
    session.add(exit_)
    session.commit()
    session.refresh(exit_)
    stock_after = available - payload.quantity
    effects = OrderEffects(
        stock_before=available,
        stock_after=stock_after,
        minimum_stock=asset.minimum_stock,
        # Strict: ending exactly at the minimum is not a crossing, and once below, later exits do not repeat it.
        threshold_crossed=asset.minimum_stock > 0 and available >= asset.minimum_stock > stock_after,
    )
    return _outbound_out(exit_, asset, effects)


def list_orders(session: Session, *, office: str | None = None) -> list[OrderOut]:
    """Every inbound and outbound order, newest first, with its asset. Two statements
    (one per table), each JOINed to ``assets``, however many orders there are."""
    entries = select(AssetEntry, Asset).join(Asset, col(AssetEntry.asset_id) == col(Asset.id))
    exits = select(AssetExit, Asset).join(Asset, col(AssetExit.asset_id) == col(Asset.id))
    if office:
        entries = entries.where(AssetEntry.office == office)
        exits = exits.where(AssetExit.office == office)
    orders = [_inbound_out(entry, asset) for entry, asset in session.exec(entries)]
    orders += [_outbound_out(exit_, asset) for exit_, asset in session.exec(exits)]
    orders.sort(key=lambda order: (order.created_at, order.type, order.id), reverse=True)
    return orders
