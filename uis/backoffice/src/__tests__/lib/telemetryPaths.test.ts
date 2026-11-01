// Which section / component of the contract a URL belongs to (`lib/telemetry/paths.ts`). Closed lists: what matches
// none is not reported rather than mislabelled.
import { componentForPath, routeIdForPath, sectionForPath } from "@/lib/telemetry/paths";

describe("sectionForPath", () => {
  it.each([
    ["/", "home"],
    ["/inventory", "inventory"],
    ["/inventory/products", "inventory"],
    ["/inventory/orders/inbound", "inbound"],
    ["/inventory/orders/outbound", "outbound"],
    ["/inventory/orders", "orders"],
    ["/suppliers", "suppliers"],
    ["/incidents", "incidents"],
    ["/incidents/INC-12", "incidents"],
    ["/incidents/analysis", "analysis"],
    ["/account/profile", "profile"],
    ["/login", "login"],
    ["/register", "register"],
  ])("%s is the %s section", (path, section) => {
    expect(sectionForPath(path)).toBe(section);
  });
  it("ignores a trailing slash", () => {
    expect(sectionForPath("/inventory/orders/inbound/")).toBe("inbound");
  });
  it.each(["/nope", "/inventory/orders/inbound/extra", "/admin"])("%s is no section", (path) => {
    expect(sectionForPath(path)).toBeNull();
  });
});

describe("componentForPath", () => {
  it.each([
    ["/api/inventory/products", "inventory"],
    ["/inventory/orders", "inventory"],
    ["http://localhost:8000/inventory/products?x=1", "inventory"],
    ["/api/suppliers", "suppliers"],
    ["/suppliers/3", "suppliers"],
    ["/api/incidents", "incidents"],
    ["/auth/me", "auth"],
    ["/auth/login", "auth"],
    ["/login", "auth"],
    ["/users", "auth"],
    ["/profiles/me", "profile"],
    ["/account/profile", "profile"],
  ])("%s belongs to %s", (path, component) => {
    expect(componentForPath(path)).toBe(component);
  });
  it("is null for the rest of the shell: the contract has no component for it", () => {
    expect(componentForPath("/")).toBeNull();
    expect(componentForPath("/something")).toBeNull();
  });
});

describe("routeIdForPath", () => {
  it.each([
    ["/auth/login", "auth_login"],
    ["/auth/me", "auth_me"],
    ["/users", "users"],
    ["/users/directory", "users"],
    ["/users/5f1c4d2e-0000-4000-8000-000000000001", "users"],
    ["/profiles/me", "profiles"],
    ["/api/inventory/products", "inventory_assets"],
    ["/api/inventory/products/12", "inventory_assets"],
    ["/api/inventory/orders/inbound", "inventory_inbound"],
    ["/api/inventory/orders/outbound", "inventory_outbound"],
    ["/api/inventory/orders", "inventory_orders"],
    ["http://localhost:8000/inventory/orders/outbound", "inventory_outbound"],
    ["/api/suppliers", "suppliers"],
    ["/api/suppliers/3/rate", "suppliers"],
    ["/api/incidents", "incidents"],
    ["/api/incidents/INC-7/status", "incidents"],
    ["/api/incidents/analyze", "incident_analysis"],
    ["/api/incidents/results/export", "incident_analysis"],
    ["/health", "health"],
  ])("%s is %s", (path, id) => expect(routeIdForPath(path)).toBe(id));

  it("is `unmatched` for anything else, and never carries the real path (a template, not the id)", () => {
    expect(routeIdForPath("/nope/12")).toBe("unmatched");
    expect(routeIdForPath("")).toBe("unmatched");
    expect(routeIdForPath("/api/inventory/products/12")).not.toContain("12");
  });
});
