"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, ChevronLeft, ChevronRight, Info } from "lucide-react";
import { DataTable } from "../components/health/charts";
import { ErrorBanner } from "../components/ui/Field";
import LoadingState from "../components/ui/LoadingState";
import { describeError, isNotFound } from "../lib/errors";
import { formatMoney } from "../lib/format";
import {
  KPIS,
  barPercent,
  currencyName,
  currentWeekStart,
  NEVER_RAN,
  describeDataHealth,
  describeFreshness,
  formatCount,
  formatValue,
  formatWeekRange,
  getLatestPipelineRun,
  getWeeklyPerformance,
  isFutureWeek,
  kpiRows,
  shiftWeek,
  totalCount,
  totalsByCurrency,
  type DataFreshness,
  type KpiDefinition,
} from "../lib/reporting";
import type { PipelineRun, WeeklyEntry, WeeklyReport } from "../types/reporting";

const TONE: Record<DataFreshness["tone"], { Icon: typeof Info; color: string }> = {
  ok: { Icon: CheckCircle2, color: "#34d399" },
  warning: { Icon: AlertTriangle, color: "#fab219" },
  info: { Icon: Info, color: "#94a3b8" },
};

/** A value with a bar next to it, so the offices and programmes can be compared at a glance. The bar only repeats the number. */
function ValueBar({ text, percent }: { text: string; percent: number }) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-32 shrink-0 text-slate-100">{text}</span>
      <div className="h-2 w-full max-w-[14rem] rounded bg-slate-800" aria-hidden="true">
        <div className="h-2 rounded bg-sky-400" style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}

/** One KPI: its name and definition from the briefing, the total of the week and a table of every office and programme. */
function KpiSection({ kpi, entries }: { kpi: KpiDefinition; entries: WeeklyEntry[] }) {
  const rows = kpiRows(entries, kpi.key);
  const nothing = rows.every((row) => row.value === 0);
  // The bars of a money KPI are compared within one currency: a dollar bar next to a euro bar would say nothing.
  const largestOf = (currency: string) => Math.max(0, ...rows.filter((row) => kpi.kind === "count" || row.currency === currency).map((row) => row.value));
  return (
    <section aria-labelledby={`kpi-${kpi.key}`} className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
      <h2 id={`kpi-${kpi.key}`} className="text-lg font-semibold text-white">
        {kpi.name}
      </h2>
      <p className="mt-1 text-sm text-slate-300">{kpi.measures}</p>
      <p className="mt-1 text-sm text-slate-400">{kpi.purpose}</p>

      {nothing ? (
        <p className="mt-4 text-slate-200">{kpi.empty}</p>
      ) : (
        <>
          <div className="mt-4 flex flex-wrap gap-x-8 gap-y-1">
            {kpi.kind === "money" ? (
              totalsByCurrency(rows).map(({ currency, total }) => (
                <p key={currency} className="text-slate-200">
                  Total en {currencyName(currency)}: <strong className="text-2xl font-bold text-white">{formatMoney(total, currency)}</strong>
                </p>
              ))
            ) : (
              <p className="text-slate-200">
                Total: <strong className="text-2xl font-bold text-white">{formatCount(totalCount(rows), kpi.unit)}</strong>
              </p>
            )}
          </div>
          <div className="mt-4 overflow-x-auto">
            <DataTable
              columns={["Oficina", "Programa", kpi.kind === "money" ? "Costo de material" : "Cantidad"]}
              rows={rows.map((row) => [
                row.officeLabel,
                row.programmeLabel,
                <ValueBar key={`${row.office}-${row.programmeLabel}`} text={formatValue(row, kpi.kind, kpi.unit)} percent={barPercent(row.value, largestOf(row.currency))} />,
              ])}
            />
          </div>
        </>
      )}
      {kpi.note && <p className="mt-3 text-xs text-slate-400">{kpi.note}</p>}
    </section>
  );
}

/**
 * Weekly performance (/reporting): the report the leadership asked for, "Reporte Semanal de Desempeño por Oficina y Programa". It shows the four KPIs
 * of the briefing, each with its name and definition, for one week at a time (the latest computed one at first), with the period it covers and how
 * fresh the data is. It is made for people who are not technical: plain Spanish, euros and dollars never added together, no jargon. It computes
 * nothing: every number comes from `GET /reporting/weekly-office-program-performance`.
 */
