/**
 * The business dashboard (`views/BusinessPerformancePage.tsx`, /reporting): the weekly report the leadership reads, the four KPIs of the briefing
 * for one week at a time. It is made for people who are not technical, so these tests also check what it must NOT say.
 *
 * Layout shared by every frontend test file: HAPPY PATH, EDGE CASES, FAILURE MODES. Arrange / Act / Assert.
 */
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import BusinessPerformancePage from "@/views/BusinessPerformancePage";
import { ApiError } from "@/lib/api";
import type { PipelineRun, WeeklyReport } from "@/types/reporting";

const mockWeek = jest.fn();
const mockRun = jest.fn();
jest.mock("@/lib/reporting", () => ({
  ...jest.requireActual("@/lib/reporting"),
  getWeeklyPerformance: (...args: unknown[]) => mockWeek(...args),
  getLatestPipelineRun: (...args: unknown[]) => mockRun(...args),
}));

/** The numbers of the real week the pipeline computed on the company's database (26 October 2026). */
const REPORT: WeeklyReport = {
  week_start: "2026-10-26",
  entries: [
    { office: "miami", programme_id: "onboarding-soporte", total_material_cost: 250, kits_delivered_count: 0, shortage_events_count: 0, cost_variance_events_count: 0, currency: "USD" },
    { office: "valencia", programme_id: "onboarding-soporte", total_material_cost: 4250, kits_delivered_count: 1, shortage_events_count: 0, cost_variance_events_count: 0, currency: "EUR" },
  ],
};
const BUSY_WEEK: WeeklyReport = {
  week_start: "2026-10-19",
  entries: [
    { office: "valencia", programme_id: "ventas-b2b", total_material_cost: 1240.5, kits_delivered_count: 18, shortage_events_count: 1, cost_variance_events_count: 0, currency: "EUR" },
    { office: "miami", programme_id: "liderazgo-basico", total_material_cost: 980, kits_delivered_count: 12, shortage_events_count: 0, cost_variance_events_count: 2, currency: "USD" },
  ],
};
const COMPLETED: PipelineRun = { state: "Completed", week_start: "2026-10-26", started_at: "2026-11-02T05:00:00Z", finished_at: "2026-11-02T05:00:09Z", error: null };

const KPI_NAMES = ["Costo de material por oficina/programa", "Kits entregados", "Frecuencia de escasez", "Frecuencia de variación de costo"];

