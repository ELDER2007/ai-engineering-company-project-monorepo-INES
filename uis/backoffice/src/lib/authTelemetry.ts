// How an API refusal becomes the `reason` of a telemetry event. Pure: from the HTTP status only, so what the user typed (an e-mail,
// a password, a file name) cannot reach an event. The values are the approved contract's enums (docs/telemetry/event-schemas.json);
// a reason the contract has no value for is not invented: a request that never got an answer is `application_error_occurred`
// (`network_failed`), not a login failure.
import type { TelemetryEvents } from "./telemetry/events";

type LoginReason = TelemetryEvents["login_failed"]["reason"];
type RegistrationReason = TelemetryEvents["registration_failed"]["reason"];
type AnalysisReason = TelemetryEvents["incident_analysis_failed"]["reason"];

/** 401 covers a wrong password, an unknown e-mail and a deactivated account alike: the API does not tell them apart, nor do we. */
export function loginFailureReason(status: number): LoginReason {
  if (status === 429) return "rate_limited";
  if (status >= 500) return "internal_error";
  if (status === 401 || status === 403) return "invalid_credentials";
  return "invalid_request";
}

/** 409 is an e-mail that is already registered; the event says "unavailable" and never which e-mail (it would reveal accounts). */
export function registrationFailureReason(status: number): RegistrationReason {
  if (status === 409) return "unavailable";
  if (status === 429) return "rate_limited";
  if (status >= 500) return "internal_error";
  return "invalid_request";
}

export function analysisFailureReason(status: number): AnalysisReason {
  if (status === 413) return "size_limit";
  if (status === 408 || status === 504) return "timeout";
  if (status >= 500) return "internal_error";
  return "invalid_csv";
}
