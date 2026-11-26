"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, Info, OctagonAlert } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { ChartCard, ColumnChart, DataTable, RankedBars, type ColumnDatum } from "../components/health/charts";
import { ErrorBanner } from "../components/ui/Field";
import LoadingState from "../components/ui/LoadingState";
import { describeError } from "../lib/errors";
import {
  RANGES,
  describeFinding,
  formatDay,
  formatMs,
  formatNumber,
  formatPercent,
  getTechnicalReport,
  summarize,
  type RangeId,
} from "../lib/telemetryReport";
import type { Finding, FindingSeverity, TechnicalReport } from "../types/telemetryReport";

const SEVERITY: Record<FindingSeverity, { label: string; color: string; Icon: typeof Info }> = {
  critical: { label: "Crítico", color: "#d03b3b", Icon: OctagonAlert },
  warning: { label: "Aviso", color: "#fab219", Icon: AlertTriangle },
  info: { label: "Información", color: "#94a3b8", Icon: Info },
};

const TOP_TYPES = 8;

function Tile({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
      <p className="text-sm text-slate-400">{label}</p>
      <p className="mt-2 text-3xl font-bold text-white">{value}</p>
      <p className="mt-1 text-xs text-slate-400">{detail}</p>
    </div>
  );
}

function FindingRow({ finding }: { finding: Finding }) {
  const { label, color, Icon } = SEVERITY[finding.severity];
  return (
    <li className="flex items-start gap-3 text-sm">
      {/* state is the icon + the word; the color only reinforces it */}
      <Icon size={18} color={color} aria-hidden="true" className="mt-0.5 shrink-0" />
      <span className="w-24 shrink-0 font-medium text-slate-200">{label}</span>
      <span className="text-slate-300">{describeFinding(finding)}</span>
    </li>
  );
}

/**
 * System health (/system-health): the technical report of `GET /telemetry/report` drawn as KPI tiles, findings and four charts. Admins only: the
 * endpoint reads everybody's telemetry. The dashboard computes nothing but sums of series it also draws; every metric comes from the API (which
 * caches it for 60 s).
 */
