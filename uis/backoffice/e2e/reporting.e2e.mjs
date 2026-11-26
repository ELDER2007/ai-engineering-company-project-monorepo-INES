// End-to-end check of the business dashboard, /reporting (needs Chromium: npx playwright install chromium).
// Prerequisites: the API on :8000 with an active user, the backoffice on :5174 (npm run dev), and at least one week computed by the pipeline
// (python data/pipelines/pipeline.py): the page shows what the destination table weekly_office_program_performance holds.
// Run from uis/backoffice:  E2E_EMAIL=you@example.com E2E_PASSWORD=... npm run e2e:reporting
// Optional: E2E_SCREENSHOTS=/some/folder saves a picture of the page.
// Covers: the menu link, the title, the four KPIs of the briefing with its names, the period the numbers cover, that what the page shows is
// what the API answers (the totals), that euros and dollars are never added together, that it reads without technical words, the move between
// weeks, how fresh and how complete the data is (the page says what the last run says), and that nothing fails in the browser.
import { chromium } from "playwright";

const APP = process.env.E2E_APP_URL ?? "http://localhost:5174";
const EMAIL = process.env.E2E_EMAIL;
const PASSWORD = process.env.E2E_PASSWORD;
const SHOTS = process.env.E2E_SCREENSHOTS;
if (!EMAIL || !PASSWORD) {
  console.error("Set E2E_EMAIL and E2E_PASSWORD to an active API user (see the header of this file).");
  process.exit(2);
}

const KPI_NAMES = ["Costo de material por oficina/programa", "Kits entregados", "Frecuencia de escasez", "Frecuencia de variación de costo"];
const FIELDS = { "Kits entregados": "kits_delivered_count", "Frecuencia de escasez": "shortage_events_count", "Frecuencia de variación de costo": "cost_variance_events_count" };

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1300, height: 1100 } })).newPage();
const problems = [];
page.on("pageerror", (e) => problems.push(String(e)));
page.on("console", (m) => m.type() === "error" && problems.push(m.text()));
const calls = [];
page.on("response", (r) => r.url().includes("/api/reporting/") && calls.push({ url: r.url(), status: r.status() }));

let fails = 0;
const ok = (condition, message) => {
  if (!condition) fails++;
  console.log(`${condition ? "PASS" : "FAIL"}  ${message}`);
};
const shot = (name) => SHOTS && page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true });
const section = (name) => page.getByRole("region", { name });
const plain = (text) => text.replace(/\s+/g, " ").trim();

// 1. login and the menu link
await page.goto(`${APP}/login`);
await page.getByLabel("Email").fill(EMAIL);
await page.getByLabel("Contraseña").fill(PASSWORD);
await page.getByRole("button", { name: "Entrar" }).click();
await page.waitForURL(`${APP}/`);
await page.getByRole("link", { name: "Desempeño semanal" }).click();
await page.waitForURL("**/reporting");
ok(true, "the menu has a link to the weekly performance that leads to /reporting");

// 2. the page, once the week has arrived
await page.getByRole("heading", { level: 2, name: KPI_NAMES[0] }).waitFor({ timeout: 20000 });
ok((await page.getByRole("heading", { level: 1 }).textContent()) === "Reporte semanal de desempeño por oficina y programa", "the title is the report the briefing asks for");
for (const name of KPI_NAMES) ok(await page.getByRole("heading", { level: 2, name }).isVisible(), `shows the KPI "${name}", with the name it has in the briefing`);
ok((await page.getByRole("heading", { level: 2 }).count()) === KPI_NAMES.length, "shows exactly the four KPIs");

const period = plain(await page.getByRole("status").textContent());
ok(/^Semana del lunes \d{1,2} de \w+( de \d{4})? al domingo \d{1,2} de \w+ de \d{4}$/.test(period), `says the period the numbers cover: "${period}"`);
await shot("reporting-semana-actual");

// 3. what the page shows is what the API answers
const token = await page.evaluate(() => localStorage.getItem("nexova.token"));
const answer = await page.evaluate(async (t) => (await fetch("/api/reporting/weekly-office-program-performance", { headers: { Authorization: `Bearer ${t}` } })).json(), token);
ok(answer.entries.length > 0, `the API has ${answer.entries.length} office/programme rows for the week of ${answer.week_start}`);
for (const [name, field] of Object.entries(FIELDS)) {
  const total = answer.entries.reduce((sum, entry) => sum + entry[field], 0);
  const text = plain(await section(name).textContent());
  const shown = total === 0 ? true : new RegExp(`Total: ${total.toLocaleString("es-ES")} (kit|kits|vez|veces)`).test(text);
  ok(shown, `"${name}": the page shows what the API says (${total})`);
}

