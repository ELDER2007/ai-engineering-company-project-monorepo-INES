// The inventory API client: every call to the /inventory endpoints lives here, so no component calls fetch itself.
// Each call carries `Authorization: Bearer <token>` (the token the login stored, read by jsonRequest) and, on a
// 4xx/5xx, throws an ApiError whose message is the one in the response body. The screens turn that into text for
// the user with `describeInventoryError` (lib/inventoryRules.ts); nothing is swallowed here.
import { API_BASE_URL, jsonRequest } from "./api";
import { trackInventoryFailure, trackInventoryOrder, type OrderContext } from "./inventoryTelemetry";
import type {
  Asset,
  AssetCreate,
  InboundOrderCreate,
  InventoryOrder,
  OutboundOrderCreate,
} from "../types/inventory";

// The inventory routes are /inventory/* on the API. Their page paths (/inventory/orders...) are the same, so in
// development the app calls them as /api/inventory/*, which next.config.mjs forwards to the inventory API
// (NEXT_PUBLIC_INVENTORY_API_URL, or API_PROXY_TARGET). With NEXT_PUBLIC_API_BASE_URL set the app calls the API
// directly instead: at NEXT_PUBLIC_INVENTORY_API_URL if the inventory lives on its own host, else at the main one.
const INVENTORY_URL = (process.env.NEXT_PUBLIC_INVENTORY_API_URL ?? "").replace(/\/+$/, "");
const PREFIX = API_BASE_URL ? `${INVENTORY_URL || API_BASE_URL}/inventory` : "/api/inventory";

/** GET /inventory/products — every asset with its `current_stock` (entries minus exits, computed by the API). */
export const listAssets = () => jsonRequest<Asset[]>(`${PREFIX}/products`);

/** GET /inventory/products/{id} — one asset with its stock as it is now. */
export const getAsset = (assetId: number) => jsonRequest<Asset>(`${PREFIX}/products/${assetId}`);

/** POST /inventory/products — registers a new asset. */
export const createAsset = (payload: AssetCreate) =>
  jsonRequest<Asset>(`${PREFIX}/products`, { method: "POST", body: JSON.stringify(payload) });

/** GET /inventory/orders — every entry and exit, with the asset's data. */
export const listOrders = () => jsonRequest<InventoryOrder[]>(`${PREFIX}/orders`);

/**
 * POST an order and report what happened to the telemetry. This is the only place that does it, so no screen
 * repeats the rules: the API computes the facts (stock before/after, minimum crossed, cost variance) in the
 * order's transaction and this turns them into events. `context` names the asset the user picked (from the
 * catalogue the API sent, never from the form) so a refusal can be attributed; `requestId` travels as
 * `X-Request-ID` and is the `requestId` of every event of this submission.
 */
async function postOrder(path: string, payload: InboundOrderCreate | OutboundOrderCreate, context?: OrderContext) {
  const headers = context?.requestId ? { "X-Request-ID": context.requestId } : undefined;
  try {
    const order = await jsonRequest<InventoryOrder>(path, { method: "POST", headers, body: JSON.stringify(payload) });
    trackInventoryOrder(order, context?.requestId);
    return order;
  } catch (err) {
    if (context) trackInventoryFailure(err, context);
    throw err;
  }
}

/** POST /inventory/orders/inbound — registers a delivery received (AssetEntry). */
export const createInboundOrder = (payload: InboundOrderCreate, context?: Omit<OrderContext, "operation">) =>
  postOrder(`${PREFIX}/orders/inbound`, payload, context && { ...context, operation: "inbound" });

/** POST /inventory/orders/outbound — registers an allocation or a consumption (AssetExit). */
export const createOutboundOrder = (payload: OutboundOrderCreate, context?: Omit<OrderContext, "operation">) =>
  postOrder(`${PREFIX}/orders/outbound`, payload, context && { ...context, operation: "outbound" });
