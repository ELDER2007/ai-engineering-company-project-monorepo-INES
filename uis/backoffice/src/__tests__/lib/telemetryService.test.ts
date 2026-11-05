// The capture system (`lib/telemetry/TelemetryService.ts`): events are queued, then leave in batches; the page
// closing flushes with sendBeacon; a failing network retries with exponential backoff and finally gives up.
// Fetch, sendBeacon and Blob are fakes and time is fake: nothing here touches a network or waits for real.
//
// Layout shared by every frontend test file: HAPPY PATH, EDGE CASES, FAILURE MODES. Arrange / Act / Assert.
import { TelemetryService, type TelemetryConfig } from "@/lib/telemetry/TelemetryService";
import type { TelemetryEnvelope } from "@/lib/telemetry/events";

const ENDPOINT = "http://api.test/telemetry/events";
const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

const fetchMock = jest.fn();
const beaconMock = jest.fn();

class FakeBlob {
  constructor(
    public parts: string[],
    public options: { type: string },
  ) {}
}

const ok = (rejected: unknown[] = []) => ({ ok: true, status: 200, json: async () => ({ received: 1, accepted: 1, rejected }) });
const status = (code: number) => ({ ok: false, status: code, json: async () => ({}) });

const created: TelemetryService[] = [];
function service(over: Partial<TelemetryConfig> = {}) {
  const s = new TelemetryService({ endpoint: ENDPOINT, environment: "test", ...over });
  created.push(s);
  return s;
}
const section = { section: "inventory", locale: "es" } as const;
const stockEvent = {
  office: "valencia", product_id: "1", product_category: "training_kit", programme_id: "ventas-b2b", quantity: 2, currency: "EUR",
  order_id: "9", stock_before: 12, stock_after: 10,
} as const;

/** The events of the n-th request sent with fetch. */
const sentBatch = (call = 0): TelemetryEnvelope[] => JSON.parse(fetchMock.mock.calls[call][1].body).events;

beforeEach(() => {
  jest.useFakeTimers();
  jest.setSystemTime(new Date("2026-10-27T10:00:00.000Z"));
  fetchMock.mockReset().mockResolvedValue(ok());
  beaconMock.mockReset().mockReturnValue(true);
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  globalThis.Blob = FakeBlob as unknown as typeof Blob;
  Object.defineProperty(navigator, "sendBeacon", { value: beaconMock, configurable: true });
  Object.defineProperty(navigator, "doNotTrack", { value: null, configurable: true });
  sessionStorage.clear();
});
afterEach(() => {
  created.splice(0).forEach((s) => s.reset()); // a service listens to the document for as long as it lives: do not leak it into the next test
  jest.useRealTimers();
});