// 4. euros and dollars never added together
const costText = plain(await section(KPI_NAMES[0]).textContent());
const fmt = (n, currency) => new Intl.NumberFormat("es-ES", { style: "currency", currency }).format(n).replace(/\s/g, " ");
for (const currency of ["EUR", "USD"]) {
  const rows = answer.entries.filter((e) => e.currency === currency);
  if (rows.length === 0) continue;
  const total = rows.reduce((sum, e) => sum + e.total_material_cost, 0);
  ok(plain(costText).replace(/\s/g, " ").includes(fmt(total, currency)), `the cost in ${currency === "EUR" ? "euros" : "dollars"} is totalled by itself: ${fmt(total, currency)}`);
}
const every = answer.entries.reduce((sum, e) => sum + e.total_material_cost, 0);
const mixed = new Set(answer.entries.map((e) => e.currency)).size > 1;
ok(!mixed || !costText.replace(/\s/g, " ").includes(fmt(every, "EUR")), "the euros and the dollars are not added into one figure");

// 5. it reads without technical words or codes
const body = plain(await page.locator("main").textContent());
ok(!/\b(pipeline|endpoint|api|json|sql|telemetr\w*|flow|task|query|undefined|null|NaN)\b/i.test(body), "uses no technical word");
ok(!/ventas-b2b|liderazgo-basico|onboarding-soporte|\bEUR\b|\bUSD\b/.test(body), "shows no programme, currency or office as a code");

// 6. moving between weeks
const before = period;
await page.getByRole("button", { name: /Semana anterior/ }).click();
await page.waitForFunction((previous) => document.querySelector('[role="status"]')?.textContent?.replace(/\s+/g, " ").trim() !== previous, before);
ok(plain(await page.getByRole("status").textContent()) !== before, "the previous week button moves to another week");
ok(calls.some((c) => c.url.includes("week_start=") && c.status === 200), "it asked the API for that week by its Monday");
await shot("reporting-semana-anterior");
await page.getByRole("button", { name: "Ir a la última semana calculada" }).click();
await page.waitForFunction((first) => document.querySelector('[role="status"]')?.textContent?.replace(/\s+/g, " ").trim() === first, before);
ok(plain(await page.getByRole("status").textContent()) === before, "can come back to the latest computed week");

// 7. how fresh and how complete the data is: what the page says matches what the last run says (read-only)
const run = await page.evaluate(async (t) => {
  const r = await fetch("/api/reporting/pipeline-runs/latest", { headers: { Authorization: `Bearer ${t}` } });
  return r.ok ? r.json() : null;
}, token);
const mainText = plain(await page.locator("main").textContent());
if (run === null) {
  ok(mainText.includes("El proceso que calcula estos datos todavía no se ha ejecutado."), "with no run at all, says the process has not run yet");
} else {
  const days = run.finished_at ? Math.floor((Date.now() - new Date(run.finished_at).getTime()) / 86_400_000) : 0;
  const expected =
    run.state === "Completed" ? (days >= 8 ? `Los datos llevan ${days} días sin actualizarse` : "Datos actualizados")
    : run.state === "Failed" || run.state === "Crashed" ? "La última actualización de los datos no terminó bien"
    : "Los datos se están actualizando en este momento";
  ok(mainText.includes(expected), `says how fresh the data is, as the last run (${run.state}) implies: "${expected}…"`);
  const notes = (run.warnings ?? "").split("; ").filter((note) => note.startsWith("data_health:"));
  const forThisWeek = run.week_start === answer.week_start ? notes.length : 0; // the latest run only speaks for the week it computed
  const warnings = await page.getByLabel("Avisos sobre los datos").locator("li").count();
  ok(warnings === forThisWeek, `shows ${forThisWeek} data warning(s) for this week, as the run's notes imply (${warnings} shown)`);
  ok(!/data_health|capture_silent|volume_drop/.test(mainText), "the warnings never show the technical codes");
}

// 8. nothing failed
ok(calls.every((c) => c.status === 200), "every call of the page to the API answered 200");
ok(problems.length === 0, `no error in the browser${problems.length ? `: ${problems.slice(0, 3).join(" | ")}` : ""}`);

await browser.close();
console.log(fails === 0 ? "\nAll checks passed." : `\n${fails} check(s) failed.`);
process.exit(fails === 0 ? 0 : 1);
