/**
 * The entry form (`views/InboundOrderPage.tsx`, /inventory/orders/inbound): an asset picked by name, the data the
 * API needs, the form cleared with a confirmation after a send, and a visible message when the API fails.
 *
 * Layout shared by every frontend test file: HAPPY PATH, EDGE CASES, FAILURE MODES. Arrange / Act / Assert.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import InboundOrderPage from "@/views/InboundOrderPage";
import { track } from "@/lib/telemetry";

const mockList = jest.fn();
const mockGet = jest.fn();
const mockCreate = jest.fn();
jest.mock("next/link", () => ({ __esModule: true, default: ({ href, children, onClick }: { href: string; children: unknown; onClick?: () => void }) => <a href={href} onClick={onClick}>{children as never}</a> }));
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
jest.mock("@/lib/telemetry/ids", () => ({ uuidV4: () => "20000000-0000-4000-8000-0000000000aa" }));
const trackMock = jest.mocked(track);
const flowEvents = () => trackMock.mock.calls.filter(([type]) => /^(flow_|form_)/.test(type)).map(([type, props]) => [type, (props as Record<string, unknown>).step ?? (props as Record<string, unknown>).field]);
jest.mock("@/lib/inventory", () => ({
  listAssets: (...args: unknown[]) => mockList(...args),
  getAsset: (...args: unknown[]) => mockGet(...args),
  createInboundOrder: (...args: unknown[]) => mockCreate(...args),
}));

const HUB = {
  id: 4, name: "Hub USB-C", sku: "NXV-PER-002", category: "peripherals", office: "Miami", current_stock: 25,
  programme_id: "onboarding-soporte", product_category: "onboarding_equipment", minimum_stock: 5,
};

const settled = () =>
  waitFor(() => {
    expect(screen.queryByLabelText("Actualizando stock")).not.toBeInTheDocument();
    expect(screen.getByTestId("available-stock")).toBeInTheDocument();
  });
const choose = async () => {
  await screen.findByRole("option", { name: /NXV-PER-002/ });
  fireEvent.change(screen.getByLabelText("Activo"), { target: { value: "4" } });
  await settled();
};
const fillAndSend = () => {
  fireEvent.change(screen.getByLabelText("Cantidad"), { target: { value: "10" } });
  fireEvent.change(screen.getByLabelText(/Coste unitario/), { target: { value: "12,50" } });
  fireEvent.change(screen.getByLabelText("Proveedor"), { target: { value: "Office Depot Miami" } });
  fireEvent.click(screen.getByRole("button", { name: "Registrar entrada" }));
};

beforeEach(() => {
  mockList.mockReset().mockResolvedValue([HUB]);
  mockGet.mockReset().mockResolvedValue(HUB);
  mockCreate.mockReset();
});

describe("InboundOrderPage", () => {
  describe("happy path", () => {
    it("lists the assets by name (never asks for a raw id) and sends the entry with the asset's office", async () => {
      mockCreate.mockResolvedValue({ type: "inbound", id: 7, asset: HUB, quantity: 10, office: "Miami" });
      render(<InboundOrderPage />);
      await choose();

      fillAndSend();

      await waitFor(() =>
        expect(mockCreate).toHaveBeenCalledWith(
          { asset_id: 4, quantity: 10, supplier: "Office Depot Miami", unit_cost_minor: 1250, office: "Miami" },
          // the asset the user picked, and the id shared by the request and its events
          { asset: HUB, requestId: expect.stringMatching(/^[0-9a-f-]{36}$/) },
        ),
      );
      expect(screen.getByRole("option", { name: "Hub USB-C · NXV-PER-002 · Miami" })).toBeInTheDocument();
    });

    it("clears the form and confirms after a successful send", async () => {
      mockCreate.mockResolvedValue({ type: "inbound", id: 7, asset: HUB, quantity: 10, office: "Miami" });
      render(<InboundOrderPage />);
      await choose();

      fillAndSend();

      expect(await screen.findByRole("status")).toHaveTextContent("Entrada registrada: 10 unidades de «Hub USB-C» (Miami)");
      expect(screen.getByLabelText("Activo")).toHaveValue("");
      expect(screen.getByLabelText("Cantidad")).toHaveValue(null);
      expect(screen.getByLabelText("Proveedor")).toHaveValue("");
      expect(screen.getByLabelText(/Coste unitario/)).toHaveValue("");
    });

    it("names the currency of the asset's office next to the cost", async () => {
      render(<InboundOrderPage />);
      await choose();
      expect(screen.getByLabelText("Coste unitario (USD)")).toBeInTheDocument(); // the hub is in Miami
    });
  });

  describe("edge cases", () => {
    it("asks for every missing field and does not call the API", async () => {
      render(<InboundOrderPage />);
      await screen.findByRole("option", { name: /NXV-PER-002/ });

      fireEvent.click(screen.getByRole("button", { name: "Registrar entrada" }));

      expect(await screen.findByText("Selecciona el activo recibido.")).toBeInTheDocument();
      expect(screen.getByText("Indica el proveedor.")).toBeInTheDocument();
      expect(screen.getByText(/Indica el coste unitario/)).toBeInTheDocument();
      expect(mockCreate).not.toHaveBeenCalled();
    });
  });

  describe("failure modes", () => {
    it("shows the API's message in a visible element on a 400", async () => {
      const { ApiError } = jest.requireMock("@/lib/api");
      mockCreate.mockRejectedValue(new ApiError("Asset 'Hub USB-C' belongs to the Miami office: an order for it cannot be registered in Valencia.", 422));
      render(<InboundOrderPage />);
      await choose();

      fillAndSend();

      expect(await screen.findByRole("alert")).toHaveTextContent(/pertenece a la oficina de Miami/);
      expect(screen.getByLabelText("Cantidad")).toHaveValue(10); // the form is kept so nothing has to be retyped
    });

    it("shows a visible message on a 500, not only in the console", async () => {
      const { ApiError } = jest.requireMock("@/lib/api");
      mockCreate.mockRejectedValue(new ApiError("Internal Server Error", 500));
      render(<InboundOrderPage />);
      await choose();

      fillAndSend();

      expect(await screen.findByRole("alert")).toHaveTextContent(/problema \(error 500\)/);
    });
  });

  describe("telemetry of the flow", () => {
    it("tells started -> validated -> submitted -> confirmed, the last two with the id sent to the API", async () => {
      mockCreate.mockResolvedValue({ type: "inbound", id: 7, asset: HUB, quantity: 10, office: "Miami" });
      render(<InboundOrderPage />);
      await choose();
      fireEvent.focus(screen.getByLabelText("Cantidad"));

      fillAndSend();
      await screen.findByRole("status");

      expect(flowEvents()).toEqual([
        ["flow_started", "form"],
        ["flow_step_completed", "validated"],
        ["flow_step_completed", "submitted"],
        ["flow_completed", "confirmed"],
      ]);
      const submitted = trackMock.mock.calls.find(([type, props]) => type === "flow_step_completed" && (props as { step: string }).step === "submitted");
      expect(submitted?.[2]).toEqual({ requestId: "20000000-0000-4000-8000-0000000000aa" });
      expect(mockCreate.mock.calls[0][1].requestId).toBe("20000000-0000-4000-8000-0000000000aa"); // the HTTP call shares it
    });

    it("a blocked submit is a form_validation_failed with 'multiple' and nothing else after it, and no request", async () => {
      render(<InboundOrderPage />);
      await screen.findByRole("option", { name: /NXV-PER-002/ });

      fireEvent.click(screen.getByRole("button", { name: "Registrar entrada" }));

      await screen.findByText("Selecciona el activo recibido.");
      expect(flowEvents()).toEqual([["flow_started", "form"], ["form_validation_failed", "multiple"]]);
      expect(mockCreate).not.toHaveBeenCalled();
      const failed = trackMock.mock.calls.find(([type]) => type === "form_validation_failed")?.[1] as { error_count: number };
      expect(failed.error_count).toBe(4); // asset, quantity, unit cost, supplier
    });

    it("a refusal by the API leaves the attempt open: no completed, no cancelled", async () => {
      const { ApiError } = jest.requireMock("@/lib/api");
      mockCreate.mockRejectedValue(new ApiError("Internal Server Error", 500));
      render(<InboundOrderPage />);
      await choose();
      fillAndSend();
      await screen.findByRole("alert");
      expect(flowEvents().map(([type]) => type)).toEqual(["flow_started", "flow_step_completed", "flow_step_completed"]);
    });

    it("leaving through 'Volver al inventario' cancels the attempt at the last step reached", async () => {
      render(<InboundOrderPage />);
      await choose();
      fireEvent.focus(screen.getByLabelText("Cantidad"));

      fireEvent.click(screen.getByText("Volver al inventario"));

      expect(flowEvents()).toEqual([["flow_started", "form"], ["flow_cancelled", "form"]]);
    });

    it("leaving without having touched the form reports nothing", async () => {
      render(<InboundOrderPage />);
      await choose();
      trackMock.mockClear();
      fireEvent.click(screen.getByText("Volver al inventario"));
      expect(flowEvents()).toEqual([]);
    });

    it("never puts what was typed in an event", async () => {
      mockCreate.mockResolvedValue({ type: "inbound", id: 7, asset: HUB, quantity: 10, office: "Miami" });
      render(<InboundOrderPage />);
      await choose();
      fillAndSend();
      await screen.findByRole("status");
      expect(JSON.stringify(trackMock.mock.calls)).not.toMatch(/Office Depot|12,50/);
    });
  });
});
