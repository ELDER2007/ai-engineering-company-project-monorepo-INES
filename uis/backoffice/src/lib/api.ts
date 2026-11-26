import type {
  Incident,
  IncidentFacets,
  IncidentFilters,
  IncidentPage,
  IncidentSummary,
  StatusChangeInput,
} from "@repo/shared-types";
import type { AnalyzeResponse } from "../types/incidents";
import type { Supplier, SupplierCreate, SupplierStatus } from "../types/suppliers";
import type { DirectoryEntry } from "../types/inventory";
import type { Me, Profile, ProfileUpdate, SignUpOut, SignUpPayload } from "../types/auth";
import { clearToken, getToken, setToken } from "./token";
import { componentForPath, routeIdForPath } from "./telemetry/paths";
import { opaqueId, uuidV4 } from "./telemetry/ids";
import { track } from "./telemetry";
import { analysisFailureReason, loginFailureReason, registrationFailureReason } from "./authTelemetry";

// Vacío = mismo origen: los rewrites de next.config.mjs reenvían las llamadas a la API local.
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    /** Per-field messages of a 422 (FastAPI validation), keyed by the body field name. */
    public fieldErrors: Record<string, string> = {},
    /** Stable machine code of a structured `detail` (`{ code, field, message }`), e.g. `direct_stock_write_forbidden`. */
    public code?: string,
    /** The body field a structured `detail` points at. */
    public field?: string,
  ) {
    super(message);
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return new ApiError(body.detail, response.status);
    if (body.detail && typeof body.detail === "object" && !Array.isArray(body.detail) && typeof body.detail.code === "string") {
      const { code, field, message } = body.detail as { code: string; field?: unknown; message?: unknown };
      return new ApiError(
        typeof message === "string" ? message : response.statusText,
        response.status,
        {},
        code,
        typeof field === "string" ? field : undefined,
      );
    }
    if (Array.isArray(body.detail)) {
      const fieldErrors: Record<string, string> = {};
      const message = body.detail
        .map((e: { loc?: unknown[]; msg?: string }) => {
          const field = e.loc?.slice(1).join(".");
          const text = (e.msg ?? "").replace(/^Value error, /, "");
          if (field && !(field in fieldErrors)) fieldErrors[field] = text;
          return field ? `${field}: ${text}` : text;
        })
        .join("; ");
      return new ApiError(message, response.status, fieldErrors);
    }
  } catch {
    /* not JSON: fall back to the status text */
  }
  return new ApiError(response.statusText, response.status);
}

// Every call to the API goes through here so it carries the bearer token. A 401 while holding
// a token means it expired (or the account was deleted/deactivated): forget it, which sends the
// user back to the login page.
async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let response: Response;
  try {
    const url = /^https?:\/\//.test(path) ? path : `${API_BASE_URL}${path}`;
    response = await fetch(url, { ...init, headers });
  } catch {
    // fetch only rejects when the request never got an answer (offline, API down, DNS...).
    const component = componentForPath(path);
    if (component) track("application_error_occurred", { error_code: "network_failed", component });
    throw new ApiError("No response from the server", 0);
  }
  // The API refused a protected call (the login's own 401 does not come through here): where, and which refusal.
  if (response.status === 401 || response.status === 403) {
    track("authorization_denied", { route_id: routeIdForPath(path), status_code: response.status });
  }
  // Only if it is still the stored token: a late 401 for an old one must not end a newer session.
  if (response.status === 401 && token && getToken() === token) {
    track("session_expired", { reason: "unauthorized_response" });
    clearToken();
  }
  return response;
}

/**
 * A JSON call to a protected route: carries the bearer token (via apiFetch) and throws an ApiError, with the
 * message taken from the response body, on any 4xx/5xx. Domain modules (lib/inventory.ts) build on this so no
 * component ever calls fetch itself.
 */
export async function jsonRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await apiFetch(path, { ...init, headers });
  if (!response.ok) {
    throw await toApiError(response);
  }
  return response.json();
}

