// Showing a value that may be missing, in one place. Whatever the API sends (a null, a field that is not there,
// a date nobody can read), the screen shows a dash or a plain text, never `undefined`, `NaN` or `Invalid Date`.

export const MISSING = "—";

/** The label of a code (`TECHNICAL` -> «Técnica»), or the code itself, or a dash when there is none. */
export function labelOf(labels: Record<string, string>, code: unknown): string {
  if (typeof code !== "string" || code === "") return MISSING;
  return labels[code] ?? code;
}

function toDate(value: unknown): Date | null {
  if (typeof value !== "string" && typeof value !== "number") return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** `2024-03-05T10:30:00Z` -> «5/3/2024, 10:30:00», or a dash if it is not a date. */
export function formatDateTime(value: unknown): string {
  return toDate(value)?.toLocaleString("es-ES") ?? MISSING;
}

/** The day of an ISO date, as it comes (`2024-03-05`), or a dash. */
export function formatDay(value: unknown): string {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}/.test(value) ? value.slice(0, 10) : MISSING;
}

export function formatMoney(value: unknown, currency: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return MISSING;
  const code = currency === "USD" || currency === "EUR" ? currency : "EUR";
  return new Intl.NumberFormat("es-ES", { style: "currency", currency: code }).format(value);
}

/** A count to show: a number, or 0 when the API did not send one. */
export function count(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

/** A percentage for a bar: between 0 and 100, 0 when it is not a number. */
export function percent(value: unknown): number {
  return Math.min(100, Math.max(0, count(value)));
}
