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
import type { Me, Profile, ProfileUpdate, SignUpOut, SignUpPayload } from "../types/auth";
import {
  isObject,
  toAnalyzeResponse,
  toIncident,
  toIncidentFacets,
  toIncidentPage,
  toIncidentSummary,
  toMe,
  toProfile,
  toSupplier,
  toSuppliers,
} from "./guards";
import { clearToken, getToken, setToken } from "./token";

// Vacío = mismo origen: los rewrites de next.config.mjs reenvían las llamadas a la API local.
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

/** A request nobody has answered after this long is given up: the person gets an error and a way to try again. */
export const REQUEST_TIMEOUT_MS = 20_000;

/** `network`: no answer; `timeout`: too slow; `http`: the API answered with an error; `invalid-response`:
 *  it answered ok but not with what was expected; `storage`: the browser would not keep the session. */
export type ApiErrorKind = "network" | "timeout" | "http" | "invalid-response" | "storage";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    /** Per-field messages of a 422 (FastAPI validation), keyed by the body field name. */
    public fieldErrors: Record<string, string> = {},
    /** The reference of a 500, which is also in the server's log. */
    public errorId?: string,
    public kind: ApiErrorKind = status === 0 ? "network" : "http",
  ) {
    super(message);
  }
}

const invalidResponse = (status: number, why: string) => new ApiError(why, status, {}, undefined, "invalid-response");

async function readBody(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return undefined; // not JSON: the status decides what to say
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  const body = await readBody(response);
  const errorId = isObject(body) && typeof body.error_id === "string" ? body.error_id : undefined;
  const detail = isObject(body) ? body.detail : undefined;
  if (typeof detail === "string") return new ApiError(detail, response.status, {}, errorId);
  if (Array.isArray(detail)) {
    const fieldErrors: Record<string, string> = {};
    const message = detail
      .filter(isObject)
      .map((e) => {
        const field = Array.isArray(e.loc) ? e.loc.slice(1).join(".") : "";
        const text = (typeof e.msg === "string" ? e.msg : "").replace(/^Value error, /, "");
        if (field && !(field in fieldErrors)) fieldErrors[field] = text;
        return field ? `${field}: ${text}` : text;
      })
      .join("; ");
    return new ApiError(message, response.status, fieldErrors, errorId);
  }
  return new ApiError(response.statusText || String(response.status), response.status, {}, errorId);
}

/** The JSON of a good response. A body that is not JSON is an `invalid-response`, not a crash. */
async function parseJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    throw invalidResponse(response.status, "The response is not valid JSON");
  }
}

// One request, with a time limit. `withToken`: it carries the bearer token, and a 401 while holding one means it
// expired (or the account was deleted or deactivated): forget it, which sends the user back to the login page.
async function send(path: string, init: RequestInit, withToken: boolean): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = withToken ? getToken() : null;
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const timeout = AbortSignal.timeout(REQUEST_TIMEOUT_MS);
  const signal = init.signal ? AbortSignal.any([init.signal, timeout]) : timeout;
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers, signal });
  } catch (cause) {
    if (init.signal?.aborted) throw cause; // the caller gave up on purpose: nobody needs to be told
    // fetch only rejects when the request never got an answer (offline, API down, DNS, too slow...).
    console.warn("[api] the request got no answer:", path, cause);
    throw timeout.aborted
      ? new ApiError("The server took too long to answer", 0, {}, undefined, "timeout")
      : new ApiError("No response from the server", 0, {}, undefined, "network");
  }
  // Only if it is still the stored token: a late 401 for an old one must not end a newer session.
  if (withToken && response.status === 401 && token && getToken() === token) clearToken();
  return response;
}

const apiFetch = (path: string, init: RequestInit = {}) => send(path, init, true);

export async function login(email: string, password: string): Promise<void> {
  // OAuth2 password flow: form-encoded, and the field is called "username" but carries the email.
  const response = await send("/auth/login", { method: "POST", body: new URLSearchParams({ username: email, password }) }, false);
  if (!response.ok) {
    throw await toApiError(response);
  }
  const body = await parseJson(response);
  const token = isObject(body) ? body.access_token : undefined;
  if (typeof token !== "string" || token === "") throw invalidResponse(response.status, "The login answer has no token");
  if (!setToken(token)) throw new ApiError("The browser would not keep the session", 0, {}, undefined, "storage");
}

/** Public sign-up (POST /users). Empty optional profile fields are left out rather than sent blank. */
export async function register(payload: SignUpPayload): Promise<SignUpOut> {
  const body = Object.fromEntries(Object.entries(payload).filter(([, value]) => value !== undefined && value !== ""));
  const response = await send("/users", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }, false);
  if (!response.ok) {
    throw await toApiError(response);
  }
  const created = await parseJson(response);
  if (!isObject(created)) throw invalidResponse(response.status, "The sign-up answer is not an account");
  return created as unknown as SignUpOut;
}