describe("TelemetryService", () => {
  describe("happy path", () => {
    it("builds the closed envelope of the contract for each event", () => {
      const s = service({ environment: "staging" });
      s.track("section_viewed", section);
      s.flushOnExit();

      const [event] = JSON.parse((beaconMock.mock.calls[0][1] as FakeBlob).parts[0]).events as TelemetryEnvelope[];
      expect(Object.keys(event).sort()).toEqual(
        ["environment", "eventId", "event_type", "properties", "requestId", "schemaVersion", "sessionId", "source", "timestamp", "userId"],
      );
      expect(event).toMatchObject({ event_type: "section_viewed", schemaVersion: "2.1.0", userId: null, source: "backoffice", environment: "staging", properties: section });
      expect(event.eventId).toMatch(UUID_V4);
      expect(event.requestId).toMatch(UUID_V4);
      expect(event.sessionId).toMatch(UUID_V4);
      expect(event.timestamp).toBe("2026-10-27T10:00:00.000Z");
    });

    it("only queues: tracking never touches the network by itself", () => {
      const s = service();
      s.track("section_viewed", section);
      expect(fetchMock).not.toHaveBeenCalled();
      expect(s.pending).toBe(1);
    });

    it("sends a burst as ONE request, 10 s after the first event, never one request per event", async () => {
      const s = service();
      for (let i = 0; i < 7; i += 1) s.track("section_viewed", section);

      await jest.advanceTimersByTimeAsync(9_999);
      expect(fetchMock).not.toHaveBeenCalled();
      await jest.advanceTimersByTimeAsync(1);

      expect(fetchMock).toHaveBeenCalledTimes(1);
      expect(sentBatch()).toHaveLength(7);
      const [url, init] = fetchMock.mock.calls[0];
      expect(url).toBe(ENDPOINT);
      expect(init).toMatchObject({ method: "POST", keepalive: true, headers: { "Content-Type": "application/json" } });
      expect(s.pending).toBe(0);
    });

    it("flushes as soon as the queue reaches the batch size, still in a single request", async () => {
      const s = service({ batchSize: 20 });
      for (let i = 0; i < 20; i += 1) s.track("section_viewed", section);

      await jest.advanceTimersByTimeAsync(0);

      expect(fetchMock).toHaveBeenCalledTimes(1);
      expect(sentBatch()).toHaveLength(20);
    });

    it("keeps the instant of capture as each event's timestamp, not the instant of delivery", async () => {
      const s = service();
      s.track("section_viewed", section);
      await jest.advanceTimersByTimeAsync(3_000);
      s.track("section_viewed", section);
      await jest.advanceTimersByTimeAsync(7_000);

      expect(sentBatch().map((e) => e.timestamp)).toEqual(["2026-10-27T10:00:00.000Z", "2026-10-27T10:00:03.000Z"]);
    });

    it("the two triggers are the only ones: a mandatory event waits for the 10 s like any other, the size comes first if it is earlier", async () => {
      const s = service();
      s.track("section_viewed", section);
      s.track("outbound_order_created", stockEvent);
      await jest.advanceTimersByTimeAsync(9_999);
      expect(fetchMock).not.toHaveBeenCalled();
      await jest.advanceTimersByTimeAsync(1);
      expect(sentBatch().map((e) => e.event_type)).toEqual(["section_viewed", "outbound_order_created"]);
    });

    it("sends the bearer token when there is one", async () => {
      const s = service({ getToken: () => "tok-1" });
      s.track("section_viewed", section);
      await jest.advanceTimersByTimeAsync(10_000);
      expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe("Bearer tok-1");
    });

    it("at logout, the events that need the user's identity leave at once with the token that still exists; the rest waits", async () => {
      let token: string | null = "tok-1";
      const s = service({ getToken: () => token });
      s.track("section_viewed", section);
      s.track("outbound_order_created", stockEvent);
      s.track("login_succeeded", { method: "password", duration_ms: 90 });

      s.track("logout_completed", { reason: "user_action" });
      token = null; // what the app does right after

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [, init] = fetchMock.mock.calls[0];
      expect(init.headers.Authorization).toBe("Bearer tok-1");
      expect(JSON.parse(init.body).events.map((e: TelemetryEnvelope) => e.event_type)).toEqual(["outbound_order_created", "login_succeeded"]);
      expect(s.pending).toBe(2); // the page view and the logout wait for their own batch
      await jest.advanceTimersByTimeAsync(10_000);
      expect(sentBatch(1).map((e) => e.event_type)).toEqual(["section_viewed", "logout_completed"]);
    });

    it("a logout with nothing that needs identity sends nothing early", () => {
      const s = service();
      s.track("section_viewed", section);
      s.track("logout_completed", { reason: "user_action" });
      expect(fetchMock).not.toHaveBeenCalled();
    });

    it("uses the requestId it is given, so the client and the API can be correlated", async () => {
      const s = service();
      s.track("section_viewed", section, { requestId: "11111111-1111-4111-8111-111111111111" });
      await jest.advanceTimersByTimeAsync(10_000);
      expect(sentBatch()[0].requestId).toBe("11111111-1111-4111-8111-111111111111");
    });
  });

  describe("the analytic session", () => {
    it("is the same across events and page loads, and is not a token or anything about the user", async () => {
      const first = service();
      first.track("section_viewed", section);
      first.track("section_viewed", section);
      const reloaded = service(); // another page load: same sessionStorage
      reloaded.track("section_viewed", section);
      first.flushOnExit();
      reloaded.flushOnExit();

      const ids = beaconMock.mock.calls.flatMap(([, blob]) => JSON.parse((blob as FakeBlob).parts[0]).events.map((e: TelemetryEnvelope) => e.sessionId));
      expect(new Set(ids).size).toBe(1);
    });

    it("is a new one after 30 minutes without activity", async () => {
      const s = service();
      s.track("section_viewed", section);
      jest.setSystemTime(new Date("2026-10-27T10:31:00.000Z"));
      s.track("section_viewed", section);
      await jest.advanceTimersByTimeAsync(10_000);
      const [a, b] = sentBatch();
      expect(a.sessionId).not.toBe(b.sessionId);
    });

    it("rotates on demand (login, logout)", async () => {
      const s = service();
      s.track("section_viewed", section);
      s.rotateSession();
      s.track("section_viewed", section);
      await jest.advanceTimersByTimeAsync(10_000);
      const [a, b] = sentBatch();
      expect(a.sessionId).not.toBe(b.sessionId);
      expect(b.sessionId).toMatch(UUID_V4);
    });

    it("still works, in memory, when the browser blocks sessionStorage", async () => {
      jest.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
        throw new Error("blocked");
      });
      jest.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
        throw new Error("blocked");
      });
      const s = service();
      s.track("section_viewed", section);
      s.track("section_viewed", section);
      await jest.advanceTimersByTimeAsync(10_000);
      const [a, b] = sentBatch();
      expect(a.sessionId).toMatch(UUID_V4);
      expect(a.sessionId).toBe(b.sessionId);
      jest.restoreAllMocks();
    });
  });

  describe("leaving the page", () => {
    it("hands the pending events to sendBeacon as text/plain, so it stays a simple CORS request", () => {
      const s = service();
      s.track("section_viewed", section);
      s.track("logout_completed", { reason: "user_action" });

      s.flushOnExit();

      expect(beaconMock).toHaveBeenCalledTimes(1);
      const [url, blob] = beaconMock.mock.calls[0] as [string, FakeBlob];
      expect(url).toBe(ENDPOINT);
      expect(blob.options.type).toBe("text/plain;charset=UTF-8");
      expect(JSON.parse(blob.parts[0]).events).toHaveLength(2);
      expect(s.pending).toBe(0);
    });

    it("sends the events that need the user's identity with keepalive fetch, because a beacon cannot carry a header", () => {
      const s = service({ getToken: () => "tok-1" });
      s.track("section_viewed", section);
      s.track("outbound_order_created", stockEvent);

      s.flushOnExit();

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [, init] = fetchMock.mock.calls[0];
      expect(init.keepalive).toBe(true);
      expect(init.headers.Authorization).toBe("Bearer tok-1");
      expect(JSON.parse(init.body).events.map((e: TelemetryEnvelope) => e.event_type)).toEqual(["outbound_order_created"]);
      expect(JSON.parse((beaconMock.mock.calls[0][1] as FakeBlob).parts[0]).events.map((e: TelemetryEnvelope) => e.event_type)).toEqual(["section_viewed"]);
    });

    it("splits a long queue into several beacons of the batch size", () => {
      const s = service({ batchSize: 20, maxQueued: 100 });
      for (let i = 0; i < 45; i += 1) s.track("section_viewed", section);
      // the size trigger has armed a flush; leaving first takes everything
      s.flushOnExit();
      expect(beaconMock.mock.calls.map(([, blob]) => JSON.parse((blob as FakeBlob).parts[0]).events.length)).toEqual([20, 20, 5]);
    });

    it("resends the batch that was in flight, since the browser may cancel it (the receiver deduplicates by eventId)", async () => {
      fetchMock.mockReturnValueOnce(new Promise(() => undefined)); // never settles
      const s = service();
      s.track("section_viewed", section);
      await jest.advanceTimersByTimeAsync(10_000);
      const inFlightId = sentBatch()[0].eventId;

      s.flushOnExit();

      expect(JSON.parse((beaconMock.mock.calls[0][1] as FakeBlob).parts[0]).events[0].eventId).toBe(inFlightId);
    });

    it("falls back to keepalive fetch when the browser refuses the beacon", () => {
      beaconMock.mockReturnValue(false);
      const s = service();
      s.track("section_viewed", section);
      s.flushOnExit();
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    it("does nothing when there is nothing pending", () => {
      service().flushOnExit();
      expect(beaconMock).not.toHaveBeenCalled();
      expect(fetchMock).not.toHaveBeenCalled();
    });

    it("flushes when the page is hidden (visibilitychange) and when it is closed (pagehide)", () => {
      const s = service();
      s.track("section_viewed", section);

      Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true });
      document.dispatchEvent(new Event("visibilitychange"));
      expect(beaconMock).toHaveBeenCalledTimes(1);

      s.track("section_viewed", section);
      window.dispatchEvent(new Event("pagehide"));
      expect(beaconMock).toHaveBeenCalledTimes(2);
      Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
    });

    it("nobody has to start the service: the first track() starts listening, once", () => {
      const add = jest.spyOn(document, "addEventListener");
      const s = service();
      s.track("section_viewed", section);
      s.track("section_viewed", section);
      expect(add.mock.calls.filter(([type]) => type === "visibilitychange")).toHaveLength(1);
      Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true });
      document.dispatchEvent(new Event("visibilitychange"));
      expect(beaconMock).toHaveBeenCalledTimes(1);
      Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
      add.mockRestore();
    });

    it("a visible page does not flush", () => {
      const s = service();
      s.start();
      s.track("section_viewed", section);
      Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
      document.dispatchEvent(new Event("visibilitychange"));
      expect(beaconMock).not.toHaveBeenCalled();
    });
  });

  describe("retries with exponential backoff", () => {
    it("retries the SAME batch 3 times, after 1, 2 and 4 s, then drops it: 4 sends in total", async () => {
      fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
      const warn = jest.spyOn(console, "warn").mockImplementation(() => undefined);
      const s = service();
      s.track("section_viewed", section);

      await jest.advanceTimersByTimeAsync(10_000);
      expect(fetchMock).toHaveBeenCalledTimes(1);
      await jest.advanceTimersByTimeAsync(999);
      expect(fetchMock).toHaveBeenCalledTimes(1);
      await jest.advanceTimersByTimeAsync(1);
      expect(fetchMock).toHaveBeenCalledTimes(2); // retry 1, after 1 s
      await jest.advanceTimersByTimeAsync(1_999);
      expect(fetchMock).toHaveBeenCalledTimes(2);
      await jest.advanceTimersByTimeAsync(1);
      expect(fetchMock).toHaveBeenCalledTimes(3); // retry 2, after 2 s
      await jest.advanceTimersByTimeAsync(4_000);
      expect(fetchMock).toHaveBeenCalledTimes(4); // retry 3, after 4 s
      await jest.advanceTimersByTimeAsync(120_000);

      expect(fetchMock).toHaveBeenCalledTimes(4); // gave up: no fifth send
      expect(new Set([0, 1, 2, 3].map((i) => sentBatch(i)[0].eventId)).size).toBe(1); // same event every time
      expect(s.pending).toBe(0);
      expect(s.droppedEvents).toBe(1);
      expect(warn).toHaveBeenCalledWith(expect.stringContaining("dropped after 4 attempts (3 retries)"));
      warn.mockRestore();
    });

    it("recovers when the network comes back, and the next batch goes out normally", async () => {
      fetchMock.mockRejectedValueOnce(new TypeError("offline")).mockResolvedValue(ok());
      const s = service();
      s.track("section_viewed", section);
      await jest.advanceTimersByTimeAsync(10_000 + 1_000);
      expect(fetchMock).toHaveBeenCalledTimes(2);
      expect(s.pending).toBe(0);
      expect(s.droppedEvents).toBe(0);
    });

    it.each([429, 500, 503])("retries a %i answer", async (code) => {
      fetchMock.mockResolvedValueOnce(status(code)).mockResolvedValue(ok());
      const s = service();
      s.track("section_viewed", section);
      await jest.advanceTimersByTimeAsync(11_000);
      expect(fetchMock).toHaveBeenCalledTimes(2);
    });

    it.each([400, 413, 422])("does NOT retry a %i: the same batch would be refused again", async (code) => {
      fetchMock.mockResolvedValue(status(code));
      const warn = jest.spyOn(console, "warn").mockImplementation(() => undefined);
      const s = service();
      s.track("section_viewed", section);
      await jest.advanceTimersByTimeAsync(60_000);
      expect(fetchMock).toHaveBeenCalledTimes(1);
      expect(s.droppedEvents).toBe(1);
      warn.mockRestore();
    });

    it("keeps capturing while a batch is waiting to be retried, and sends those events afterwards", async () => {
      fetchMock.mockRejectedValueOnce(new TypeError("offline")).mockResolvedValue(ok());
      const s = service();
      s.track("section_viewed", section);
      await jest.advanceTimersByTimeAsync(10_000);
      s.track("logout_completed", { reason: "user_action" }); // captured during the backoff wait
      await jest.advanceTimersByTimeAsync(1_000);
      await jest.advanceTimersByTimeAsync(10_000);

      expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(3);
      expect(sentBatch(fetchMock.mock.calls.length - 1).map((e) => e.event_type)).toEqual(["logout_completed"]);
    });

    it("tells the developer, without any event contents, which events the receiver rejected", async () => {
      fetchMock.mockResolvedValue(ok([{ index: 0, path: "/properties", rule: "unevaluatedProperties" }]));
      const warn = jest.spyOn(console, "warn").mockImplementation(() => undefined);
      const s = service();
      s.track("section_viewed", section);
      await jest.advanceTimersByTimeAsync(10_000);
      expect(warn).toHaveBeenCalledWith("[telemetry] the receiver rejected 1 event(s): #0 /properties (unevaluatedProperties)");
      warn.mockRestore();
    });

    it("a 200 with an empty or non-JSON body is not an error", async () => {
      fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => { throw new Error("no body"); } });
      const s = service();
      s.track("section_viewed", section);
      await jest.advanceTimersByTimeAsync(10_000);
      expect(s.droppedEvents).toBe(0);
    });
  });

  describe("limits", () => {
    it("never holds more than 100 events: the oldest are dropped first", () => {
      const s = service({ batchSize: 1_000, maxQueued: 100 });
      for (let i = 0; i < 130; i += 1) s.track("section_viewed", { section: "inventory", locale: "es" });
      expect(s.pending).toBe(100);
      expect(s.droppedEvents).toBe(30);
    });

    it("never holds more than the byte budget", () => {
      const s = service({ batchSize: 1_000, maxQueuedBytes: 2_000 });
      for (let i = 0; i < 30; i += 1) s.track("section_viewed", section);
      expect(s.pending).toBeLessThan(10);
      expect(s.droppedEvents).toBeGreaterThan(20);
    });

    it("sends at most maxBatchEvents per request and the rest in the next one", async () => {
      const s = service({ batchSize: 1_000, maxBatchEvents: 3 });
      for (let i = 0; i < 5; i += 1) s.track("section_viewed", section);
      await s.flush();
      await jest.advanceTimersByTimeAsync(10_000);
      expect(fetchMock.mock.calls.map((_, i) => sentBatch(i).length)).toEqual([3, 2]);
    });
  });

  describe("off switches and failure modes", () => {
    it("does nothing without an endpoint", async () => {
      const s = service({ endpoint: "" });
      s.track("section_viewed", section);
      await jest.advanceTimersByTimeAsync(10_000);
      s.flushOnExit();
      expect(s.pending).toBe(0);
      expect(fetchMock).not.toHaveBeenCalled();
      expect(beaconMock).not.toHaveBeenCalled();
    });

    it("respects Do Not Track and Global Privacy Control", () => {
      Object.defineProperty(navigator, "doNotTrack", { value: "1", configurable: true });
      expect(service().enabled).toBe(false);
      Object.defineProperty(navigator, "doNotTrack", { value: null, configurable: true });
      Object.defineProperty(navigator, "globalPrivacyControl", { value: true, configurable: true });
      expect(service().enabled).toBe(false);
      Object.defineProperty(navigator, "globalPrivacyControl", { value: false, configurable: true });
      expect(service().enabled).toBe(true);
    });

    it("never throws into the application, whatever fails inside", () => {
      jest.spyOn(Date.prototype, "toISOString").mockImplementation(() => {
        throw new Error("clock exploded");
      });
      const s = service();
      expect(() => s.track("section_viewed", section)).not.toThrow();
      expect(s.pending).toBe(0);
      jest.restoreAllMocks();
    });

    it("survives a browser without sendBeacon", () => {
      Object.defineProperty(navigator, "sendBeacon", { value: undefined, configurable: true });
      const s = service();
      s.track("section_viewed", section);
      expect(() => s.flushOnExit()).not.toThrow();
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    it("survives a fetch that throws synchronously while leaving, and a sendBeacon that throws", () => {
      fetchMock.mockImplementation(() => {
        throw new Error("sync failure");
      });
      beaconMock.mockImplementation(() => {
        throw new Error("beacon failure");
      });
      const s = service({ getToken: () => "t" });
      s.track("section_viewed", section);
      s.track("outbound_order_created", stockEvent);
      expect(() => s.flushOnExit()).not.toThrow();
      expect(s.droppedEvents).toBeGreaterThanOrEqual(1);
    });

    it("an exit listener that cannot be attached costs the exit flush, never the event being captured", async () => {
      jest.spyOn(document, "addEventListener").mockImplementation(() => {
        throw new Error("no listeners here");
      });
      const s = service();
      s.track("section_viewed", section);
      expect(s.pending).toBe(1);
      await jest.advanceTimersByTimeAsync(10_000);
      expect(fetchMock).toHaveBeenCalledTimes(1);
      jest.restoreAllMocks();
    });

    it("a failed keepalive fetch (offline while leaving) is swallowed", async () => {
      fetchMock.mockRejectedValue(new TypeError("offline"));
      const s = service();
      s.track("outbound_order_created", stockEvent);
      expect(() => s.flushOnExit()).not.toThrow();
      await jest.advanceTimersByTimeAsync(0);
    });

    it("reset() forgets the queue and the timers", async () => {
      const s = service();
      s.track("section_viewed", section);
      s.reset();
      await jest.advanceTimersByTimeAsync(10_000);
      expect(fetchMock).not.toHaveBeenCalled();
      expect(s.pending).toBe(0);
    });

    it("flush() with nothing queued does not send an empty batch", async () => {
      await service().flush();
      expect(fetchMock).not.toHaveBeenCalled();
    });
  });
});
