/**
 * @jest-environment node
 */
// What the API client (`lib/api.ts`) reports to the telemetry: a session ended by a 401, a request that never got an
// answer, and how a structured `detail` ({ code, field, message }) becomes an ApiError. `track` is mocked.
//
// Layout shared by every frontend test file: HAPPY PATH, EDGE CASES, FAILURE MODES. Arrange / Act / Assert.
import {
  ApiError,
  analyzeIncidentsFile,
  changeIncidentStatus,
  createIncident,
  createSupplier,
  fetchMe,
  jsonRequest,
  login,
  register,
  setSupplierStatus,
  updateMyProfile,
  updateSupplierRate,
} from "@/lib/api";
import { track } from "@/lib/telemetry";
import { clearToken, getToken, setToken } from "@/lib/token";

jest.mock("@/lib/telemetry", () => ({ track: jest.fn() }));
const trackMock = jest.mocked(track);

class MemoryStorage {
  private items = new Map<string, string>();
  getItem(key: string) {
    return this.items.get(key) ?? null;
  }
  setItem(key: string, value: string) {
    this.items.set(key, String(value));
  }
  removeItem(key: string) {
    this.items.delete(key);
  }
}
const fetchMock = jest.fn();
beforeEach(() => {
  Object.defineProperty(globalThis, "localStorage", { value: new MemoryStorage(), configurable: true, writable: true });
  fetchMock.mockReset();
  globalThis.fetch = fetchMock as unknown as typeof fetch;
});
afterAll(() => clearToken());

const jsonResponse = (body: unknown, status = 200, statusText = "") =>
  new Response(JSON.stringify(body), { status, statusText, headers: { "Content-Type": "application/json" } });
const failWith = async (response: Response) => {
  fetchMock.mockResolvedValueOnce(response);
  return (await jsonRequest("/x").catch((e) => e)) as ApiError;
};

const calls = () => trackMock.mock.calls.map(([type, props]) => [type, props]);

describe("session_expired", () => {
  it("is reported when a 401 ends a session the user had", async () => {
    setToken("old.jwt");
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "Could not validate credentials" }, 401));
    await fetchMe().catch(() => undefined);
    expect(trackMock).toHaveBeenCalledWith("session_expired", { reason: "unauthorized_response" });
  });

  it("is not reported for a 401 when nobody was logged in (the denial still is)", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "Not authenticated" }, 401));
    await fetchMe().catch(() => undefined);
    expect(calls()).toEqual([["authorization_denied", { route_id: "auth_me", status_code: 401 }]]);
  });

  it("is not reported for a failed login: wrong credentials are not an expired session", async () => {
    setToken("old.jwt");
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "Incorrect email or password" }, 401));
    await login("a@b.c", "x").catch(() => undefined);
    expect(trackMock.mock.calls.map(([type]) => type)).toEqual(["login_attempted", "login_failed"]);
  });
});

describe("network_failed", () => {
  it("is reported with the component the request belongs to, and the call still fails as before", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(jsonRequest("/api/inventory/products")).rejects.toMatchObject({ status: 0 });
    await expect(jsonRequest("/api/suppliers")).rejects.toMatchObject({ status: 0 });
    expect(trackMock.mock.calls).toEqual([
      ["application_error_occurred", { error_code: "network_failed", component: "inventory" }],
      ["application_error_occurred", { error_code: "network_failed", component: "suppliers" }],
    ]);
  });

  it("is not reported for a path that belongs to no component of the contract", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(jsonRequest("/somewhere/else")).rejects.toMatchObject({ status: 0 });
    expect(trackMock).not.toHaveBeenCalled();
  });
});

