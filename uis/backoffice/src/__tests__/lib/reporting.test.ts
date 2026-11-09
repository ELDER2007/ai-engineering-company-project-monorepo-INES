/**
 * The business dashboard's logic (`lib/reporting.ts`): the calls to the /reporting API, the four KPIs with the names and definitions of the
 * briefing, and the plain-Spanish helpers (weeks, offices, programmes, money, freshness of the data).
 *
 * Layout shared by every frontend test file: HAPPY PATH, EDGE CASES, FAILURE MODES. Arrange / Act / Assert.
 */
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
  officeLabel,
  programmeLabel,
  shiftWeek,
  totalCount,
  totalsByCurrency,
} from "@/lib/reporting";
import type { WeeklyEntry } from "@/types/reporting";

const mockJsonRequest = jest.fn();
jest.mock("@/lib/api", () => ({ API_BASE_URL: "", jsonRequest: (...args: unknown[]) => mockJsonRequest(...args) }));

const ENTRIES: WeeklyEntry[] = [
  { office: "miami", programme_id: "onboarding-soporte", total_material_cost: 250, kits_delivered_count: 0, shortage_events_count: 1, cost_variance_events_count: 0, currency: "USD" },
  { office: "valencia", programme_id: "onboarding-soporte", total_material_cost: 4250, kits_delivered_count: 3, shortage_events_count: 0, cost_variance_events_count: 2, currency: "EUR" },
  { office: "valencia", programme_id: "ventas-b2b", total_material_cost: 100.5, kits_delivered_count: 1, shortage_events_count: 0, cost_variance_events_count: 0, currency: "EUR" },
];

// ─────────────────────────────────────────── HAPPY PATH

describe("the four KPIs of the briefing", () => {
  it("are the four of its 'KPIs a medir' table, with its names word for word", () => {
    expect(KPIS.map((kpi) => kpi.name)).toEqual([
      "Costo de material por oficina/programa",
      "Kits entregados",
      "Frecuencia de escasez",
      "Frecuencia de variación de costo",
    ]);
  });

  it("each one reads a field of the destination table weekly_office_program_performance", () => {
    expect(KPIS.map((kpi) => kpi.key)).toEqual(["total_material_cost", "kits_delivered_count", "shortage_events_count", "cost_variance_events_count"]);
  });

  it("each one carries the briefing's own definition of what it measures", () => {
    expect(KPIS[0].measures).toBe("Cuánto gastó una oficina adquiriendo material de formación o incorporación para un programa dado, durante la semana.");
    expect(KPIS[1].measures).toBe("Cuántos kits o certificados se entregaron realmente a clientes, candidatos, consultores o agentes durante la semana.");
    expect(KPIS[2].measures).toBe("Cuántas veces durante la semana el stock de material de un programa cayó por debajo del mínimo configurado.");
    expect(KPIS[3].measures).toBe("Cuántas veces durante la semana el costo de un proveedor de material subió de forma anómala respecto a su histórico.");
  });

  it("only the cost is money; the other three are counts", () => {
    expect(KPIS.map((kpi) => kpi.kind)).toEqual(["money", "count", "count", "count"]);
  });

  it("every one says what it is for and what to say when the week has nothing", () => {
    for (const kpi of KPIS) {
      expect(kpi.purpose.length).toBeGreaterThan(20);
      expect(kpi.empty.length).toBeGreaterThan(10);
    }
  });

  it("the reading rules of the cost (separate currencies) and of the kits (one delivery order counts once) are written down", () => {
    expect(KPIS[0].note).toMatch(/euros.*dólares.*Nunca se suman/);
    expect(KPIS[1].note).toMatch(/cuenta una vez/);
  });
});

