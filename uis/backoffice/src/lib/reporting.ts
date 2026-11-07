// The business dashboard (/reporting): the weekly KPIs per office and programme that the leadership reads. This file holds what is not drawing:
// the calls to the API, the four KPIs with the names and the definitions of the briefing ("KPIs a medir"), and the plain-Spanish helpers (weeks,
// offices, programmes, money, how fresh the data is). The numbers themselves are never computed here: they come from the API.
import { API_BASE_URL, jsonRequest } from "./api";
import { formatDateTime, formatMoney } from "./format";
import type { Currency, PipelineRun, WeeklyEntry, WeeklyReport } from "../types/reporting";

// In development the app calls /api/reporting/*, which next.config.mjs forwards to /reporting/* on the API: the prefix keeps the API apart from
// the /reporting page of the app (the same way /api/inventory/* is kept apart from the /inventory/* pages). With NEXT_PUBLIC_API_BASE_URL set
// the app calls the API directly.
const PREFIX = API_BASE_URL ? `${API_BASE_URL}/reporting` : "/api/reporting";

/** The KPIs of a week. Without `weekStart` the API answers with the latest week it has computed (404 if it has computed none). */
export const getWeeklyPerformance = (weekStart?: string) =>
  jsonRequest<WeeklyReport>(`${PREFIX}/weekly-office-program-performance${weekStart ? `?week_start=${encodeURIComponent(weekStart)}` : ""}`);

/** The latest run of the process that computes the KPIs (404 if it never ran). */
export const getLatestPipelineRun = () => jsonRequest<PipelineRun>(`${PREFIX}/pipeline-runs/latest`);

// ------------------------------------------------------------------------------------------------ the four KPIs of the briefing

export type KpiKey = "total_material_cost" | "kits_delivered_count" | "shortage_events_count" | "cost_variance_events_count";

export interface KpiDefinition {
  key: KpiKey;
  /** The name the KPI has in the briefing, word for word. */
  name: string;
  /** What it measures: the briefing's own sentence. */
  measures: string;
  /** What it is for, in the briefing's words without the names of the people. */
  purpose: string;
  kind: "money" | "count";
  /** Singular and plural of what is counted ("kit", "kits"); empty for money. */
  unit: readonly [string, string];
  /** What to say when the week has nothing to report for this KPI. */
  empty: string;
  /** A reading rule the stakeholder needs to read the number right. */
  note?: string;
}

export const KPIS: readonly KpiDefinition[] = [
  {
    key: "total_material_cost",
    name: "Costo de material por oficina/programa",
    measures: "Cuánto gastó una oficina adquiriendo material de formación o incorporación para un programa dado, durante la semana.",
    purpose: "Muestra dónde se concentra la inversión en formación y si coincide con la demanda de matrículas.",
    kind: "money",
    unit: ["", ""],
    empty: "Esta semana no se compró material.",
    note: "Cada oficina se muestra en su moneda: Valencia en euros y Miami en dólares. Nunca se suman entre sí.",
  },
  {
    key: "kits_delivered_count",
    name: "Kits entregados",
    measures: "Cuántos kits o certificados se entregaron realmente a clientes, candidatos, consultores o agentes durante la semana.",
    purpose: "Es la señal de adopción: el gasto en material solo importa si llega a las personas que lo necesitan.",
    kind: "count",
    unit: ["kit", "kits"],
    empty: "Esta semana no se entregó ningún kit.",
    note: "Cada pedido de entrega cuenta una vez, aunque incluya varias unidades.",
  },
  {
    key: "shortage_events_count",
    name: "Frecuencia de escasez",
    measures: "Cuántas veces durante la semana el stock de material de un programa cayó por debajo del mínimo configurado.",
    purpose: "Es un aviso temprano de que hay que reimprimir o reordenar antes de que afecte a una ola grande de matrículas.",
    kind: "count",
    unit: ["vez", "veces"],
    empty: "Ningún programa se quedó corto de material esta semana.",
  },
  {
    key: "cost_variance_events_count",
    name: "Frecuencia de variación de costo",
    measures: "Cuántas veces durante la semana el costo de un proveedor de material subió de forma anómala respecto a su histórico.",
    purpose: "Indica cuándo conviene renegociar con un proveedor o buscar uno alternativo.",
    kind: "count",
    unit: ["vez", "veces"],
    empty: "Ningún proveedor subió su costo de forma anómala esta semana.",
  },
];