describe("structured error details", () => {
  it("keeps the code, the field and the message of {code, field, message}", async () => {
    const error = await failWith(jsonResponse({ detail: { code: "direct_stock_write_forbidden", field: "current_stock", message: "Stock cannot be written directly" } }, 422));
    expect(error).toMatchObject({ status: 422, message: "Stock cannot be written directly", code: "direct_stock_write_forbidden", field: "current_stock", fieldErrors: {} });
  });

  it("falls back to the status text when the detail has a code but no message, and ignores a non-string field", async () => {
    const error = await failWith(jsonResponse({ detail: { code: "x", field: 7 } }, 409, "Conflict"));
    expect(error).toMatchObject({ message: "Conflict", code: "x", field: undefined });
  });

  it("leaves a plain string detail and a validation list as they were, with no code", async () => {
    expect(await failWith(jsonResponse({ detail: "Nope" }, 400))).toMatchObject({ message: "Nope", code: undefined });
    expect(await failWith(jsonResponse({ detail: [{ loc: ["body", "quantity"], msg: "bad" }] }, 422))).toMatchObject({ fieldErrors: { quantity: "bad" }, code: undefined });
  });

  it("does not take an object detail without a string code for a structured one", async () => {
    const error = await failWith(jsonResponse({ detail: { message: "x" } }, 500, "Server Error"));
    expect(error).toMatchObject({ message: "Server Error", code: undefined });
  });
});

// ---- authentication ------------------------------------------------------------------------------

const types = () => trackMock.mock.calls.map(([type]) => type);
const at = (type: string) => trackMock.mock.calls.find(([t]) => t === type)?.[1];

describe("login telemetry", () => {
  const EMAIL = "maria.lopez@example.com";
  const PASSWORD = "correct horse battery";

  it("a successful login reports the attempt, then the success, with a duration and never what was typed", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ access_token: "jwt.value", token_type: "bearer" }));
    await login(EMAIL, PASSWORD);
    expect(types()).toEqual(["login_attempted", "login_succeeded"]);
    expect(at("login_attempted")).toEqual({ method: "password", duration_ms: 0 });
    expect(at("login_succeeded")).toEqual({ method: "password", duration_ms: expect.any(Number) });
    expect(JSON.stringify(trackMock.mock.calls)).not.toMatch(/maria|correct horse|jwt\.value/);
  });

  it("the success is reported BEFORE the token is stored, so it belongs to the session of the attempt, not the next one", async () => {
    clearToken();
    let tokenWhenReported: string | null | undefined;
    trackMock.mockImplementation((type) => {
      if (type === "login_succeeded") tokenWhenReported = getToken();
    });
    fetchMock.mockResolvedValueOnce(jsonResponse({ access_token: "jwt.value" }));
    await login(EMAIL, PASSWORD);
    expect(tokenWhenReported).toBeNull();
    expect(getToken()).toBe("jwt.value");
  });

  it.each([
    [401, "invalid_credentials"],
    [422, "invalid_request"],
    [429, "rate_limited"],
    [500, "internal_error"],
  ])("HTTP %i is login_failed with the reason %s, and nothing about the credentials", async (status, reason) => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: `bad ${EMAIL}` }, status));
    await expect(login(EMAIL, PASSWORD)).rejects.toBeInstanceOf(ApiError);
    expect(types()).toEqual(["login_attempted", "login_failed"]);
    expect(at("login_failed")).toEqual({ method: "password", duration_ms: expect.any(Number), reason });
    expect(JSON.stringify(trackMock.mock.calls)).not.toMatch(/maria|correct horse|bad /);
  });

  it("a server that answers without a token is an internal error, not a success", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ token_type: "bearer" }));
    await expect(login(EMAIL, PASSWORD)).rejects.toMatchObject({ status: 502 });
    expect(types()).toEqual(["login_attempted", "login_failed"]);
    expect(at("login_failed")).toMatchObject({ reason: "internal_error" });
  });

  it("no answer at all is a network error of the auth component, not a login failure (it would skew the API's failure rate)", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    await expect(login(EMAIL, PASSWORD)).rejects.toBeInstanceOf(TypeError);
    expect(trackMock.mock.calls).toEqual([
      ["login_attempted", { method: "password", duration_ms: 0 }],
      ["application_error_occurred", { error_code: "network_failed", component: "auth" }],
    ]);
  });
});

