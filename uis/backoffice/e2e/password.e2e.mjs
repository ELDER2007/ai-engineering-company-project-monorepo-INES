// End-to-end check of the password flows: forgotten password (email link) and change while logged in.
// Needs Chromium: npx playwright install chromium.
// Prerequisites: API on :8000 and the backoffice on :5174 (npm run dev). No existing user is needed: the test
// signs up its own (unique email on every run) and never touches anybody else's password.
// Run from uis/backoffice:  npm run e2e:password
// The reset link only exists in the email. To cover the whole reset, run the API with EMAIL_BACKEND=console and
// FRONTEND_URL=<this app's URL>, send its output to a file, and point E2E_API_LOG at it:
//   EMAIL_BACKEND=console FRONTEND_URL=http://localhost:5174 uvicorn main:app --port 8000 > /tmp/api.log 2>&1
//   E2E_API_LOG=/tmp/api.log npm run e2e:password
// Without E2E_API_LOG those steps are skipped (and reported as such).
import { readFileSync } from "node:fs";
import { chromium } from "playwright";
const APP = process.env.E2E_APP_URL ?? "http://localhost:5174";
const API = process.env.E2E_API_URL ?? "http://localhost:8000";
const API_LOG = process.env.E2E_API_LOG;
const EMAIL = `e2e-password-${Date.now()}@example.com`;
const FIRST = "password-e2e-1";
const SECOND = "password-e2e-2";
const THIRD = "password-e2e-3";

const signUp = await fetch(`${API}/users`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: EMAIL, password: FIRST, name: "Clave E2E" }) }).catch(() => null);
if (!signUp?.ok) {
  console.error(`Could not sign up the test user (${signUp?.status ?? "no answer"}): is the API running on ${API}?`);
  process.exit(2);
}
const apiLogin = (password) => fetch(`${API}/auth/login`, { method: "POST", body: new URLSearchParams({ username: EMAIL, password }) });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1200, height: 1000 } });
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => m.type() === "error" && !/40[019]|422|503|ERR_FAILED/.test(m.text()) && errors.push(m.text()));
let fails = 0;
const ok = (c, msg) => { if (!c) fails++; console.log(`${c ? "PASS" : "FAIL"}  ${msg}`); };
// The app's own alerts: Next.js adds a hidden route announcer that also has role="alert".
const appAlert = () => page.locator('[role="alert"]:not(#__next-route-announcer__)');
const path = () => new globalThis.URL(page.url()).pathname;
const token = () => page.evaluate(() => localStorage.getItem("nexova.token"));
const fieldError = (id) => page.locator(`#${id}-error`);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
/** The newest reset link the API "sent" to the test user (console mail backend), or null. */
async function resetLinkFromLog() {
  for (let attempt = 0; attempt < 20; attempt++) {
    const emails = readFileSync(API_LOG, "utf8").split("----- email").filter((e) => e.includes(`To: ${EMAIL}`));
    const link = emails.at(-1)?.match(/https?:\/\/\S+\/reset-password\?token=\S+/)?.[0];
    if (link) return link;
    await sleep(250);
  }
  return null;
}

// 1. /login enlaza con /forgot-password; validación en cliente sin llamar a la API
let forgotCalls = 0;
page.on("request", (r) => r.method() === "POST" && r.url().endsWith("/auth/forgot-password") && forgotCalls++);
await page.goto(`${APP}/login`);
await page.getByRole("link", { name: "¿Olvidaste tu contraseña?" }).click();
await page.waitForURL("**/forgot-password");
ok(path() === "/forgot-password", "el login enlaza con /forgot-password");
await page.getByRole("button", { name: "Enviar enlace" }).click();
ok(/obligatorio/.test(await fieldError("email").innerText()) && forgotCalls === 0, "email vacío: error en el campo, sin llamar a la API");
await page.getByLabel("Email").fill("no-es-email");
await page.getByRole("button", { name: "Enviar enlace" }).click();
ok(/no es válido/.test(await fieldError("email").innerText()) && forgotCalls === 0, "email mal formado bloqueado en cliente");

// 2. la respuesta es la misma exista o no la cuenta
await page.getByLabel("Email").fill(`nadie-${Date.now()}@example.com`);
await page.getByRole("button", { name: "Enviar enlace" }).click();
await page.getByRole("status").waitFor();
const unknownText = await page.getByRole("status").innerText();
await page.goto(`${APP}/forgot-password`);
await page.getByLabel("Email").fill(`  ${EMAIL.toUpperCase()}  `);
await page.getByRole("button", { name: "Enviar enlace" }).click();
await page.getByRole("status").waitFor();
const knownText = await page.getByRole("status").innerText();
ok(forgotCalls === 2 && knownText === unknownText && /Si esa dirección está registrada, recibirás un enlace en breve\./.test(knownText) && (await appAlert().count()) === 0, "cuenta existente e inexistente: el mismo aviso (no revela qué emails están registrados)");

