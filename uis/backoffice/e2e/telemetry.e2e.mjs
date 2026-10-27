// End-to-end check of the frontend event capture (needs Chromium: npx playwright install chromium).
// Prerequisites: API on :8000 with an active user and the inventory seed (`uv run seed-inventory`), the backoffice on
// :5174 (npm run dev) with NEXT_PUBLIC_TELEMETRY_ENDPOINT=http://localhost:8000/telemetry/events in .env.local.
// Run from uis/backoffice:  E2E_EMAIL=you@example.com E2E_PASSWORD=... npm run e2e:telemetry
// WRITES to the inventory: it registers three setup entries, one entry and one exit for NXV-IT-001 (run it on a
// development database, never on Supabase). What it proves, watching the real requests the browser makes:
//   - events leave in batches (never one request per event) to the endpoint of the env var, and the receiver
//     accepts every one of them against the approved JSON Schema (accepted === received, rejected === []);
//   - the five mandatory events of the briefing, with the contract's properties, from real orders;
//   - one requestId links the flow steps, the HTTP call and the events of a submission;
//   - the flow story, the page views, the section loads, a blocked form, and logout;
//   - nothing personal (email, supplier name, token) is in any event.
import { chromium } from "playwright";
const APP = process.env.E2E_APP_URL ?? "http://localhost:5174";
const ENDPOINT = process.env.E2E_TELEMETRY_ENDPOINT ?? "http://localhost:8000/telemetry/events";
const API = process.env.E2E_API_URL ?? "http://localhost:8000";
const EMAIL = process.env.E2E_EMAIL;
const PASSWORD = process.env.E2E_PASSWORD;
if (!EMAIL || !PASSWORD) {
  console.error("Set E2E_EMAIL and E2E_PASSWORD to an active API user (see the header of this file).");
  process.exit(2);
}
const SUPPLIER = "TechDistrib Valencia S.L."; // the supplier of the seeded entries of NXV-IT-001: its baseline
const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1300, height: 900 } })).newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => m.type() === "error" && !/status of (401|400)\b/.test(m.text()) && errors.push(m.text()));
let fails = 0;
const ok = (c, msg) => { if (!c) fails++; console.log(`${c ? "PASS" : "FAIL"}  ${msg}`); };

// every batch the browser posts to the receiver, with what the receiver answered
const batches = [];
page.on("response", async (response) => {
  const request = response.request();
  if (request.url() !== ENDPOINT || request.method() !== "POST") return;
  batches.push({ at: Date.now(), status: response.status(), events: JSON.parse(request.postData()).events, ack: await response.json().catch(() => null) });
});
const events = () => batches.flatMap((b) => b.events);
const of = (type) => events().filter((e) => e.event_type === type);
const waitForEvent = (type, ms = 30000) => page.waitForFunction(() => true).then(async () => {
  const start = Date.now();
  while (Date.now() - start < ms) { if (of(type).length > 0) return true; await page.waitForTimeout(250); }
  return false;
});

// 1. login: the login page is a section view with no user
await page.goto(`${APP}/login`);
await page.getByLabel("Email").fill(EMAIL);
await page.getByLabel("Contraseña").fill(PASSWORD);
await page.getByRole("button", { name: "Entrar" }).click();
await page.waitForURL(`${APP}/`);

// setup: five prior entries of NXV-IT-001 from the same supplier give the 5-entry cost baseline (2 seeded + 3 here)
const token = await page.evaluate(() => localStorage.getItem("nexova.token"));
const headers = { "Content-Type": "application/json", Authorization: `Bearer ${token}` };
for (let i = 0; i < 3; i += 1) {
  const r = await fetch(`${API}/inventory/orders/inbound`, { method: "POST", headers, body: JSON.stringify({ asset_id: 1, quantity: 1, supplier: SUPPLIER, office: "Valencia", unit_cost_minor: 86000 }) });
  if (!r.ok) throw new Error(`setup entry failed: ${r.status}`);
}

