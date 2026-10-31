// The one TelemetryService of the app, configured from the build-time env vars, and the only thing that wires it to the rest of
// the app. Not part of the public surface: the app imports `track` from "./index"; tests import the instance from here.
import { getToken, onTokenChange } from "../token";
import type { TelemetryEnvelope } from "./events";
import { TelemetryService } from "./TelemetryService";

// Referenced literally so Next.js inlines it at build time (a computed `process.env[name]` would not be).
const ENDPOINT = process.env.NEXT_PUBLIC_TELEMETRY_ENDPOINT ?? "";

function environment(): TelemetryEnvelope["environment"] {
  const declared = process.env.NEXT_PUBLIC_TELEMETRY_ENVIRONMENT;
  if (declared === "development" || declared === "test" || declared === "staging" || declared === "production") return declared;
  return process.env.NODE_ENV === "production" ? "production" : process.env.NODE_ENV === "test" ? "test" : "development";
}

export const telemetry = new TelemetryService({ endpoint: ENDPOINT, environment: environment(), getToken });

// A new analytic session at each login and each logout (the token is set or cleared; also when a 401 ends the session), so no
// caller has to say so. The events captured before the change keep the old session: the listener runs after them.
if (typeof window !== "undefined") onTokenChange(() => telemetry.rotateSession());
