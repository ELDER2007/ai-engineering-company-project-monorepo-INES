// Which section / component of the contract a URL path of the backoffice belongs to. Closed lists: the contract
// has no free-text field, so anything that cannot be named from them is not reported (never invented).
import type { Component, RouteId, Section } from "./events";

/** The logical view for a page path (`usePathname()`), or null for a path that is not a view of the contract. */
export function sectionForPath(pathname: string): Section | null {
  const path = pathname.replace(/\/+$/, "") || "/";
  if (path === "/") return "home";
  if (path === "/inventory" || path === "/inventory/products") return "inventory";
  if (path === "/inventory/orders/inbound") return "inbound";
  if (path === "/inventory/orders/outbound") return "outbound";
  if (path === "/inventory/orders") return "orders";
  if (path === "/suppliers") return "suppliers";
  if (path === "/incidents/analysis") return "analysis";
  if (path === "/incidents" || path.startsWith("/incidents/")) return "incidents";
  if (path === "/account/profile") return "profile";
  if (path === "/login") return "login";
  if (path === "/register") return "register";
  return null;
}

/** The component an error belongs to, from a page path or an API URL/path; null when it matches none. */
export function componentForPath(pathOrUrl: string): Component | null {
  let path = pathOrUrl;
  try {
    path = new URL(pathOrUrl, "http://local").pathname;
  } catch {
    /* keep the raw text */
  }
  if (/^\/(api\/)?inventory(\/|$)/.test(path)) return "inventory";
  if (/^\/(api\/)?suppliers(\/|$)/.test(path)) return "suppliers";
  if (/^\/(api\/)?incidents(\/|$)/.test(path)) return "incidents";
  if (/^\/(auth|login|register)(\/|$)/.test(path) || path === "/users") return "auth";
  if (/^\/(profiles|account|users)(\/|$)/.test(path)) return "profile";
  return null;
}

/**
 * The contract's `route_id` of an API call: the route template, never the path with a real id in it (plan, section 10). The
 * detail and the list of a resource share one id, so their latencies cannot be told apart until the map is versioned.
 */
export function routeIdForPath(pathOrUrl: string): RouteId {
  let path = pathOrUrl;
  try {
    path = new URL(pathOrUrl, "http://local").pathname;
  } catch {
    /* keep the raw text */
  }
  if (path === "/auth/login") return "auth_login";
  if (path === "/auth/me") return "auth_me";
  if (/^\/users(\/|$)/.test(path)) return "users";
  if (/^\/profiles(\/|$)/.test(path)) return "profiles";
  if (/^\/(api\/)?inventory\/orders\/inbound$/.test(path)) return "inventory_inbound";
  if (/^\/(api\/)?inventory\/orders\/outbound$/.test(path)) return "inventory_outbound";
  if (/^\/(api\/)?inventory\/orders$/.test(path)) return "inventory_orders";
  if (/^\/(api\/)?inventory\/products(\/|$)/.test(path)) return "inventory_assets";
  if (/^\/(api\/)?suppliers(\/|$)/.test(path)) return "suppliers";
  if (/^\/api\/incidents\/(analyze|results)(\/|$)/.test(path)) return "incident_analysis";
  if (/^\/(api\/)?incidents(\/|$)/.test(path)) return "incidents";
  if (path === "/health") return "health";
  return "unmatched";
}
