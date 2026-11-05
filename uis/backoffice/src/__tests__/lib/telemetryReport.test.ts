/**
 * The dashboard's own logic (`lib/telemetryReport.ts`): the period query, the KPI sums and the number/day formats.
 *
 * Layout shared by every frontend test file: HAPPY PATH, EDGE CASES, FAILURE MODES. Arrange / Act / Assert.
 */
import { describeFinding, formatDay, formatMs, formatNumber, formatPercent, niceMax, rangeQuery, summarize } from "@/lib/telemetryReport";
import type { Finding, TechnicalReport } from "@/types/telemetryReport";

const REPORT: TechnicalReport = {
  period: { from: "2026-10-25T00:00:00+00:00", to: "2026-11-01T00:00:00+00:00" },
  metrics: {
    events_per_day: [
      { day: "2026-10-29", events: 7 },
      { day: "2026-10-30", events: 143 },
    ],
    events_by_type: [{ event_type: "web_vital_reported", events: 49, share: 0.3427 }],
    errors_per_day: [
      { day: "2026-10-29", technical_events: 20, errors: 1, error_rate: 0.05 },
      { day: "2026-10-30", technical_events: 80, errors: 3, error_rate: 0.0375 },
    ],
    auth_failure_rate: [
      { day: "2026-10-29", succeeded: 1, failed: 1, attempts: 2, failure_rate: 0.5 },
      { day: "2026-10-30", succeeded: 3, failed: 5, attempts: 8, failure_rate: 0.625 },
    ],
    section_load_latency: [
      { section: "inventory", loads: 4, errors: 0, error_rate: 0, p50_ms: 900, p95_ms: 2500, max_ms: 3000, over_target: true },
      { section: "home", loads: 2, errors: 0, error_rate: 0, p50_ms: 100, p95_ms: 120, max_ms: 130, over_target: false },
    ],
  },
  findings: [],
  generated_at: "2026-10-31T12:00:00+00:00",
  truncated: false,
  cached: false,
  cache_age_seconds: 0,
};

describe("rangeQuery", () => {
  const NOW = new Date("2026-10-31T15:30:45.123Z");

  describe("happy path", () => {
    it("sends nothing for the default 7 days: the API's own default, and its best cache hit", () => {
      expect(rangeQuery("7d", NOW)).toBe("");
    });

    it("starts the 30 and 90 day periods at the UTC midnight that many days ago", () => {
      expect(decodeURIComponent(rangeQuery("30d", NOW))).toBe("?start_date=2026-10-01T00:00:00.000Z");
      expect(decodeURIComponent(rangeQuery("90d", NOW))).toBe("?start_date=2026-08-02T00:00:00.000Z");
    });
  });

  describe("edge cases", () => {
    it("gives the same query all day long, so the API's 60 s cache can hit", () => {
      expect(rangeQuery("30d", new Date("2026-10-31T00:00:00Z"))).toBe(rangeQuery("30d", new Date("2026-10-31T23:59:59Z")));
    });
  });
});

describe("summarize", () => {
  describe("happy path", () => {
    it("adds each KPI up from the series the page also draws", () => {
      const summary = summarize(REPORT);

      expect(summary.events).toBe(150);
      expect(summary).toMatchObject({ technicalEvents: 100, errors: 4, errorRate: 0.04 });
      expect(summary).toMatchObject({ loginAttempts: 10, loginFailures: 6, loginFailureRate: 0.6 });
    });

    it("takes the slowest section from the head of the list (the API sends it slowest first)", () => {
      expect(summarize(REPORT).slowest).toEqual({ section: "inventory", p95: 2500, overTarget: true });
    });
  });

  describe("edge cases", () => {
    it("has no rate and no slowest section for a report without data: no data is not 0 %", () => {
      const empty: TechnicalReport = { ...REPORT, metrics: { events_per_day: [], events_by_type: [], errors_per_day: [], auth_failure_rate: [], section_load_latency: [] } };

      expect(summarize(empty)).toEqual({ events: 0, technicalEvents: 0, errors: 0, errorRate: null, loginAttempts: 0, loginFailures: 0, loginFailureRate: null, slowest: null });
    });

    it("skips a section without a p95 when looking for the slowest", () => {
      const noP95 = { ...REPORT.metrics.section_load_latency[0], p95_ms: null, over_target: false };
      const report = { ...REPORT, metrics: { ...REPORT.metrics, section_load_latency: [noP95, REPORT.metrics.section_load_latency[1]] } };

      expect(summarize(report).slowest?.section).toBe("home");
    });
  });
});

