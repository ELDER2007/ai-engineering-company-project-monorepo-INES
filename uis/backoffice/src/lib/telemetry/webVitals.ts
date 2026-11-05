// Core Web Vitals as telemetry (`web_vital_reported`, contract 2.1.0). Next.js measures them (`useReportWebVitals`, wired in
// TelemetryProvider); this decides which ones are sent and for what page. The section is the page the visit LANDED on: LCP, CLS
// and INP are only final when the page is hidden, by which time an SPA navigation may have moved on, and a vital belongs to the
// page load it was measured in.
import { track } from "./index";
import { sectionForPath } from "./paths";

/** The subset of Next.js's `NextWebVitalsMetric` this uses (`next/web-vitals`). */
export interface WebVitalMetric {
  name: string;
  value: number;
  rating?: string;
}

const METRICS = new Set(["LCP", "CLS", "INP", "FCP", "TTFB"]);
const RATINGS = new Set(["good", "needs-improvement", "poor"]);

let landingPath: string | null = null;

/** Remembers the page of this load; only the first call counts. */
export function setLandingPath(pathname: string): void {
  landingPath ??= pathname;
}

/** Test hook: forget the landing page. */
export function resetLandingPath(): void {
  landingPath = null;
}

/** A stable function (Next.js calls it again whenever its identity changes, which would duplicate the metrics). */
export function reportWebVital(metric: WebVitalMetric): void {
  const section = landingPath === null ? null : sectionForPath(landingPath);
  if (!section || !METRICS.has(metric.name) || !RATINGS.has(metric.rating ?? "") || !Number.isFinite(metric.value) || metric.value < 0) return;
  track("web_vital_reported", {
    metric: metric.name as "LCP" | "CLS" | "INP" | "FCP" | "TTFB",
    value: Math.round(metric.value * 10_000) / 10_000, // CLS is a fraction (0.0123); the milliseconds do not need more than this
    rating: metric.rating as "good" | "needs-improvement" | "poor",
    section,
  });
}
