import { jsonRequest } from "./api";
import type { Finding, TechnicalReport } from "../types/telemetryReport";

/** The periods the dashboard offers. "7d" is the API's own default, so it sends no parameter at all. */
export const RANGES = [
  { id: "7d", label: "Últimos 7 días", days: 7 },
  { id: "30d", label: "Últimos 30 días", days: 30 },
  { id: "90d", label: "Últimos 90 días", days: 90 },
] as const;

export type RangeId = (typeof RANGES)[number]["id"];

/**
 * The query string of a period. The start is the UTC midnight `days` ago, not "exactly N days ago": the API caches a report per requested
 * `start_date` for 60 s, and a start that moves every millisecond would never hit that cache. The end is left out (= now).
 */
export function rangeQuery(range: RangeId, now: Date = new Date()): string {
  if (range === "7d") return "";
  const days = RANGES.find((r) => r.id === range)!.days;
  const start = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() - days));
  return `?start_date=${encodeURIComponent(start.toISOString())}`;
}

/** The technical report of the period. Admin only: the API answers 403 to anybody else. */
export const getTechnicalReport = (range: RangeId) => jsonRequest<TechnicalReport>(`/telemetry/report${rangeQuery(range)}`);

export interface Summary {
  events: number;
  technicalEvents: number;
  errors: number;
  errorRate: number | null;
  loginAttempts: number;
  loginFailures: number;
  loginFailureRate: number | null;
  slowest: { section: string; p95: number; overTarget: boolean } | null;
}

const sum = (values: number[]) => values.reduce((total, value) => total + value, 0);
const ratio = (part: number, whole: number) => (whole > 0 ? part / whole : null);

/** The headline numbers of the KPI row, each one added up from a series the page also draws (so the tiles and the charts agree). */
export function summarize(report: TechnicalReport): Summary {
  const { events_per_day, errors_per_day, auth_failure_rate, section_load_latency } = report.metrics;
  const technicalEvents = sum(errors_per_day.map((d) => d.technical_events));
  const errors = sum(errors_per_day.map((d) => d.errors));
  const loginAttempts = sum(auth_failure_rate.map((d) => d.attempts));
  const loginFailures = sum(auth_failure_rate.map((d) => d.failed));
  const withP95 = section_load_latency.filter((s) => s.p95_ms !== null); // the API lists them slowest first
  return {
    events: sum(events_per_day.map((d) => d.events)),
    technicalEvents,
    errors,
    errorRate: ratio(errors, technicalEvents),
    loginAttempts,
    loginFailures,
    loginFailureRate: ratio(loginFailures, loginAttempts),
    slowest: withP95.length ? { section: withP95[0].section, p95: withP95[0].p95_ms as number, overTarget: withP95[0].over_target } : null,
  };
}

const percentFormat = new Intl.NumberFormat("es-ES", { style: "percent", maximumFractionDigits: 1 });
const numberFormat = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 1 });

/** 0.5556 → "55,6 %"; null (no denominator) → "—". */
export const formatPercent = (rate: number | null) => (rate === null ? "—" : percentFormat.format(rate));
export const formatNumber = (value: number | null) => (value === null ? "—" : numberFormat.format(value));
export const formatMs = (ms: number | null) => (ms === null ? "—" : `${numberFormat.format(Math.round(ms))} ms`);

/** "2026-10-30" → "30/10" (the year is in the period line). The day is already a UTC calendar date: no timezone shifts it. */
export function formatDay(day: string): string {
  const [, month, date] = day.split("-");
  return `${date}/${month}`;
}

/** The longest "nice" value at or above `value` for an axis maximum: 1, 2, 5 × 10ⁿ. */
export function niceMax(value: number): number {
  if (value <= 0) return 1;
  const power = 10 ** Math.floor(Math.log10(value));
  const step = [1, 2, 5, 10].find((s) => s * power >= value)!;
  return step * power;
}