describe("the calls to the API", () => {
  beforeEach(() => mockJsonRequest.mockResolvedValue({}));

  it("asks for the latest computed week without a parameter", async () => {
    await getWeeklyPerformance();
    expect(mockJsonRequest).toHaveBeenCalledWith("/api/reporting/weekly-office-program-performance");
  });

  it("asks for one week by its Monday", async () => {
    await getWeeklyPerformance("2026-10-26");
    expect(mockJsonRequest).toHaveBeenCalledWith("/api/reporting/weekly-office-program-performance?week_start=2026-10-26");
  });

  it("asks for the latest run of the process that computes the numbers", async () => {
    await getLatestPipelineRun();
    expect(mockJsonRequest).toHaveBeenCalledWith("/api/reporting/pipeline-runs/latest");
  });

  it("calls the API directly, at its own address, when the app is configured with one", async () => {
    jest.resetModules();
    jest.doMock("@/lib/api", () => ({ API_BASE_URL: "https://api.nexova.test", jsonRequest: (...args: unknown[]) => mockJsonRequest(...args) }));
    const direct = await import("@/lib/reporting");
    await direct.getWeeklyPerformance("2026-10-26");
    expect(mockJsonRequest).toHaveBeenCalledWith("https://api.nexova.test/reporting/weekly-office-program-performance?week_start=2026-10-26");
    jest.dontMock("@/lib/api");
  });
});

describe("weeks, from Monday to Sunday", () => {
  it("moves a Monday a week forward and a week back", () => {
    expect(shiftWeek("2026-10-26", 1)).toBe("2026-11-02");
    expect(shiftWeek("2026-10-26", -1)).toBe("2026-10-19");
    expect(shiftWeek("2026-10-26", 0)).toBe("2026-10-26");
  });

  it("says the period a week covers, in plain Spanish", () => {
    expect(formatWeekRange("2026-10-26")).toBe("Semana del lunes 26 de octubre al domingo 1 de noviembre de 2026");
  });

  it("finds the Monday of the week of any day", () => {
    expect(currentWeekStart(new Date("2026-11-04T10:00:00Z"))).toBe("2026-11-02"); // a Wednesday
    expect(currentWeekStart(new Date("2026-11-02T00:00:00Z"))).toBe("2026-11-02"); // the Monday itself
  });
});

describe("names a person can read", () => {
  it("shows the offices, the programmes and the currencies by name", () => {
    expect(officeLabel("valencia")).toBe("Valencia");
    expect(officeLabel("miami")).toBe("Miami");
    expect(programmeLabel("ventas-b2b")).toBe("Ventas B2B");
    expect(programmeLabel("liderazgo-basico")).toBe("Liderazgo básico");
    expect(programmeLabel("onboarding-soporte")).toBe("Onboarding de soporte");
    expect(currencyName("EUR")).toBe("euros");
    expect(currencyName("USD")).toBe("dólares");
  });

  it("counts in singular and plural", () => {
    expect(formatCount(1, ["kit", "kits"])).toBe("1 kit");
    expect(formatCount(3, ["kit", "kits"])).toBe("3 kits");
    expect(formatCount(0, ["vez", "veces"])).toBe("0 veces");
    expect(formatCount(12345, ["kit", "kits"])).toBe("12.345 kits");
  });
});