export async function fetchMe(): Promise<Me> {
  const response = await apiFetch("/auth/me");
  if (!response.ok) {
    throw await toApiError(response);
  }
  const me = toMe(await parseJson(response));
  if (!me) throw invalidResponse(response.status, "The session answer is not a user");
  return me;
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
  const profile = toProfile(await parseJson(response));
  if (!profile) throw invalidResponse(response.status, "The profile answer is not a profile");
  return profile;
}

export async function analyzeIncidentsFile(file: File): Promise<AnalyzeResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await apiFetch("/api/incidents/analyze", {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw await toApiError(response);
  }

  const result = toAnalyzeResponse(await parseJson(response));
  if (!result) throw invalidResponse(response.status, "The analysis answer is not an analysis");
  return result;
}

export async function downloadResultsCsv(): Promise<void> {
  const response = await apiFetch("/api/incidents/results/export");

  if (!response.ok) {
    throw await toApiError(response);
  }

  let blob: Blob;
  try {
    blob = await response.blob();
  } catch {
    throw new ApiError("The download was interrupted", 0, {}, undefined, "network");
  }
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "results.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function suppliersRequest(path: string, init?: RequestInit): Promise<unknown> {
  const response = await apiFetch(`/api/suppliers${path}`, {
    ...init,
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
  });
  if (!response.ok) {
    throw await toApiError(response);
  }
  return parseJson(response);
}

async function oneSupplier(path: string, init?: RequestInit): Promise<Supplier> {
  const body = await suppliersRequest(path, init);
  if (!isObject(body)) throw invalidResponse(200, "The supplier answer is not a supplier");
  return toSupplier(body);
}

export async function listSuppliers(): Promise<Supplier[]> {
  const suppliers = toSuppliers(await suppliersRequest(""));
  if (!suppliers) throw invalidResponse(200, "The supplier list answer is not a list");
  return suppliers;
}

export const createSupplier = (payload: SupplierCreate) => oneSupplier("", { method: "POST", body: JSON.stringify(payload) });

export const updateSupplierRate = (id: number, monthly_rate: number) =>
  oneSupplier(`/${id}/rate`, { method: "PATCH", body: JSON.stringify({ monthly_rate }) });

export const setSupplierStatus = (id: number, status: SupplierStatus) =>
  oneSupplier(`/${id}/status`, { method: "PATCH", body: JSON.stringify({ status }) });

// ---- Incident manager -----------------------------------------------------------------------

export type SortField = "created_at" | "id" | "updated_at";
export type SortOrder = "asc" | "desc";

function filtersQuery(filters: IncidentFilters): URLSearchParams {
  const params = new URLSearchParams();
  filters.status.forEach((v) => params.append("status", v));
  filters.category.forEach((v) => params.append("category", v));
  filters.origin.forEach((v) => params.append("origin", v));
  for (const key of ["branch", "agent_id", "client_company", "q", "date_from", "date_to"] as const) {
    if (filters[key].trim()) params.set(key, filters[key].trim());
  }
  return params;
}

async function incidentsRequest(path: string, init?: RequestInit): Promise<unknown> {
  const response = await apiFetch(`/api/incidents${path}`, {
    ...init,
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
  });
  if (!response.ok) {
    throw await toApiError(response);
  }
  return parseJson(response);
}

/** Checks what an incident endpoint answered with `convert`; anything else is an `invalid-response`. */
async function incidentsAs<T>(convert: (raw: unknown) => T | null, what: string, path: string, init?: RequestInit): Promise<T> {
  const value = convert(await incidentsRequest(path, init));
  if (value === null) throw invalidResponse(200, `The ${what} answer has an unexpected shape`);
  return value;
}

export function listIncidents(
  filters: IncidentFilters,
  options: { sort: SortField; order: SortOrder; page: number; pageSize: number },
): Promise<IncidentPage> {
  const params = filtersQuery(filters);
  params.set("sort", options.sort);
  params.set("order", options.order);
  params.set("page", String(options.page));
  params.set("page_size", String(options.pageSize));
  return incidentsAs(toIncidentPage, "incident list", `?${params}`);
}

export const getIncidentSummary = (filters: IncidentFilters): Promise<IncidentSummary> =>
  incidentsAs(toIncidentSummary, "summary", `/summary?${filtersQuery(filters)}`);

export const getIncidentFacets = (): Promise<IncidentFacets> => incidentsAs(toIncidentFacets, "filter options", "/facets");

export const getIncident = (incidentId: string): Promise<Incident> =>
  incidentsAs(toIncident, "incident", `/${encodeURIComponent(incidentId)}`);

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

export const createIncident = (payload: IncidentFields): Promise<Incident> =>
  incidentsAs(toIncident, "incident", "", { method: "POST", body: JSON.stringify(payload) });

export const updateIncident = (incidentId: string, changes: Partial<IncidentFields>): Promise<Incident> =>
  incidentsAs(toIncident, "incident", `/${encodeURIComponent(incidentId)}`, { method: "PATCH", body: JSON.stringify(changes) });

export const changeIncidentStatus = (incidentId: string, change: StatusChangeInput): Promise<Incident> =>
  incidentsAs(toIncident, "incident", `/${encodeURIComponent(incidentId)}/status`, { method: "PATCH", body: JSON.stringify(change) });