export async function login(email: string, password: string): Promise<void> {
  // The telemetry of the login is here, in the one function every login goes through (the form, and the sign-up's automatic one),
  // not on each page. The reason of a failure comes from the HTTP status: what was typed (email, password) never reaches an event.
  track("login_attempted", { method: "password", duration_ms: 0 });
  const startedAt = performance.now();
  const elapsed = () => Math.round(performance.now() - startedAt);
  let response: Response;
  try {
    // OAuth2 password flow: form-encoded, and the field is called "username" but carries the email.
    response = await fetch(`${API_BASE_URL}/auth/login`, {
      method: "POST",
      body: new URLSearchParams({ username: email, password }),
    });
  } catch (err) {
    // The request never got an answer: not a refusal by the API, so not a `login_failed` (it would count against its rate).
    track("application_error_occurred", { error_code: "network_failed", component: "auth" });
    throw err;
  }
  if (!response.ok) {
    const error = await toApiError(response);
    track("login_failed", { method: "password", duration_ms: elapsed(), reason: loginFailureReason(response.status) });
    throw error;
  }
  const { access_token } = await response.json();
  if (typeof access_token !== "string" || !access_token) {
    // Storing `undefined` would save the text "undefined" and send it as the bearer token on every call.
    track("login_failed", { method: "password", duration_ms: elapsed(), reason: "internal_error" });
    throw new ApiError("Unexpected response from the server", 502);
  }
  // Before the token is stored: storing it starts a new analytic session, and the attempt and its result belong to the old one.
  track("login_succeeded", { method: "password", duration_ms: elapsed() });
  setToken(access_token);
}