describe("registration telemetry", () => {
  const payload = { email: "ana@example.com", password: "s3cret-pass", name: "Ana Pérez" } as Parameters<typeof register>[0];

  it("a created account reports registration_completed with its duration only", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: "x", email: "ana@example.com" }, 201));
    await register(payload);
    expect(trackMock.mock.calls).toEqual([["registration_completed", { method: "password", duration_ms: expect.any(Number) }]]);
  });

  it.each([
    [409, "unavailable"],
    [422, "invalid_request"],
    [429, "rate_limited"],
    [500, "internal_error"],
  ])("HTTP %i is registration_failed with %s, never naming the e-mail or the name", async (status, reason) => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "ana@example.com is taken" }, status));
    await expect(register(payload)).rejects.toBeInstanceOf(ApiError);
    expect(trackMock.mock.calls).toEqual([["registration_failed", { reason }]]);
  });

  it("no answer is a network error of the auth component", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("offline"));
    await expect(register(payload)).rejects.toBeInstanceOf(TypeError);
    expect(trackMock.mock.calls).toEqual([["application_error_occurred", { error_code: "network_failed", component: "auth" }]]);
  });
});

describe("profile_updated", () => {
  it("reports how many fields changed, not which ones or their values", async () => {
    setToken("jwt");
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: "p" }));
    await updateMyProfile({ name: "María López", phone: "+34 600 000 000" });
    expect(trackMock.mock.calls).toEqual([["profile_updated", { changed_field_count: 2 }]]);
  });

  it("reports nothing for an empty update or a failed one", async () => {
    setToken("jwt");
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: "p" }));
    await updateMyProfile({});
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "no" }, 422));
    await updateMyProfile({ name: "x" }).catch(() => undefined);
    expect(types()).not.toContain("profile_updated");
  });
});

describe("authorization_denied", () => {
  it.each([
    ["/api/inventory/orders/outbound", 403, "inventory_outbound"],
    ["/api/suppliers", 401, "suppliers"],
    ["/api/incidents/analyze", 403, "incident_analysis"],
    ["/auth/me", 401, "auth_me"],
  ])("a %s answered %i is reported by its route template", async (path, status, route_id) => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "no" }, status));
    await jsonRequest(path).catch(() => undefined);
    expect(trackMock).toHaveBeenCalledWith("authorization_denied", { route_id, status_code: status });
  });

  it("is not reported for other failures", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "no" }, 404));
    await jsonRequest("/api/suppliers").catch(() => undefined);
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "no" }, 500));
    await jsonRequest("/api/suppliers").catch(() => undefined);
    expect(trackMock).not.toHaveBeenCalled();
  });

  it("a 401 with a session reports the denial and the expired session, in that order", async () => {
    setToken("old.jwt");
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "x" }, 401));
    await jsonRequest("/api/suppliers").catch(() => undefined);
    expect(types()).toEqual(["authorization_denied", "session_expired"]);
  });
});

// ---- suppliers, incidents, analysis --------------------------------------------------------------

describe("supplier telemetry", () => {
  const supplier = { id: 7, name: "LinkedIn Talent Solutions", monthly_rate: 1200 };

  it("a created supplier is reported by its id only", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(supplier, 201));
    const created = await createSupplier({ name: "LinkedIn Talent Solutions" } as Parameters<typeof createSupplier>[0]);
    expect(created).toEqual(supplier);
    expect(trackMock.mock.calls).toEqual([["supplier_created", { supplier_id: "7" }]]);
  });

  it("a new rate and a status change are supplier_updated", async () => {
    fetchMock.mockImplementation(async () => jsonResponse(supplier)); // a fresh Response per call: a body is read once
    await updateSupplierRate(7, 1500);
    await setSupplierStatus(7, "suspended");
    expect(trackMock.mock.calls).toEqual([
      ["supplier_updated", { supplier_id: "7" }],
      ["supplier_updated", { supplier_id: "7" }],
    ]);
    expect(JSON.stringify(trackMock.mock.calls)).not.toMatch(/LinkedIn|1500|suspended/);
  });

  it("nothing is reported when the change failed", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "no" }, 422));
    await createSupplier({} as Parameters<typeof createSupplier>[0]).catch(() => undefined);
    expect(trackMock).not.toHaveBeenCalled();
  });
});

