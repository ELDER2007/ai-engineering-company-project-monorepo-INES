"""ORM tables of the inventory domain (SQLModel), stored in Supabase/PostgreSQL.

Three tables and nothing else:

* ``assets``        the catalogue. **No stock column**: stock is derived from the orders.
* ``asset_entries`` inbound orders (a purchase or delivery received). They add stock.
* ``asset_exits``   outbound orders (an allocation or a consumption). They remove stock.

The only way to change an asset's stock is to insert a row in one of the two order tables.
Orders point to their author with ``user_uuid``, the ``User.id`` kept in TinyDB. There is no
users table here and no foreign key on that column (README, "Storage rule").

These classes are persistence only. Request/response shapes live in ``schemas.py``: an ORM
object is never returned from an endpoint.
"""

from datetime import datetime, timezone
from enum import Enum

from sqlmodel import CheckConstraint, DateTime, Field, SQLModel


class Office(str, Enum):
    valencia = "Valencia"
    miami = "Miami"


class AssetCategory(str, Enum):
    hardware = "hardware"
    peripherals = "peripherals"
    office_supplies = "office_supplies"
    training_materials = "training_materials"


class ProductCategory(str, Enum):
    """Business classification of the telemetry contract (docs/telemetry). Deliberately NOT derived from
    ``AssetCategory``: the plan forbids mapping the legacy categories automatically, Elena classifies."""

    training_kit = "training_kit"
    certification = "certification"
    onboarding_equipment = "onboarding_equipment"


# Money is recorded in the currency of the office (no conversion anywhere): Valencia EUR, Miami USD.
OFFICE_CURRENCY = {Office.valencia.value: "EUR", Office.miami.value: "USD"}


class ExitType(str, Enum):
    allocation = "allocation"  # assigned to an employee
    consumption = "consumption"  # used up (paper, ...)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Asset(SQLModel, table=True):
    __tablename__ = "assets"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    sku: str = Field(unique=True, index=True)
    category: str
    office: str
    # Telemetry classification. NULL = not classified yet: such an asset emits no inventory events (the plan
    # forbids inventing a programme), and there is no automatic backfill of the assets that already existed.
    programme_id: str | None = Field(default=None, max_length=128)
    product_category: str | None = None
    # Alert level of ``stock_threshold_triggered``; 0 switches the alert off.
    minimum_stock: int = Field(default=0, sa_column_kwargs={"server_default": "0"})


class AssetEntry(SQLModel, table=True):
    """Inbound order: ``quantity`` units of an asset received from ``supplier``."""

    __tablename__ = "asset_entries"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_asset_entries_quantity_positive"),
        CheckConstraint("unit_cost_minor IS NULL OR unit_cost_minor >= 0", name="ck_asset_entries_unit_cost_not_negative"),
    )

    id: int | None = Field(default=None, primary_key=True)
    asset_id: int = Field(foreign_key="assets.id", index=True)
    quantity: int
    supplier: str
    office: str
    # Opaque id derived from ``supplier`` (see service.supplier_id_for); the name itself never goes to telemetry.
    supplier_id: str | None = Field(default=None, index=True)
    # Unit cost in minor units (cents) of the currency of ``office``. NULL for entries that predate the cost.
    unit_cost_minor: int | None = None
    created_at: datetime = Field(default_factory=_utcnow, sa_type=DateTime(timezone=True))
    user_uuid: str = Field(index=True)  # TinyDB User.id; deliberately not a foreign key


class AssetExit(SQLModel, table=True):
    """Outbound order: ``quantity`` units handed out or consumed."""

    __tablename__ = "asset_exits"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_asset_exits_quantity_positive"),
        CheckConstraint(
            "(exit_type = 'allocation' AND assigned_to IS NOT NULL)"
            " OR (exit_type = 'consumption' AND assigned_to IS NULL)",
            name="ck_asset_exits_assigned_to_matches_type",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    asset_id: int = Field(foreign_key="assets.id", index=True)
    quantity: int
    exit_type: str
    assigned_to: str | None = None
    office: str
    created_at: datetime = Field(default_factory=_utcnow, sa_type=DateTime(timezone=True))
    user_uuid: str = Field(index=True)  # TinyDB User.id; deliberately not a foreign key
