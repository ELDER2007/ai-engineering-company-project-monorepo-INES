// The global part of the capture (`components/TelemetryProvider.tsx`): one page view per logical navigation and the
// unhandled-error listeners. `track` and the telemetry service are mocked.
//
// Layout shared by every frontend test file: HAPPY PATH, EDGE CASES, FAILURE MODES. Arrange / Act / Assert.
import { StrictMode } from "react";
import { act, render } from "@testing-library/react";
import TelemetryProvider from "@/components/TelemetryProvider";
import { resetLandingPath } from "@/lib/telemetry/webVitals";
import { track } from "@/lib/telemetry";

let mockPath = "/";
jest.mock("next/navigation", () => ({ usePathname: () => mockPath }));
jest.mock("@/lib/telemetry", () => ({ track: jest.fn() }));
const mockUseReportWebVitals = jest.fn();
jest.mock("next/web-vitals", () => ({ useReportWebVitals: (...args: unknown[]) => mockUseReportWebVitals(...args) }));
const trackMock = jest.mocked(track);
const views = () => trackMock.mock.calls.filter(([type]) => type === "section_viewed").map(([, props]) => (props as { section: string }).section);

beforeEach(() => {
  resetLandingPath();
  mockPath = "/";
  window.history.pushState({}, "", "/");
});

describe("TelemetryProvider", () => {
  describe("happy path", () => {
    it("reports the page view of the section the user lands on, in Spanish", () => {
      mockPath = "/inventory/orders/inbound";
      render(<TelemetryProvider />);
      expect(trackMock).toHaveBeenCalledWith("section_viewed", { section: "inbound", locale: "es" });
    });

    it("reports a new view on each navigation, and a later return to a page counts as another visit", () => {
      mockPath = "/";
      const { rerender } = render(<TelemetryProvider />);
      mockPath = "/suppliers";
      rerender(<TelemetryProvider />);
      mockPath = "/";
      rerender(<TelemetryProvider />);
      expect(views()).toEqual(["home", "suppliers", "home"]);
    });
  });

  describe("web vitals", () => {
    it("hands Next.js the same stable function on every render, so no metric is reported twice", () => {
      const { rerender } = render(<TelemetryProvider />);
      rerender(<TelemetryProvider />);
      const [first, second] = mockUseReportWebVitals.mock.calls.map(([fn]) => fn);
      expect(typeof first).toBe("function");
      expect(first).toBe(second);
    });

    it("remembers the page the visit landed on, not the later ones", () => {
      mockPath = "/suppliers";
      const { rerender } = render(<TelemetryProvider />);
      mockPath = "/inventory/products";
      rerender(<TelemetryProvider />);
      const report = mockUseReportWebVitals.mock.calls[0][0];
      report({ name: "LCP", value: 900, rating: "good" });
      expect(trackMock).toHaveBeenCalledWith("web_vital_reported", { metric: "LCP", value: 900, rating: "good", section: "suppliers" });
    });
  });

  describe("edge cases", () => {
    it("re-rendering on the same path, or Strict Mode's double effect, is not a second view", () => {
      mockPath = "/suppliers";
      const { rerender } = render(
        <StrictMode>
          <TelemetryProvider />
        </StrictMode>,
      );
      rerender(
        <StrictMode>
          <TelemetryProvider />
        </StrictMode>,
      );
      expect(views()).toEqual(["suppliers"]);
    });

    it("a path that is not a view of the contract reports nothing", () => {
      mockPath = "/something/else";
      render(<TelemetryProvider />);
      expect(views()).toEqual([]);
    });
  });

  describe("unhandled errors", () => {
    const errors = () => trackMock.mock.calls.filter(([type]) => type === "application_error_occurred");

    it("reports an unhandled error and a rejected promise with the component of the current page, never the message", () => {
      window.history.pushState({}, "", "/inventory/products");
      render(<TelemetryProvider />);

      act(() => {
        window.dispatchEvent(new ErrorEvent("error", { message: "Cannot read maria.lopez@example.com" }));
        window.dispatchEvent(new Event("unhandledrejection"));
      });

      expect(errors()).toEqual([
        ["application_error_occurred", { error_code: "unhandled_exception", component: "inventory" }],
        ["application_error_occurred", { error_code: "unhandled_exception", component: "inventory" }],
      ]);
      expect(JSON.stringify(errors())).not.toContain("maria");
    });

    it("says nothing for a page whose area the contract cannot name (no mislabelling)", () => {
      render(<TelemetryProvider />); // "/"
      act(() => {
        window.dispatchEvent(new ErrorEvent("error"));
      });
      expect(errors()).toEqual([]);
    });

    it("caps a flood at 10 per minute, and starts counting again afterwards", () => {
      jest.useFakeTimers().setSystemTime(new Date("2026-10-27T10:00:00Z"));
      window.history.pushState({}, "", "/suppliers");
      render(<TelemetryProvider />);
      act(() => {
        for (let i = 0; i < 25; i += 1) window.dispatchEvent(new ErrorEvent("error"));
      });
      expect(errors()).toHaveLength(10);

      jest.setSystemTime(new Date("2026-10-27T10:01:01Z"));
      act(() => {
        window.dispatchEvent(new ErrorEvent("error"));
      });
      expect(errors()).toHaveLength(11);
      jest.useRealTimers();
    });

    it("stops listening when unmounted", () => {
      window.history.pushState({}, "", "/suppliers");
      const { unmount } = render(<TelemetryProvider />);
      unmount();
      act(() => {
        window.dispatchEvent(new ErrorEvent("error"));
      });
      expect(errors()).toEqual([]);
    });
  });
});