describe("incident telemetry", () => {
  const incident = (history: object[]) => ({ id: "INC-42", title: "Impresora", customer_email: "c@example.com", status: "resolved", history });
  const fields = { title: "Impresora rota" } as Parameters<typeof createIncident>[0];

  it("a created incident is reported by its id, never its title, description or customer", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(incident([]), 201));
    await createIncident(fields);
    expect(trackMock.mock.calls).toEqual([["incident_created", { incident_id: "INC-42" }]]);
  });

  it("a status change reports the transition the API recorded, from the last status_changed entry of the history", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        incident([
          { kind: "created", from_status: null, to_status: "open" },
          { kind: "status_changed", from_status: "open", to_status: "in_progress" },
          { kind: "edited", from_status: null, to_status: null },
          { kind: "status_changed", from_status: "in_progress", to_status: "resolved" },
        ]),
      ),
    );
    await changeIncidentStatus("INC-42", { status: "resolved", satisfaction_score: 5 });
    expect(trackMock.mock.calls).toEqual([["incident_status_changed", { incident_id: "INC-42", from_status: "in_progress", to_status: "resolved" }]]);
  });

  it.each([
    ["no history", undefined],
    ["no status change in it", [{ kind: "created", from_status: null, to_status: "open" }]],
    ["a move to the same status", [{ kind: "status_changed", from_status: "open", to_status: "open" }]],
    ["a move with no origin", [{ kind: "status_changed", from_status: null, to_status: "open" }]],
  ])("reports nothing with %s, and the change itself still succeeds", async (_name, history) => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ ...incident([]), history }));
    await expect(changeIncidentStatus("INC-42", { status: "open" })).resolves.toMatchObject({ id: "INC-42" });
    expect(trackMock).not.toHaveBeenCalled();
  });

  it("an id that could be a name is dropped, not sent", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ ...incident([]), id: "María López" }, 201));
    await createIncident(fields);
    expect(trackMock).not.toHaveBeenCalled();
  });
});

describe("incident analysis telemetry", () => {
  const file = () => new File(["a,b\n1,2"], "clientes-maria-lopez.csv", { type: "text/csv" });
  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

  it("a finished analysis reports an id made for the attempt, the row count and the duration, never the file", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ total_records: 250, valid_records: 240 }));
    await analyzeIncidentsFile(file());
    expect(trackMock.mock.calls).toEqual([["incident_analysis_completed", { analysis_id: expect.stringMatching(UUID), row_count: 250, duration_ms: expect.any(Number) }]]);
    expect(JSON.stringify(trackMock.mock.calls)).not.toMatch(/maria|clientes|csv/i);
  });

  it.each([
    [413, "size_limit"],
    [422, "invalid_csv"],
    [504, "timeout"],
    [500, "internal_error"],
  ])("HTTP %i is incident_analysis_failed with %s", async (status, reason) => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "x" }, status));
    await expect(analyzeIncidentsFile(file())).rejects.toBeInstanceOf(ApiError);
    expect(trackMock.mock.calls).toEqual([["incident_analysis_failed", { analysis_id: expect.stringMatching(UUID), reason }]]);
  });

  it("no answer is the network's failure, not an analysis failure", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("offline"));
    await expect(analyzeIncidentsFile(file())).rejects.toMatchObject({ status: 0 });
    expect(trackMock.mock.calls).toEqual([["application_error_occurred", { error_code: "network_failed", component: "incidents" }]]);
  });

  it("each attempt has its own id", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ total_records: 1 }));
    await analyzeIncidentsFile(file());
    await analyzeIncidentsFile(file());
    const [a, b] = trackMock.mock.calls.map(([, props]) => (props as { analysis_id: string }).analysis_id);
    expect(a).not.toBe(b);
  });
});