// ------------------------------------------------------------------------------------------------ names a person can read

const OFFICES: Record<string, string> = { valencia: "Valencia", miami: "Miami" };
const PROGRAMMES: Record<string, string> = {
  "ventas-b2b": "Ventas B2B",
  "liderazgo-basico": "Liderazgo básico",
  "onboarding-soporte": "Onboarding de soporte",
};
const CURRENCY_NAMES: Record<Currency, string> = { EUR: "euros", USD: "dólares" };

const capitalize = (text: string) => (text ? text[0].toUpperCase() + text.slice(1) : text);

export const officeLabel = (office: string) => OFFICES[office] ?? capitalize(office);

/** A programme id as a name ("ventas-b2b" -> "Ventas B2B"). A programme this file does not know is shown readable, never hidden. */
export const programmeLabel = (id: string) => PROGRAMMES[id] ?? capitalize(id.replace(/[-_]+/g, " ").trim());

export const currencyName = (currency: Currency) => CURRENCY_NAMES[currency] ?? currency;

/** "1 kit", "3 kits", "0 veces". */
export const formatCount = (value: number, unit: readonly [string, string]) => `${new Intl.NumberFormat("es-ES").format(value)} ${value === 1 ? unit[0] : unit[1]}`;

// ------------------------------------------------------------------------------------------------ weeks (Monday to Sunday, UTC)

const DAY_MS = 86_400_000;
const parseDay = (iso: string) => new Date(`${iso}T00:00:00Z`);
const toIso = (date: Date) => date.toISOString().slice(0, 10);

/** The Monday `weeks` weeks after (or before, if negative) the Monday `weekStart`. */
export const shiftWeek = (weekStart: string, weeks: number) => toIso(new Date(parseDay(weekStart).getTime() + weeks * 7 * DAY_MS));

/** The Monday (UTC) of the week of `now`: the newest week that can have data. */
export function currentWeekStart(now: Date = new Date()): string {
  const day = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  return toIso(new Date(day.getTime() - ((day.getUTCDay() + 6) % 7) * DAY_MS));
}

/** A week that has not started yet: there is nothing to show for it. */
export const isFutureWeek = (weekStart: string, now: Date = new Date()) => weekStart > currentWeekStart(now);

const dayName = (date: Date, withYear: boolean) =>
  new Intl.DateTimeFormat("es-ES", { weekday: "long", day: "numeric", month: "long", ...(withYear ? { year: "numeric" } : {}), timeZone: "UTC" })
    .format(date)
    .replace(",", "");

/** "Semana del lunes 26 de octubre al domingo 1 de noviembre de 2026": the period the numbers cover. */
export function formatWeekRange(weekStart: string): string {
  const start = parseDay(weekStart);
  const end = new Date(start.getTime() + 6 * DAY_MS);
  const sameYear = start.getUTCFullYear() === end.getUTCFullYear();
  return `Semana del ${dayName(start, !sameYear)} al ${dayName(end, true)}`;
}

// ------------------------------------------------------------------------------------------------ one KPI as rows and totals

export interface KpiRow {
  office: string;
  officeLabel: string;
  programmeLabel: string;
  value: number;
  currency: Currency;
}

/** The rows of one KPI, in the order the API gives them (by office, then programme). */
export const kpiRows = (entries: WeeklyEntry[], key: KpiKey): KpiRow[] =>
  entries.map((entry) => ({
    office: entry.office,
    officeLabel: officeLabel(entry.office),
    programmeLabel: programmeLabel(entry.programme_id),
    value: entry[key],
    currency: entry.currency,
  }));