// 2. an entry at ~40 % above its baseline: inbound_order_created + kit_cost_variance_detected
await page.getByRole("link", { name: "Entrada de activos" }).first().click();
await page.waitForURL("**/inventory/orders/inbound");
await page.getByLabel("Activo").selectOption("1");
await page.getByLabel("Cantidad").fill("2");
await page.getByLabel(/Coste unitario/).fill("1200,00");
await page.getByLabel("Proveedor").fill(SUPPLIER);
await page.getByRole("button", { name: "Registrar entrada" }).click();
await page.getByRole("status").waitFor();

// 3. an exit that leaves 1 unit, under the asset's minimum of 2: outbound_order_created + stock_threshold_triggered
await page.getByRole("link", { name: "Salida de activos" }).first().click();
await page.waitForURL("**/inventory/orders/outbound");
await page.getByLabel("Activo").selectOption("1");
await page.getByTestId("available-stock").waitFor();
const stockBefore = Number((await page.getByTestId("available-stock").textContent()).match(/\d+/)[0]);
await page.getByLabel("Tipo de salida").selectOption("consumption");
await page.getByLabel("Cantidad").fill(String(stockBefore - 1));
await page.getByRole("button", { name: "Registrar salida" }).click();
await page.getByRole("status").waitFor();

// 4. a blocked submit (nothing filled), then logout
await page.getByRole("link", { name: "Entrada de activos" }).first().click();
await page.waitForURL("**/inventory/orders/inbound");
await page.getByRole("button", { name: "Registrar entrada" }).click();
await page.getByText("Indica el coste unitario").waitFor();
await page.getByRole("button", { name: "Cerrar sesión" }).click();
await page.waitForURL("**/login**");

for (const type of ["kit_cost_variance_detected", "stock_threshold_triggered", "form_validation_failed", "logout_completed"]) {
  ok(await waitForEvent(type), `llega ${type} al receptor`);
}
await page.waitForTimeout(1500); // the last batch leaves 10 s after its first event (or at 20 events)

// ---- what the receiver got ----
ok(batches.length > 0 && batches.every((b) => b.status === 200), `el receptor respondió 200 a los ${batches.length} lotes`);
ok(batches.every((b) => b.ack && b.ack.accepted === b.ack.received && b.ack.rejected.length === 0), "el receptor aceptó todos los eventos contra el JSON Schema (rejected: [])");
ok(events().length >= 18 && batches.length * 3 <= events().length, `en lotes, no de uno en uno: ${events().length} eventos en ${batches.length} peticiones`);
ok(batches.every((b) => b.events.length >= 1 && b.events.length <= 100), "ningún lote vacío ni por encima de 100");

const mandatory = ["inbound_order_created", "outbound_order_created", "stock_threshold_triggered", "kit_cost_variance_detected"];
for (const type of mandatory) ok(of(type).length === 1, `exactamente un ${type}`);
const inbound = of("inbound_order_created")[0].properties;
ok(inbound.office === "valencia" && inbound.currency === "EUR" && inbound.programme_id === "onboarding-soporte" && inbound.product_category === "onboarding_equipment" && inbound.product_id === "1", "inbound_order_created: oficina, moneda, programa, categoría y producto del dominio de Nexova");
ok(inbound.quantity === 2 && inbound.unit_cost_minor === 120000 && inbound.total_cost_minor === 240000 && /^sup-[0-9a-f]{12}$/.test(inbound.supplier_id), "inbound_order_created: total = cantidad x coste unitario en céntimos, proveedor como id opaco");
const variance = of("kit_cost_variance_detected")[0].properties;
ok(variance.baseline_order_count === 5 && variance.threshold_percent === 10 && variance.variance_percent > 10 && variance.reference_unit_cost_minor > 80000 && variance.reference_unit_cost_minor < 90000, `kit_cost_variance_detected: ${variance.variance_percent.toFixed(1)} % sobre una referencia de ${variance.reference_unit_cost_minor}`);
const outbound = of("outbound_order_created")[0].properties;
const threshold = of("stock_threshold_triggered")[0].properties;
ok(outbound.stock_before === stockBefore && outbound.stock_after === 1 && outbound.quantity === stockBefore - 1, `outbound_order_created: stock ${stockBefore} -> 1`);
ok(threshold.minimum_stock === 2 && threshold.stock_before === stockBefore && threshold.stock_after === 1, "stock_threshold_triggered: cruza el mínimo de 2");

