/**
 * @jest-environment node
 */
// An environment with a `window` but no `document` (a worker-like context, or a test harness): the first track() starts the
// service, which cannot listen to the document. That costs the exit flush, never the event being captured. (Found when the very first
// event of a real run went missing.)
import { TelemetryService } from "@/lib/telemetry/TelemetryService";

describe("TelemetryService without a document", () => {
  beforeEach(() => {
    (globalThis as { window?: unknown }).window = globalThis;
  });
  afterEach(() => {
    delete (globalThis as { window?: unknown }).window;
  });

  it("still queues the very first event, and the next ones", () => {
    const s = new TelemetryService({ endpoint: "http://api.test/telemetry/events", environment: "test" });
    s.track("section_viewed", { section: "home", locale: "es" });
    s.track("section_viewed", { section: "home", locale: "es" });
    expect(s.pending).toBe(2);
    s.reset();
  });
});