ok(await page.getByLabel("Email").isDisabled() && await page.getByRole("button", { name: "Enlace enviado" }).isDisabled(), "tras el envío el formulario queda desactivado (campo y botón)");

// 3. enlace sin token, o con un token inventado -> enlace no válido, con salida a pedir otro
await page.goto(`${APP}/reset-password`);
await appAlert().waitFor();
ok(/no es válido o ha caducado/.test(await appAlert().innerText()) && (await page.getByLabel("Nueva contraseña", { exact: true }).count()) === 0, "/reset-password sin token: enlace no válido y sin formulario");
await page.goto(`${APP}/reset-password?token=token-inventado`);
await page.getByLabel("Nueva contraseña", { exact: true }).fill(SECOND);
await page.getByLabel("Repite la nueva contraseña").fill(SECOND);
await page.getByRole("button", { name: "Guardar contraseña" }).click();
await appAlert().waitFor();
ok(/no es válido o ha caducado/.test(await appAlert().innerText()), "token inventado: la API responde 400 y se muestra enlace no válido");
await page.goto(`${APP}/reset-password?token=otro-token`);
await page.route("**/auth/reset-password", (route) => route.abort());
await page.getByLabel("Nueva contraseña", { exact: true }).fill(SECOND);
await page.getByLabel("Repite la nueva contraseña").fill(SECOND);
await page.getByRole("button", { name: "Guardar contraseña" }).click();
await appAlert().waitFor();
ok(/No se pudo cambiar/.test(await appAlert().innerText()) && (await appAlert().getByRole("link", { name: "Solicitar un enlace nuevo" }).getAttribute("href")) === "/forgot-password" && (await page.getByLabel("Nueva contraseña", { exact: true }).count()) === 1, "fallo de red: error claro con enlace a /forgot-password y el formulario sigue activo");
await page.unroute("**/auth/reset-password");
await page.goto(`${APP}/reset-password?token=token-inventado`);
await page.getByLabel("Nueva contraseña", { exact: true }).fill(SECOND);
await page.getByLabel("Repite la nueva contraseña").fill(SECOND);
await page.getByRole("button", { name: "Guardar contraseña" }).click();
await appAlert().waitFor();
ok((await apiLogin(FIRST)).ok, "la contraseña no ha cambiado");
await page.getByRole("link", { name: "Solicitar otro enlace" }).click();
await page.waitForURL("**/forgot-password");
ok(path() === "/forgot-password", "desde el enlace no válido se puede pedir otro");

// 4. restablecer con el enlace del correo (backend de correo "console": el enlace está en la salida de la API)
let current = FIRST;
if (!API_LOG) {
  console.log("SKIP  restablecer con el enlace del correo (define E2E_API_LOG; ver la cabecera de este archivo)");
} else {
  const emailed = await resetLinkFromLog();
  // The host in the email is FRONTEND_URL (the public URL in a Codespace): open the same path and token on APP.
  const link = emailed && `${APP}${new globalThis.URL(emailed).pathname}${new globalThis.URL(emailed).search}`;
  ok(!!emailed && new globalThis.URL(emailed).pathname === "/reset-password" && !!new globalThis.URL(emailed).searchParams.get("token"), "el correo lleva un enlace a /reset-password con el token");
  if (link) {
    await page.goto(link);
    let resetCalls = 0;
    let sent = null;
    page.on("request", (r) => {
      if (r.method() === "POST" && r.url().endsWith("/auth/reset-password")) { resetCalls++; sent = JSON.parse(r.postData()); }
    });
    await page.getByLabel("Nueva contraseña", { exact: true }).fill("corta");
    await page.getByLabel("Repite la nueva contraseña").fill("otra");
    await page.getByRole("button", { name: "Guardar contraseña" }).click();
    ok(/al menos 8/.test(await fieldError("password").innerText()) && /no coinciden/.test(await fieldError("confirmPassword").innerText()) && resetCalls === 0, "contraseña corta y confirmación distinta bloqueadas en cliente");
    await page.getByLabel("Nueva contraseña", { exact: true }).fill(SECOND);
    await page.getByLabel("Repite la nueva contraseña").fill(SECOND);
    await page.getByRole("button", { name: "Guardar contraseña" }).click();
    await page.waitForURL("**/login**");
    await page.getByRole("status").waitFor();
    ok(path() === "/login" && /Contraseña actualizada/.test(await page.getByRole("status").innerText()) && resetCalls === 1 && Object.keys(sent).sort().join() === "new_password,token", "contraseña restablecida: POST /auth/reset-password con token y new_password, y redirección a /login con mensaje de éxito");
    ok((await token()) === null, "restablecer no inicia sesión");
    ok(!(await apiLogin(FIRST)).ok && (await apiLogin(SECOND)).ok, "en la API: la contraseña antigua ya no entra y la nueva sí");
    current = SECOND;

    // el enlace es de un solo uso
    await page.goto(link);
    await page.getByLabel("Nueva contraseña", { exact: true }).fill(THIRD);
    await page.getByLabel("Repite la nueva contraseña").fill(THIRD);
    await page.getByRole("button", { name: "Guardar contraseña" }).click();
    await appAlert().waitFor();
    ok(/no es válido o ha caducado/.test(await appAlert().innerText()) && (await apiLogin(SECOND)).ok, "el mismo enlace no sirve dos veces");
  }
}

