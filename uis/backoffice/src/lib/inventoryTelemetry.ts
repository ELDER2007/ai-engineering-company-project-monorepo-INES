// The inventory events (plan, section 5 and the table of the inventory flow): how an order's response, or a
// refusal, becomes `track()` calls. Pure translation, no state. The facts come from the API (`order.effects`,
// computed in the order's transaction); nothing here recomputes a threshold or a variance.
//
// An event is only emitted when the asset has what the contract requires (programme, business category) and, for
// an entry, a cost and a supplier id. Otherwise nothing is invented: the plan prefers a missing event to a wrong one.
import { ApiError } from "./api";
import { classifyInventoryFailure } from "./inventoryRules";
import { track } from "./telemetry";
import type { InventoryOperation, InventoryProperties, OfficeId } from "./telemetry/events";
import type { AssetBrief, InventoryOrder } from "../types/inventory";

export interface OrderContext {
  operation: InventoryOperation;
  /** The asset the user picked, as the API listed it. */
  asset: AssetBrief;
  /** Sent as `X-Request-ID` and shared by every event of this submission. */
  requestId?: string;
}

const OFFICE: Record<AssetBrief["office"], OfficeId> = { Valencia: "valencia", Miami: "miami" };
const CURRENCY = { valencia: "EUR", miami: "USD" } as const;

/** The six common properties of an inventory event, or null when the asset is not classified for telemetry. */
export function inventoryProperties(asset: AssetBrief, quantity: number): InventoryProperties | null {
  if (!asset.programme_id || !asset.product_category) return null;
  const office = OFFICE[asset.office];
  return {
    office,
    product_id: String(asset.id),
    product_category: asset.product_category,
    programme_id: asset.programme_id,
    quantity,
    currency: CURRENCY[office],
  };
}

/**
 * A confirmed order: its event, plus the alert it caused (threshold crossing or cost variance) if any.
 * It runs after the order is already saved: whatever is wrong with the response, it must not turn a saved order
 * into an error on screen, so it never throws.
 */
export function trackInventoryOrder(order: InventoryOrder, requestId?: string): void {
  try {
    emitOrder(order, requestId);
  } catch {
    /* telemetry never breaks the business operation */
  }
}

function emitOrder(order: InventoryOrder, requestId?: string): void {
  const effects = order.effects;
  const base = inventoryProperties(order.asset, order.quantity);
  if (!base || !effects) return;
  const opts = { requestId };
  const order_id = String(order.id);

  if (order.type === "inbound") {
    if (order.supplier_id === null || order.unit_cost_minor === null) return;
    const { supplier_id, unit_cost_minor } = order;
    track("inbound_order_created", { ...base, order_id, supplier_id, unit_cost_minor, total_cost_minor: order.quantity * unit_cost_minor }, opts);
    if (effects.cost_variance) {
      track(
        "kit_cost_variance_detected",
        {
          ...base,
          order_id,
          supplier_id,
          unit_cost_minor,
          reference_unit_cost_minor: effects.cost_variance.reference_unit_cost_minor,
          baseline_order_count: 5,
          variance_percent: effects.cost_variance.variance_percent,
          threshold_percent: 10,
        },
        opts,
      );
    }
    return;
  }

  track("outbound_order_created", { ...base, order_id, stock_before: effects.stock_before, stock_after: effects.stock_after }, opts);
  if (effects.threshold_crossed) {
    track(
      "stock_threshold_triggered",
      { ...base, order_id, stock_before: effects.stock_before, stock_after: effects.stock_after, minimum_stock: effects.minimum_stock },
      opts,
    );
  }
}

/**
 * A refused order. A refusal moves no material, so `quantity` is 0 (plan, section 4). One attempt is one event,
 * with the precedence of the plan: a stock write beats a validation failure beats a business-rule rejection.
 */
export function trackInventoryFailure(err: unknown, context: OrderContext): void {
  try {
    emitFailure(err, context);
  } catch {
    /* the original error is what the caller must see */
  }
}

function emitFailure(err: unknown, context: OrderContext): void {
  if (!(err instanceof ApiError)) return;
  const failure = classifyInventoryFailure(err);
  const base = inventoryProperties(context.asset, 0);
  if (!failure || !base) return;
  const opts = { requestId: context.requestId };

  switch (failure.kind) {
    case "direct_stock_write":
      track("direct_stock_edit_rejected", { ...base, attempted_field: failure.field, reason: "direct_stock_write_forbidden" }, opts);
      break;
    case "insufficient_stock":
      track("inventory_order_rejected", { ...base, operation: context.operation, field: "quantity", error_code: "insufficient_stock" }, opts);
      break;
    case "office_mismatch":
      track("inventory_order_rejected", { ...base, operation: context.operation, field: "office", error_code: "office_mismatch" }, opts);
      break;
    case "validation":
      track(
        "inventory_validation_failed",
        {
          ...base,
          operation: context.operation,
          field: failure.field,
          error_code: failure.field === "quantity" ? "invalid_quantity" : "invalid_field",
        },
        opts,
      );
      break;
  }
}
