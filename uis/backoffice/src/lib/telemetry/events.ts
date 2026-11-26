// The telemetry events the backoffice can emit, typed from the approved contract
// (docs/telemetry/event-schemas.json, schemaVersion 2.0.0; docs/telemetry/telemetry-plan.md for the "why").
// `track()` only accepts a name from `TelemetryEvents` with exactly the properties listed for it, so an
// undeclared key, or a name or an e-mail in a free-text field, does not compile. The server validates the same
// contract again (services/api/telemetry/contract.py): this file is the compile-time half of the allowlist.
//
// Not every event of the contract is here: http_request_completed, dependency_call_completed, supplier_deleted (this app has no way
// to delete one), product_*, the talent ones and the worker ones belong to the API, the website or a screen that does not exist.
// The events the API decides (logins, suppliers, incidents...) are relayed from the response the app received; the receiver
// stamps their `source` (see services/api/telemetry/contract.py).

// 2.1.0 is 2.0.0 plus `web_vital_reported`; every other event is identical in both, so the whole app sends 2.1.0.
export const SCHEMA_VERSION = "2.1.0";

export type OfficeId = "valencia" | "miami";
export type Currency = "EUR" | "USD";
export type ProductCategoryId = "training_kit" | "certification" | "onboarding_equipment";

export type Section =
  | "home"
  | "inventory"
  | "inbound"
  | "outbound"
  | "orders"
  | "suppliers"
  | "incidents"
  | "analysis"
  | "profile"
  | "login"
  | "register"
  | "talent";

export type FlowName = "inbound" | "outbound" | "supplier" | "incident" | "analysis" | "registration" | "talent";
export type FlowStep = "form" | "validated" | "submitted" | "confirmed";
export type Component = "auth" | "inventory" | "suppliers" | "incidents" | "profile" | "website" | "telemetry";
export type InventoryOperation = "create_product" | "inbound" | "outbound";
export type RouteId =
  | "auth_login"
  | "auth_me"
  | "users"
  | "profiles"
  | "inventory_assets"
  | "inventory_inbound"
  | "inventory_outbound"
  | "inventory_orders"
  | "suppliers"
  | "incidents"
  | "incident_analysis"
  | "health"
  | "unmatched";
export type IncidentState = "open" | "in_progress" | "resolved" | "discarded";

/** The six properties every inventory event carries (briefing, section 3), also in rejections and alerts. */
export interface InventoryProperties {
  office: OfficeId;
  product_id: string;
  product_category: ProductCategoryId;
  programme_id: string;
  quantity: number;
  currency: Currency;
}