const text = (value: unknown): string | null => (typeof value === "string" ? value : null);
const count = (value: unknown): number | null => (typeof value === "number" ? value : null);
const plural = (n: number, one: string, many: string) => `${formatNumber(n)} ${n === 1 ? one : many}`;

/**
 * A finding in Spanish. The API sends its messages in English (it is JSON for tools as much as for this page), so the dashboard writes its own
 * sentence per `code`, with the numbers from `evidence`. A code it does not know, or evidence it cannot read, falls back to the API's text:
 * a new kind of finding appears in English instead of not appearing.
 */
export function describeFinding(finding: Finding): string {
  const e = finding.evidence ?? {};
  const rows = (key: string): Record<string, unknown>[] => (Array.isArray(e[key]) ? (e[key] as Record<string, unknown>[]) : []);
  let spanish: string | null = null;
  switch (finding.code) {
    case "application_errors": {
      const total = count(e.total);
      const worst = rows("by_component_and_code")[0];
      if (total !== null && worst) spanish = `${plural(total, "error de aplicación sin gestionar", "errores de aplicación sin gestionar")}; el más frecuente: ${text(worst.component)}/${text(worst.error_code)} (${count(worst.errors)}).`;
      break;
    }
    case "login_failure_rate": {
      const failed = count(e.failed);
      const completed = count(e.completed);
      if (failed !== null && completed) spanish = `${formatPercent(failed / completed)} de los ${completed} logins con resultado fallaron (alerta propuesta: más del 30 %).`;
      break;
    }
    case "login_internal_error": {
      const n = count(e.count);
      if (n !== null) spanish = `${plural(n, "login falló", "logins fallaron")} por error interno: es el servidor fallando, no unas credenciales incorrectas.`;
      break;
    }
    case "slow_section":
      if (text(e.section) && count(e.p95_ms) !== null) spanish = `La sección «${text(e.section)}» tarda ${formatMs(count(e.p95_ms))} en el p95 (objetivo: menos de 2 s).`;
      break;
    case "section_load_errors":
      if (text(e.section) && count(e.errors) !== null && count(e.loads) !== null) spanish = `La sección «${text(e.section)}» terminó en error en ${e.errors} de ${plural(e.loads as number, "carga", "cargas")}.`;
      break;
    case "poor_web_vital":
      if (text(e.metric) && count(e.poor) !== null && count(e.readings) !== null) spanish = `${text(e.metric)} valorado como malo en ${e.poor} de ${plural(e.readings as number, "lectura", "lecturas")} (p75 = ${formatNumber(count(e.p75))}).`;
      break;
    case "api_5xx_rate":
      if (text(e.route) && count(e.error_rate) !== null && count(e.requests) !== null) spanish = `La ruta «${text(e.route)}» devolvió 5xx en el ${formatPercent(count(e.error_rate))} de ${plural(e.requests as number, "petición", "peticiones")}.`;
      break;
    case "api_slow_route":
      if (text(e.route) && count(e.p95_ms) !== null) spanish = `La ruta «${text(e.route)}» tarda ${formatMs(count(e.p95_ms))} en el p95 (alerta propuesta: más de 1 s).`;
      break;
    case "authorization_denied": {
      const byRoute = rows("by_route");
      if (byRoute.length) spanish = `${plural(byRoute.reduce((total, row) => total + (count(row.denied) ?? 0), 0), "petición denegada", "peticiones denegadas")} (401/403); la ruta más afectada: ${text(byRoute[0].route_id)}.`;
      break;
    }
    case "instrumentation_gap": {
      const missing = Array.isArray(e.not_observed) ? (e.not_observed as string[]) : null;
      if (missing) spanish = `No llegan eventos de ${plural(missing.length, "tipo técnico", "tipos técnicos")} (${missing.slice(0, 3).join(", ")}${missing.length > 3 ? ", …" : ""}): el reporte no puede decir nada sobre ellos.`;
      break;
    }
  }
  return spanish ?? finding.message;
}
