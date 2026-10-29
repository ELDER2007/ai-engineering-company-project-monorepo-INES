// The capture system of the backoffice: events are queued in memory and leave in batches, never one request per
// event. Three mechanisms (docs/telemetry/telemetry-plan.md, sections 6 and 10):
//
//  1. Queue + batch: `track()` only appends to an array. The batch goes out when the queue reaches `batchSize`
//     (20) events or `flushIntervalMs` (10 s) after the first queued event, whichever comes first. Each event
//     keeps the timestamp of its capture.
//  2. Reliable flush on exit: when the page is hidden or unloaded the browser cancels pending requests, so what
//     is left goes with `navigator.sendBeacon` (text/plain, which keeps it a CORS "simple" request, no preflight).
//     A beacon cannot carry `Authorization`, so the events that need the user's identity use
//     `fetch(..., { keepalive: true })`, which survives the unload and can.
//  3. Retries with exponential backoff: a network error, a 429 or a 5xx retries the same batch (same eventIds, so
//     the receiver can deduplicate) after 1 s, 2 s and 4 s, at most `maxRetries` (3) times; then the batch is
//     dropped. It is telemetry: it never blocks, retries forever or throws into the application.
//
// The service adds to every event what a caller must never pass: eventId, sessionId (a new one at each login and
// logout, see instance.ts), timestamp, schemaVersion, requestId and the environment. `userId` is null here: the
// server derives it from the verified session. Nobody starts or stops the service: the first `track()` does.
//
// The service knows nothing of the application: it has no import from the API client (the token is injected), so
// a failure of its own delivery can never be reported through the channel that failed.
import {
  IDENTITY_BOUND_EVENTS,
  SCHEMA_VERSION,
  SESSION_ENDING_EVENTS,
  type TelemetryEnvelope,
  type TelemetryEventType,
  type TelemetryEvents,
  type TrackOptions,
} from "./events";
import { uuidV4 } from "./ids";

export interface TelemetryConfig {
  /** Where batches are POSTed (NEXT_PUBLIC_TELEMETRY_ENDPOINT). Empty = telemetry is off and `track()` does nothing. */
  endpoint: string;
  environment: TelemetryEnvelope["environment"];
  /** Bearer token for the batches sent with fetch, or null. */
  getToken: () => string | null;
  batchSize: number;
  flushIntervalMs: number;
  /** In-memory queue cap (plan: 100 events / 256 KB). Beyond it the OLDEST events are dropped. */
  maxQueued: number;
  maxQueuedBytes: number;
  /** Most events in one request (the receiver refuses more than 100). */
  maxBatchEvents: number;
  /** After the first failure, how many more times the same batch is sent before it is dropped. */
  maxRetries: number;
  baseBackoffMs: number;
  maxBackoffMs: number;
  /** A new analytic session after this much inactivity (plan, section 11). */
  sessionIdleMs: number;
}

export const DEFAULT_CONFIG: Omit<TelemetryConfig, "endpoint" | "environment" | "getToken"> = {
  batchSize: 20,
  flushIntervalMs: 10_000,
  maxQueued: 100,
  maxQueuedBytes: 256 * 1024,
  maxBatchEvents: 100,
  maxRetries: 3,
  baseBackoffMs: 1_000,
  maxBackoffMs: 30_000,
  sessionIdleMs: 30 * 60 * 1000,
};

const SESSION_KEY = "nexova.telemetry.session";

interface Session {
  id: string;
  lastActivity: number;
}

interface InFlight {
  events: TelemetryEnvelope[];
  attempt: number;
}

export class TelemetryService {
  private queue: TelemetryEnvelope[] = [];
  private inFlight: InFlight | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private timerDue = Infinity;
  private session: Session | null = null;
  private started = false;
  private detach: (() => void) | null = null;
  private readonly config: TelemetryConfig;
  /** Events thrown away because the queue was full or a batch ran out of attempts: for diagnosis, never sent. */
  droppedEvents = 0;

  constructor(config: Partial<TelemetryConfig> & Pick<TelemetryConfig, "endpoint" | "environment">) {
    this.config = { ...DEFAULT_CONFIG, getToken: () => null, ...config };
  }

  /** Off without an endpoint, on the server (no `window`), or when the browser asks not to be tracked. */
  get enabled(): boolean {
    if (!this.config.endpoint || typeof window === "undefined") return false;
    const nav = typeof navigator === "undefined" ? undefined : (navigator as Navigator & { globalPrivacyControl?: boolean });
    return !(nav?.doNotTrack === "1" || nav?.globalPrivacyControl === true);
  }

  get pending(): number {
    return this.queue.length + (this.inFlight?.events.length ?? 0);
  }