describe("one KPI as rows and totals", () => {
  it("turns the entries into the rows of one KPI, with readable names, in the order the API gives them", () => {
    expect(kpiRows(ENTRIES, "kits_delivered_count")).toEqual([
      { office: "miami", officeLabel: "Miami", programmeLabel: "Onboarding de soporte", value: 0, currency: "USD" },
      { office: "valencia", officeLabel: "Valencia", programmeLabel: "Onboarding de soporte", value: 3, currency: "EUR" },
      { office: "valencia", officeLabel: "Valencia", programmeLabel: "Ventas B2B", value: 1, currency: "EUR" },
    ]);
  });

  it("adds the cost per currency and never euros with dollars", () => {
    expect(totalsByCurrency(kpiRows(ENTRIES, "total_material_cost"))).toEqual([
      { currency: "USD", total: 250 },
      { currency: "EUR", total: 4350.5 },
    ]);
  });

  it("adds the counts of all the offices", () => {
    expect(totalCount(kpiRows(ENTRIES, "kits_delivered_count"))).toBe(4);
    expect(totalCount(kpiRows(ENTRIES, "cost_variance_events_count"))).toBe(2);
  });

  it("writes each value in its own unit: money in the office's currency, counts with their word", () => {
    const [miami, valencia] = kpiRows(ENTRIES, "total_material_cost");
    const plain = (text: string) => text.replace(/\s/g, " "); // Intl puts a non-breaking space between the amount and the symbol
    expect(plain(formatValue(miami, "money", ["", ""]))).toBe("250,00 US$");
    expect(plain(formatValue(valencia, "money", ["", ""]))).toBe("4250,00 €");
    expect(formatValue(kpiRows(ENTRIES, "kits_delivered_count")[1], "count", ["kit", "kits"])).toBe("3 kits");
  });
});

describe("how fresh the numbers are", () => {
  const run = { week_start: "2026-10-26", started_at: "2026-11-02T05:00:00Z", error: null, warnings: null };
  const NOW = new Date("2026-11-04T09:00:00Z"); // two days after the run: never read the real clock in a test

  it("says when the data was updated, once the last run completed", () => {
    const fresh = describeFreshness({ ...run, state: "Completed", finished_at: "2026-11-02T05:00:09Z" }, NOW);
    expect(fresh.tone).toBe("ok");
    expect(fresh.text).toMatch(/^Datos actualizados el .+\.$/);
  });

  it("warns when the last completed update is older than a week and a day: the weekly process has stopped", () => {
    const finished = { ...run, state: "Completed" as const, finished_at: "2026-11-02T05:00:09Z" };
    expect(describeFreshness(finished, new Date("2026-11-09T05:00:09Z")).tone).toBe("ok"); // 7 days: still on schedule
    const late = describeFreshness(finished, new Date("2026-11-10T05:00:09Z")); // 8 days
    expect(late.tone).toBe("warning");
    expect(late.text).toBe("Los datos llevan 8 días sin actualizarse: se esperaba una actualización cada semana, así que pueden estar desfasados.");
  });

  it("never reads a completed run without a finish time as stale", () => {
    expect(describeFreshness({ ...run, state: "Completed", finished_at: null }, NOW)).toEqual({ tone: "ok", text: "Datos actualizados." });
  });

  it("says, when the process has never run, that it has not run yet", () => {
    expect(NEVER_RAN.tone).toBe("warning");
    expect(NEVER_RAN.text).toBe("El proceso que calcula estos datos todavía no se ha ejecutado.");
  });

  it("warns, in plain words, when the last update did not end well", () => {
    for (const state of ["Failed", "Crashed"] as const) {
      const fresh = describeFreshness({ ...run, state, finished_at: "2026-11-02T05:00:09Z" }, NOW);
      expect(fresh.tone).toBe("warning");
      expect(fresh.text).toBe("La última actualización de los datos no terminó bien, así que estos números pueden no estar al día.");
    }
  });

  it("says the data is being updated while a run is going", () => {
    for (const state of ["Running", "Skipped"] as const) {
      expect(describeFreshness({ ...run, state, finished_at: null }, NOW)).toEqual({ tone: "info", text: "Los datos se están actualizando en este momento." });
    }
  });
});