// 5. entrar con la contraseña vigente y cambiarla desde /account/change-password
await page.goto(`${APP}/login`);
await page.getByLabel("Email").fill(EMAIL);
await page.getByLabel("Contraseña").fill(current);
await page.getByRole("button", { name: "Entrar" }).click();
await page.waitForURL(`${APP}/`);
await page.getByRole("navigation", { name: "Navegación principal" }).getByRole("link", { name: "Cambiar contraseña" }).click();
await page.waitForURL("**/account/change-password");
const sessionToken = await token();
let changeCalls = 0;
page.on("request", (r) => r.method() === "POST" && r.url().endsWith("/auth/change-password") && changeCalls++);
const fill = async (currentPassword, newPassword, confirm = newPassword) => {
  await page.getByLabel("Contraseña actual").fill(currentPassword);
  await page.getByLabel("Nueva contraseña", { exact: true }).fill(newPassword);
  await page.getByLabel("Repite la nueva contraseña").fill(confirm);
  await page.getByRole("button", { name: "Cambiar contraseña" }).click();
};
await page.getByRole("button", { name: "Cambiar contraseña" }).click();
ok(/obligatoria/.test(await fieldError("currentPassword").innerText()) && /obligatoria/.test(await fieldError("newPassword").innerText()) && changeCalls === 0, "vacío: campos obligatorios, sin llamar a la API");
await fill(current, current);
ok(/distinta de la actual/.test(await fieldError("newPassword").innerText()) && changeCalls === 0, "nueva igual que la actual: bloqueada en cliente");
await fill(current, THIRD, "no-coincide");
ok(/no coinciden/.test(await fieldError("confirmPassword").innerText()) && changeCalls === 0, "confirmación distinta: bloqueada en cliente");

await fill("no-es-mi-clave", THIRD);
await fieldError("currentPassword").waitFor();
ok(/no es correcta/.test(await fieldError("currentPassword").innerText()) && changeCalls === 1, "contraseña actual incorrecta (400): error en el campo");
ok(path() === "/account/change-password" && (await token()) === sessionToken, "un 400 no cierra la sesión");

await fill(current, THIRD);
await page.getByRole("status").waitFor();
ok(/Contraseña cambiada/.test(await page.getByRole("status").innerText()) && (await page.getByLabel("Contraseña actual").inputValue()) === "", "contraseña cambiada: aviso y formulario vacío");
ok(!(await apiLogin(current)).ok && (await apiLogin(THIRD)).ok, "en la API: la contraseña anterior ya no entra y la nueva sí");
ok((await token()) === sessionToken, "la sesión abierta sigue activa");

// 6. con sesión, /forgot-password devuelve a la app; sin sesión, /account/change-password pide login
await page.goto(`${APP}/forgot-password`);
await page.waitForURL(`${APP}/`);
ok(path() === "/", "con sesión abierta, /forgot-password redirige a /");
await page.getByRole("button", { name: "Cerrar sesión" }).click();
await page.waitForURL("**/login**");
await page.goto(`${APP}/account/change-password`);
await page.waitForURL("**/login?next=%2Faccount%2Fchange-password");
ok(path() === "/login", "sin sesión, /account/change-password redirige a /login?next=…");
await page.getByLabel("Email").fill(EMAIL);
await page.getByLabel("Contraseña").fill(THIRD);
await page.getByRole("button", { name: "Entrar" }).click();
await page.waitForURL("**/account/change-password");
ok(path() === "/account/change-password", "y el login con la contraseña nueva vuelve a /account/change-password");

ok(errors.length === 0, `sin errores de consola/página (${errors.length}) ${errors.slice(0, 2).join(" || ")}`);
console.log(fails === 0 ? "\nALL OK" : `\n${fails} FAILED`);
await browser.close();
process.exit(fails === 0 ? 0 : 1);