  /** The one entry point: capture `type` now. Never throws, never waits, never touches the network itself. */
  track<T extends TelemetryEventType>(type: T, properties: TelemetryEvents[T], options: TrackOptions = {}): void {
    if (!this.enabled) return;
    try {
      this.startSafely();
      const event: TelemetryEnvelope<T> = {
        eventId: uuidV4(),
        event_type: type,
        schemaVersion: SCHEMA_VERSION,
        timestamp: new Date().toISOString(),
        userId: null,
        sessionId: this.sessionId(),
        requestId: options.requestId ?? uuidV4(),
        environment: this.config.environment,
        source: "backoffice",
        properties,
      };
      this.queue.push(event);
      this.enforceBounds();
      this.schedule();
      if (SESSION_ENDING_EVENTS.has(type)) this.flushIdentityBound();
    } catch {
      /* analytics must never break the application */
    }
  }

  /** Sends what is queued now (used by tests and by the size trigger). Resolves when that batch is settled. */
  async flush(): Promise<void> {
    if (!this.enabled || this.inFlight || this.queue.length === 0) return;
    this.clearTimer();
    this.inFlight = { events: this.queue.splice(0, this.config.maxBatchEvents), attempt: 0 };
    await this.send();
  }

  /** Page hidden or closing: hand everything pending to the browser in a way that survives the unload. */
  flushOnExit(): void {
    if (!this.enabled) return;
    this.clearTimer();
    const events = [...(this.inFlight?.events ?? []), ...this.queue]; // a batch in flight may be cancelled: resend it
    this.queue = [];
    this.inFlight = null;
    if (events.length === 0) return;
    const needsIdentity = events.filter((event) => IDENTITY_BOUND_EVENTS.has(event.event_type));
    const anonymous = events.filter((event) => !IDENTITY_BOUND_EVENTS.has(event.event_type));
    if (needsIdentity.length > 0) this.sendWithKeepalive(needsIdentity);
    for (let i = 0; i < anonymous.length; i += this.config.batchSize) {
      this.beacon(anonymous.slice(i, i + this.config.batchSize));
    }
  }

  /**
   * The session is ending (the caller clears the token right after): send the events that need the user's identity now, in one
   * request with the token that still exists. Everything else keeps waiting for its own batch.
   */
  private flushIdentityBound(): void {
    const bound = this.queue.filter((event) => IDENTITY_BOUND_EVENTS.has(event.event_type));
    if (bound.length === 0) return;
    this.queue = this.queue.filter((event) => !IDENTITY_BOUND_EVENTS.has(event.event_type));
    this.sendWithKeepalive(bound);
  }

  /** A new analytic session (login, logout or change of user): from now on events carry a different `sessionId`. */
  rotateSession(): void {
    this.session = { id: uuidV4(), lastActivity: Date.now() };
    this.persistSession();
  }

  /** A listener that cannot be attached (an exotic environment) costs the exit flush, never the event being captured. */
  private startSafely(): void {
    try {
      this.start();
    } catch {
      /* the queue and the timer still work */
    }
  }