describe("formats", () => {
  it("shows a missing value as a dash, never as 0", () => {
    expect(formatPercent(null)).toBe("—");
    expect(formatNumber(null)).toBe("—");
    expect(formatMs(null)).toBe("—");
  });

  it("formats a rate as a Spanish percentage with one decimal", () => {
    expect(formatPercent(0.5556).replace(/\s/g, " ")).toBe("55,6 %");
    expect(formatPercent(0).replace(/\s/g, " ")).toBe("0 %");
  });

  it("formats milliseconds rounded", () => {
    expect(formatMs(239.7)).toMatch(/^240 ms$/);
  });

  it("turns a UTC calendar day into day/month without a timezone shift", () => {
    expect(formatDay("2026-10-30")).toBe("30/10");
    expect(formatDay("2026-01-01")).toBe("01/01");
  });

  it("rounds an axis maximum up to 1, 2 or 5 times a power of ten", () => {
    expect([0, 0.3, 1, 3, 143, 600, 1200].map(niceMax)).toEqual([1, 0.5, 1, 5, 200, 1000, 2000]);
  });
});

describe("describeFinding", () => {
  const finding = (code: string, evidence: Record<string, unknown> | undefined, severity: Finding["severity"] = "warning"): Finding => ({ severity, code, message: `ENGLISH ${code}`, evidence });
  const spanish = (f: Finding) => describeFinding(f).replace(/\s/g, " ");

  describe("happy path", () => {
    it.each([
      ["application_errors", { total: 3, by_component_and_code: [{ component: "inventory", error_code: "network_failed", errors: 2 }] }, "3 errores de aplicación sin gestionar; el más frecuente: inventory/network_failed (2)."],
      ["login_failure_rate", { failed: 5, completed: 9 }, "55,6 % de los 9 logins con resultado fallaron (alerta propuesta: más del 30 %)."],
      ["login_internal_error", { count: 1 }, "1 login falló por error interno: es el servidor fallando, no unas credenciales incorrectas."],
      ["slow_section", { section: "inventory", p95_ms: 2500 }, "La sección «inventory» tarda 2500 ms en el p95 (objetivo: menos de 2 s)."],
      ["section_load_errors", { section: "home", errors: 2, loads: 4 }, "La sección «home» terminó en error en 2 de 4 cargas."],
      ["poor_web_vital", { metric: "INP", poor: 1, readings: 21, p75: 96 }, "INP valorado como malo en 1 de 21 lecturas (p75 = 96)."],
      ["api_5xx_rate", { route: "suppliers", error_rate: 0.25, requests: 4 }, "La ruta «suppliers» devolvió 5xx en el 25 % de 4 peticiones."],
      ["api_slow_route", { route: "users", p95_ms: 2500 }, "La ruta «users» tarda 2500 ms en el p95 (alerta propuesta: más de 1 s)."],
      ["authorization_denied", { by_route: [{ route_id: "users", status_code: 403, denied: 1 }, { route_id: "unmatched", status_code: 401, denied: 2 }] }, "3 peticiones denegadas (401/403); la ruta más afectada: users."],
      ["instrumentation_gap", { not_observed: ["http_request_completed", "dependency_call_completed", "background_job_completed", "telemetry_delivery_failed"] }, "No llegan eventos de 4 tipos técnicos (http_request_completed, dependency_call_completed, background_job_completed, …): el reporte no puede decir nada sobre ellos."],
    ])("writes %s in Spanish with the numbers of its evidence", (code, evidence, expected) => {
      expect(spanish(finding(code, evidence))).toBe(expected);
    });
  });

  describe("edge cases", () => {
    it("uses the singular for one", () => {
      expect(spanish(finding("application_errors", { total: 1, by_component_and_code: [{ component: "auth", error_code: "render_failed", errors: 1 }] }))).toMatch(/^1 error de aplicación sin gestionar;/);
    });
  });

  describe("failure modes", () => {
    it("falls back to the API's text for a code it does not know", () => {
      expect(describeFinding(finding("something_new", { a: 1 }))).toBe("ENGLISH something_new");
    });

    it("falls back to the API's text when the evidence is missing or unreadable, instead of printing undefined", () => {
      expect(describeFinding(finding("slow_section", undefined))).toBe("ENGLISH slow_section");
      expect(describeFinding(finding("slow_section", { section: "inventory" }))).toBe("ENGLISH slow_section");
      expect(describeFinding(finding("login_failure_rate", { failed: 5, completed: 0 }))).toBe("ENGLISH login_failure_rate");
    });
  });
});