// one requestId per submission, shared by the steps, the order event and its alerts
const byRequest = (type) => of(type)[0].requestId;
ok(byRequest("inbound_order_created") === byRequest("kit_cost_variance_detected"), "la entrada y su alerta de coste comparten requestId");
ok(byRequest("outbound_order_created") === byRequest("stock_threshold_triggered"), "la salida y su alerta de mínimo comparten requestId");
const submitted = events().filter((e) => e.event_type === "flow_step_completed" && e.properties.step === "submitted");
ok(submitted.some((e) => e.requestId === byRequest("inbound_order_created")) && submitted.some((e) => e.requestId === byRequest("outbound_order_created")), "el paso 'submitted' del flujo comparte requestId con la petición y sus eventos");

// the story of the flows, the views and the loads
const flow = (name) => events().filter((e) => e.properties.flow_name === name).map((e) => e.event_type === "flow_started" ? "started" : e.properties.step ?? e.event_type);
ok(JSON.stringify(flow("inbound").slice(0, 4)) === JSON.stringify(["started", "validated", "submitted", "confirmed"]), `flujo de entrada: ${flow("inbound").slice(0, 4).join(" > ")}`);
ok(JSON.stringify(flow("outbound")) === JSON.stringify(["started", "validated", "submitted", "confirmed"]), `flujo de salida: ${flow("outbound").join(" > ")}`);
ok(of("form_validation_failed").some((e) => e.properties.field === "multiple" && e.properties.error_count === 4), "form_validation_failed: un envío bloqueado = un evento, field=multiple");
const views = of("section_viewed").map((e) => e.properties.section);
ok(["login", "home", "inbound", "outbound"].every((s) => views.includes(s)), `section_viewed: ${[...new Set(views)].join(", ")}`);
ok(of("section_load_completed").some((e) => e.properties.section === "inbound" && e.properties.outcome === "success" && e.properties.duration_ms >= 0), "section_load_completed de la carga de la entrada");
ok(of("logout_completed").length === 1 && of("logout_completed")[0].properties.reason === "user_action", "logout_completed");

// the envelope
const all = events();
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
ok(all.every((e) => e.schemaVersion === "2.1.0" && uuid.test(e.eventId) && uuid.test(e.sessionId) && uuid.test(e.requestId) && e.userId === null && /Z$/.test(e.timestamp)), "sobre del contrato: schemaVersion 2.1.0, UUID v4, timestamp UTC, userId null desde el navegador");
ok(new Set(all.map((e) => e.eventId)).size === all.length, "ningún eventId repetido");
ok(batches.every((b) => b.events.every((e) => Date.parse(e.timestamp) <= b.at)), "el timestamp es el instante de captura, nunca posterior al envío");
const sessions = [...new Set(all.map((e) => e.sessionId))];
ok(sessions.length >= 2, `la sesión analítica rota con el login/logout (${sessions.length} sesiones)`);

// privacy
const dump = JSON.stringify(all);
ok(![EMAIL, PASSWORD, "TechDistrib", token, "Bearer"].some((secret) => dump.includes(secret)), "ningún evento contiene el email, la contraseña, el token ni el nombre del proveedor");

ok(errors.length === 0, `sin errores en la consola del navegador${errors.length ? `: ${errors.slice(0, 2).join(" | ")}` : ""}`);
await browser.close();
console.log(fails === 0 ? "\nOK" : `\n${fails} FAIL`);
process.exit(fails === 0 ? 0 : 1);