/** Freeze only the date: the timers stay real so waitFor keeps working. */
function freezeClock(iso: string) {
  jest.useFakeTimers({ now: new Date(iso), doNotFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval", "setImmediate", "clearImmediate", "nextTick", "queueMicrotask", "performance"] });
}

const kpi = (name: string) => screen.getByRole("region", { name });

beforeEach(() => {
  mockWeek.mockResolvedValue(REPORT);
  mockRun.mockResolvedValue(COMPLETED);
});
afterEach(() => jest.useRealTimers());

async function renderLoaded() {
  render(<BusinessPerformancePage />);
  await screen.findByText(/Semana del lunes/);
}

// ─────────────────────────────────────────── HAPPY PATH

describe("what the leadership sees", () => {
  it("has the title of the report the briefing asks for and says what it is about", async () => {
    await renderLoaded();
    expect(screen.getByRole("heading", { level: 1, name: "Reporte semanal de desempeño por oficina y programa" })).toBeInTheDocument();
    expect(screen.getByText("Cómo van Valencia y Miami en inversión y entrega de material de formación.")).toBeInTheDocument();
  });

  it("shows each of the four KPIs of the briefing, labelled with the name it has there", async () => {
    await renderLoaded();
    for (const name of KPI_NAMES) expect(screen.getByRole("heading", { level: 2, name })).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 2 })).toHaveLength(4);
  });

  it("says the period the numbers cover, from Monday to Sunday", async () => {
    await renderLoaded();
    expect(screen.getByRole("status")).toHaveTextContent("Semana del lunes 26 de octubre al domingo 1 de noviembre de 2026");
  });

  it("under each KPI explains in the briefing's words what it measures", async () => {
    await renderLoaded();
    expect(within(kpi("Costo de material por oficina/programa")).getByText(/Cuánto gastó una oficina adquiriendo material de formación/)).toBeInTheDocument();
    expect(within(kpi("Kits entregados")).getByText(/Cuántos kits o certificados se entregaron realmente/)).toBeInTheDocument();
    expect(within(kpi("Frecuencia de escasez")).getByText(/cayó por debajo del mínimo configurado/)).toBeInTheDocument();
    expect(within(kpi("Frecuencia de variación de costo")).getByText(/subió de forma anómala respecto a su histórico/)).toBeInTheDocument();
  });

  it("shows the cost of every office in its own currency and totals euros and dollars apart, never together", async () => {
    await renderLoaded();
    const cost = kpi("Costo de material por oficina/programa");
    expect(within(cost).getByText(/Total en euros:/)).toHaveTextContent("Total en euros: 4250,00 €");
    expect(within(cost).getByText(/Total en dólares:/)).toHaveTextContent("Total en dólares: 250,00 US$");
    const rows = within(cost).getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("MiamiOnboarding de soporte250,00 US$");
    expect(rows[1]).toHaveTextContent("ValenciaOnboarding de soporte4250,00 €");
    expect(cost).not.toHaveTextContent("4500"); // 4250 + 250: the sum that must never be shown
  });

  it("shows the kits delivered with their total and the office and programme of each", async () => {
    await renderLoaded();
    const kits = kpi("Kits entregados");
    expect(within(kits).getByText(/^Total:/)).toHaveTextContent("Total: 1 kit");
    const rows = within(kits).getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("MiamiOnboarding de soporte0 kits");
    expect(rows[1]).toHaveTextContent("ValenciaOnboarding de soporte1 kit");
  });

  it("says in plain words that a KPI had nothing to report, instead of showing a table of zeros", async () => {
    await renderLoaded();
    expect(within(kpi("Frecuencia de escasez")).getByText("Ningún programa se quedó corto de material esta semana.")).toBeInTheDocument();
    expect(within(kpi("Frecuencia de variación de costo")).getByText("Ningún proveedor subió su costo de forma anómala esta semana.")).toBeInTheDocument();
    expect(within(kpi("Frecuencia de escasez")).queryByRole("table")).not.toBeInTheDocument();
  });

  it("explains how to read the kits and the cost", async () => {
    await renderLoaded();
    expect(within(kpi("Kits entregados")).getByText("Cada pedido de entrega cuenta una vez, aunque incluya varias unidades.")).toBeInTheDocument();
    expect(within(kpi("Costo de material por oficina/programa")).getByText(/Valencia en euros y Miami en dólares\. Nunca se suman entre sí\./)).toBeInTheDocument();
  });

  it("shows several programmes and counts, with every office", async () => {
    mockWeek.mockResolvedValue(BUSY_WEEK);
    await renderLoaded();
    const kits = kpi("Kits entregados");
    expect(within(kits).getByText(/^Total:/)).toHaveTextContent("Total: 30 kits");
    expect(within(kits).getAllByRole("row")[1]).toHaveTextContent("ValenciaVentas B2B18 kits");
    expect(within(kpi("Frecuencia de variación de costo")).getByText(/^Total:/)).toHaveTextContent("Total: 2 veces");
    expect(within(kpi("Frecuencia de escasez")).getByText(/^Total:/)).toHaveTextContent("Total: 1 vez");
  });

  it("says how fresh the data is", async () => {
    await renderLoaded();
    expect(await screen.findByText(/^Datos actualizados el /)).toBeInTheDocument();
  });

  it("asks the API for the latest computed week first, with no date", async () => {
    await renderLoaded();
    expect(mockWeek).toHaveBeenCalledTimes(1);
    expect(mockWeek).toHaveBeenCalledWith(undefined);
  });
});