describe("whether the data was collected (data health)", () => {
  const WEEK = "2026-10-26";
  const base = { week_start: WEEK, started_at: "2026-11-02T05:00:00Z", finished_at: "2026-11-02T05:00:09Z", error: null, state: "Completed" as const };

  it("says nothing when the run has no notes", () => {
    expect(describeDataHealth({ ...base, warnings: null }, WEEK)).toEqual([]);
    expect(describeDataHealth({ ...base, warnings: "" }, WEEK)).toEqual([]);
  });

  it("explains a silent capture in plain words", () => {
    const [text] = describeDataHealth({ ...base, warnings: "data_health:capture_silent: 0 events in the window" }, WEEK);
    expect(text).toMatch(/^No se registró ninguna actividad en el sistema durante esta semana/);
  });

  it("explains a drop in activity in plain words", () => {
    const [text] = describeDataHealth({ ...base, warnings: "data_health:volume_drop: 3 of a typical 100" }, WEEK);
    expect(text).toMatch(/^Esta semana hay mucha menos actividad/);
  });

  it("ignores the other notes of the run and keeps only the data health ones, in order", () => {
    const warnings = "optional step skipped; data_health:volume_drop: x; data_health:capture_silent: y";
    expect(describeDataHealth({ ...base, warnings }, WEEK)).toHaveLength(2);
    expect(describeDataHealth({ ...base, warnings: "optional step skipped" }, WEEK)).toEqual([]);
  });

  it("does not make up an explanation for a code it does not know, but still warns", () => {
    expect(describeDataHealth({ ...base, warnings: "data_health:something_new: z" }, WEEK)).toEqual(["Hay un aviso sobre si los datos de esta semana se han recogido bien."]);
  });

  it("only speaks for the week the run computed: looking at another week it says nothing", () => {
    expect(describeDataHealth({ ...base, warnings: "data_health:capture_silent: y" }, "2026-10-19")).toEqual([]);
  });

  it("uses no technical word", () => {
    const all = ["capture_silent", "volume_drop", "other"].flatMap((code) => describeDataHealth({ ...base, warnings: `data_health:${code}: x` }, WEEK)).join(" ");
    expect(all).not.toMatch(/\b(pipeline|endpoint|api|json|sql|telemetr\w*|flow|task|data_health|undefined|null)\b/i);
  });
});

// ─────────────────────────────────────────── EDGE CASES

describe("edge cases", () => {
  it("shows a programme it does not know readable, never hidden or as a code", () => {
    expect(programmeLabel("curso-nuevo_2027")).toBe("Curso nuevo 2027");
    expect(programmeLabel("x")).toBe("X");
    expect(officeLabel("madrid")).toBe("Madrid");
  });

  it("does not crash on an empty text", () => {
    expect(programmeLabel("")).toBe("");
    expect(officeLabel("")).toBe("");
  });

  it("shows a currency it does not know as it comes", () => {
    expect(currencyName("GBP" as never)).toBe("GBP");
  });

  it("puts a week that crosses a year in plain words, with both years", () => {
    expect(formatWeekRange("2026-12-28")).toBe("Semana del lunes 28 de diciembre de 2026 al domingo 3 de enero de 2027");
  });

  it("treats a Sunday as the end of the week that started on the Monday before", () => {
    expect(currentWeekStart(new Date("2026-11-08T23:59:59Z"))).toBe("2026-11-02");
    expect(currentWeekStart(new Date("2026-11-09T00:00:00Z"))).toBe("2026-11-09");
  });

  it("knows a week that has not started yet, and that the current one has", () => {
    const now = new Date("2026-11-04T10:00:00Z");
    expect(isFutureWeek("2026-11-09", now)).toBe(true);
    expect(isFutureWeek("2026-11-02", now)).toBe(false);
    expect(isFutureWeek("2026-10-26", now)).toBe(false);
  });

  it("totals nothing when there are no rows", () => {
    expect(totalsByCurrency([])).toEqual([]);
    expect(totalCount([])).toBe(0);
    expect(kpiRows([], "total_material_cost")).toEqual([]);
  });

  it("draws a bar in proportion to the largest value, with a minimum so a small value is still seen, and none for zero", () => {
    expect(barPercent(50, 100)).toBe(50);
    expect(barPercent(100, 100)).toBe(100);
    expect(barPercent(1, 1000)).toBe(2);
    expect(barPercent(0, 100)).toBe(0);
    expect(barPercent(5, 0)).toBe(0);
    expect(barPercent(500, 100)).toBe(100);
  });
});
