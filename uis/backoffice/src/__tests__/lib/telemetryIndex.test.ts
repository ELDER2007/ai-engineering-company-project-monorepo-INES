// The door to the telemetry (`lib/telemetry/index.ts`): configuration from the build-time env vars and `track()`
// delegating to the one service.
const load = (env: Record<string, string | undefined>) => {
  const saved = { ...process.env };
  Object.assign(process.env, env);
  for (const [key, value] of Object.entries(env)) if (value === undefined) delete process.env[key];
  let mod!: { telemetry: typeof import("@/lib/telemetry/instance").telemetry; track: typeof import("@/lib/telemetry").track };
  jest.isolateModules(() => {
    mod = { ...require("@/lib/telemetry/instance"), ...require("@/lib/telemetry") };
  });
  process.env = saved;
  return mod;
};

describe("lib/telemetry", () => {
  it("is off without NEXT_PUBLIC_TELEMETRY_ENDPOINT: track() is a harmless no-op", () => {
    const { telemetry, track } = load({ NEXT_PUBLIC_TELEMETRY_ENDPOINT: undefined });
    expect(telemetry.enabled).toBe(false);
    track("section_viewed", { section: "home", locale: "es" });
    expect(telemetry.pending).toBe(0);
  });

  it("is on with an endpoint, and track() puts the event in the one service's queue", () => {
    const { telemetry, track } = load({ NEXT_PUBLIC_TELEMETRY_ENDPOINT: "http://api.test/telemetry/events" });
    expect(telemetry.enabled).toBe(true);
    track("section_viewed", { section: "home", locale: "es" });
    track("logout_completed", { reason: "user_action" }, { requestId: "11111111-1111-4111-8111-111111111111" });
    expect(telemetry.pending).toBe(2);
    telemetry.reset();
  });

  it.each([
    ["staging", "production", "staging"],
    ["bogus", "production", "production"],
    [undefined, "production", "production"],
    [undefined, "test", "test"],
    [undefined, "development", "development"],
  ])("environment: declared %p with NODE_ENV %p is %p", (declared, nodeEnv, expected) => {
    const { telemetry, track } = load({
      NEXT_PUBLIC_TELEMETRY_ENDPOINT: "http://api.test/telemetry/events",
      NEXT_PUBLIC_TELEMETRY_ENVIRONMENT: declared,
      NODE_ENV: nodeEnv,
    });
    track("section_viewed", { section: "home", locale: "es" });
    telemetry.flushOnExit = telemetry.flushOnExit.bind(telemetry);
    const beacon = jest.fn().mockReturnValue(true);
    Object.defineProperty(navigator, "sendBeacon", { value: beacon, configurable: true });
    Object.defineProperty(navigator, "doNotTrack", { value: null, configurable: true });
    class FakeBlob { constructor(public parts: string[]) {} }
    globalThis.Blob = FakeBlob as unknown as typeof Blob;
    telemetry.flushOnExit();
    expect(JSON.parse((beacon.mock.calls[0][1] as FakeBlob).parts[0]).events[0].environment).toBe(expected);
  });

  it("its public surface is track() and nothing else", () => {
    jest.isolateModules(() => {
      const exported = Object.keys(require("@/lib/telemetry")).filter((key) => key !== "__esModule");
      expect(exported).toEqual(["track"]);
    });
  });

  describe("the analytic session follows the login", () => {
    const sessions = () => {
      const beacon = jest.fn().mockReturnValue(true);
      Object.defineProperty(navigator, "sendBeacon", { value: beacon, configurable: true });
      class FakeBlob { constructor(public parts: string[]) {} }
      globalThis.Blob = FakeBlob as unknown as typeof Blob;
      return { beacon, ids: () => beacon.mock.calls.flatMap(([, blob]) => JSON.parse((blob as FakeBlob).parts[0]).events.map((e: { sessionId: string }) => e.sessionId)) };
    };

    it("starts a new session when a token is set (login) and again when it is cleared (logout), with no caller saying so", () => {
      sessionStorage.clear();
      Object.defineProperty(navigator, "doNotTrack", { value: null, configurable: true });
      const env = { NEXT_PUBLIC_TELEMETRY_ENDPOINT: "http://api.test/telemetry/events" };
      const saved = { ...process.env };
      Object.assign(process.env, env);
      let mod!: { telemetry: { flushOnExit: () => void; reset: () => void }; token: typeof import("@/lib/token"); track: typeof import("@/lib/telemetry").track };
      jest.isolateModules(() => {
        mod = { ...require("@/lib/telemetry/instance"), token: require("@/lib/token"), track: require("@/lib/telemetry").track };
      });
      process.env = saved;
      const { beacon, ids } = sessions();

      mod.track("section_viewed", { section: "login", locale: "es" });
      mod.token.setToken("jwt"); // login
      mod.track("section_viewed", { section: "home", locale: "es" });
      mod.track("logout_completed", { reason: "user_action" });
      mod.token.clearToken(); // logout
      mod.track("section_viewed", { section: "login", locale: "es" });
      mod.telemetry.flushOnExit();

      expect(beacon).toHaveBeenCalled();
      const [beforeLogin, loggedIn, loggedInToo, afterLogout] = ids();
      expect(loggedIn).toBe(loggedInToo); // the logout event belongs to the session that is ending
      expect(new Set([beforeLogin, loggedIn, afterLogout]).size).toBe(3);
      mod.token.clearToken();
    });
  });
});
