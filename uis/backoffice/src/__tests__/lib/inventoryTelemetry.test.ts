// How an order's response, or a refusal, becomes telemetry events (`lib/inventoryTelemetry.ts`), and that the inventory
// client (`lib/inventory.ts`) does it for every order. `track` is mocked: what is asserted is the event and its exact
// properties, which are the contract of docs/telemetry/event-schemas.json.
//
// Layout shared by every frontend test file: HAPPY PATH, EDGE CASES, FAILURE MODES. Arrange / Act / Assert.
import { ApiError } from "@/lib/api";
import { createInboundOrder, createOutboundOrder } from "@/lib/inventory";
import { inventoryProperties, trackInventoryFailure, trackInventoryOrder } from "@/lib/inventoryTelemetry";
import { track } from "@/lib/telemetry";
import type { AssetBrief, InventoryOrder, OrderEffects } from "@/types/inventory";

jest.mock("@/lib/telemetry", () => ({ track: jest.fn() }));
const trackMock = jest.mocked(track);

const ASSET: AssetBrief = {
  id: 101, name: "Kit de certificación en ventas B2B", sku: "NXV-KIT-1", category: "training_materials", office: "Valencia",
  programme_id: "ventas-b2b", product_category: "training_kit", minimum_stock: 10,
};
const MIAMI: AssetBrief = { ...ASSET, id: 102, office: "Miami", programme_id: "liderazgo-basico", product_category: "certification" };
const REQUEST_ID = "20000000-0000-4000-8000-000000000001";

const effects = (over: Partial<OrderEffects> = {}): OrderEffects => ({
  stock_before: 12, stock_after: 7, minimum_stock: 10, threshold_crossed: false, cost_variance: null, ...over,
});
const order = (over: Partial<InventoryOrder> = {}): InventoryOrder => ({
  type: "outbound", id: 601, asset: ASSET, quantity: 5, office: "Valencia", created_at: "2026-10-27T10:00:00Z",
  user_uuid: "u", supplier: null, supplier_id: null, unit_cost_minor: null, currency: "EUR", exit_type: "consumption",
  assigned_to: null, effects: effects(), ...over,
});
const inbound = (over: Partial<InventoryOrder> = {}) =>
  order({ type: "inbound", id: 501, quantity: 10, supplier: "Imprenta Levante", supplier_id: "sup-abc123def456", unit_cost_minor: 1200, exit_type: null, effects: effects({ stock_before: 0, stock_after: 10 }), ...over });
const calls = () => trackMock.mock.calls.map(([type, properties, options]) => ({ type, properties, options }));

const COMMON_VALENCIA = { office: "valencia", product_id: "101", product_category: "training_kit", programme_id: "ventas-b2b", currency: "EUR" };

describe("inventoryProperties", () => {
  it("uses the contract's vocabulary: lowercase office, string ids, the currency of the office", () => {
    expect(inventoryProperties(ASSET, 3)).toEqual({ ...COMMON_VALENCIA, quantity: 3 });
    expect(inventoryProperties(MIAMI, 0)).toMatchObject({ office: "miami", currency: "USD", product_category: "certification", programme_id: "liderazgo-basico" });
  });
  it("is null for an asset without a programme or a business category: nothing is invented", () => {
    expect(inventoryProperties({ ...ASSET, programme_id: null }, 1)).toBeNull();
    expect(inventoryProperties({ ...ASSET, product_category: null }, 1)).toBeNull();
  });
});

