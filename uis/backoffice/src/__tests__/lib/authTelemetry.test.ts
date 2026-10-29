// The `reason` of the failure events (`lib/authTelemetry.ts`): from the HTTP status only, with the approved contract's values.
import { analysisFailureReason, loginFailureReason, registrationFailureReason } from "@/lib/authTelemetry";

describe("loginFailureReason", () => {
  it.each([[401, "invalid_credentials"], [403, "invalid_credentials"], [400, "invalid_request"], [422, "invalid_request"], [404, "invalid_request"], [429, "rate_limited"], [500, "internal_error"], [502, "internal_error"], [503, "internal_error"]])(
    "HTTP %i is %s",
    (status, reason) => expect(loginFailureReason(status)).toBe(reason),
  );
});

describe("registrationFailureReason", () => {
  it.each([[409, "unavailable"], [400, "invalid_request"], [422, "invalid_request"], [429, "rate_limited"], [500, "internal_error"]])(
    "HTTP %i is %s (an existing e-mail is 'unavailable', never named)",
    (status, reason) => expect(registrationFailureReason(status)).toBe(reason),
  );
});

describe("analysisFailureReason", () => {
  it.each([[413, "size_limit"], [408, "timeout"], [504, "timeout"], [400, "invalid_csv"], [415, "invalid_csv"], [422, "invalid_csv"], [500, "internal_error"], [503, "internal_error"]])(
    "HTTP %i is %s",
    (status, reason) => expect(analysisFailureReason(status)).toBe(reason),
  );
});