export interface TelemetryEvents {
  // --- the five mandatory ones (business) ---
  inbound_order_created: InventoryProperties & {
    order_id: string;
    supplier_id: string;
    unit_cost_minor: number;
    total_cost_minor: number;
  };
  outbound_order_created: InventoryProperties & { order_id: string; stock_before: number; stock_after: number };
  stock_threshold_triggered: InventoryProperties & {
    order_id: string;
    stock_before: number;
    stock_after: number;
    minimum_stock: number;
  };
  direct_stock_edit_rejected: InventoryProperties & {
    attempted_field: "stock" | "current_stock";
    reason: "direct_stock_write_forbidden";
  };
  kit_cost_variance_detected: InventoryProperties & {
    order_id: string;
    supplier_id: string;
    unit_cost_minor: number;
    reference_unit_cost_minor: number;
    baseline_order_count: 5;
    variance_percent: number;
    threshold_percent: 10;
  };
  // --- inventory rejections (business) ---
  inventory_order_rejected: InventoryProperties & {
    operation: InventoryOperation;
    field: "quantity" | "office" | "product_id" | "supplier_id" | "unit_cost_minor" | "sku" | "multiple" | "none";
    error_code: "insufficient_stock" | "office_mismatch" | "duplicate_sku" | "invalid_quantity" | "invalid_field" | "conflict";
  };
  inventory_validation_failed: InventoryProperties & {
    operation: InventoryOperation;
    field: "quantity" | "office" | "product_id" | "supplier_id" | "unit_cost_minor" | "sku" | "multiple" | "none";
    error_code: "insufficient_stock" | "office_mismatch" | "duplicate_sku" | "invalid_quantity" | "invalid_field" | "conflict";
  };
  // --- navigation and flows (product) ---
  section_viewed: { section: Section; locale: "es" | "en" };
  section_load_completed: { section: Section; duration_ms: number; outcome: "success" | "error" };
  search_performed: { section: Section; result_count: number; filter_count: number };
  flow_started: { flow_id: string; flow_name: FlowName; step: "form"; elapsed_ms: 0 };
  flow_step_completed: { flow_id: string; flow_name: FlowName; step: FlowStep; elapsed_ms: number };
  flow_completed: { flow_id: string; flow_name: FlowName; step: "confirmed"; elapsed_ms: number };
  flow_cancelled: { flow_id: string; flow_name: FlowName; step: FlowStep; elapsed_ms: number };
  form_validation_failed: {
    flow_id: string;
    flow_name: FlowName;
    field: "product_id" | "quantity" | "supplier" | "assigned_to" | "multiple" | "other";
    error_count: number;
  };
  // --- authentication and session (security) ---
  login_attempted: { method: "password"; duration_ms: 0 };
  login_succeeded: { method: "password"; duration_ms: number };
  login_failed: {
    method: "password";
    duration_ms: number;
    reason: "invalid_credentials" | "invalid_request" | "rate_limited" | "internal_error";
  };
  logout_completed: { reason: "user_action" };
  session_expired: { reason: "token_expired" | "unauthorized_response" };
  authorization_denied: { route_id: RouteId; status_code: 401 | 403 };
  registration_completed: { method: "password"; duration_ms: number };
  registration_failed: { reason: "invalid_request" | "unavailable" | "rate_limited" | "internal_error" };
  profile_updated: { changed_field_count: number };
  // --- suppliers and incidents (operations) ---
  supplier_created: { supplier_id: string };
  supplier_updated: { supplier_id: string };
  incident_created: { incident_id: string };
  incident_status_changed: { incident_id: string; from_status: IncidentState; to_status: IncidentState };
  incident_analysis_completed: { analysis_id: string; row_count: number; duration_ms: number };
  incident_analysis_failed: { analysis_id: string; reason: "invalid_csv" | "size_limit" | "timeout" | "internal_error" };
  // --- performance ---
  web_vital_reported: {
    metric: "LCP" | "CLS" | "INP" | "FCP" | "TTFB";
    value: number;
    rating: "good" | "needs-improvement" | "poor";
    section: Section;
  };
  // --- technical ---
  application_error_occurred: {
    error_code: "unhandled_exception" | "render_failed" | "network_failed" | "invalid_response";
    component: Component;
  };
}

export type TelemetryEventType = keyof TelemetryEvents;

/**
 * Events that need the user's pseudonym (the inventory ones, a login or a registration that succeeded). The server stamps it
 * from the session. Without an
 * `Authorization` header (a `sendBeacon` cannot carry one) the receiver rejects them, so on unload these go out
 * with `fetch(..., { keepalive: true })` instead.
 */
export const IDENTITY_BOUND_EVENTS: ReadonlySet<TelemetryEventType> = new Set<TelemetryEventType>([
  "inbound_order_created",
  "outbound_order_created",
  "stock_threshold_triggered",
  "direct_stock_edit_rejected",
  "kit_cost_variance_detected",
  "inventory_order_rejected",
  "inventory_validation_failed",
  "login_succeeded",
  "registration_completed",
]);

/**
 * Events after which the session is gone: the events waiting for the user's identity must leave while the token still exists,
 * or a batch flushed later would reach the receiver anonymous and be refused. (Found with a real browser: an order, then a
 * logout within the batch interval, lost the order's event.)
 */
export const SESSION_ENDING_EVENTS: ReadonlySet<TelemetryEventType> = new Set<TelemetryEventType>(["logout_completed"]);

/** One event as it is queued and sent: the closed envelope of the contract. */
export interface TelemetryEnvelope<T extends TelemetryEventType = TelemetryEventType> {
  eventId: string;
  event_type: T;
  schemaVersion: typeof SCHEMA_VERSION;
  /** Instant of capture (UTC, ISO 8601, ends in Z), never the instant of delivery. */
  timestamp: string;
  /** Always null from the browser: the pseudonym is computed by the server from the verified session. */
  userId: null;
  sessionId: string;
  requestId: string;
  environment: "development" | "test" | "staging" | "production";
  /** What this app is. The server decides the source of the inventory events (`inventory_api`). */
  source: "backoffice";
  properties: TelemetryEvents[T];
}

export interface TrackOptions {
  /** The operation this event belongs to; pass the one sent as `X-Request-ID` so client and API correlate. */
  requestId?: string;
}