  /** Listens, once, for the page being hidden or closed. The first `track()` calls it; the service lives as long as the page. */
  start(): void {
    if (this.started || typeof window === "undefined" || typeof document === "undefined") return;
    this.started = true;
    const onVisibility = () => {
      if (document.visibilityState === "hidden") this.flushOnExit();
    };
    const onPageHide = () => this.flushOnExit();
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pagehide", onPageHide);
    this.detach = () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pagehide", onPageHide);
    };
  }

  /** Forgets everything queued, cancels timers and stops listening (for tests: the app never tears the service down). */
  reset(): void {
    this.detach?.();
    this.detach = null;
    this.started = false;
    this.clearTimer();
    this.queue = [];
    this.inFlight = null;
    this.droppedEvents = 0;
  }

  // ---- scheduling ----------------------------------------------------------------------------

  private schedule(): void {
    this.arm(this.queue.length >= this.config.batchSize ? 0 : this.config.flushIntervalMs);
  }

  /** One timer for the earliest deadline: the size trigger brings a flush planned for later forward, never delays it. */
  private arm(delay: number): void {
    if (this.inFlight) return; // the batch in flight reschedules the next flush when it settles
    const due = Date.now() + delay;
    if (this.timer && this.timerDue <= due) return;
    this.clearTimer();
    this.timerDue = due;
    this.timer = setTimeout(() => {
      this.timer = null;
      this.timerDue = Infinity;
      void this.flush();
    }, delay);
  }

  private clearTimer(): void {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    this.timerDue = Infinity;
  }

  private enforceBounds(): void {
    let bytes = this.queue.reduce((sum, event) => sum + JSON.stringify(event).length, 0);
    while (this.queue.length > 0 && (this.queue.length > this.config.maxQueued || bytes > this.config.maxQueuedBytes)) {
      const dropped = this.queue.shift()!;
      bytes -= JSON.stringify(dropped).length;
      this.droppedEvents += 1;
    }
  }

  // ---- delivery ------------------------------------------------------------------------------

  private async send(): Promise<void> {
    const batch = this.inFlight;
    if (!batch) return;
    let retry = false;
    try {
      const response = await fetch(this.config.endpoint, {
        method: "POST",
        headers: this.headers({ "Content-Type": "application/json" }),
        body: JSON.stringify({ events: batch.events }),
        keepalive: true,
      });
      if (response.ok) await this.reportRejections(response);
      else if (response.status === 429 || response.status >= 500) retry = true;
      else this.drop(batch, `batch refused with HTTP ${response.status}; dropped without retry`);
    } catch {
      retry = true; // offline, DNS, CORS, the API is down...
    }
    if (!retry) return this.settle();

    batch.attempt += 1; // failures so far: the first send plus the retries already made
    if (batch.attempt > this.config.maxRetries) {
      this.drop(batch, `batch dropped after ${batch.attempt} attempts (${this.config.maxRetries} retries)`);
      return this.settle();
    }
    const wait = Math.min(this.config.baseBackoffMs * 2 ** (batch.attempt - 1), this.config.maxBackoffMs);
    await new Promise<void>((resolve) => setTimeout(resolve, wait));
    if (this.inFlight === batch) await this.send(); // flushOnExit may have taken the batch meanwhile
  }

  private settle(): void {
    this.inFlight = null;
    if (this.queue.length > 0) this.schedule();
  }

  /** The receiver answers 200 even when it rejects some events; surface them (field and rule, never a value). */
  private async reportRejections(response: Response): Promise<void> {
    try {
      const body = (await response.json()) as { rejected?: { index: number; path: string; rule: string }[] };
      if (body.rejected && body.rejected.length > 0) {
        const summary = body.rejected.map((r) => `#${r.index} ${r.path} (${r.rule})`).join(", ");
        this.warn(`the receiver rejected ${body.rejected.length} event(s): ${summary}`);
      }
    } catch {
      /* an empty or non-JSON body is not an error */
    }
  }

  private sendWithKeepalive(events: TelemetryEnvelope[]): void {
    try {
      void fetch(this.config.endpoint, {
        method: "POST",
        headers: this.headers({ "Content-Type": "application/json" }),
        body: JSON.stringify({ events }),
        keepalive: true,
      }).catch(() => undefined);
    } catch {
      this.droppedEvents += events.length;
    }
  }

  private beacon(events: TelemetryEnvelope[]): void {
    if (events.length === 0) return;
    const body = JSON.stringify({ events });
    let queued = false;
    try {
      if (typeof navigator !== "undefined" && typeof navigator.sendBeacon === "function") {
        queued = navigator.sendBeacon(this.config.endpoint, new Blob([body], { type: "text/plain;charset=UTF-8" }));
      }
    } catch {
      queued = false;
    }
    if (!queued) this.sendWithKeepalive(events); // no beacon, or the browser refused it (too big, quota)
  }

  private headers(base: Record<string, string>): Record<string, string> {
    const token = this.config.getToken();
    return token ? { ...base, Authorization: `Bearer ${token}` } : base;
  }

  private drop(batch: InFlight, message: string): void {
    this.droppedEvents += batch.events.length;
    this.warn(message);
  }

  /** Development aid only: nothing is logged in production. Never includes event contents. */
  private warn(message: string): void {
    if (process.env.NODE_ENV !== "production") console.warn(`[telemetry] ${message}`);
  }

  // ---- analytic session ------------------------------------------------------------------------

  private sessionId(): string {
    const now = Date.now();
    this.session ??= this.readSession();
    if (!this.session || now - this.session.lastActivity > this.config.sessionIdleMs) {
      this.session = { id: uuidV4(), lastActivity: now };
    }
    this.session.lastActivity = now;
    this.persistSession();
    return this.session.id;
  }

  private readSession(): Session | null {
    try {
      const parsed = JSON.parse(sessionStorage.getItem(SESSION_KEY) ?? "null");
      return parsed && typeof parsed.id === "string" && typeof parsed.lastActivity === "number" ? parsed : null;
    } catch {
      return null; // storage blocked or corrupt: a session that lives in memory only
    }
  }

  private persistSession(): void {
    try {
      if (this.session) sessionStorage.setItem(SESSION_KEY, JSON.stringify(this.session));
    } catch {
      /* in-memory only */
    }
  }
}
