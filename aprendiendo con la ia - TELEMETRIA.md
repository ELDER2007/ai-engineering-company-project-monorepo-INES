# 📘 Aprendiendo con la IA — Captura de eventos de telemetría

> **Estudiante:** INES
> **Proyecto:** Nexova — backoffice (`uis/backoffice`, Next.js) y API (`services/api`, FastAPI)
> **Qué es este documento:** el diario de la captura de telemetría. Aquí está **cómo se hizo, qué decisiones se tomaron y por qué, y cómo se resolvió cada problema**, incluidos **los errores que cometió la IA** (están marcados). Está escrito para estudiar, no para entregar.
> El entregable oficial es el [PR #27](https://github.com/ELDER2007/ai-engineering-company-project-monorepo-INES/pull/27). Este cuaderno es su complemento. Continúa a [`aprendiendo con la ia - PERF-AUDIT.md`](./aprendiendo%20con%20la%20ia%20-%20PERF-AUDIT.md). El **plan** que se implementa está en [`docs/telemetry/`](./docs/telemetry/README.md).

---

## 📑 Índice

1. [El encargo, en palabras sencillas](#1-el-encargo-en-palabras-sencillas)
2. [Conceptos que necesitas antes de empezar](#2-conceptos-que-necesitas-antes-de-empezar)
3. [El método](#3-el-método)
4. [Paso a paso: qué se hizo](#4-paso-a-paso-qué-se-hizo)
5. [Las decisiones importantes (y por qué)](#5-las-decisiones-importantes-y-por-qué)
6. [Problemas y errores, y cómo se resolvieron](#6-problemas-y-errores-y-cómo-se-resolvieron)
7. [Resultados](#7-resultados)
8. [Archivos que se tocaron](#8-archivos-que-se-tocaron)
9. [Cómo repetirlo tú](#9-cómo-repetirlo-tú)
10. [Glosario](#10-glosario)
11. [Ejercicios para practicar](#11-ejercicios-para-practicar)
12. [Lo que queda pendiente](#12-lo-que-queda-pendiente)

---

## 1. El encargo, en palabras sencillas

Tu plan de telemetría (Fase 1) decía **qué** medir. Este encargo es **medirlo de verdad**:

1. Una **API receptora de mentira** («stub») que recibe los eventos y comprueba que tienen buen formato, pero **no los guarda**.
2. En el backoffice, un **`TelemetryService`**: apunta cada cosa que pasa en el momento en que pasa, la guarda en una lista en memoria y la manda al servidor **en paquetes**, nunca de uno en uno.
3. **Una sola función**, `track()`, por la que pasa todo. Nada de poner código de medición suelto en cada componente.
4. Instrumentar **todas las métricas obligatorias** de tu briefing (las 5 de inventario de Nexova) y un **«piso técnico»**: errores, rendimiento y páginas vistas.
5. Actividad extra: autenticación (login fallido, sesión expirada…) y Web Vitals.

> 💡 **La idea clave:** el usuario **nunca ve** esta parte. Si funciona bien, nadie lo nota; si falla, **no debe romper la aplicación**. Esa regla guió casi todas las decisiones.

---

## 2. Conceptos que necesitas antes de empezar

### 📮 Un evento es una «postal» con formato fijo

Cada vez que algo importante ocurre (se crea una orden de entrada, alguien falla el login…) se escribe una postal. Todas llevan **el mismo sobre** (el *envelope*): quién (`userId`, `sessionId`), cuándo (`timestamp`), qué (`event_type`), de qué versión del contrato (`schemaVersion`), a qué operación pertenece (`requestId`) y un identificador único (`eventId`). Lo específico de cada evento va dentro, en `properties`.

### 🚚 Lote (batch): un camión, no mil mensajeros

Si cada clic mandara una petición HTTP, una app activa haría cientos por minuto y saturaría el servidor. Por eso los eventos **se acumulan en una cola** y salen **juntos** cuando se cumple lo primero que ocurra: pasan **10 segundos** o hay **20 eventos**.

### 🚪 `sendBeacon`: la carta que se echa al buzón al irte

Cuando cierras la pestaña, el navegador **cancela** las peticiones en curso. `navigator.sendBeacon` le dice al navegador: «envía esto aunque me cierre». Es la forma fiable de no perder lo que quedaba en la cola.

### 🔁 Reintentos con *backoff* exponencial

Si el envío falla (sin red, servidor caído), se reintenta **esperando cada vez el doble**: 1 s, 2 s, 4 s. Si tras **3 reintentos** sigue fallando, el lote se **descarta**: son datos de medición, no críticos, y no deben bloquear nada. Esperar más cada vez evita «martillear» a un servidor que ya está mal.

### 📜 El contrato: JSON Schema y *allowlist*

`docs/telemetry/event-schemas.json` es el **contrato**: dice exactamente qué eventos existen y qué claves puede llevar cada uno. Una *allowlist* («lista de permitidos») significa que **todo lo que no está escrito está prohibido**. Así es imposible que, «por si acaso», se cuele un email o un nombre en un evento.

### 🕵️ PII y seudonimización

**PII** = datos personales (nombre, email, contraseña…). **Nunca** van en un evento. El `userId` no es el id real del usuario: es un **HMAC** (una huella calculada con una clave secreta que **solo conoce el servidor**). Con la misma clave sale siempre la misma huella (se puede contar «usuarios distintos»), pero no se puede deshacer para saber quién es.

### 🆔 `eventId`, `sessionId`, `requestId`

- `eventId`: identifica **ese** evento. Si un envío se repite, el servidor puede detectar que ya lo vio.
- `sessionId`: una «visita» del navegador. Cambia al hacer login y al cerrar sesión.
- `requestId`: une las cosas que pertenecen a **la misma operación** (el clic en «Registrar», la petición HTTP y los eventos que provoca).

### 🧱 Piezas de código que aparecen

| Pieza | Para qué sirve |
|---|---|
| **Pydantic** (`TelemetryEvent`) | Describe y valida la forma de un dato en Python. |
| **FastAPI** | El framework de la API. |
| **React hook** (`useFlowTelemetry`) | Reutiliza lógica con estado dentro de componentes. |
| **Jest + fake timers** | Pruebas del frontend; los *fake timers* permiten «avanzar el reloj» sin esperar de verdad. |
| **Playwright** | Un navegador real controlado por código, para pruebas de punta a punta (e2e). |
| **CORS / preflight** | Reglas del navegador para llamar a otro dominio; un «preflight» es una petición previa de permiso. |

---

## 3. El método

> **Leer el contrato → construir de dentro hacia fuera → probar cada capa → comprobar con el sistema real → documentar.**

El enunciado marcaba un orden: **stub → servicio → instrumentación**. No se instrumenta antes de tener un sitio al que enviar. Y cada fase se verificó **contra el enunciado**, no contra la memoria de lo que «ya estaba hecho» (eso evitó errores, ver el problema 1).

Reglas que se siguieron:

1. **El contrato manda.** Los nombres de eventos y de claves salen de tu plan aprobado, no de ejemplos genéricos.
2. **La telemetría nunca rompe la app.** Todo `track()` está protegido; un fallo de medición se traga, no se propaga.
3. **No inventar datos.** Si falta un dato para un evento, el evento no se emite (mejor ausente que falso).
4. **Probar con el sistema real**, no solo con pruebas que yo mismo escribí. Las pruebas de verdad encontraron fallos que las unitarias no.
5. **Preguntar cuando la decisión es tuya** (ampliar el inventario, cambiar el contrato, instalar paquetes del sistema).

---

## 4. Paso a paso: qué se hizo

### 4.1 Explorar antes de tocar
Se leyeron el briefing, el plan y el esquema, y el código del backoffice y la API. Hallazgos: **`docs/telemetry/event-schemas.json` no estaba en `main`** (vive en la rama del PR #24), y el inventario **no tenía** programa, moneda, coste ni mínimo, datos que exigen los eventos obligatorios.

### 4.2 Fase 1 — El receptor (stub) — `services/api/telemetry/`
`POST /telemetry/events` recibe `{"events": [...]}`, valida cada evento (primero el modelo Pydantic `TelemetryEvent`, luego el JSON Schema), **registra en el log** cuántos llegaron y de qué tipo, y responde `200`. Lee `TELEMETRY_ENDPOINT` del entorno (sin usarla aún).

### 4.3 Ampliar el inventario — `services/api/inventory/`
Se añadieron `programme_id`, `product_category`, `minimum_stock`, coste unitario y `supplier_id`. La API **calcula dentro de la transacción** de cada orden el stock antes/después, si se cruzó el mínimo y si el coste varió más de un 10 %. También se **rechaza explícitamente** un campo `stock`/`current_stock` en el cuerpo (antes se ignoraba en silencio).

### 4.4 Fase 2 — `TelemetryService` — `uis/backoffice/src/lib/telemetry/`
Cola, lote a 10 s/20 eventos, `sendBeacon`, reintentos, sesión y los campos automáticos. Una sola función pública: `track()`.

### 4.5 Fase 3 — Instrumentar
- **Inventario**: en `lib/inventory.ts`, el único sitio por donde pasan las órdenes. Traduce la respuesta de la API en eventos (`lib/inventoryTelemetry.ts`).
- **Formularios**: `useFlowTelemetry` cuenta la historia de un intento (empezó → validado → enviado → confirmado).
- **Páginas y errores**: `TelemetryProvider` (vistas de página, `window.onerror`, `unhandledrejection`), el Error Boundary y `useAsyncResource` (tiempo de carga).
- **Autenticación**: en `login()` y `register()` de `lib/api.ts`, no en cada página.
- **Proveedores e incidencias**: en las funciones de `lib/api.ts`.
- **Web Vitals**: con `useReportWebVitals` de Next.js.

### 4.6 Probar en tres niveles
1. **Pruebas unitarias** (Jest, pytest) para cada pieza.
2. **Integración real**: el código del frontend contra la API en marcha.
3. **Navegador real** (Playwright): el flujo completo, mirando las peticiones de verdad.

### 4.7 Entregar
Cuatro *commits* por tema, rama `feature/telemetry-capture`, [PR #27](https://github.com/ELDER2007/ai-engineering-company-project-monorepo-INES/pull/27) contra `main`.

---

## 5. Las decisiones importantes (y por qué)

| # | Decisión | Por qué |
|---|---|---|
| 1 | **Ampliar el inventario** (en vez de inventar valores en el navegador) | Tu plan prohíbe inventar el programa o mapear categorías antiguas automáticamente. Era una decisión tuya, así que se te **preguntó**. |
| 2 | **El servidor calcula** el cruce del mínimo y la variación de coste | Solo el servidor ve el stock real en el instante de la orden; el navegador podría tener datos viejos. Una sola «fuente de verdad». |
| 3 | `supplier_id` = **huella del nombre normalizado** | El «directorio de proveedores» contiene herramientas (LinkedIn, Workable…), no proveedores de material. Un id opaco evita enviar el nombre. Es **provisional**. |
| 4 | **`userId` lo pone el servidor**, el navegador manda `null` | La clave HMAC no puede estar en el navegador (cualquiera podría verla). El plan lo prohíbe. |
| 5 | El receptor responde **200 aunque rechace algunos eventos**, y los lista | Un evento malo no debe costar los buenos de su lote. Así también se **ve** qué falla. |
| 6 | El receptor lee el cuerpo **sin fijarse en el `Content-Type`**; `sendBeacon` envía `text/plain` | `text/plain` evita el «preflight» de CORS, que algunos navegadores no permiten en un beacon. |
| 7 | Una **única** función pública `track()` y propiedades **tipadas** | Si te equivocas de clave (o añades una no permitida), **ni compila**. La allowlist se aplica antes de ejecutar nada. |
| 8 | La telemetría de inventario va en **`lib/inventory.ts`**, no en los componentes | El profesor pidió «no tracking disperso». Un sitio, una regla. |
| 9 | **10 s / 20 eventos** exactos (se quitó mi atajo de 1 s para los obligatorios) | Un tercer disparador contradecía «lo que ocurra primero». El enunciado manda. |
| 10 | `login_succeeded` se registra **antes** de guardar el token | Guardar el token abre una sesión nueva; el intento y su resultado deben ir en la **misma** sesión (el plan lo pide). |
| 11 | Un fallo de red al entrar **no** es `login_failed` | No llegó al servidor: contaría contra su tasa de fallos y la falsearía. Se usa `application_error_occurred` (`network_failed`). |
| 12 | Las razones de `login_failed` son **las del esquema aprobado** | El enunciado nombraba otras (`network_error`, `session_expired`); el aviso de IMPORTANTE dice que mandan **tus** esquemas. |
| 13 | **Web Vitals → contrato 2.1.0** (cambio aditivo) | Necesitaba un evento nuevo que el esquema no tenía. Se te preguntó y quedó **documentado** en la sección 17 del plan, pendiente de revisión. |
| 14 | `sessionId` rota **al detectar el cambio de token** | Así ningún componente tiene que acordarse de hacerlo. |
| 15 | Este cuaderno en **archivo aparte** | El PR #24 edita el cuaderno principal; un archivo nuevo no choca. |

---

## 6. Problemas y errores, y cómo se resolvieron

> 🏷️ **Leyenda:** 🔴 error mío (de la IA) · 🟠 hallazgo importante · 🟡 detalle técnico · 🟢 entorno.

### 🔴 Problema 1: el primer stub no cumplía el enunciado
**Qué pasó:** se construyó un stub que devolvía `202` y no tenía el modelo `TelemetryEvent`, ni log de tipos, ni `TELEMETRY_ENDPOINT`. **Cómo se vio:** al comparar con la captura del enunciado de la Fase 1, punto por punto. **Solución:** se añadieron las tres piezas y tests. **Lección:** *antes de dar algo por hecho, léelo contra la lista de lo que se pidió.* Se repitió con las Fases 2 y 3 y salieron más diferencias (5 s en vez de 10 s, 5 intentos en vez de 3…).

### 🟠 Problema 2: el esquema no estaba en `main`
**Qué pasó:** `docs/telemetry/event-schemas.json` solo existía en la rama del PR #24. **Solución:** se trajo con `git checkout origin/docs/telemetry-design-plan -- docs/telemetry` (copiar archivos de otra rama sin cambiar de rama). **Consecuencia:** el PR #27 incluye `docs/telemetry` y, si el #24 se fusiona primero, habrá conflicto en esos archivos (se avisó en el PR).

### 🟠 Problema 3: faltaban datos para las métricas obligatorias
**Qué pasó:** el inventario no guardaba programa, moneda, coste ni mínimo. Emitir los eventos «tal cual» obligaba a **inventar** valores. **Solución:** se te preguntó y elegiste ampliar el inventario. Incluyó una **migración aditiva** (`add_missing_columns`) porque `create_all` crea tablas nuevas pero **no añade columnas** a las existentes.

### 🟡 Problema 4: el mensaje de error de validación podía filtrar un dato personal
**Qué pasó:** los mensajes de `jsonschema` citan el valor que falló (podría ser un email). **Solución:** el receptor solo informa de **dónde** falla (`/properties`) y **qué regla**, nunca el valor; hay un test que lo comprueba con un email.

### 🟡 Problema 5: un error de validación decía solo «ruta `/`»
**Qué pasó:** cuando ninguna de las 41 variantes encajaba, el esquema respondía de forma inútil. **Solución:** se baja a la variante que corresponde al `event_type` del evento y se informa de **su** error.

### 🟡 Problema 6: las fechas no se validaban
**Qué pasó:** `jsonschema` **ignora en silencio** el formato `date-time` si falta el paquete `rfc3339-validator`. **Solución:** se añadió esa dependencia y se actualizó `uv.lock`. *Una validación que no se ejecuta es peor que no tenerla.*

### 🟠 Problema 7: la telemetría podía romper una operación de negocio
**Qué pasó:** con una respuesta de la API incompleta, `trackInventoryOrder` lanzaba una excepción **después de que la orden ya estaba guardada**, y el usuario veía un error. Lo mismo con `changeIncidentStatus` sin `history`. **Solución:** todo código de medición va protegido (`try/catch`, `?? []`). **Regla:** *medir nunca puede cambiar el resultado de lo medido.*

### 🟠 Problema 8: se perdía el primer evento de una ejecución real
**Qué pasó:** en la prueba contra la API real faltaba el primer `login_attempted`. **Causa:** el primer `track()` arranca el servicio; si arrancar fallaba (no había `document`), la excepción **descartaba el evento**. **Solución:** `startSafely()` — un arranque fallido cuesta el envío al cerrar la pestaña, **nunca** el evento. **Lección:** las pruebas unitarias que yo escribí no lo vieron; la **prueba de integración real** sí.

### 🟠 Problema 9: al cerrar sesión se perdía una orden
**Qué pasó:** con el navegador real, el evento `outbound_order_created` fue **rechazado** por falta de `userId`. **Causa:** el lote se envió *después* del logout (el reloj de 10 s saltó tras cerrar sesión), ya sin token; el receptor exige identidad para eventos de inventario. Un operador que registra una orden y cierra sesión en menos de 10 s perdía el evento obligatorio. **Solución:** al cerrar sesión, los eventos que necesitan identidad **salen en ese instante**, con el token aún vigente. **Coste honesto:** es un disparador más que los «10 s / 20 eventos» del enunciado; está declarado en el PR.

### 🟡 Problema 10: las pruebas del propio script de e2e estaban mal
**Qué pasó:** el script suponía stock 14 (era 17) y `schemaVersion` 2.0.0 (ya es 2.1.0). **Solución:** leer el stock de la pantalla y actualizar la versión. *El fallo estaba en la prueba, no en el código, pero hubo que comprobarlo para saberlo.*

### 🟡 Problema 11: los tests se contaminaban entre sí
**Qué pasó:** cada test creaba un servicio que dejaba **escuchas** (`visibilitychange`, `pagehide`) en el documento; los siguientes recibían eventos ajenos. **Solución:** `reset()` ahora también las retira, y los tests resetean cada servicio que crean. Otro caso: un *mock* reutilizaba el **mismo** `Response`, cuyo cuerpo solo se puede leer una vez; se creó uno nuevo por llamada.

### 🟡 Problema 12: el `mock` de `next/link` no pasaba `onClick`
**Qué pasó:** el test de «Volver al inventario» no veía el clic. **Causa:** el *mock* del enlace descartaba `onClick`; el `Link` real sí lo reenvía. **Solución:** el mock lo reenvía.

### 🟠 Problema 13: confusión con dos repositorios
**Qué pasó:** `gh` apuntaba al repo del curso (4GeeksAcademy), donde el plan es el PR #93, y no a tu copia (donde es el #24). **Solución:** indicar siempre `--repo ELDER2007/...`. **Lección:** *comprueba a qué repositorio habla una herramienta antes de actuar.*

### 🟢 Problema 14: el entorno
- No había `uv` ni dependencias → se creó un entorno virtual temporal **fuera** del repo.
- Ese directorio temporal **se borró varias veces** → se recreó.
- **Chromium no arrancaba** (faltaban librerías del sistema). Instalarlas requiere `sudo`/`apt`, un cambio fuera del repo: se te **preguntó** y autorizaste.
- 🔴 Un `pkill -f "next dev"` **mató mi propia terminal**: el patrón coincidía con la línea del propio comando. Se pasó a localizar el proceso por **puerto** (`ss -ltnp`).

### 🟢 Problema 15: Next.js «no es el que conoces»
El archivo `AGENTS.md` del backoffice avisa de que esta versión de Next.js tiene cambios incompatibles y pide **leer su documentación local** antes de escribir código. Se leyó (variables `NEXT_PUBLIC_`, `usePathname`, `useReportWebVitals`) en vez de fiarse de la memoria.

### 🟡 Problema 16: ¿romperá esto mis otros PR?
Se simularon las fusiones (`git merge-tree`, sin tocar nada) del #27 con cada PR abierto. Resultado: conflictos nuevos en `main.py` (casi siempre solo las líneas donde cada PR registra rutas) y en inventario con #22 y #23. **Consejo:** que el #27 se fusione **el último**.

---

## 7. Resultados

| Qué | Resultado |
|---|---|
| Eventos instrumentados | **32 de los 41** del catálogo (5 obligatorios + 27 identificados) |
| Tests de la API | **837** pasan (+7 `xfail` que ya existían); antes eran 724 |
| Tests del backoffice | **851** pasan; antes eran 551. `tsc` limpio, `next build` correcto |
| Integración real (código del frontend + API viva) | 12 eventos en **1** petición, todos aceptados, sin datos personales |
| Navegador real (Playwright) | **32 eventos en 3 peticiones**, todas `200` y `rejected: []`; los 5 obligatorios con sus propiedades; un mismo `requestId` une paso del formulario, petición HTTP y eventos |
| PR | [#27 `feat: telemetry event capture`](https://github.com/ELDER2007/ai-engineering-company-project-monorepo-INES/pull/27), sin conflictos con `main` |

> ⚠️ **Los 9 eventos que no están** no se pueden emitir desde este frontend: `product_*` (no hay pantalla), `supplier_deleted` (la app no borra), `http_request_completed` y `dependency_call_completed` (solo el servidor sabe lo que tarda), los dos de procesos internos y los dos del website.

---

## 8. Archivos que se tocaron

| Dónde | Archivos principales |
|---|---|
| **API — receptor** | `services/api/telemetry/` (`router.py`, `contract.py`, `schemas.py`), `core/config.py`, `main.py` |
| **API — inventario** | `inventory/models.py`, `schemas.py`, `service.py`, `seeding.py`, `database.py`, `routers/inventory.py` |
| **Contrato y plan** | `docs/telemetry/event-schemas.json` (2.1.0), `telemetry-plan.md` (sección 17), `README.md` |
| **Frontend — servicio** | `src/lib/telemetry/` (`TelemetryService.ts`, `instance.ts`, `index.ts`, `events.ts`, `useFlow.ts`, `webVitals.ts`, `paths.ts`, `ids.ts`) |
| **Frontend — instrumentación** | `lib/api.ts`, `lib/inventory.ts`, `lib/inventoryTelemetry.ts`, `lib/authTelemetry.ts`, `lib/useAsyncResource.ts`, `components/TelemetryProvider.tsx`, `auth/AuthContext.tsx`, vistas de entrada/salida/inventario |
| **Pruebas** | `services/api/tests/test_telemetry_receiver.py`, `test_inventory_telemetry.py`; `src/__tests__/lib/*elemetry*.test.ts`, `e2e/telemetry.e2e.mjs` |

---

## 9. Cómo repetirlo tú

**Pruebas automáticas**
```bash
cd services/api && uv run --group dev pytest              # API
cd uis/backoffice && npm test                              # frontend
cd uis/backoffice && npx tsc --noEmit && npm run build    # tipos y compilación
```

**Ver los lotes con tus propios ojos (DevTools)** — esto es lo que te pide el PR:
1. En `services/api`, arranca la API con un usuario inicial:
   `AUTH_INITIAL_EMAIL=tu@correo.com AUTH_INITIAL_PASSWORD=una-clave-larga uv run uvicorn main:app --port 8000`
2. En `uis/backoffice`, comprueba que `.env.local` tiene `NEXT_PUBLIC_TELEMETRY_ENDPOINT=/telemetry/events` (ruta relativa: Next.js la reenvía a la API, así no hay problemas de CORS ni de «localhost» en un Codespace) y ejecuta `npm run dev`.
3. Abre la app (en un Codespace: pestaña **PORTS** → puerto 5174 → icono del globo; en local: `http://localhost:5174`), pulsa **F12 → pestaña Network** y escribe `telemetry` en el filtro.
4. Entra, registra una entrada de activos y espera hasta **10 segundos**.
5. Pulsa la petición `events` (método POST): en **Payload** verás `{"events": [...]}` y en **Response** `{"received": N, "accepted": N, "rejected": []}`; el estado es **200**. **Haz la captura ahí.**

En la terminal de la API verás líneas como `received 20 event(s): section_viewed, …`.

**Prueba de punta a punta con navegador** (escribe órdenes: solo en una base de desarrollo)
```bash
cd uis/backoffice && npx playwright install chromium
# En un Codespace puede hacer falta: sudo npx playwright install-deps chromium
E2E_EMAIL=tu@correo.com E2E_PASSWORD=... npm run e2e:telemetry
```

---

## 10. Glosario

| Término | Significado |
|---|---|
| **Telemetría** | Medir lo que ocurre en una aplicación para tomar decisiones. |
| **Evento** | Un hecho concreto (`login_failed`) con sus datos. |
| **Envelope** | El «sobre» común de todos los eventos. |
| **Lote / batch** | Varios eventos enviados juntos. |
| **Stub** | Pieza provisional que simula a la real (aquí, el receptor que no guarda). |
| **Contrato** | El acuerdo escrito de qué forma tienen los datos (el JSON Schema). |
| **Allowlist** | Lista de lo permitido; lo demás se rechaza. |
| **PII** | Datos personales. |
| **HMAC** | Huella calculada con una clave secreta; no se puede deshacer. |
| **Backoff exponencial** | Esperar cada vez el doble entre reintentos. |
| **`sendBeacon`** | API del navegador para enviar datos al cerrar la página. |
| **`keepalive`** | Opción de `fetch` para que la petición sobreviva al cierre de la página. |
| **CORS / preflight** | Permisos del navegador al llamar a otro dominio / la petición previa de permiso. |
| **Web Vitals** | Métricas de rendimiento percibido: LCP (carga), CLS (estabilidad visual), INP (respuesta), FCP, TTFB. |
| **Idempotente** | Que repetir la operación no cambia el resultado (el `eventId` lo permite). |
| **Migración aditiva** | Cambiar una base de datos solo **añadiendo** columnas, sin borrar nada. |
| **Mock** | Pieza falsa que sustituye a la real en un test. |
| **e2e** | Prueba de punta a punta, como lo haría un usuario. |
| **Conflicto de merge** | Dos ramas cambiaron lo mismo y Git no sabe cuál elegir. |

---

## 11. Ejercicios para practicar

1. **Lee un lote real.** Haz la captura de DevTools y busca `eventId`, `sessionId` y `requestId` de un evento. ¿Cuáles se repiten dentro del lote y cuáles no? ¿Por qué?
2. **Rompe el contrato a propósito.** En `useFlow.ts` intenta añadir una clave no permitida a `flow_started`. ¿Qué dice el compilador? ¿Y qué diría el receptor si se la saltaras?
3. **Cambia el intervalo.** Pon 2 000 ms en `DEFAULT_CONFIG.flushIntervalMs`, mira cómo cambian los lotes y vuelve a 10 000.
4. **Simula una caída.** Para la API, haz una acción en el backoffice y arráncala de nuevo. ¿Cuántos intentos se ven y con qué esperas? (Pista: 1 s, 2 s, 4 s.)
5. **Piensa en privacidad.** ¿Por qué `incident_created` lleva `incident_id` y no el título? ¿Qué pasaría si algún día llevara el email del cliente?
6. **Encuentra el hueco.** El problema 9 se descubrió con un navegador real. Pensando en el flujo «registro una orden y cierro sesión enseguida», ¿qué otros eventos podrían quedarse sin identidad? (No hay respuesta única: apunta tus hipótesis y pruébalas.)
7. **Calcula a mano.** Cinco entradas a 1000 y una nueva a 1100: ¿alerta de variación? ¿Y a 1200? (Mira `cost_variance` en `inventory/service.py`: «más del 10 %» es **estrictamente** mayor.)

---

## 12. Lo que queda pendiente

- **Tu captura de DevTools** en la descripción del PR #27 (la IA no puede hacerla: la rúbrica pide una real).
- **El contrato 2.1.0** (Web Vitals) cambia un contrato ya aprobado: queda **pendiente de la revisión** de tu profesor y está declarado en el PR.
- **El orden de fusión** con tus otros PR: conviene fusionar el #27 el último (ver problema 16).
- **Fases siguientes** (fuera de este PR): guardar los eventos en base de datos, una *outbox* transaccional en el servidor, la política de consentimiento y almacenamiento analítico, y clasificar el catálogo real de productos.
- **Sin comprobar a mano** en DevTools: lo verifiqué con Playwright (que ve las mismas peticiones), pero la pestaña Network no la he abierto yo.