describe("a person who is not technical can read it without help", () => {
  it("uses no technical word anywhere on the page", async () => {
    await renderLoaded();
    await screen.findByText(/^Datos actualizados/);
    expect(document.body.textContent).not.toMatch(/\b(pipeline|endpoint|api|json|sql|telemetr\w*|flow|task|query|undefined|null|NaN)\b/i);
  });

  it("never shows an office, a programme or a currency as a code", async () => {
    mockWeek.mockResolvedValue(BUSY_WEEK);
    await renderLoaded();
    expect(document.body.textContent).not.toMatch(/ventas-b2b|liderazgo-basico|onboarding-soporte|\bEUR\b|\bUSD\b|\bvalencia\b|\bmiami\b/);
  });

  it("writes the page in Spanish", async () => {
    await renderLoaded();
    expect(screen.getByRole("button", { name: /Semana anterior/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Semana siguiente/ })).toBeInTheDocument();
  });
});

describe("moving between weeks", () => {
  it("goes to the week before, asking the API for that Monday", async () => {
    mockWeek.mockResolvedValueOnce(REPORT).mockResolvedValueOnce(BUSY_WEEK);
    await renderLoaded();
    fireEvent.click(screen.getByRole("button", { name: /Semana anterior/ }));
    await waitFor(() => expect(mockWeek).toHaveBeenLastCalledWith("2026-10-19"));
    expect(await screen.findByText(/Semana del lunes 19 de octubre al domingo 25 de octubre de 2026/)).toBeInTheDocument();
  });

  it("goes to the week after when it has already started", async () => {
    freezeClock("2026-11-04T10:00:00Z");
    mockWeek.mockResolvedValueOnce(REPORT).mockResolvedValueOnce({ week_start: "2026-11-02", entries: [] });
    await renderLoaded();
    fireEvent.click(screen.getByRole("button", { name: /Semana siguiente/ }));
    await waitFor(() => expect(mockWeek).toHaveBeenLastCalledWith("2026-11-02"));
  });

  it("offers to come back to the latest computed week after moving away from it", async () => {
    mockWeek.mockResolvedValueOnce(REPORT).mockResolvedValueOnce(BUSY_WEEK).mockResolvedValueOnce(REPORT);
    await renderLoaded();
    expect(screen.queryByRole("button", { name: "Ir a la última semana calculada" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Semana anterior/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Ir a la última semana calculada" }));
    await waitFor(() => expect(mockWeek).toHaveBeenLastCalledWith(undefined));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Ir a la última semana calculada" })).not.toBeInTheDocument());
  });
});

// ─────────────────────────────────────────── EDGE CASES

describe("edge cases", () => {
  it("cannot move to a week that has not started yet", async () => {
    freezeClock("2026-10-29T10:00:00Z"); // Thursday of the week of 26 October: the next Monday is still in the future
    await renderLoaded();
    expect(screen.getByRole("button", { name: /Semana siguiente/ })).toBeDisabled();
  });

  it("can move to the next week as soon as it starts", async () => {
    freezeClock("2026-11-02T00:00:00Z");
    await renderLoaded();
    expect(screen.getByRole("button", { name: /Semana siguiente/ })).toBeEnabled();
  });

  it("says there is nothing to show when the week has no operations, and still says which week it is", async () => {
    mockWeek.mockResolvedValue({ week_start: "2026-09-07", entries: [] });
    await renderLoaded();
    expect(screen.getByText("No hay operaciones registradas en esta semana, así que no hay números que mostrar.")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Semana del lunes 7 de septiembre");
    expect(screen.queryAllByRole("heading", { level: 2 })).toHaveLength(0);
  });

  it("tells the reader the week is closed (or still going)", async () => {
    await renderLoaded();
    expect(screen.getByText("Semana cerrada: de lunes a domingo.")).toBeInTheDocument();
  });

  it("shows a programme it does not know with a readable name", async () => {
    mockWeek.mockResolvedValue({ week_start: "2026-10-26", entries: [{ ...REPORT.entries[1], programme_id: "curso-nuevo" }] });
    await renderLoaded();
    expect(within(kpi("Kits entregados")).getByText("Curso nuevo")).toBeInTheDocument();
  });

  it("does not let a slower answer for an older choice overwrite the newer one", async () => {
    let answerOld: (value: WeeklyReport) => void = () => undefined;
    mockWeek.mockResolvedValueOnce(REPORT).mockReturnValueOnce(new Promise<WeeklyReport>((resolve) => { answerOld = resolve; })).mockResolvedValueOnce(BUSY_WEEK);
    await renderLoaded();
    fireEvent.click(screen.getByRole("button", { name: /Semana anterior/ })); // slow request, for the week of 19 October
    fireEvent.click(screen.getByRole("button", { name: "Ir a la última semana calculada" })); // quick request, answered first
    await screen.findByText(/Semana del lunes 19 de octubre/);
    await act(async () => answerOld({ week_start: "2026-10-12", entries: [] })); // the slow one arrives last
    expect(screen.getByRole("status")).toHaveTextContent("Semana del lunes 19 de octubre");
  });
});

describe("how fresh the data is, in every case", () => {
  it("warns when the last update did not end well", async () => {
    mockRun.mockResolvedValue({ ...COMPLETED, state: "Failed", error: "x" });
    await renderLoaded();
    expect(await screen.findByText("La última actualización de los datos no terminó bien, así que estos números pueden no estar al día.")).toBeInTheDocument();
  });

  it("says the data is being updated while a run is going", async () => {
    mockRun.mockResolvedValue({ ...COMPLETED, state: "Running", finished_at: null });
    await renderLoaded();
    expect(await screen.findByText("Los datos se están actualizando en este momento.")).toBeInTheDocument();
  });

  it("simply does not say it when it cannot be read, and the report still shows", async () => {
    mockRun.mockRejectedValue(new ApiError("Not found", 404));
    await renderLoaded();
    await waitFor(() => expect(mockRun).toHaveBeenCalled());
    expect(screen.queryByText(/actualiza/i)).not.toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 2 })).toHaveLength(4);
  });
});

// ─────────────────────────────────────────── FAILURE MODES

describe("failure modes", () => {
  it("shows a loading message while the first week arrives", () => {
    mockWeek.mockReturnValue(new Promise(() => undefined));
    render(<BusinessPerformancePage />);
    expect(screen.getByText("Cargando el reporte semanal…")).toBeInTheDocument();
  });

  it("says, without blaming the reader, that no week has been computed yet", async () => {
    mockWeek.mockRejectedValue(new ApiError("No week has been computed yet", 404));
    render(<BusinessPerformancePage />);
    expect(await screen.findByText("Todavía no hay ninguna semana calculada. Cuando se calcule la primera, sus números aparecerán aquí.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Semana anterior/ })).not.toBeInTheDocument();
  });

  it("shows a message the reader can act on when the server fails, and lets them try again", async () => {
    mockWeek.mockRejectedValueOnce(new ApiError("Internal Server Error", 500)).mockResolvedValueOnce(REPORT);
    render(<BusinessPerformancePage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("El servidor ha tenido un problema. Inténtalo de nuevo en unos minutos.");
    fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByText(/Semana del lunes 26 de octubre/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("says the connection failed when the server cannot be reached", async () => {
    mockWeek.mockRejectedValue(new ApiError("Network", 0));
    render(<BusinessPerformancePage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("No se pudo conectar con el servidor. Comprueba tu conexión e inténtalo de nuevo.");
  });

  it("uses its own message for an error that is not an API error", async () => {
    mockWeek.mockRejectedValue(new Error("boom"));
    render(<BusinessPerformancePage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("No se pudo cargar el reporte semanal.");
  });

  it("keeps the week on screen when moving to another one fails", async () => {
    mockWeek.mockResolvedValueOnce(REPORT).mockRejectedValueOnce(new ApiError("Internal Server Error", 500));
    await renderLoaded();
    fireEvent.click(screen.getByRole("button", { name: /Semana anterior/ }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 2 })).toHaveLength(4);
  });
});
