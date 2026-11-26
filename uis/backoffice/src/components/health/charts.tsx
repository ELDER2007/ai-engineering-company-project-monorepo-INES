"use client";

import { useState, type ReactNode } from "react";
import { niceMax } from "../../lib/telemetryReport";

// Hand-drawn SVG/HTML charts for the system-health dashboard: the backoffice has no chart library and a dashboard of four charts does not need
// one. Colors are the dark-surface steps of the data-viz palette (one blue hue for magnitude; the series color stays on the marks, never on text)
// and were validated against this app's card surface (slate-900).
const BAR = "#3987e5";
const BAR_HOVER = "#6da7ec";
const GRID = "#1e293b";
const BASELINE = "#334155";
const AXIS_TEXT = "#94a3b8";

export function ChartCard({ title, subtitle, children, table }: { title: string; subtitle?: string; children: ReactNode; table?: ReactNode }) {
  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
      <h2 className="text-base font-semibold text-white">{title}</h2>
      {subtitle && <p className="mt-1 text-sm text-slate-400">{subtitle}</p>}
      <div className="mt-4">{children}</div>
      {table && (
        <details className="mt-4 text-sm">
          <summary className="cursor-pointer text-slate-400 hover:text-slate-200">Ver los datos como tabla</summary>
          <div className="mt-3 overflow-x-auto">{table}</div>
        </details>
      )}
    </section>
  );
}

