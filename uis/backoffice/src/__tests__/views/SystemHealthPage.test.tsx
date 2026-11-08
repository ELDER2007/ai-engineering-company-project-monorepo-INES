/**
 * The system-health dashboard (`views/SystemHealthPage.tsx`, /system-health): the technical report drawn as tiles, findings and charts.
 *
 * Layout shared by every frontend test file: HAPPY PATH, EDGE CASES, FAILURE MODES. Arrange / Act / Assert.
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import SystemHealthPage from "@/views/SystemHealthPage";
import type { TechnicalReport } from "@/types/telemetryReport";

const mockUser = jest.fn();
const mockReport = jest.fn();
jest.mock("@/auth/AuthContext", () => ({ useAuth: () => ({ user: mockUser() }) }));
jest.mock("@/lib/telemetryReport", () => ({
  ...jest.requireActual("@/lib/telemetryReport"),
  getTechnicalReport: (...args: unknown[]) => mockReport(...args),
}));

const ADMIN = { id: "1", email: "admin@nexova.com", role: "admin" };

const REPORT: TechnicalReport = {
  period: { from: "2026-10-25T00:00:00+00:00", to: "2026-11-01T00:00:00+00:00" },
  metrics: {
    events_per_day: [{ day: "2026-10-30", events: 143 }],
    events_by_type: [
      { event_type: "web_vital_reported", events: 49, share: 0.3427 },
      { event_type: "section_viewed", events: 33, share: 0.2308 },
    ],
    errors_per_day: [{ day: "2026-10-30", technical_events: 79, errors: 0, error_rate: 0 }],
    auth_failure_rate: [{ day: "2026-10-30", succeeded: 4, failed: 5, attempts: 9, failure_rate: 0.5556 }],
    section_load_latency: [
      { section: "inventory", loads: 3, errors: 0, error_rate: 0, p50_ms: 900, p95_ms: 2500, max_ms: 3000, over_target: true },
      { section: "suppliers", loads: 5, errors: 0, error_rate: 0, p50_ms: 67, p95_ms: 71.4, max_ms: 72, over_target: false },
    ],
  },
  findings: [
    { severity: "warning", code: "login_failure_rate", message: "56% of 9 completed logins failed (proposed alert: >30%).", evidence: { failed: 5, completed: 9 } },
    { severity: "info", code: "instrumentation_gap", message: "No events of 7 technical type(s): the report cannot say anything about them.", evidence: { not_observed: ["http_request_completed", "dependency_call_completed"] } },
    { severity: "info", code: "brand_new_code", message: "A finding this dashboard has no Spanish text for." },
  ],
  generated_at: "2026-10-31T12:00:00+00:00",
  truncated: false,
  cached: false,
  cache_age_seconds: 0,
};

/** Resolves when the first report is drawn. */
const ready = () => screen.findByTestId("report-meta");
/** The KPI tile with this label (the same words also head a table column and a chart). */
const tile = (label: string) => within(screen.getByText(label, { selector: "p" }).parentElement!);

beforeEach(() => {
  mockUser.mockReset().mockReturnValue(ADMIN);
  mockReport.mockReset().mockResolvedValue(REPORT);
});

