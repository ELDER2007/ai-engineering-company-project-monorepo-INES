"""Pydantic request/response shapes of the inventory API.

Kept apart from ``models.py`` on purpose: endpoints take and return these, never ORM objects.
``current_stock`` exists only here, in a response; no request can carry it and no table stores it.
``user_uuid`` is not an input either: it is always the authenticated user, whatever the body says.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .models import AssetCategory, ExitType, Office, ProductCategory

# Opaque ids of the telemetry contract (schema `$defs/id`): never free text, so never a name.
ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]*$"

# Stock is derived from the orders and can never be written. A body that carries one of these is refused with
# an explicit code (docs/telemetry/telemetry-plan.md, section 5: `direct_stock_edit_rejected`), not just ignored.
FORBIDDEN_STOCK_FIELDS = ("stock", "current_stock")
DIRECT_STOCK_WRITE_CODE = "direct_stock_write_forbidden"


class _NoDirectStock(BaseModel):
    """Mixin of every write body: declares the forbidden stock fields only so the handler can see them were sent."""

    stock: Any = Field(default=None, exclude=True, description="Always refused: stock is derived from the orders.")
    current_stock: Any = Field(default=None, exclude=True, description="Always refused: stock is derived from the orders.")

    def forbidden_stock_field(self) -> str | None:
        """The stock field the caller explicitly sent, if any (`current_stock` wins when both came)."""
        for name in reversed(FORBIDDEN_STOCK_FIELDS):
            if name in self.model_fields_set:
                return name
        return None


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


class AssetCreate(_NoDirectStock):
    name: str = Field(min_length=1, max_length=200)
    sku: str = Field(min_length=1, max_length=50)
    category: AssetCategory
    office: Office
    # Telemetry classification (optional: an unclassified asset simply emits no inventory events).
    programme_id: str | None = Field(default=None, max_length=128, pattern=ID_PATTERN)
    product_category: ProductCategory | None = None
    minimum_stock: int = Field(default=0, ge=0)

    @field_validator("name", "sku")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class AssetOut(BaseModel):
    id: int
    name: str
    sku: str
    category: AssetCategory
    office: Office
    programme_id: str | None = None
    product_category: ProductCategory | None = None
    minimum_stock: int = 0
    current_stock: int  # computed from the orders on every read, never stored


class AssetEntryCreate(_NoDirectStock):
    """Inbound order. The author and the timestamp are set by the server."""

    asset_id: int
    quantity: int = Field(gt=0)
    supplier: str = Field(min_length=1, max_length=200)
    office: Office
    # Unit cost in minor units (cents) of the office's currency. Optional for legacy callers; without it the
    # order is stored but no cost telemetry can be derived from it.
    unit_cost_minor: int | None = Field(default=None, ge=0)

    @field_validator("supplier")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class AssetExitCreate(_NoDirectStock):
    """Outbound order. ``assigned_to`` is required for an allocation and must be null for a
    consumption (business rule 3)."""

    asset_id: int
    quantity: int = Field(gt=0)
    exit_type: ExitType
    assigned_to: str | None = Field(default=None, max_length=200)
    office: Office

    @model_validator(mode="after")
    def _assigned_to_matches_exit_type(self) -> AssetExitCreate:
        self.assigned_to = _blank_to_none(self.assigned_to)
        if self.exit_type is ExitType.allocation and self.assigned_to is None:
            raise ValueError("assigned_to is required when exit_type is 'allocation'")
        if self.exit_type is ExitType.consumption and self.assigned_to is not None:
            raise ValueError("assigned_to must be null when exit_type is 'consumption'")
        return self


class AssetBrief(BaseModel):
    id: int
    name: str
    sku: str
    category: AssetCategory
    office: Office
    programme_id: str | None = None
    product_category: ProductCategory | None = None
    minimum_stock: int = 0


class CostVariance(BaseModel):
    """An inbound unit cost more than 10 % away from the history of the same asset, supplier and office."""

    reference_unit_cost_minor: int
    baseline_order_count: int
    variance_percent: float
    threshold_percent: int


class OrderEffects(BaseModel):
    """What one order did, computed by the server inside the same transaction (the only place that can know it
    exactly). Present only in the response that creates the order, never in a listing. The backoffice turns it
    into telemetry events; it never recomputes thresholds or variances itself."""

    stock_before: int
    stock_after: int
    minimum_stock: int
    threshold_crossed: bool = False  # outbound only: stock went from >= minimum to < minimum
    cost_variance: CostVariance | None = None  # inbound only


class OrderOut(BaseModel):
    """One inbound or outbound order with its asset. ``supplier`` is set on inbound orders,
    ``exit_type``/``assigned_to`` on outbound ones."""

    type: Literal["inbound", "outbound"]
    id: int
    asset: AssetBrief
    quantity: int
    office: Office
    created_at: datetime
    user_uuid: str
    supplier: str | None = None
    supplier_id: str | None = None
    unit_cost_minor: int | None = None
    currency: Literal["EUR", "USD"] | None = None
    exit_type: ExitType | None = None
    assigned_to: str | None = None
    effects: OrderEffects | None = None

    @field_validator("created_at")
    @classmethod
    def _as_utc(cls, value: datetime) -> datetime:
        # SQLite hands timestamps back without a zone; they were stored as UTC.
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