/** The accessible twin of a chart: every value it draws, reachable without a pointer. */
export function DataTable({ columns, rows }: { columns: string[]; rows: ReactNode[][] }) {
  return (
    <table className="w-full text-left text-slate-300">
      <thead>
        <tr className="border-b border-slate-800 text-xs uppercase tracking-wide text-slate-400">
          {columns.map((column) => (
            <th key={column} scope="col" className="py-2 pr-4 font-medium">
              {column}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, index) => (
          <tr key={index} className="border-b border-slate-800/60">
            {row.map((cell, cellIndex) => (
              <td key={cellIndex} className="py-2 pr-4 tabular-nums">
                {cell}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export interface ColumnDatum {
  label: string; // x axis (a day)
  value: number | null; // null = nothing to draw (no data that day), told apart from a real 0
  lines: string[]; // tooltip lines, the first one is the value
}

const W = 480; // about the width the card gives the SVG, so 12px text stays 12px on screen
const H = 200;
const PAD = { left: 44, right: 8, top: 12, bottom: 26 };

/** A column with a 4px rounded top and a square foot on the baseline. */
function columnPath(x: number, y: number, width: number, height: number): string {
  const r = Math.min(4, height, width / 2);
  return `M${x},${y + height} L${x},${y + r} Q${x},${y} ${x + r},${y} L${x + width - r},${y} Q${x + width},${y} ${x + width},${y + r} L${x + width},${y + height} Z`;
}

/**
 * Columns over time. One series, one blue, bars at most 24px wide however few there are (one day of data is one thin bar, not a wall), hairline
 * grid, and a tooltip on hover AND on keyboard focus of each column's full-height hit area.
 */
export function ColumnChart({
  data,
  label,
  format,
  max,
  zeroNote,
}: {
  data: ColumnDatum[];
  label: string; // accessible name of the whole chart
  format: (value: number) => string; // y-axis ticks
  max?: number; // fixed axis maximum (e.g. 1 for a rate); default: the next "nice" value above the data
  zeroNote?: string; // said under the plot when every value is 0, so an empty plot reads as "nothing happened", not as "broken"
}) {
  const [active, setActive] = useState<number | null>(null);
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;
  const slot = plotW / Math.max(data.length, 1);
  const barW = Math.min(24, slot * 0.6);
  const yMax = max ?? niceMax(Math.max(0, ...data.map((d) => d.value ?? 0)));
  const y = (value: number) => PAD.top + plotH - (value / yMax) * plotH;
  const labelEvery = Math.ceil(data.length / 8);
  const ticks = [0, yMax / 2, yMax];
  const allZero = data.length > 0 && data.every((d) => !d.value);

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label} className="h-auto w-full">
        {ticks.map((tick) => (
          <g key={tick}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(tick)} y2={y(tick)} stroke={tick === 0 ? BASELINE : GRID} strokeWidth={1} />
            <text x={PAD.left - 8} y={y(tick) + 4} textAnchor="end" fontSize={12} fill={AXIS_TEXT}>
              {format(tick)}
            </text>
          </g>
        ))}
        {data.map((datum, index) => {
          const x = PAD.left + index * slot + (slot - barW) / 2;
          const height = datum.value ? (datum.value / yMax) * plotH : 0;
          return (
            <g key={datum.label}>
              {height > 0 && <path d={columnPath(x, y(datum.value as number), barW, height)} fill={active === index ? BAR_HOVER : BAR} />}
              {index % labelEvery === 0 && (
                <text x={PAD.left + index * slot + slot / 2} y={H - 8} textAnchor="middle" fontSize={12} fill={AXIS_TEXT}>
                  {datum.label}
                </text>
              )}
              {/* the hit target is the whole slot, much bigger than the mark */}
              <rect
                x={PAD.left + index * slot}
                y={PAD.top}
                width={slot}
                height={plotH}
                fill="transparent"
                tabIndex={0}
                aria-label={`${datum.label}: ${datum.lines.join(", ")}`}
                onPointerEnter={() => setActive(index)}
                onPointerLeave={() => setActive(null)}
                onFocus={() => setActive(index)}
                onBlur={() => setActive(null)}
                className="outline-none focus-visible:stroke-cyan-300"
                strokeWidth={2}
              />
            </g>
          );
        })}
      </svg>
      {zeroNote && allZero && <p className="mt-1 text-center text-xs text-slate-400">{zeroNote}</p>}
      {active !== null && (
        <div
          role="tooltip"
          className="pointer-events-none absolute top-0 z-10 -translate-x-1/2 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs shadow-lg"
          style={{ left: `${((PAD.left + (active + 0.5) * slot) / W) * 100}%` }}
        >
          <p className="text-sm font-semibold text-white">{data[active].lines[0]}</p>
          {data[active].lines.slice(1).map((line) => (
            <p key={line} className="text-slate-300">
              {line}
            </p>
          ))}
          <p className="text-slate-400">{data[active].label}</p>
        </div>
      )}
    </div>
  );
}

export interface RankedRow {
  label: string;
  value: number;
  valueLabel: string; // printed at the tip of the bar
  tooltip: string;
  note?: ReactNode; // an icon + label for a state, never color alone
}

/**
 * Ranked horizontal bars, one hue, each from a shared baseline, the value at the tip. `target` draws a hairline at a threshold on the same axis
 * (its meaning is spelled out by `targetLabel` under the bars).
 */
export function RankedBars({ rows, max, target, targetLabel }: { rows: RankedRow[]; max?: number; target?: number; targetLabel?: string }) {
  // With a target the axis runs a little past it, so the threshold line sits inside the plot instead of on its edge.
  const scale = max ?? (target !== undefined ? Math.max(target, ...rows.map((row) => row.value)) * 1.15 : niceMax(Math.max(0, ...rows.map((row) => row.value))));
  const percent = (value: number) => Math.min(100, (value / scale) * 100);
  // The value column has the same width in every row: an `auto` one would give each row a track of a different length, and bars on different
  // scales cannot be compared.
  const columns = `12rem minmax(0, 1fr) ${rows.some((row) => row.note) ? "12rem" : "4rem"}`;
  return (
    <div>
      <ul className="space-y-3">
        {rows.map((row) => (
          <li key={row.label} tabIndex={0} title={row.tooltip} aria-label={`${row.label}: ${row.tooltip}`} className="group grid items-center gap-3 text-sm outline-none focus-visible:ring-1 focus-visible:ring-cyan-300" style={{ gridTemplateColumns: columns }}>
            <span className="truncate text-slate-200">{row.label}</span>
            <div className="relative h-3">
              <div className="h-full rounded-r-[4px] group-hover:brightness-125 group-focus:brightness-125" style={{ width: `${row.value > 0 ? Math.max(percent(row.value), 0.5) : 0}%`, background: BAR }} />
              {target !== undefined && <div className="absolute inset-y-[-4px] w-px bg-slate-400" style={{ left: `${percent(target)}%` }} aria-hidden="true" />}
            </div>
            <span className="flex items-center gap-2 tabular-nums text-slate-300">
              {row.valueLabel}
              {row.note}
            </span>
          </li>
        ))}
      </ul>
      {target !== undefined && targetLabel && <p className="mt-3 text-xs text-slate-400">│ {targetLabel}</p>}
    </div>
  );
}