export default function SystemHealthPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [range, setRange] = useState<RangeId>("7d");
  const [report, setReport] = useState<TechnicalReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0);

  const load = useCallback(async (selected: RangeId) => {
    const request = ++latest.current;
    setLoading(true);
    setError(null);
    try {
      const fresh = await getTechnicalReport(selected);
      if (request === latest.current) setReport(fresh); // a slower answer to an older choice must not overwrite a newer one
    } catch (err) {
      if (request === latest.current) setError(describeError(err, "No se pudo cargar el reporte técnico."));
    } finally {
      if (request === latest.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isAdmin) void load(range);
  }, [isAdmin, range, load]);

  if (!isAdmin) {
    return (
      <div className="mx-auto max-w-4xl">
        <h1 className="text-3xl font-bold text-white">Salud del sistema</h1>
        <p className="mt-4 text-slate-300">Esta página es solo para administradores.</p>
      </div>
    );
  }

  const summary = report ? summarize(report) : null;
  const metrics = report?.metrics;

  const eventsPerDay: ColumnDatum[] = (metrics?.events_per_day ?? []).map((d) => ({ label: formatDay(d.day), value: d.events, lines: [`${d.events} eventos`] }));
  const errorsPerDay: ColumnDatum[] = (metrics?.errors_per_day ?? []).map((d) => ({
    label: formatDay(d.day),
    value: d.error_rate,
    lines: d.error_rate === null ? ["Sin eventos técnicos"] : [formatPercent(d.error_rate), `${d.errors} errores de ${d.technical_events} eventos técnicos`],
  }));
  const authPerDay: ColumnDatum[] = (metrics?.auth_failure_rate ?? []).map((d) => ({
    label: formatDay(d.day),
    value: d.failure_rate,
    lines: d.failure_rate === null ? ["Sin intentos de login"] : [formatPercent(d.failure_rate), `${d.failed} fallidos de ${d.attempts} logins con resultado`],
  }));
  const topTypes = (metrics?.events_by_type ?? []).slice(0, TOP_TYPES);
  const sections = (metrics?.section_load_latency ?? []).filter((s) => s.p95_ms !== null);

  return (
    <div className="mx-auto max-w-6xl">
      <header>
        <h1 className="text-3xl font-bold text-white">Salud del sistema</h1>
        <p className="mt-2 text-slate-400">Reporte técnico de la telemetría: volumen, errores, acceso y velocidad de carga.</p>
      </header>

      <div role="group" aria-label="Período" className="mt-6 flex flex-wrap items-center gap-2">
        {RANGES.map((option) => (
          <button
            key={option.id}
            type="button"
            aria-pressed={range === option.id}
            onClick={() => setRange(option.id)}
            className={`rounded-full px-4 py-1.5 text-sm font-medium transition ${
              range === option.id ? "bg-cyan-400 text-slate-950" : "border border-slate-700 text-slate-300 hover:bg-slate-800"
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>

      {error && (
        <div className="mt-6">
          <ErrorBanner message={error} />
          <button type="button" onClick={() => void load(range)} className="mt-2 text-sm text-cyan-300 hover:text-cyan-200">
            Reintentar
          </button>
        </div>
      )}

      {!report && loading && <LoadingState label="Cargando el reporte técnico…" reserveSpace className="mt-8" />}

      {report && summary && metrics && (
        // refetching keeps the frame: the previous render stays, dimmed, until the new one arrives
        <div className={`mt-6 space-y-6 transition-opacity ${loading ? "opacity-60" : ""}`} aria-busy={loading}>
          <p className="text-xs text-slate-400" data-testid="report-meta">
            Del {new Date(report.period.from).toLocaleDateString("es-ES", { timeZone: "UTC" })} al {new Date(report.period.to).toLocaleDateString("es-ES", { timeZone: "UTC" })} (UTC)
            {report.cached ? ` · en caché, de hace ${formatNumber(report.cache_age_seconds)} s` : " · calculado ahora"}
          </p>
          {report.truncated && (
            <ErrorBanner message="El período tiene más eventos de los que el reporte lee: las cifras cubren solo los más antiguos. Elige un período más corto." />
          )}

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Tile label="Eventos" value={formatNumber(summary.events)} detail="en el período elegido" />
            <Tile label="Errores técnicos" value={formatPercent(summary.errorRate)} detail={`${summary.errors} de ${summary.technicalEvents} eventos técnicos`} />
            <Tile label="Logins fallidos" value={formatPercent(summary.loginFailureRate)} detail={`${summary.loginFailures} de ${summary.loginAttempts} con resultado`} />
            <Tile
              label="Sección más lenta (p95)"
              value={summary.slowest ? formatMs(summary.slowest.p95) : "—"}
              detail={summary.slowest ? `${summary.slowest.section}${summary.slowest.overTarget ? " · supera el objetivo" : ""}` : "sin cargas medidas"}
            />
          </div>

          <section className="rounded-2xl border border-slate-800 bg-slate-900 p-5" aria-labelledby="findings-title">
            <h2 id="findings-title" className="text-base font-semibold text-white">
              Qué mirar primero
            </h2>
            {report.findings.length ? (
              <ul className="mt-4 space-y-3">
                {report.findings.map((finding) => (
                  <FindingRow key={`${finding.code}-${finding.message}`} finding={finding} />
                ))}
              </ul>
            ) : (
              <p className="mt-3 text-sm text-slate-300">Nada que destacar en este período.</p>
            )}
          </section>

          <div className="grid gap-6 lg:grid-cols-2">
            <ChartCard
              title="Eventos por día"
              subtitle="Cuánta telemetría llega cada día (días UTC)."
              table={<DataTable columns={["Día", "Eventos"]} rows={metrics.events_per_day.map((d) => [d.day, d.events])} />}
            >
              <ColumnChart data={eventsPerDay} label="Eventos por día" format={(v) => formatNumber(v)} />
            </ChartCard>

            <ChartCard
              title="Tasa de errores técnicos por día"
              subtitle="Errores entre los eventos técnicos del día."
              table={<DataTable columns={["Día", "Errores", "Eventos técnicos", "Tasa"]} rows={metrics.errors_per_day.map((d) => [d.day, d.errors, d.technical_events, formatPercent(d.error_rate)])} />}
            >
              <ColumnChart data={errorsPerDay} label="Tasa de errores técnicos por día" format={(v) => formatPercent(v)} max={1} zeroNote="Sin errores técnicos en el período." />
            </ChartCard>

            <ChartCard
              title="Fallos de login por día"
              subtitle="Fallidos entre los logins con resultado (fallidos + exitosos)."
              table={<DataTable columns={["Día", "Exitosos", "Fallidos", "Tasa"]} rows={metrics.auth_failure_rate.map((d) => [d.day, d.succeeded, d.failed, formatPercent(d.failure_rate)])} />}
            >
              <ColumnChart data={authPerDay} label="Fallos de login por día" format={(v) => formatPercent(v)} max={1} zeroNote="Ningún login falló en el período." />
            </ChartCard>

            <ChartCard
              title="Qué eventos dominan"
              subtitle={`Los ${Math.min(TOP_TYPES, metrics.events_by_type.length)} tipos más frecuentes.`}
              table={<DataTable columns={["Tipo de evento", "Eventos", "Cuota"]} rows={metrics.events_by_type.map((t) => [t.event_type, t.events, formatPercent(t.share)])} />}
            >
              <RankedBars
                rows={topTypes.map((t) => ({ label: t.event_type, value: t.events, valueLabel: formatNumber(t.events), tooltip: `${t.events} eventos (${formatPercent(t.share)})` }))}
              />
            </ChartCard>

            <div className="lg:col-span-2">
              <ChartCard
                title="Velocidad de carga por sección (p95)"
                subtitle="Tiempo hasta que la sección está usable; el 95 % de las cargas tarda menos que esto."
                table={
                  <DataTable
                    columns={["Sección", "Cargas", "Errores", "p50", "p95", "Máximo"]}
                    rows={(metrics.section_load_latency).map((s) => [s.section, s.loads, s.errors, formatMs(s.p50_ms), formatMs(s.p95_ms), formatMs(s.max_ms)])}
                  />
                }
              >
                {sections.length ? (
                  <RankedBars
                    target={2000}
                    targetLabel="Objetivo: p95 por debajo de 2 s"
                    rows={sections.map((s) => ({
                      label: s.section,
                      value: s.p95_ms as number,
                      valueLabel: formatMs(s.p95_ms),
                      tooltip: `p50 ${formatMs(s.p50_ms)}, p95 ${formatMs(s.p95_ms)}, máximo ${formatMs(s.max_ms)}, ${s.loads} cargas`,
                      note: s.over_target ? (
                        <span className="flex items-center gap-1 text-xs text-slate-200">
                          <AlertTriangle size={14} color="#fab219" aria-hidden="true" />
                          Supera el objetivo
                        </span>
                      ) : undefined,
                    }))}
                  />
                ) : (
                  <p className="text-sm text-slate-300">Todavía no hay cargas de sección medidas en este período.</p>
                )}
              </ChartCard>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