describe("SystemHealthPage", () => {
  describe("happy path", () => {
    it("shows the four KPI tiles added up from the report", async () => {
      render(<SystemHealthPage />);

      await ready();
      expect(tile("Eventos").getByText("143")).toBeInTheDocument();
      expect(screen.getByText("0 de 79 eventos técnicos")).toBeInTheDocument();
      expect(screen.getByText("5 de 9 con resultado")).toBeInTheDocument();
      expect(screen.getByText(/inventory · supera el objetivo/)).toBeInTheDocument();
    });

    it("lists the findings with the severity as a word, not only as a color", async () => {
      render(<SystemHealthPage />);

      const findings = within(await screen.findByRole("heading", { name: "Qué mirar primero" }).then((h) => h.closest("section")!));
      expect(findings.getByText("Aviso")).toBeInTheDocument();
      expect(findings.getAllByText("Información")).toHaveLength(2);
      expect(findings.getByText(/55,6\s%\sde los 9 logins con resultado fallaron/)).toBeInTheDocument();
      expect(findings.queryByText(/completed logins failed/)).not.toBeInTheDocument(); // translated, not the API's English
      expect(findings.getByText("A finding this dashboard has no Spanish text for.")).toBeInTheDocument(); // unknown code: the API's text
    });

    it("draws the charts and flags the section over the 2 s target with words", async () => {
      render(<SystemHealthPage />);

      expect(await screen.findByRole("img", { name: "Eventos por día" })).toBeInTheDocument();
      expect(screen.getByRole("img", { name: "Fallos de login por día" })).toBeInTheDocument();
      expect(screen.getAllByText("web_vital_reported").length).toBeGreaterThan(0); // the bar label and its table row
      expect(screen.getByText("Supera el objetivo")).toBeInTheDocument();
      expect(screen.getByText("Objetivo: p95 por debajo de 2 s", { exact: false })).toBeInTheDocument();
    });

    it("gives every bar the same track length, so bars of different rows are comparable", async () => {
      render(<SystemHealthPage />);

      await screen.findByRole("img", { name: "Eventos por día" });
      const rows = screen.getAllByRole("listitem").filter((li) => li.style.gridTemplateColumns);
      expect(rows.length).toBeGreaterThan(2);
      expect(new Set(rows.filter((li) => li.textContent?.includes("ms")).map((li) => li.style.gridTemplateColumns)).size).toBe(1);
    });

    it("offers every chart's values as a table too", async () => {
      render(<SystemHealthPage />);

      await screen.findByRole("img", { name: "Eventos por día" });
      expect(screen.getAllByText("Ver los datos como tabla")).toHaveLength(5);
      expect(screen.getByRole("columnheader", { name: "Tipo de evento" })).toBeInTheDocument();
    });

    it("reads the report again when another period is chosen", async () => {
      render(<SystemHealthPage />);
      await ready();
      expect(mockReport).toHaveBeenLastCalledWith("7d");

      fireEvent.click(screen.getByRole("button", { name: "Últimos 30 días" }));

      await waitFor(() => expect(mockReport).toHaveBeenLastCalledWith("30d"));
      expect(screen.getByRole("button", { name: "Últimos 30 días" })).toHaveAttribute("aria-pressed", "true");
    });

    it("shows a hover tooltip on a column", async () => {
      render(<SystemHealthPage />);
      const chart = await screen.findByRole("img", { name: "Eventos por día" });

      fireEvent.focus(within(chart).getByLabelText(/30\/10: 143 eventos/));

      expect(await screen.findByRole("tooltip")).toHaveTextContent("143 eventos");
    });
  });

  describe("edge cases", () => {
    it("says it is a cached answer, and how old", async () => {
      mockReport.mockResolvedValue({ ...REPORT, cached: true, cache_age_seconds: 12.3 });
      render(<SystemHealthPage />);

      expect(await screen.findByTestId("report-meta")).toHaveTextContent("en caché, de hace 12,3 s");
    });

    it("warns that the figures are partial when the period was too big to read whole", async () => {
      mockReport.mockResolvedValue({ ...REPORT, truncated: true });
      render(<SystemHealthPage />);

      expect(await screen.findByText(/solo los más antiguos/)).toBeInTheDocument();
    });

    it("says so under a chart whose values are all 0, instead of leaving an empty plot", async () => {
      render(<SystemHealthPage />); // the fixture has no technical errors

      expect(await screen.findByText("Sin errores técnicos en el período.")).toBeInTheDocument();
      expect(screen.queryByText("Ningún login falló en el período.")).not.toBeInTheDocument(); // 5 of 9 failed
    });

    it("renders an empty report without breaking: dashes for the rates and a note for the sections", async () => {
      mockReport.mockResolvedValue({
        ...REPORT,
        metrics: { events_per_day: [], events_by_type: [], errors_per_day: [], auth_failure_rate: [], section_load_latency: [] },
        findings: [],
      });
      render(<SystemHealthPage />);

      expect(await screen.findByText("Nada que destacar en este período.")).toBeInTheDocument();
      expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(3);
      expect(screen.getByText(/no hay cargas de sección medidas/)).toBeInTheDocument();
    });

    it("keeps the previous report on screen, dimmed, while a new period loads", async () => {
      render(<SystemHealthPage />);
      await ready();
      mockReport.mockReturnValue(new Promise(() => {})); // never answers

      fireEvent.click(screen.getByRole("button", { name: "Últimos 90 días" }));

      await waitFor(() => expect(screen.getByTestId("report-meta").parentElement).toHaveAttribute("aria-busy", "true"));
      expect(tile("Eventos").getByText("143")).toBeInTheDocument();
    });

    it("ignores a slow answer to an older choice that arrives after a newer one", async () => {
      let answerOld: (report: TechnicalReport) => void = () => {};
      mockReport.mockReturnValueOnce(new Promise<TechnicalReport>((resolve) => (answerOld = resolve)));
      render(<SystemHealthPage />); // the 7 day request is still pending
      mockReport.mockResolvedValue({ ...REPORT, metrics: { ...REPORT.metrics, events_per_day: [{ day: "2026-10-30", events: 999 }] } });

      fireEvent.click(screen.getByRole("button", { name: "Últimos 30 días" }));
      await waitFor(() => expect(tile("Eventos").getByText("999")).toBeInTheDocument());
      answerOld(REPORT); // the stale one finally arrives

      await waitFor(() => expect(mockReport).toHaveBeenCalledTimes(2));
      expect(tile("Eventos").getByText("999")).toBeInTheDocument();
      expect(screen.queryAllByText("143")).toHaveLength(0);
    });
  });

  describe("failure modes", () => {
    it("explains the failure and lets the user retry", async () => {
      mockReport.mockRejectedValueOnce(new Error("boom"));
      render(<SystemHealthPage />);

      expect(await screen.findByRole("alert")).toHaveTextContent("No se pudo cargar el reporte técnico.");
      fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));

      await ready();
      expect(mockReport).toHaveBeenCalledTimes(2);
    });

    it("is for admins only: another user sees a notice and the API is never called", () => {
      mockUser.mockReturnValue({ ...ADMIN, role: "user" });
      render(<SystemHealthPage />);

      expect(screen.getByText("Esta página es solo para administradores.")).toBeInTheDocument();
      expect(mockReport).not.toHaveBeenCalled();
    });
  });
});
