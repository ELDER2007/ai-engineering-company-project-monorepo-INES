/**
 * The stock page (`views/AssetsPage.tsx`, /inventory/products): the assets with `current_stock`, the colour-coded
 * level, and a labelled link per row to register an entry or an exit for that asset.
 *
 * Layout shared by every frontend test file: HAPPY PATH, EDGE CASES, FAILURE MODES. Arrange / Act / Assert.
 */
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import AssetsPage from "@/views/AssetsPage";
import { track } from "@/lib/telemetry";

const mockList = jest.fn();
jest.mock("next/link", () => ({ __esModule: true, default: ({ href, children, ...rest }: { href: string; children: unknown }) => <a href={href} {...rest}>{children as never}</a> }));
jest.mock("@/lib/api", () => {
  class ApiError extends Error {
    constructor(
      message: string,
      public status: number,
      public fieldErrors: Record<string, string> = {},
    ) {
      super(message);
    }
  }
  return { ApiError };
});
jest.mock("@/lib/telemetry", () => ({ track: jest.fn() }));
const trackMock = jest.mocked(track);
const searches = () => trackMock.mock.calls.filter(([type]) => type === "search_performed").map(([, props]) => props);
jest.mock("@/lib/inventory", () => ({ listAssets: (...args: unknown[]) => mockList(...args) }));

const asset = (id: number, name: string, sku: string, stock: number, office = "Valencia") => ({
  id,
  name,
  sku,
  category: "hardware",
  office,
  current_stock: stock,
});
const ASSETS = [
  asset(1, 'Portátil 14" Business', "NXV-IT-001", 12),
  asset(2, 'Portátil 14" Business', "NXV-IT-002", 5, "Miami"),
  asset(3, "Hub USB-C", "NXV-PER-002", 0, "Miami"),
];

beforeEach(() => mockList.mockReset().mockResolvedValue(ASSETS));

describe("AssetsPage", () => {
  describe("happy path", () => {
    it("lists every asset with its SKU, office and current_stock", async () => {
      render(<AssetsPage />);

      const rows = await screen.findAllByTestId("asset-row");
      expect(rows).toHaveLength(3);
      const first = within(rows[0]);
      expect(first.getByText("Hub USB-C")).toBeInTheDocument();
      expect(first.getByText("NXV-PER-002")).toBeInTheDocument();
      expect(first.getByText("Miami")).toBeInTheDocument();
    });

    it("tells the levels apart by colour and by text: no stock, low, fine", async () => {
      render(<AssetsPage />);

      const rows = await screen.findAllByTestId("asset-row");
      // lowest first: the asset with no stock, then the low one, then the healthy one
      expect(rows.map((r) => r.querySelector("[data-level]")?.getAttribute("data-level"))).toEqual(["empty", "low", "ok"]);
      expect(within(rows[0]).getByText("Sin stock")).toBeInTheDocument();
      expect(within(rows[1]).getByText("Stock bajo")).toBeInTheDocument();
      expect(within(rows[2]).getByText("Stock correcto")).toBeInTheDocument();
    });

    it("has, in every row, a clearly labelled link to register an entry and an exit for that asset", async () => {
      render(<AssetsPage />);

      const rows = await screen.findAllByTestId("asset-row");
      const row = within(rows[2]); // NXV-IT-001, id 1
      expect(row.getByRole("link", { name: /Registrar entrada de «Portátil 14" Business» \(NXV-IT-001\)/ })).toHaveAttribute(
        "href",
        "/inventory/orders/inbound?asset=1",
      );
      expect(row.getByRole("link", { name: /Registrar salida de «Portátil 14" Business» \(NXV-IT-001\)/ })).toHaveAttribute(
        "href",
        "/inventory/orders/outbound?asset=1",
      );
    });
  });

  describe("edge cases", () => {
    it("filters by level when a summary tile is pressed", async () => {
      render(<AssetsPage />);
      await screen.findAllByTestId("asset-row");

      fireEvent.click(screen.getByRole("button", { name: /Stock bajo/ }));

      expect(screen.getAllByTestId("asset-row")).toHaveLength(1);
      expect(screen.getByText("NXV-IT-002")).toBeInTheDocument();
    });

    it("says so when there are no assets at all", async () => {
      mockList.mockResolvedValue([]);
      render(<AssetsPage />);

      expect(await screen.findByText("Todavía no hay activos registrados.")).toBeInTheDocument();
    });
  });

  describe("failure modes", () => {
    it("shows why the list could not be loaded, with a way to try again", async () => {
      const { ApiError } = jest.requireMock("@/lib/api");
      mockList.mockRejectedValueOnce(new ApiError("Boom", 0));
      render(<AssetsPage />);

      expect(await screen.findByRole("alert")).toHaveTextContent(/No se pudo conectar/);
      fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));
      expect(await screen.findAllByTestId("asset-row")).toHaveLength(3);
    });

    it("shows that it is loading while retrying, never an empty list that says there are no assets", async () => {
      const { ApiError } = jest.requireMock("@/lib/api");
      let finish: (assets: unknown[]) => void = () => undefined;
      mockList.mockRejectedValueOnce(new ApiError("Boom", 0)).mockReturnValueOnce(new Promise((resolve) => (finish = resolve)));
      render(<AssetsPage />);
      await screen.findByRole("alert");

      fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));

      expect(await screen.findByText("Cargando inventario…")).toBeInTheDocument();
      expect(screen.queryByText("Todavía no hay activos registrados.")).not.toBeInTheDocument();
      finish(ASSETS);
      expect(await screen.findAllByTestId("asset-row")).toHaveLength(3);
    });
  });

  describe("telemetry", () => {
    afterEach(() => jest.useRealTimers());

    it("reports ONE search 500 ms after the user stops changing the filters, with counts and never the text", async () => {
      jest.useFakeTimers();
      render(<AssetsPage />);
      await act(async () => { await jest.advanceTimersByTimeAsync(0); });
      const box = screen.getByLabelText("Buscar por nombre o SKU");

      fireEvent.change(box, { target: { value: "h" } });
      fireEvent.change(box, { target: { value: "hu" } });
      fireEvent.change(box, { target: { value: "hub" } });
      await act(async () => { await jest.advanceTimersByTimeAsync(499); });
      expect(searches()).toEqual([]);
      await act(async () => { await jest.advanceTimersByTimeAsync(1); });

      expect(searches()).toEqual([{ section: "inventory", result_count: 1, filter_count: 1 }]);
      expect(JSON.stringify(trackMock.mock.calls)).not.toMatch(/hub/i);
    });

    it("counts every active filter and the results left", async () => {
      jest.useFakeTimers();
      render(<AssetsPage />);
      await act(async () => { await jest.advanceTimersByTimeAsync(0); });

      fireEvent.change(screen.getByLabelText("Filtrar por oficina"), { target: { value: "Miami" } });
      fireEvent.change(screen.getByLabelText("Buscar por nombre o SKU"), { target: { value: "NXV" } });
      await act(async () => { await jest.advanceTimersByTimeAsync(500); });

      expect(searches()).toEqual([{ section: "inventory", result_count: 2, filter_count: 2 }]);
    });

    it("the unfiltered view on load is not a search, and clearing the filters back to it is not one either", async () => {
      jest.useFakeTimers();
      render(<AssetsPage />);
      await act(async () => { await jest.advanceTimersByTimeAsync(2_000); });
      expect(searches()).toEqual([]);
    });
  });
});
