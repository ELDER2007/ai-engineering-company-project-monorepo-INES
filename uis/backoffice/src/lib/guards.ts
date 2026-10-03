// What the API sends is checked here before any screen sees it. A response with another shape (an older
// server, a proxy page, a damaged record) becomes an error the screen can show with a retry, not a crash;
// a field that is missing inside an otherwise good response gets a default.
import type {
  HistoryEntry,
  Incident,
  IncidentFacets,
  IncidentListItem,
  IncidentPage,
  IncidentSummary,
} from "@repo/shared-types";
import type { AnalyzeResponse } from "../types/incidents";
import type { Me, Profile } from "../types/auth";
import type { Supplier } from "../types/suppliers";

export const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const list = (value: unknown): unknown[] => (Array.isArray(value) ? value : []);
const strings = (value: unknown): string[] => list(value).filter((x): x is string => typeof x === "string");
const num = (value: unknown, fallback = 0): number => (typeof value === "number" && Number.isFinite(value) ? value : fallback);
const text = (value: unknown, fallback = ""): string => (typeof value === "string" ? value : fallback);
const textOrNull = (value: unknown): string | null => (typeof value === "string" ? value : null);
const numbers = (value: unknown): Record<string, number> =>
  isObject(value) ? Object.fromEntries(Object.entries(value).map(([key, n]) => [key, num(n)])) : {};

/** Whether `value` is an object that has a text `id`: the minimum to show a row. */
const hasId = (value: unknown): value is Record<string, unknown> => isObject(value) && typeof value.id === "string";

function historyEntry(raw: Record<string, unknown>): HistoryEntry {
  return {
    at: text(raw.at),
    kind: raw.kind as HistoryEntry["kind"],
    actor: text(raw.actor),
    from_status: (textOrNull(raw.from_status) as HistoryEntry["from_status"]) ?? null,
    to_status: (textOrNull(raw.to_status) as HistoryEntry["to_status"]) ?? null,
    fields: strings(raw.fields),
    note: textOrNull(raw.note),
  };
}

function listItem(raw: Record<string, unknown>): IncidentListItem {
  return {
    ...(raw as unknown as IncidentListItem),
    created_at: text(raw.created_at),
    updated_at: text(raw.updated_at),
    allowed_transitions: strings(raw.allowed_transitions) as IncidentListItem["allowed_transitions"],
    editable: raw.editable === true,
    customer_email_masked: textOrNull(raw.customer_email_masked),
  };
}

/** The page of incidents, or `null` when the response is not one. Rows without an id are dropped. */
export function toIncidentPage(raw: unknown): IncidentPage | null {
  if (!isObject(raw) || !Array.isArray(raw.items)) return null;
  const items = raw.items.filter(hasId);
  if (items.length < raw.items.length) console.warn(`[api] ${raw.items.length - items.length} incident row(s) without an id were left out`);
  return {
    items: items.map(listItem),
    total: num(raw.total, items.length),
    page: num(raw.page, 1),
    page_size: num(raw.page_size, items.length),
    pages: num(raw.pages, items.length ? 1 : 0),
  };
}

/** The summary, or `null` when the response is not one. Missing counts are 0 and missing lists are empty. */
export function toIncidentSummary(raw: unknown): IncidentSummary | null {
  if (!isObject(raw)) return null;
  const item = (x: unknown) => (isObject(x) ? { name: text(x.name), count: num(x.count) } : null);
  return {
    total: num(raw.total),
    status_counts: numbers(raw.status_counts),
    status_percentages: numbers(raw.status_percentages),
    category_counts: numbers(raw.category_counts),
    category_percentages: numbers(raw.category_percentages),
    origin_counts: numbers(raw.origin_counts),
    active_by_category: numbers(raw.active_by_category),
    satisfaction_average: typeof raw.satisfaction_average === "number" ? raw.satisfaction_average : null,
    satisfaction_scored: num(raw.satisfaction_scored),
    satisfaction_distribution: numbers(raw.satisfaction_distribution),
    top_branches: list(raw.top_branches).map(item).filter((x) => x !== null),
    top_clients: list(raw.top_clients).map(item).filter((x) => x !== null),
  } as unknown as IncidentSummary;
}

export function toIncidentFacets(raw: unknown): IncidentFacets | null {
  if (!isObject(raw)) return null;
  return { branches: strings(raw.branches), clients: strings(raw.clients), agents: strings(raw.agents) };
}

/** One incident with its history, or `null` when the response is not one. */
export function toIncident(raw: unknown): Incident | null {
  if (!hasId(raw)) return null;
  return {
    ...listItem(raw),
    customer_email: textOrNull(raw.customer_email),
    history: list(raw.history).filter(isObject).map(historyEntry),
  } as unknown as Incident;
}

export function toSupplier(raw: Record<string, unknown>): Supplier {
  return { ...(raw as unknown as Supplier), categories: strings(raw.categories) as Supplier["categories"] };
}

export function toSuppliers(raw: unknown): Supplier[] | null {
  if (!Array.isArray(raw)) return null;
  return raw.filter(isObject).map(toSupplier);
}

export function toProfile(raw: unknown, userId = ""): Profile | null {
  if (!isObject(raw)) return null;
  return {
    id: text(raw.id),
    user_id: text(raw.user_id, userId),
    name: text(raw.name),
    contact_email: textOrNull(raw.contact_email),
    phone: textOrNull(raw.phone),
    address: textOrNull(raw.address),
  };
}

/** The session's user. A profile that is missing is built from the email, so no screen has to guess. */
export function toMe(raw: unknown): Me | null {
  if (!isObject(raw) || typeof raw.id !== "string" || typeof raw.email !== "string") return null;
  const profile = toProfile(raw.profile, raw.id) ?? {
    id: "",
    user_id: raw.id,
    name: raw.email.split("@")[0],
    contact_email: null,
    phone: null,
    address: null,
  };
  return { ...(raw as unknown as Me), profile: { ...profile, name: profile.name || raw.email.split("@")[0] } };
}

export function toAnalyzeResponse(raw: unknown): AnalyzeResponse | null {
  if (!isObject(raw) || !isObject(raw.satisfaction) || !isObject(raw.category_counts) || !isObject(raw.status_counts)) return null;
  const satisfaction = raw.satisfaction;
  return {
    ...(raw as unknown as AnalyzeResponse),
    total_records: num(raw.total_records),
    valid_records: num(raw.valid_records),
    invalid_records: num(raw.invalid_records),
    invalid_breakdown: numbers(raw.invalid_breakdown) as unknown as AnalyzeResponse["invalid_breakdown"],
    category_counts: numbers(raw.category_counts),
    category_percentages: numbers(raw.category_percentages),
    status_counts: numbers(raw.status_counts),
    status_percentages: numbers(raw.status_percentages),
    satisfaction: {
      scored: num(satisfaction.scored),
      closed: num(satisfaction.closed),
      average: typeof satisfaction.average === "number" ? satisfaction.average : null,
      distribution: numbers(satisfaction.distribution),
    },
  };
}