export default function BusinessPerformancePage() {
  const [report, setReport] = useState<WeeklyReport | null>(null);
  const [selected, setSelected] = useState<string | null>(null); // null: the latest week the API has computed
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nothingYet, setNothingYet] = useState(false);
  const [run, setRun] = useState<PipelineRun | null>(null);
  const [neverRan, setNeverRan] = useState(false);
  const latest = useRef(0);

  const load = useCallback(async (weekStart: string | null) => {
    const request = ++latest.current;
    setLoading(true);
    setError(null);
    try {
      const fresh = await getWeeklyPerformance(weekStart ?? undefined);
      if (request !== latest.current) return; // a slower answer to an older choice must not overwrite a newer one
      setReport(fresh);
      setNothingYet(false);
    } catch (err) {
      if (request !== latest.current) return;
      if (isNotFound(err)) setNothingYet(true); // the process has not computed any week yet: not an error of the reader
      else setError(describeError(err, "No se pudo cargar el reporte semanal."));
    } finally {
      if (request === latest.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(null);
  }, [load]);

  useEffect(() => {
    // How fresh the numbers are is a nicety: if it cannot be read, the page simply does not say it.
    getLatestPipelineRun()
      .then(setRun)
      .catch((err) => setNeverRan(isNotFound(err))); // "never ran" is worth saying; any other failure is not
  }, []);

  const go = (weekStart: string) => {
    setSelected(weekStart);
    void load(weekStart);
  };

  const shown = report?.week_start ?? null;
  const next = shown ? shiftWeek(shown, 1) : null;
  const freshness = run ? describeFreshness(run) : neverRan ? NEVER_RAN : null;
  const FreshIcon = freshness ? TONE[freshness.tone].Icon : null;
  const health = run && shown ? describeDataHealth(run, shown) : [];

  return (
    <div className="mx-auto max-w-5xl">
      <h1 className="text-3xl font-bold text-white">Reporte semanal de desempeño por oficina y programa</h1>
      <p className="mt-2 text-slate-300">Cómo van Valencia y Miami en inversión y entrega de material de formación.</p>
      {freshness && FreshIcon && (
        <p className="mt-2 flex items-center gap-2 text-sm text-slate-300">
          <FreshIcon size={16} color={TONE[freshness.tone].color} aria-hidden="true" className="shrink-0" />
          {freshness.text}
        </p>
      )}

      {health.length > 0 && (
        <ul aria-label="Avisos sobre los datos" className="mt-3 space-y-2">
          {health.map((text) => (
            <li key={text} className="flex items-start gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
              <AlertTriangle size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
              {text}
            </li>
          ))}
        </ul>
      )}

      {shown && (
        <div className="mt-6 flex flex-wrap items-center gap-3">
          <button type="button" onClick={() => go(shiftWeek(shown, -1))} className="inline-flex items-center gap-1 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-200 hover:bg-slate-800">
            <ChevronLeft size={16} aria-hidden="true" />
            Semana anterior
          </button>
          <p role="status" className="min-w-0 flex-1 text-center font-medium text-white">
            {formatWeekRange(shown)}
          </p>
          <button
            type="button"
            onClick={() => next && go(next)}
            disabled={!next || isFutureWeek(next)}
            className="inline-flex items-center gap-1 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-200 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Semana siguiente
            <ChevronRight size={16} aria-hidden="true" />
          </button>
        </div>
      )}
      {selected !== null && (
        <button type="button" onClick={() => { setSelected(null); void load(null); }} className="mt-3 text-sm text-sky-300 underline hover:text-sky-200">
          Ir a la última semana calculada
        </button>
      )}

      {error && (
        <div className="mt-6">
          <ErrorBanner message={error} />
          <button type="button" onClick={() => void load(selected)} className="mt-3 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-200 hover:bg-slate-800">
            Reintentar
          </button>
        </div>
      )}
      {!report && loading && <LoadingState label="Cargando el reporte semanal…" reserveSpace className="mt-8" />}
      {nothingYet && !report && (
        <p className="mt-8 rounded-2xl border border-slate-800 bg-slate-900 p-5 text-slate-200">
          Todavía no hay ninguna semana calculada. Cuando se calcule la primera, sus números aparecerán aquí.
        </p>
      )}

      {report && (
        <div className="mt-6 space-y-5" aria-busy={loading}>
          {report.entries.length === 0 ? (
            <p className="rounded-2xl border border-slate-800 bg-slate-900 p-5 text-slate-200">
              No hay operaciones registradas en esta semana, así que no hay números que mostrar.
            </p>
          ) : (
            KPIS.map((kpi) => <KpiSection key={kpi.key} kpi={kpi} entries={report.entries} />)
          )}
          <p className="text-xs text-slate-500">Semana {report.week_start < currentWeekStart() ? "cerrada" : "en curso"}: de lunes a domingo.</p>
        </div>
      )}
    </div>
  );
}
