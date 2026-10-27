// The only public function of the telemetry: `track()`. Components, hooks and the API client call it and nothing else; there is no
// other way to put an event in the queue (the queue and the service are private to this folder). Nobody configures, starts, flushes
// or rotates the session: the service does it by itself (see TelemetryService.ts and instance.ts).
import type { TelemetryEventType, TelemetryEvents, TrackOptions } from "./events";
import { telemetry } from "./instance";

/**
 * Captures `eventType` at the moment it happens. The service adds eventId, sessionId, timestamp, schemaVersion, requestId and
 * environment (`userId` comes from the verified session, on the server); callers pass only what the event is.
 * `properties` is checked against the approved contract at compile time (lib/telemetry/events.ts), so an undeclared key does not
 * compile. `options.requestId` exists only to correlate with the HTTP request that caused the event (`X-Request-ID`).
 * Safe to call anywhere: it does nothing without an endpoint, on the server, or when the browser sends Do Not Track, and it
 * never throws or waits.
 */
export function track<T extends TelemetryEventType>(eventType: T, properties: TelemetryEvents[T], options?: TrackOptions): void {
  telemetry.track(eventType, properties, options);
}

export type { TelemetryEventType, TelemetryEvents, TrackOptions } from "./events";