/** Public sign-up (POST /users). Empty optional profile fields are left out rather than sent blank. */
export async function register(payload: SignUpPayload): Promise<SignUpOut> {
  const body = Object.fromEntries(Object.entries(payload).filter(([, value]) => value !== undefined && value !== ""));
  const startedAt = performance.now();
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/users`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (err) {
    track("application_error_occurred", { error_code: "network_failed", component: "auth" });
    throw err;
  }
  if (!response.ok) {
    const error = await toApiError(response);
    track("registration_failed", { reason: registrationFailureReason(response.status) });
    throw error;
  }
  // The account exists whatever happens to the automatic login that follows (plan, section 11).
  track("registration_completed", { method: "password", duration_ms: Math.round(performance.now() - startedAt) });
  return response.json();
}

export async function fetchMe(): Promise<Me> {
  const response = await apiFetch("/auth/me");
  if (!response.ok) {
    throw await toApiError(response);
  }
  return response.json();
}

/** Edits the session's own profile; the owner comes from the bearer token, never from the body. */
export async function updateMyProfile(update: ProfileUpdate): Promise<Profile> {
  const response = await apiFetch("/profiles/me", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(update),
  });
  if (!response.ok) {
    throw await toApiError(response);
  }
  const changed = Object.keys(update).length; // `update` holds only the fields that changed (profileChanges)
  if (changed > 0) track("profile_updated", { changed_field_count: changed });
  return response.json();
}

export async function analyzeIncidentsFile(file: File): Promise<AnalyzeResponse> {
  const formData = new FormData();
  formData.append("file", file);
  // One id per analysis attempt, made here: the API has none to give. Never the file's name or contents.
  const analysisId = uuidV4();
  const startedAt = performance.now();

  try {
    const response = await apiFetch("/api/incidents/analyze", {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      throw await toApiError(response);
    }

    const result: AnalyzeResponse = await response.json();
    track("incident_analysis_completed", {
      analysis_id: analysisId,
      row_count: result.total_records,
      duration_ms: Math.round(performance.now() - startedAt),
    });
    return result;
  } catch (err) {
    // No answer at all (status 0) is the network's failure, reported by apiFetch; the rest is the analysis's.
    if (err instanceof ApiError && err.status !== 0) {
      track("incident_analysis_failed", { analysis_id: analysisId, reason: analysisFailureReason(err.status) });
    }
    throw err;
  }
}

export async function downloadResultsCsv(): Promise<void> {
  const response = await apiFetch("/api/incidents/results/export");

  if (!response.ok) {
    throw await toApiError(response);
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "results.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

const suppliersRequest = <T>(path: string, init?: RequestInit) => jsonRequest<T>(`/api/suppliers${path}`, init);

export const listSuppliers = () => suppliersRequest<Supplier[]>("");

/** Reports a confirmed supplier change by its id only (never the name, the rate or the contact). */
async function reportSupplier(event: "supplier_created" | "supplier_updated", supplier: Supplier): Promise<Supplier> {
  const supplier_id = opaqueId(supplier.id);
  if (supplier_id) track(event, { supplier_id });
  return supplier;
}

export const createSupplier = async (payload: SupplierCreate) =>
  reportSupplier("supplier_created", await suppliersRequest<Supplier>("", { method: "POST", body: JSON.stringify(payload) }));

export const updateSupplierRate = async (id: number, monthly_rate: number) =>
  reportSupplier(
    "supplier_updated",
    await suppliersRequest<Supplier>(`/${id}/rate`, { method: "PATCH", body: JSON.stringify({ monthly_rate }) }),
  );

export const setSupplierStatus = async (id: number, status: SupplierStatus) =>
  reportSupplier(
    "supplier_updated",
    await suppliersRequest<Supplier>(`/${id}/status`, { method: "PATCH", body: JSON.stringify({ status }) }),
  );

// ---- Incident manager -----------------------------------------------------------------------

export type SortField = "created_at" | "id" | "updated_at";
export type SortOrder = "asc" | "desc";

export function filtersQuery(filters: IncidentFilters): URLSearchParams {
  const params = new URLSearchParams();
  filters.status.forEach((v) => params.append("status", v));
  filters.category.forEach((v) => params.append("category", v));
  filters.origin.forEach((v) => params.append("origin", v));
  for (const key of ["branch", "agent_id", "client_company", "q", "date_from", "date_to"] as const) {
    if (filters[key].trim()) params.set(key, filters[key].trim());
  }
  return params;
}

const incidentsRequest = <T>(path: string, init?: RequestInit) => jsonRequest<T>(`/api/incidents${path}`, init);

export function listIncidents(
  filters: IncidentFilters,
  options: { sort: SortField; order: SortOrder; page: number; pageSize: number },
): Promise<IncidentPage> {
  const params = filtersQuery(filters);
  params.set("sort", options.sort);
  params.set("order", options.order);
  params.set("page", String(options.page));
  params.set("page_size", String(options.pageSize));
  return incidentsRequest<IncidentPage>(`?${params}`);
}

export const getIncidentSummary = (filters: IncidentFilters) =>
  incidentsRequest<IncidentSummary>(`/summary?${filtersQuery(filters)}`);

export const getIncidentFacets = () => incidentsRequest<IncidentFacets>("/facets");

export const getIncident = (incidentId: string) =>
  incidentsRequest<Incident>(`/${encodeURIComponent(incidentId)}`);

/** What the form sends. Optional text fields are `null` to clear them (edit) and left out when empty (create). */
export type IncidentFields = {
  title: string;
  description: string;
  category: string;
  origin: string;
  branch: string;
  client_company: string | null;
  agent_id: string | null;
  customer_email: string | null;
};

export const createIncident = async (payload: IncidentFields) => {
  const incident = await incidentsRequest<Incident>("", { method: "POST", body: JSON.stringify(payload) });
  const incident_id = opaqueId(incident.id); // the id only: never the title, the description or the customer
  if (incident_id) track("incident_created", { incident_id });
  return incident;
};

export const updateIncident = (incidentId: string, changes: Partial<IncidentFields>) =>
  incidentsRequest<Incident>(`/${encodeURIComponent(incidentId)}`, { method: "PATCH", body: JSON.stringify(changes) });

export const changeIncidentStatus = async (incidentId: string, change: StatusChangeInput) => {
  const incident = await incidentsRequest<Incident>(`/${encodeURIComponent(incidentId)}/status`, {
    method: "PATCH",
    body: JSON.stringify(change),
  });
  // The transition as the API recorded it (the last `status_changed` entry of the history), not as the form asked for it.
  const move = [...(incident.history ?? [])].reverse().find((entry) => entry.kind === "status_changed");
  const incident_id = opaqueId(incident.id);
  if (incident_id && move?.from_status && move.to_status && move.from_status !== move.to_status) {
    track("incident_status_changed", { incident_id, from_status: move.from_status, to_status: move.to_status });
  }
  return incident;
};

/** Names of the active users, to show who registered each inventory order (orders only carry the user's UUID). */
export async function listUserDirectory(): Promise<DirectoryEntry[]> {
  return jsonRequest<DirectoryEntry[]>("/users/directory");
}
