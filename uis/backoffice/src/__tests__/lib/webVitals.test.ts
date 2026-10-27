// Web Vitals as telemetry (`lib/telemetry/webVitals.ts`): which metrics are sent, with which section, and with what value.
import { track } from "@/lib/telemetry";
import { reportWebVital, resetLandingPath, setLandingPath } from "@/lib/telemetry/webVitals";

jest.mock("@/lib/telemetry", () => ({ track: jest.fn() }));
const trackMock = jest.mocked(track);

beforeEach(() => resetLandingPath());

describe("reportWebVital", () => {
  it("reports each of the five vitals with the section of the page the visit landed on", () => {
    setLandingPath("/inventory/products");
    for (const name of ["LCP", "CLS", "INP", "FCP", "TTFB"]) reportWebVital({ name, value: 100, rating: "good" });
    expect(trackMock.mock.calls.map(([type, props]) => [type, (props as { metric: string }).metric])).toEqual(
      ["LCP", "CLS", "INP", "FCP", "TTFB"].map((metric) => ["web_vital_reported", metric]),
    );
    expect(trackMock.mock.calls[0][1]).toEqual({ metric: "LCP", value: 100, rating: "good", section: "inventory" });
  });

  it("the section is the landing page, not wherever the user navigated to before the metric was final", () => {
    setLandingPath("/suppliers");
    setLandingPath("/inventory/orders/inbound"); // a later navigation: ignored
    reportWebVital({ name: "CLS", value: 0.05, rating: "good" });
    expect(trackMock.mock.calls[0][1]).toMatchObject({ section: "suppliers" });
  });

  it("keeps a fractional CLS and rounds a long float", () => {
    setLandingPath("/");
    reportWebVital({ name: "CLS", value: 0.123456789, rating: "needs-improvement" });
    reportWebVital({ name: "LCP", value: 1840.123456, rating: "good" });
    expect(trackMock.mock.calls.map(([, props]) => (props as { value: number }).value)).toEqual([0.1235, 1840.1235]);
  });

  it.each([
    [{ name: "FID", value: 10, rating: "good" }],
    [{ name: "Next.js-hydration", value: 10, rating: "good" }],
    [{ name: "LCP", value: 10, rating: "fine" }],
    [{ name: "LCP", value: 10 }],
    [{ name: "LCP", value: -1, rating: "good" }],
    [{ name: "LCP", value: Number.NaN, rating: "good" }],
    [{ name: "LCP", value: Infinity, rating: "poor" }],
  ])("ignores %p: outside the contract's allowlist", (metric) => {
    setLandingPath("/");
    reportWebVital(metric);
    expect(trackMock).not.toHaveBeenCalled();
  });

  it("says nothing before the landing page is known, or for a page that is not a section of the contract", () => {
    reportWebVital({ name: "LCP", value: 10, rating: "good" });
    setLandingPath("/somewhere/else");
    reportWebVital({ name: "LCP", value: 10, rating: "good" });
    expect(trackMock).not.toHaveBeenCalled();
  });
});