/** The total of a money KPI PER CURRENCY: euros and dollars are never added together. */
export function totalsByCurrency(rows: KpiRow[]): { currency: Currency; total: number }[] {
  const totals = new Map<Currency, number>();
  for (const row of rows) totals.set(row.currency, (totals.get(row.currency) ?? 0) + row.value);
  return [...totals].map(([currency, total]) => ({ currency, total }));
}

export const totalCount = (rows: KpiRow[]) => rows.reduce((sum, row) => sum + row.value, 0);

/** How long a bar is, as a percentage of the largest value it is compared with (a bar of a value above zero is always visible). */
export const barPercent = (value: number, largest: number) => (largest <= 0 || value <= 0 ? 0 : Math.max(2, Math.min(100, (value / largest) * 100)));

export const formatValue = (row: KpiRow, kind: KpiDefinition["kind"], unit: readonly [string, string]) =>
  kind === "money" ? formatMoney(row.value, row.currency) : formatCount(row.value, unit);

// ------------------------------------------------------------------------------------------------ how fresh and how complete the numbers are

export interface DataFreshness {
  tone: "ok" | "warning" | "info";
  text: string;
}

/** The numbers are computed once a week, so a last update older than a week and a day means the process has stopped. */
export const STALE_AFTER_DAYS = 8;

/** The process that computes the numbers has not run at all: the report may be empty for that reason, not because nothing happened. */
export const NEVER_RAN: DataFreshness = { tone: "warning", text: "El proceso que calcula estos datos todavía no se ha ejecutado." };

/** What to tell the reader about the process that computes the numbers, without naming it. */
export function describeFreshness(run: PipelineRun, now: Date = new Date()): DataFreshness {
  if (run.state === "Completed") {
    if (!run.finished_at) return { tone: "ok", text: "Datos actualizados." };
    const days = Math.floor((now.getTime() - new Date(run.finished_at).getTime()) / DAY_MS);
    if (days >= STALE_AFTER_DAYS) {
      return { tone: "warning", text: `Los datos llevan ${days} días sin actualizarse: se esperaba una actualización cada semana, así que pueden estar desfasados.` };
    }
    return { tone: "ok", text: `Datos actualizados el ${formatDateTime(run.finished_at)}.` };
  }
  if (run.state === "Failed" || run.state === "Crashed") {
    return { tone: "warning", text: "La última actualización de los datos no terminó bien, así que estos números pueden no estar al día." };
  }
  return { tone: "info", text: "Los datos se están actualizando en este momento." };
}

// What the process says about whether the data was COLLECTED (its "data_health" notes), in words for the reader. The codes are the pipeline's.
const DATA_HEALTH: Record<string, string> = {
  capture_silent:
    "No se registró ninguna actividad en el sistema durante esta semana. Si no era de esperar, es posible que los datos no se hayan recogido y que los números de abajo estén incompletos.",
  volume_drop: "Esta semana hay mucha menos actividad registrada que en las semanas anteriores. Conviene comprobar que los datos se están recogiendo bien.",
};
const DATA_HEALTH_UNKNOWN = "Hay un aviso sobre si los datos de esta semana se han recogido bien.";

/**
 * The notes about whether the data of `weekStart` was collected, in plain Spanish. The latest run only speaks for the week it computed:
 * looking at another week it says nothing.
 */
export function describeDataHealth(run: PipelineRun, weekStart: string): string[] {
  if (run.week_start !== weekStart || !run.warnings) return [];
  return run.warnings
    .split("; ")
    .map((note) => /^data_health:([a-z_]+):/.exec(note))
    .filter((match): match is RegExpExecArray => match !== null)
    .map((match) => DATA_HEALTH[match[1]] ?? DATA_HEALTH_UNKNOWN);
}