describe("trackInventoryOrder", () => {
  describe("happy path", () => {
    it("an entry emits inbound_order_created with the total = quantity x unit cost, in minor units", () => {
      trackInventoryOrder(inbound(), REQUEST_ID);
      expect(calls()).toEqual([
        {
          type: "inbound_order_created",
          properties: { ...COMMON_VALENCIA, quantity: 10, order_id: "501", supplier_id: "sup-abc123def456", unit_cost_minor: 1200, total_cost_minor: 12000 },
          options: { requestId: REQUEST_ID },
        },
      ]);
    });

    it("an exit emits outbound_order_created with the stock before and after, from the API", () => {
      trackInventoryOrder(order(), REQUEST_ID);
      expect(calls()).toEqual([
        { type: "outbound_order_created", properties: { ...COMMON_VALENCIA, quantity: 5, order_id: "601", stock_before: 12, stock_after: 7 }, options: { requestId: REQUEST_ID } },
      ]);
    });

    it("an exit that crosses the minimum also emits stock_threshold_triggered, with the minimum in force", () => {
      trackInventoryOrder(order({ effects: effects({ threshold_crossed: true }) }), REQUEST_ID);
      expect(calls().map((c) => c.type)).toEqual(["outbound_order_created", "stock_threshold_triggered"]);
      expect(calls()[1].properties).toEqual({ ...COMMON_VALENCIA, quantity: 5, order_id: "601", stock_before: 12, stock_after: 7, minimum_stock: 10 });
    });

    it("an entry far from its baseline also emits kit_cost_variance_detected, with the fixed baseline size and threshold", () => {
      const variance = { reference_unit_cost_minor: 1000, baseline_order_count: 5, variance_percent: 20, threshold_percent: 10 };
      trackInventoryOrder(inbound({ effects: effects({ cost_variance: variance }) }), REQUEST_ID);
      expect(calls().map((c) => c.type)).toEqual(["inbound_order_created", "kit_cost_variance_detected"]);
      expect(calls()[1].properties).toEqual({
        ...COMMON_VALENCIA, quantity: 10, order_id: "501", supplier_id: "sup-abc123def456", unit_cost_minor: 1200,
        reference_unit_cost_minor: 1000, baseline_order_count: 5, variance_percent: 20, threshold_percent: 10,
      });
    });

    it("every event of one submission carries the same requestId", () => {
      trackInventoryOrder(order({ effects: effects({ threshold_crossed: true }) }), REQUEST_ID);
      expect(new Set(calls().map((c) => c.options?.requestId))).toEqual(new Set([REQUEST_ID]));
    });

    it("a Miami order is reported in USD", () => {
      trackInventoryOrder(order({ asset: MIAMI, office: "Miami" }), REQUEST_ID);
      expect(calls()[0].properties).toMatchObject({ office: "miami", currency: "USD" });
    });
  });

  describe("edge cases", () => {
    it("an exit that stays above the minimum raises no alert", () => {
      trackInventoryOrder(order(), REQUEST_ID);
      expect(calls().map((c) => c.type)).toEqual(["outbound_order_created"]);
    });

    it("an unclassified asset emits nothing, not a half-empty event", () => {
      trackInventoryOrder(order({ asset: { ...ASSET, programme_id: null } }), REQUEST_ID);
      expect(trackMock).not.toHaveBeenCalled();
    });

    it("an entry without a cost or a supplier id emits nothing: the total cannot be known", () => {
      trackInventoryOrder(inbound({ unit_cost_minor: null }), REQUEST_ID);
      trackInventoryOrder(inbound({ supplier_id: null }), REQUEST_ID);
      expect(trackMock).not.toHaveBeenCalled();
    });

    it("a response without effects (an old API) emits nothing", () => {
      trackInventoryOrder(order({ effects: null }), REQUEST_ID);
      expect(trackMock).not.toHaveBeenCalled();
    });

    it("never carries the supplier's name, the employee or the author", () => {
      trackInventoryOrder(inbound({ supplier: "Imprenta Levante S.L." }), REQUEST_ID);
      trackInventoryOrder(order({ exit_type: "allocation", assigned_to: "María López" }), REQUEST_ID);
      const everything = JSON.stringify(calls());
      expect(everything).not.toMatch(/Levante|María|López|"u"|user_uuid|assigned_to|supplier"/);
    });

    it("never throws, even for a response that is not an order", () => {
      expect(() => trackInventoryOrder({} as InventoryOrder, REQUEST_ID)).not.toThrow();
      expect(() => trackInventoryOrder(null as unknown as InventoryOrder, REQUEST_ID)).not.toThrow();
    });
  });
});

describe("trackInventoryFailure", () => {
  const ctx = (operation: "inbound" | "outbound" = "outbound") => ({ operation, asset: ASSET, requestId: REQUEST_ID });
  const ZERO = { ...COMMON_VALENCIA, quantity: 0 };

  it("a refused stock write emits direct_stock_edit_rejected with quantity 0 and the field, not the value", () => {
    trackInventoryFailure(new ApiError("Stock cannot be written directly", 422, {}, "direct_stock_write_forbidden", "current_stock"), ctx());
    expect(calls()).toEqual([
      { type: "direct_stock_edit_rejected", properties: { ...ZERO, attempted_field: "current_stock", reason: "direct_stock_write_forbidden" }, options: { requestId: REQUEST_ID } },
    ]);
  });

  it("insufficient stock emits inventory_order_rejected for the quantity", () => {
    trackInventoryFailure(new ApiError("Insufficient stock for asset 'X'. Available: 2, requested: 5.", 400), ctx());
    expect(calls()[0]).toMatchObject({ type: "inventory_order_rejected", properties: { ...ZERO, operation: "outbound", field: "quantity", error_code: "insufficient_stock" } });
  });

  it("an order for the wrong office emits inventory_order_rejected for the office", () => {
    trackInventoryFailure(new ApiError("Asset 'X' belongs to the Valencia office: an order for it cannot be registered in Miami.", 422), ctx("inbound"));
    expect(calls()[0]).toMatchObject({ type: "inventory_order_rejected", properties: { operation: "inbound", field: "office", error_code: "office_mismatch" } });
  });

  it("a failed validation emits inventory_validation_failed with the one field, or 'multiple'", () => {
    trackInventoryFailure(new ApiError("quantity: x", 422, { quantity: "Input should be greater than 0" }), ctx());
    trackInventoryFailure(new ApiError("a", 422, { quantity: "x", supplier: "y" }), ctx("inbound"));
    trackInventoryFailure(new ApiError("a", 422, { unit_cost_minor: "x" }), ctx("inbound"));
    expect(calls().map((c) => [c.type, (c.properties as { field: string }).field, (c.properties as { error_code: string }).error_code])).toEqual([
      ["inventory_validation_failed", "quantity", "invalid_quantity"],
      ["inventory_validation_failed", "multiple", "invalid_field"],
      ["inventory_validation_failed", "unit_cost_minor", "invalid_field"],
    ]);
  });

  it.each([
    new ApiError("Internal Server Error", 500),
    new ApiError("Asset 9 not found", 404),
    new ApiError("No response from the server", 0),
    new ApiError("Could not validate credentials", 401),
    new Error("boom"),
    "text",
  ])("emits nothing for %p: it is not an inventory refusal", (err) => {
    trackInventoryFailure(err, ctx());
    expect(trackMock).not.toHaveBeenCalled();
  });

  it("emits nothing for an unclassified asset", () => {
    trackInventoryFailure(new ApiError("Insufficient stock for asset 'X'. Available: 2, requested: 5.", 400), { ...ctx(), asset: { ...ASSET, product_category: null } });
    expect(trackMock).not.toHaveBeenCalled();
  });
});

describe("the inventory client", () => {
  const fetchMock = jest.fn();
  beforeEach(() => {
    fetchMock.mockReset();
    globalThis.fetch = fetchMock as unknown as typeof fetch;
  });
  const respond = (body: unknown, status = 201) =>
    fetchMock.mockResolvedValue({ ok: status < 400, status, statusText: "", json: async () => body } as Response);
  const payload = { asset_id: 101, quantity: 10, supplier: "Imprenta", office: "Valencia" as const, unit_cost_minor: 1200 };

  it("an entry sends X-Request-ID, then reports the events with that same id", async () => {
    respond(inbound());

    await createInboundOrder(payload, { asset: ASSET, requestId: REQUEST_ID });

    expect(new Headers(fetchMock.mock.calls[0][1].headers).get("X-Request-ID")).toBe(REQUEST_ID);
    expect(calls().map((c) => [c.type, c.options?.requestId])).toEqual([["inbound_order_created", REQUEST_ID]]);
  });

  it("an exit reports its events", async () => {
    respond(order({ effects: effects({ threshold_crossed: true }) }));
    await createOutboundOrder({ asset_id: 101, quantity: 5, exit_type: "consumption", assigned_to: null, office: "Valencia" }, { asset: ASSET, requestId: REQUEST_ID });
    expect(calls().map((c) => c.type)).toEqual(["outbound_order_created", "stock_threshold_triggered"]);
  });

  it("a refused order reports the refusal and still throws the error to the screen", async () => {
    respond({ detail: "Insufficient stock for asset 'X'. Available: 2, requested: 5." }, 400);
    await expect(
      createOutboundOrder({ asset_id: 101, quantity: 5, exit_type: "consumption", assigned_to: null, office: "Valencia" }, { asset: ASSET, requestId: REQUEST_ID }),
    ).rejects.toBeInstanceOf(ApiError);
    expect(calls().map((c) => c.type)).toEqual(["inventory_order_rejected"]);
  });

  it("a refused stock write is recognised from the API's structured detail", async () => {
    respond({ detail: { code: "direct_stock_write_forbidden", field: "stock", message: "Stock cannot be written directly" } }, 422);
    await expect(createInboundOrder({ ...payload, ...({ stock: 99 } as object) }, { asset: ASSET, requestId: REQUEST_ID })).rejects.toMatchObject({ code: "direct_stock_write_forbidden", field: "stock" });
    expect(calls()[0]).toMatchObject({ type: "direct_stock_edit_rejected", properties: { attempted_field: "stock", quantity: 0 } });
  });

  it("without a context there is no header and no refusal event, but a confirmed order is still reported", async () => {
    respond(order());
    await createOutboundOrder({ asset_id: 101, quantity: 5, exit_type: "consumption", assigned_to: null, office: "Valencia" });
    expect(new Headers(fetchMock.mock.calls[0][1].headers).has("X-Request-ID")).toBe(false);
    expect(calls().map((c) => c.type)).toEqual(["outbound_order_created"]);

    trackMock.mockClear();
    respond({ detail: "Insufficient stock for asset 'X'. Available: 2, requested: 5." }, 400);
    await expect(createOutboundOrder({ asset_id: 101, quantity: 5, exit_type: "consumption", assigned_to: null, office: "Valencia" })).rejects.toBeInstanceOf(ApiError);
    expect(trackMock).not.toHaveBeenCalled();
  });
});
