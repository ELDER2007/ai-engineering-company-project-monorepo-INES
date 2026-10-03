# Auditoría de gestión de errores — monorepo Nexova

**Alcance:** resiliencia, manejo de errores, mensajes al usuario y seguridad.
**Código auditado:** rama `main` (commit `9e49b73`): `services/api`, `uis/backoffice`, `uis/website`, `scripts/`, `packages/shared` y `src/` (código histórico de la raíz).
**Fuera de alcance:** funcionalidades nuevas y refactorizaciones. Cada hallazgo lleva solo una corrección breve.
**Código modificado:** ninguno. Las pruebas se hicieron contra copias temporales, fuera del repositorio.

## Cómo se hizo

- **Lectura** de todo el código fuente (no de los tests).
- **Ejecución real** de los casos dudosos: `scripts/analyze.py` con entradas malas y la API con un `TestClient` sobre una base temporal. Cada hallazgo indica su evidencia:
  - **✔ Verificado**: lo ejecuté y el resultado es el descrito.
  - **◐ Leído**: lo deduzco del código y no lo he ejecutado.
- **Criterios:** no existe en el repositorio ningún documento de criterios del tech lead. He usado el objetivo indicado para esta auditoría: resiliencia, manejo de errores, mensajes al usuario y seguridad. Si hay criterios más concretos, hay que contrastarlos con este informe.

## Resumen

| Severidad | Parte 1 (E-xx) | Parte 2 (T-xx / C-xx) | Parte 3 (S-xx) | Parte 4 (R-xx) | Parte 5 (D-xx) | Parte 6 (U-xx) | Total |
|---|---|---|---|---|---|---|---|
| Alta | 5 (E-01 a E-05) | 2 (T-01, T-02) | 0 | 0 | 2 (D-01, D-02) | 1 (U-01) | **10** |
| Media | 8 (E-06 a E-13) | 3 (T-03, T-04, C-01) | 6 (S-01 a S-06) | 2 (R-01, R-02) | 1 (D-03) | 6 (U-02 a U-07) | **26** |
| Baja | 7 (E-14 a E-20) | 9 (T-05 a T-08, C-03 a C-07) | 4 (S-07 a S-10) | 2 (R-03, R-04) | 4 (D-04 a D-07) | 4 (U-08 a U-11) | **30** |

La **Parte 1** es la auditoría general (resiliencia, errores, mensajes y seguridad). La **Parte 2** es la revisión archivo por archivo con dos criterios concretos: `try/catch` ausente en operaciones que pueden fallar (`fetch`, llamadas a la API, `await`, lectura de ficheros, parseo de JSON) y `catch` demasiado amplio. La **Parte 3** busca fallos silenciosos: errores capturados pero ignorados (`catch {}` vacío, `except: pass`, logs sin acción). La **Parte 4** busca errores en crudo: mensajes técnicos que podrían llegar al usuario (trazas, códigos HTTP, errores de parseo, mensajes internos del servidor). La **Parte 5** busca filtración de datos sensibles en errores y logs: claves secretas, cadenas de conexión, rutas internas y datos personales. La **Parte 6** revisa la interfaz: componentes sin estado de carga o de error, que se rompen sin avisar o que no tienen un plan B seguro. Las partes 2 a 6 están al final, antes de la tabla de la rama.

**Lo más urgente:**
1. Un error inesperado devuelve texto plano y sin cabeceras CORS, así que el navegador lo muestra como "sin conexión" (E-01).
2. Subir un CSV con un campo muy largo tumba la petición con un 500, y no hay límite de tamaño (E-02).
3. Un usuario puede descargar el análisis que hizo otro (E-03).
4. El formulario de la web pública dice "Hemos recibido tu información" y no envía nada (E-04).
5. Un documento mal formado en la base de incidencias rompe la lista y el resumen con un 500 (E-05).

---

## Hallazgos de severidad alta

### E-01 · Errores inesperados: 500 en texto plano y sin CORS
- **Dónde:** [services/api/main.py](../services/api/main.py), [services/api/core/errors.py](../services/api/core/errors.py)
- **Evidencia:** ✔ Verificado.
  - Un fallo sin controlar responde `500 text/plain "Internal Server Error"`.
  - La respuesta no lleva `access-control-allow-origin`.
  - El frontend ([api.ts](../uis/backoffice/src/lib/api.ts)) lo interpreta como fallo de red (`status 0`) y enseña "No se pudo conectar con el servidor" aunque el servidor haya respondido.
  - No queda `error_id` ni traza ordenada en ningún log.
- **Impacto:** el usuario cree que no hay conexión y el equipo no puede relacionar un reporte con su causa.
- **Corrección breve:** añadir un middleware que capture cualquier excepción y devuelva un JSON genérico con un `error_id` (el traceback se escribe en el log con ese mismo id). Ponerlo dentro del middleware de CORS.

### E-02 · Subida de CSV: sin límite de tamaño y `csv.Error` sin capturar
- **Dónde:** [services/api/incidents/router.py:24-37](../services/api/incidents/router.py#L24-L37), [incidents/service.py](../services/api/incidents/service.py)
- **Evidencia:** ✔ Verificado.
  - Una celda de más de 128 KB provoca `csv.Error` y devuelve `500` en texto plano.
  - Un CSV de unos 20 MB y 400.000 filas se acepta, se lee entero en memoria y se analiza.
- **Impacto:** cualquier usuario con sesión puede agotar memoria y CPU del proceso, y un fichero raro da un 500 en lugar de un mensaje útil.
- **Corrección breve:** rechazar con `413` por encima de un tamaño máximo (leyendo por trozos) y capturar `csv.Error` para devolver `400` con un mensaje claro.

### E-03 · El último análisis es global: otro usuario puede descargarlo
- **Dónde:** `_last_result` en [incidents/service.py](../services/api/incidents/service.py), `GET /api/incidents/results/export`
- **Evidencia:** ✔ Verificado. Si el usuario A analiza un CSV, el usuario B recibe ese resultado en `/results/export`.
- **Impacto:**
  - Se mezclan datos entre sesiones. Los datos son agregados y no incluyen emails.
  - Con varios workers el export devuelve resultados distintos o un 404.
  - El comentario del código lo reconoce solo como limitación de despliegue, no como problema de privacidad.
- **Corrección breve:** guardar el resultado por `user.id` (con caducidad) o hacer que `POST /analyze` devuelva ya el CSV exportable.

### E-04 · Web pública: confirma una recepción que no ocurre
- **Dónde:** `submit` en [uis/website/src/App.tsx](../uis/website/src/App.tsx) (`if (!Object.keys(e).length) setSent(true)`)
- **Evidencia:** ◐ Leído.
  - No hay `fetch` ni `try/catch`.
  - Tras validar, muestra "¡Gracias por tu interés en Nexova! Hemos recibido tu información".
  - El [.env.example](../uis/website/.env.example) confirma que el envío "se simula".
- **Impacto:** el candidato cree que su perfil, con teléfono y email, ha llegado y se pierde.
- **Corrección breve:** mientras el envío sea simulado, no afirmar que se ha recibido. Cuando se conecte a la API, usar estado `enviando/error/éxito` con reintento.

### E-05 · Un documento mal formado en la base de incidencias rompe lista y resumen
- **Dónde:** `incident_store.get_db`/`all_docs` y `incident_service._view` en [services/api/incidents/](../services/api/incidents/)
- **Evidencia:** ✔ Verificado.
  - Un documento al que le faltan campos devuelve `500` en `GET /api/incidents` y `/api/incidents/summary`.
  - Un `db.json` corrupto devuelve `500`.
- **Impacto:** un solo registro malo (migración antigua, edición a mano) deja inutilizable todo el panel.
- **Corrección breve:** saltarse los documentos ilegibles y registrarlos en el log. Para un fichero corrupto, un error claro.

---

## Hallazgos de severidad media

### E-06 · Sin límite de intentos en login y registro
- **Dónde:** [auth/router.py](../services/api/auth/router.py), `POST /users`
- **Evidencia:** ✔ Verificado. 30 logins incorrectos seguidos devuelven todos `401`, sin bloqueo ni retardo.
- **Impacto:** fuerza bruta de contraseñas, y registros masivos de cuentas activas al instante.
- **Corrección breve:** limitar por IP y por email (por ejemplo `slowapi`) con `429` y `Retry-After`.

### E-07 · El registro revela qué emails existen
- **Dónde:** `EmailTakenError` en [users/service.py](../services/api/users/service.py) y [users/router.py](../services/api/users/router.py)
- **Evidencia:** ◐ Leído. `POST /users` responde `409 "A user with email 'x' already exists"`.
- **Impacto:** permite enumerar cuentas, aunque el login sí evita esa fuga (`_DUMMY_HASH`).
- **Corrección breve:** combinado con E-06, limitar el endpoint. Si se prefiere no revelar el dato, usar un mensaje genérico y confirmar por otro canal.

### E-08 · `AuthContext` cierra la sesión ante cualquier fallo de `/auth/me`
- **Dónde:** `restoreSession` en [uis/backoffice/src/auth/AuthContext.tsx:52-66](../uis/backoffice/src/auth/AuthContext.tsx#L52-L66)
- **Evidencia:** ◐ Leído. El `.catch` hace `clearToken()` siempre, incluso con red caída o un 500.
- **Impacto:** un parpadeo de la API en el momento de recargar la página expulsa al usuario y le hace volver a identificarse, aunque el token siga siendo válido.
- **Corrección breve:** borrar el token solo si el error es `401`. En los demás casos mostrar "No se pudo comprobar la sesión" con botón Reintentar.

### E-09 · No hay pantalla de error para las rutas públicas ni para el layout raíz
- **Dónde:** solo existe [app/(app)/error.tsx](../uis/backoffice/src/app/(app)/error.tsx). No hay `global-error.tsx` ni `error.tsx` en `(public)`.
- **Evidencia:** ✔ Verificado por el listado de ficheros.
- **Impacto:** un fallo de renderizado en login, registro o `AuthProvider` deja la pantalla en blanco.
- **Corrección breve:** añadir `app/global-error.tsx` y `app/(public)/error.tsx` con el mismo patrón que el existente.

### E-10 · Mensajes de error del API en inglés y respuestas vacías
- **Dónde:** `toApiError` en [api.ts](../uis/backoffice/src/lib/api.ts), y las páginas [SuppliersPage](../uis/backoffice/src/views/SuppliersPage.tsx), `SupplierForm`, `SupplierRow` e [IncidentsAnalysisPage](../uis/backoffice/src/views/IncidentsAnalysisPage.tsx)
- **Evidencia:** ◐ Leído.
  - Estas pantallas muestran `err.message` tal cual, así que el usuario ve textos como "Missing required columns: …" o "Update would produce an invalid supplier" dentro de una interfaz en español.
  - Si el 500 no trae cuerpo JSON, el mensaje es `response.statusText`, que puede estar vacío con HTTP/2, y la alerta sale sin texto.
- **Impacto:** mensajes poco útiles o en blanco para el usuario final.
- **Corrección breve:** reutilizar `describeError` (ya existe en [errors.ts](../uis/backoffice/src/lib/errors.ts)) en esas pantallas y usar un texto por defecto según el código de estado cuando `statusText` esté vacío.

### E-11 · `scripts/analyze.py` termina con traceback ante entradas habituales
- **Dónde:** [scripts/analyze.py:26-47](../scripts/analyze.py#L26-L47)
- **Evidencia:** ✔ Verificado.
  - Un fichero que no es UTF-8 acaba en `UnicodeDecodeError` (solo se capturan `OSError` y `csv.Error`).
  - Sin entrada interactiva (`</dev/null`, CI o pipe) acaba en `EOFError` en `input()`, después de haber imprimido el informe.
  - ◐ Leído: el fallo al escribir `results.csv` (`OSError` por permisos o disco) tampoco se captura.
  - ◐ Leído: no se llama a `missing_required_columns`, que la API sí usa, así que un CSV con otras columnas imprime un informe con todo inválido en lugar de un error claro.
  - ◐ Leído: se abre con `utf-8` y no `utf-8-sig`, así que un CSV con BOM deja la primera columna como `﻿ticket_id`.
- **Impacto:** el script falla de forma poco clara y con código de salida 1 por excepción en lugar de un mensaje.
- **Corrección breve:** capturar `UnicodeDecodeError`, `EOFError` y el `OSError` de escritura con mensajes y códigos de salida claros. Validar las columnas antes de analizar y leer con `utf-8-sig`. Ver también T-01 (estado desconocido en el CSV).

### E-12 · Valores `NaN` / `Infinity` en JSON dan 500 en proveedores
- **Dónde:** `monthly_rate` en [suppliers/schemas.py](../services/api/suppliers/schemas.py) y el manejador de validación de [core/errors.py](../services/api/core/errors.py)
- **Evidencia:** ✔ Verificado. `monthly_rate: 1e999` o `NaN` devuelve `500` en lugar de `422`. En la prueba la categoría era inválida a propósito, así que el 500 viene de serializar el error de validación. ◐ Leído: con una categoría válida, `1e999` pasaría `gt=0` y podría guardarse como infinito.
- **Impacto:** un cliente malintencionado o un fallo de formato provoca un 500 sin mensaje útil.
- **Corrección breve:** usar `allow_inf_nan=False` en los campos numéricos de dinero.

### E-13 · Concurrencia en TinyDB: handlers `async` con E/S bloqueante y sin lock
- **Dónde:** [users/service.py](../services/api/users/service.py), [profiles/service.py](../services/api/profiles/service.py), [suppliers/service.py](../services/api/suppliers/service.py)
- **Evidencia:** ◐ Leído.
  - Los routers son `async def`, pero llaman a TinyDB (lectura y escritura de fichero) y a bcrypt (CPU) de forma síncrona. Mientras un login se calcula, la API entera espera.
  - `create_user` comprueba el email y luego inserta sin lock. Dos registros simultáneos con el mismo email pueden crear dos cuentas.
  - `incident_store` sí usa lock.
- **Impacto:** la API se congela brevemente bajo carga y puede haber cuentas duplicadas.
- **Corrección breve:** declarar los handlers con `def` (FastAPI los ejecuta en un hilo) y proteger comprobar+insertar con un `RLock`, como ya hace `incident_store`.

---

## Hallazgos de severidad baja

### E-14 · `SECRET_KEY` ausente solo avisa
- **Dónde:** `get_jwt_secret` en [core/config.py](../services/api/core/config.py)
- **Evidencia:** ◐ Leído. Sin la variable genera una clave aleatoria y emite un warning.
- **Impacto:** en producción con varios workers cada uno firma con una clave distinta y las sesiones fallan de forma intermitente. El propio comentario lo admite.
- **Corrección breve:** si existe una variable `ENV=production` (o similar), lanzar `RuntimeError` en lugar de continuar.

### E-15 · Arranque con trazas poco claras ante configuración incorrecta
- **Dónde:** `bootstrap_first_user` ([users/service.py](../services/api/users/service.py)), `get_db()` de suppliers al importar el módulo
- **Evidencia:** ◐ Leído.
  - Un `AUTH_INITIAL_PASSWORD` demasiado corto lanza `ValidationError` con traceback al arrancar.
  - Un `suppliers/db.json` corrupto rompe el `import` de todo el módulo (`get_db()` se ejecuta al final del fichero).
- **Impacto:** el fallo en el arranque es correcto, pero el mensaje no dice qué variable o fichero arreglar.
- **Corrección breve:** capturar el error y relanzarlo con un mensaje que nombre la variable o la ruta.

### E-16 · Registro de errores casi inexistente
- **Dónde:** solo [users/service.py](../services/api/users/service.py), [profiles/service.py](../services/api/profiles/service.py) y [core/config.py](../services/api/core/config.py) usan `logging`
- **Evidencia:** ✔ Verificado por búsqueda en el código.
- **Impacto:** no hay rastro de logins fallidos, 5xx ni de quién hizo qué, lo que impide investigar incidentes.
- **Corrección breve:** loguear (sin datos personales) logins fallidos, errores 5xx con `error_id` y cambios de rol o desactivaciones.

### E-17 · `GET /users/directory` expone a cualquier sesión la lista de usuarios activos
- **Dónde:** [users/router.py](../services/api/users/router.py) (`/directory`)
- **Evidencia:** ✔ Verificado. Devuelve `user_id` y `name` de todos los usuarios activos a cualquier sesión.
- **Impacto:** divulgación menor, ya que está documentado e incluye solo el nombre. Facilita saber quién usa el sistema, sobre todo con registro público abierto.
- **Corrección breve:** confirmar que es un requisito. Si no lo es, restringirlo a admin.

### E-18 · El token vive en `localStorage`
- **Dónde:** [lib/token.ts](../uis/backoffice/src/lib/token.ts)
- **Evidencia:** ◐ Leído. Es una decisión documentada en el propio fichero.
- **Impacto:** cualquier XSS podría robar el token. No se ha encontrado `dangerouslySetInnerHTML` ni `innerHTML` en el código.
- **Corrección breve:** mantenerlo. Añadir cabeceras de seguridad (CSP) en `next.config.mjs` para reducir el riesgo.

### E-19 · Respuestas con eco de entrada del usuario en rutas no protegidas por el manejador
- **Dónde:** [core/errors.py](../services/api/core/errors.py) (`_CREDENTIAL_PATHS`) y 404 de [incident_router.py](../services/api/incidents/incident_router.py)
- **Evidencia:** ✔ Verificado.
  - Suppliers y profiles no están en `_CREDENTIAL_PATHS`, así que su 422 devuelve el `input` rechazado.
  - `GET /api/incidents/%00` responde `404 "Incident \u0000 not found"`, devolviendo el id recibido.
- **Impacto:** bajo hoy. Se vuelve relevante si esas rutas pasan a recibir datos personales.
- **Corrección breve:** aplicar el filtrado de `input` a todos los 422 y no repetir el id recibido en el texto del 404.

### E-20 · Código histórico `src/` de la raíz: sin guardas de entrada
- **Dónde:** [src/utils/](../src/utils/) (`validations.ts`, `search.ts`, `transformations.ts`, `collections.ts`)
- **Evidencia:** ✔ Verificado. Ningún fichero del monorepo lo importa, así que es código muerto, y no contiene ningún `try/catch`.
- **Impacto:** nulo hoy. Si se reutiliza:
  - `validateCandidate` no detecta `NaN` ni `undefined` en los campos numéricos.
  - `findCandidateByEmail` falla con `TypeError` si falta `email`.
  - `binarySearchCandidateBySalary` da resultados erróneos, sin avisar, si el array no está ordenado.
  - Los casos de listas vacías sí están bien resueltos (devuelven 0).
- **Corrección breve:** si se va a usar, validar la entrada. Si no, marcarlo como histórico o retirarlo.

---

---

# Parte 2 — Revisión archivo por archivo

**Criterios aplicados a cada fichero:**
1. **`try/catch` ausente** en operaciones que pueden fallar: `fetch`, llamadas a la API, `await`, lectura de ficheros, parseo de JSON.
2. **`catch` demasiado amplio:** bloques que envuelven una función entera o demasiado código, y que por eso capturan errores que no esperaban.

**Método:** primero localicé con búsquedas todas las operaciones de riesgo (`fetch`, `await`, `.json()`, `JSON.parse`, `open`, `read_text`, `json.loads`, `csv`, `TinyDB(`, `int(`, `UUID(`) y todos los `try/catch/except`. Después leí cada bloque para ver qué envuelve. No hay ningún `except:` desnudo ni `except Exception: pass` en el código Python.

## Hallazgos de `try/catch` ausente

### T-01 · `analyze()` falla con `KeyError` si el estado del CSV no es uno de los tres válidos — **Alta**
- **Dónde:** [packages/shared/incidents_analyzer/.../core.py:199-211](../packages/shared/incidents_analyzer/incidents_analyzer/core.py#L199-L211), usado por `scripts/analyze.py` y por `POST /api/incidents/analyze`
- **Evidencia:** ✔ Verificado.
  - `validate_record` no comprueba que `status` sea `OPEN`, `CLOSED` o `DISCARDED`, pero `analyze` hace `status_counts[status] += 1`.
  - El script termina con `KeyError: 'PENDING'` (estado desconocido), `KeyError: 'closed'` (minúsculas) y `KeyError: 'status'` (columna ausente).
  - La API responde `500` con un CSV que tiene `status = PENDING`.
  - El seed (`seeding.py`) sí protege este caso con su propia comprobación, lo que confirma que la regla falta en el validador compartido.
- **Impacto:** una sola fila con un estado raro tumba todo el análisis en lugar de contarla como inválida.
- **Corrección breve:** añadir al validador una regla `invalid_or_missing_status` (el seed ya la tiene) para que esa fila cuente como inválida y no llegue a `status_counts`.

### T-02 · Apertura y lectura de las bases TinyDB sin ningún `try` — **Alta**
- **Dónde:** `get_db()` en [users/service.py:79](../services/api/users/service.py#L79), [profiles/service.py:41](../services/api/profiles/service.py#L41), [suppliers/service.py:57](../services/api/suppliers/service.py#L57), [incidents/incident_store.py:24](../services/api/incidents/incident_store.py#L24)
- **Evidencia:** ✔ Verificado.
  - Con `users/db.json` corrupto, `POST /auth/login` devuelve `500 Internal Server Error`: nadie puede entrar.
  - Con `suppliers/db.json` corrupto, **el `import` de la API falla** con `JSONDecodeError` y el servidor no arranca (`get_db()` se ejecuta al final de `suppliers/service.py`).
  - ◐ Leído: los fallos de escritura (permisos, disco lleno) tampoco se capturan en ningún `insert`/`update`.
- **Impacto:** un fichero dañado deja la API sin servicio o devuelve errores sin explicación. Es la lectura de ficheros más importante del backend y no tiene manejo de errores.
- **Corrección breve:** envolver solo la creación de `TinyDB(...)` y capturar `json.JSONDecodeError` y `OSError`. Convertirlos en un error de dominio ("base de datos no disponible") que el router traduzca a `503` con un mensaje claro. En proveedores, no abrir la base al importar el módulo.

### T-03 · Respuestas correctas con cuerpo no JSON: `response.json()` sin proteger — **Media**
- **Dónde:** [uis/backoffice/src/lib/api.ts](../uis/backoffice/src/lib/api.ts), líneas 78, 93, 101, 114, 130, 159 y 197 (todos los `return response.json()` de las respuestas con éxito)
- **Evidencia:** ◐ Leído. Solo `toApiError` protege el parseo (para los errores). Si un `200`/`201` llega con HTML o vacío (un proxy mal configurado, una página de login intermedia), `response.json()` lanza `SyntaxError`, que no es un `ApiError`. Las pantallas lo tratan como un fallo genérico y `RegisterPage` dice "Comprueba tu conexión" aunque la cuenta **sí** se haya creado.
- **Segundo punto:** en [`login()`](../uis/backoffice/src/lib/api.ts#L78) `const { access_token } = await response.json()` no comprueba que exista `access_token`. Si falta, `setToken(undefined)` guarda el texto `"undefined"` como token.
- **Corrección breve:** una función `parseJson(response)` con `try/catch` que lance `ApiError("Respuesta no válida del servidor", status)`, usada en todos esos puntos. Comprobar que `access_token` es un `string` no vacío.

### T-04 · `setToken` esconde que el almacenamiento falló, y el login dice "contraseña incorrecta" — **Media**
- **Dónde:** [lib/token.ts:15-22](../uis/backoffice/src/lib/token.ts#L15-L22) y [`login()`](../uis/backoffice/src/auth/AuthContext.tsx#L95-L100) en `AuthContext.tsx`
- **Evidencia:** ◐ Leído.
  - Si `localStorage.setItem` falla (modo privado, almacenamiento bloqueado, cuota llena), el `catch` lo ignora y `setToken` termina como si todo hubiera ido bien.
  - `login()` sigue con `fetchMe()`, que ya no tiene token, y recibe un `401`.
  - [LoginPage](../uis/backoffice/src/views/LoginPage.tsx#L41-L46) interpreta cualquier `401` como "Email o contraseña incorrectos, o la cuenta está desactivada", aunque las credenciales fueran correctas.
- **Impacto:** un usuario con el almacenamiento bloqueado no puede entrar y le dicen que se equivoca de contraseña.
- **Corrección breve:** que `setToken` devuelva `false` (o lance) si no pudo guardar, y que `login()` muestre "Tu navegador bloquea el almacenamiento; no se puede iniciar sesión".

### T-05 · `contract.py` solo captura `FileNotFoundError` — **Baja**
- **Dónde:** [contract.py:24-31](../packages/shared/incidents_analyzer/incidents_analyzer/contract.py#L24-L31)
- **Evidencia:** ◐ Leído. Se lee y parsea `contract.json` al importar el paquete. Un JSON inválido (`json.JSONDecodeError`) o un fichero sin permisos (`PermissionError`) escapan con traceback y rompen el arranque de la API y de los scripts.
- **Corrección breve:** capturar `(OSError, json.JSONDecodeError)` y relanzar `RuntimeError` con la ruta del fichero.

### T-06 · Scripts de línea de comandos sin captura en pasos que tocan ficheros — **Baja**
- **Dónde:**
  - [scripts/seed_incidents.py:62-64](../scripts/seed_incidents.py#L62-L64): `TinyDB(args.db)` y `seeding.seed_rows(...)`.
  - [services/api/seed.py](../services/api/seed.py): `TinyDB(path)`.
  - [services/api/auth/cli.py:23](../services/api/auth/cli.py#L23): `getpass.getpass(...)`.
- **Evidencia:** ◐ Leído. Una base corrupta o sin permisos, o `Ctrl+C`/`EOF` al pedir la contraseña, terminan con traceback. `seed_incidents.py` sí protege bien la lectura del CSV, que es el ejemplo a seguir.
- **Corrección breve:** capturar `OSError`/`JSONDecodeError`/`EOFError`/`KeyboardInterrupt` en el `main()` de cada uno, con un mensaje y un código de salida.

### T-07 · Si `fetchMe()` falla justo después del login, el token queda guardado — **Baja**
- **Dónde:** `login` en [AuthContext.tsx:95-100](../uis/backoffice/src/auth/AuthContext.tsx#L95-L100)
- **Evidencia:** ◐ Leído. `apiLogin` guarda el token y después `fetchMe()` puede fallar (red, `500`). La pantalla muestra "No se pudo iniciar sesión" pero el token sigue en `localStorage`; al recargar, la sesión aparece abierta.
- **Corrección breve:** si `fetchMe()` falla dentro de `login`, llamar a `clearToken()` antes de relanzar el error.

### T-08 · `await file.read()` sin `try` en la subida de CSV — **Baja**
- **Dónde:** [incidents/router.py:25](../services/api/incidents/router.py#L25)
- **Evidencia:** ◐ Leído. Si el cliente corta la conexión durante la subida, la excepción sale como `500`. Además lee el fichero entero en memoria (ver E-02, donde se verificó el `csv.Error` sin capturar).
- **Corrección breve:** capturar el error de lectura y responder `400`. Combinarlo con el límite de tamaño de E-02.

## Hallazgos de `catch` demasiado amplio

### C-01 · El `try` abarca también la acción que se ejecuta *después* de guardar — **Media**
- **Dónde:**
  - [IncidentForm.tsx:84-106](../uis/backoffice/src/components/incidents/IncidentForm.tsx#L84-L106): `onSaved(await createIncident(...))`.
  - [StatusActions.tsx:59-75](../uis/backoffice/src/components/incidents/StatusActions.tsx#L59-L75): `reset(); onChanged(updated)`.
  - [SupplierForm.tsx:50-65](../uis/backoffice/src/components/suppliers/SupplierForm.tsx#L50-L65): `onCreated(created)`.
  - [SuppliersPage.tsx:33-39](../uis/backoffice/src/views/SuppliersPage.tsx#L33-L39) y [SuppliersPage.tsx:43-48](../uis/backoffice/src/views/SuppliersPage.tsx#L43-L48): `replace(await ...)`.
- **Evidencia:** ◐ Leído. La llamada a la API y la reacción de la pantalla están dentro del mismo `try`. Si el servidor guarda bien pero la función de reacción (`onSaved`, `onChanged`, `replace`) lanza una excepción, el `catch` muestra "No se pudo crear la incidencia" aunque **ya se creó**.
- **Impacto:** el usuario reintenta y crea duplicados (incidencias, proveedores), o cree que un cambio de estado no se aplicó.
- **Corrección breve:** dejar dentro del `try` solo la llamada a la API (`const created = await createIncident(...)`) y llamar a `onSaved(created)` fuera.

### C-02 · `restoreSession` captura con el mismo `.catch` el fallo de red y los fallos de la propia pantalla — **Media** (amplía E-08)
- **Dónde:** [AuthContext.tsx:42-54](../uis/backoffice/src/auth/AuthContext.tsx#L42-L54)
- **Evidencia:** ◐ Leído. En `fetchMe().then(...).catch(...)`, el `.catch` recoge tanto el error de la llamada como cualquier excepción dentro del `.then` (`setUser`, `setStatus`). Todo acaba en `clearToken()`.
- **Impacto:** además de lo descrito en E-08, un error de programación en el `.then` también cierra la sesión del usuario sin dejar rastro.
- **Corrección breve:** distinguir el error por tipo (`ApiError` con `status === 401`) y registrar el resto.

### C-03 · `toApiError` mete el parseo y la transformación en el mismo `try` — **Baja**
- **Dónde:** [api.ts:29-44](../uis/backoffice/src/lib/api.ts#L29-L44)
- **Evidencia:** ◐ Leído. El `try` envuelve `await response.json()` **y** todo el `.map(...)` que construye los mensajes. Un fallo dentro del `.map` (por ejemplo `body` nulo, o un `loc` raro) se traga sin avisar y cae a `response.statusText`, que puede estar vacío (E-10).
- **Corrección breve:** dejar dentro del `try` solo `await response.json()`.

### C-04 · `AuthContext.register` ignora cualquier error del login automático — **Baja**
- **Dónde:** [AuthContext.tsx:104-112](../uis/backoffice/src/auth/AuthContext.tsx#L104-L112)
- **Evidencia:** ◐ Leído. El `catch {}` sin variable captura todo (red caída, `401`, errores de programación) y devuelve `"created"`. La decisión es razonable, porque la cuenta existe, pero no queda ningún registro de la causa.
- **Corrección breve:** capturar `err` y registrarlo con `console.warn` (o equivalente).

### C-05 · `.catch(() => undefined)` sin explicación en dos pantallas — **Baja**
- **Dónde:** [IncidentsPage.tsx:79](../uis/backoffice/src/views/IncidentsPage.tsx#L79) (con comentario) y [IncidentDetailPage.tsx:52](../uis/backoffice/src/views/IncidentDetailPage.tsx#L52) (sin comentario)
- **Evidencia:** ◐ Leído. El fallo al cargar las listas desplegables se descarta en silencio. Es razonable porque solo rellena desplegables, pero el usuario ve desplegables vacíos sin ningún aviso.
- **Corrección breve:** poner el mismo comentario en la segunda y mostrar un aviso discreto ("No se pudieron cargar las opciones de los filtros").

### C-06 · `except Exception` al deshacer el alta de usuario — **Baja**
- **Dónde:** [users/service.py:138-145](../services/api/users/service.py#L138-L145)
- **Evidencia:** ◐ Leído. Es el único `except Exception` del backend. El bloque `try` envuelve una sola llamada (`ensure_profile`), deshace el alta y **relanza**, así que el uso es correcto. El riesgo es que, si el `remove(...)` del rollback también falla, esa segunda excepción tapa la original.
- **Corrección breve:** proteger el `remove` con su propio `try/except` que registre el fallo y deje salir la excepción original.

### C-07 · `except ValueError` del seed atribuye cualquier `ValueError` a "fecha inválida" — **Baja**
- **Dónde:** [incidents/seeding.py:135-140](../services/api/incidents/seeding.py#L135-L140)
- **Evidencia:** ◐ Leído. El `try` envuelve toda la construcción del documento (`to_document`). `ValidationError` ya se captura antes (es subclase de `ValueError`), pero cualquier otro `ValueError` (por ejemplo `int(score)`) se informaría como `invalid_date`.
- **Impacto:** hoy no ocurre porque la puntuación se valida antes, pero el mensaje sería engañoso si cambia.
- **Corrección breve:** parsear la fecha en una línea aparte con su propio `try` y dejar el resto sin `except ValueError`.

## Ficheros revisados sin hallazgos relevantes

| Fichero | Qué se comprobó | Resultado |
|---|---|---|
| `api.ts` → `apiFetch` | `try` de una sola sentencia (`fetch`) | Bien acotado |
| `token.ts` (`getToken`, `clearToken`) | `try` de una sola sentencia sobre `localStorage` | Bien (ver T-04 solo para `setToken`) |
| `LoginPage`, `RegisterPage`, `ProfilePage` | `try/catch/finally` con `setSubmitting(false)` en `finally` | Bien |
| `IncidentsAnalysisPage` | Dos `try/catch/finally` (analizar, exportar) | Bien |
| `IncidentsPage`, `IncidentDetailPage` (carga) | `.then/.catch/.finally` con control de peticiones obsoletas | Bien |
| `SupplierRow` | `catch {}` vacío con comentario: el error ya lo muestra la página | Aceptable |
| Routers de la API (`users`, `suppliers`, `incidents`, `profiles`) | Cada `try` envuelve una sola llamada y captura excepciones de dominio concretas, no `Exception` | Bien |
| `auth/security.py` | `except ValueError` y `except (JWTError, KeyError, ValueError)`, con lista concreta | Bien |
| `core/config.py` (`int(raw)`) | `except ValueError` concreto, y relanza un error claro | Bien |
| `scripts/seed_incidents.py` (lectura del CSV) | `except (OSError, UnicodeDecodeError, csv.Error)` | Bien, es el modelo a seguir |
| `core.py` → `_parse_int` | `try` de una línea con `except ValueError` | Bien |
| `uis/website` (`App.tsx`, `main.tsx`) | Sin `fetch`, sin `JSON.parse` (ver E-04) | Sin operaciones asíncronas que proteger |
| `packages/shared/types`, `src/` (raíz) | Sin E/S ni `await` | Sin operaciones asíncronas que proteger |

---

# Parte 3 — Fallos silenciosos

**Criterio:** errores capturados pero ignorados. Se buscaron tres patrones: `catch {}` vacío, `except: pass` y logs sin acción (un aviso que se escribe y después el programa sigue como si nada).

**Método:** listé todos los bloques `catch`/`.catch(` del frontend y todos los `except` del backend con sus primeras líneas, y todas las llamadas a `logger.*`, `print` y `console.*`. Después lo comprobé ejecutando lo que se podía.

**Resultado del inventario:**
- **`except: pass` o `except Exception: pass` en Python:** ninguno. Todos los `except` del backend relanzan, traducen el error a una respuesta HTTP o devuelven un valor con significado concreto.
- **`catch` sin variable en TypeScript (no recogen el error):** 7. Son `api.ts` ×2, `token.ts` ×3, `SupplierRow.tsx` ×1 y `AuthContext.tsx` ×1. De ellos, 4 tienen el cuerpo vacío (solo un comentario): `api.ts:44`, `token.ts:18`, `token.ts:27` y `SupplierRow.tsx:40`. Los otros 3 devuelven un valor o lanzan otro error sin conservar la causa.
- **`.catch(() => …)` que no usan el error:** 2 con `undefined` (`IncidentsPage`, `IncidentDetailPage`) y 2 con efecto (`AuthContext.tsx:49`, que cierra la sesión, y `ProfilePage.tsx:46`, que muestra un aviso).
- Los analizo uno a uno a continuación.
- **`console.*` en el frontend:** ninguno. El frontend no registra ningún error en ninguna parte.
- **Logs en el backend:** 6 llamadas a `logger.*` en 3 ficheros, todas de arranque. No hay ningún log en los caminos de error de las peticiones (login fallido, token inválido, 5xx).

## Mapa: fallos silenciosos que ya estaban en el informe

Para no contarlos dos veces, estos hallazgos anteriores también son fallos silenciosos:

| Hallazgo | Qué se ignora en silencio |
|---|---|
| E-04 | La web dice "Hemos recibido tu información" y los datos **se pierden**: es el fallo silencioso más grave de todo el repositorio |
| E-14 | `SECRET_KEY` ausente: un `logger.warning` y el servidor sigue con una clave aleatoria |
| E-16 | Logins fallidos, 5xx y cambios de rol: no dejan ningún rastro |
| T-04 | `setToken` ignora que no pudo guardar y después el login dice "contraseña incorrecta" |
| T-07 | `fetchMe()` falla tras el login y el token se queda guardado |
| C-02 / E-08 | `restoreSession` ignora el error y cierra la sesión |
| C-03 | `toApiError` ignora el fallo de parseo y pierde el mensaje del servidor |
| C-04 | El login automático tras el registro falla y no queda constancia de la causa |
| C-05 | `.catch(() => undefined)` en las listas desplegables |

## Hallazgos nuevos

### S-01 · `apiFetch` convierte cualquier fallo de `fetch` en "sin respuesta" y descarta la causa — **Media**
- **Dónde:** [api.ts:58-63](../uis/backoffice/src/lib/api.ts#L58-L63)
- **Evidencia:** ◐ Leído.
  - El `catch {}` no recoge la excepción original: la sustituye siempre por `ApiError("No response from the server", 0)`.
  - Con eso se confunden tres casos: red caída, el 500 sin cabeceras CORS de E-01 (que el navegador bloquea) y un error de configuración.
  - Nada queda en `console` ni en ningún otro sitio.
- **Impacto:** el usuario ve "No se pudo conectar" y el equipo no tiene ninguna pista para distinguir un corte de red de un fallo del servidor.
- **Corrección breve:** capturar `err` y conservarla (`new ApiError("…", 0, {}, { cause: err })`) y escribirla con `console.warn` mientras no haya otro sistema de registro.

### S-02 · "Cerrar sesión" puede no cerrar nada y nadie se entera — **Media**
- **Dónde:** `clearToken` en [token.ts:23-31](../uis/backoffice/src/lib/token.ts#L23-L31), usado por `logout` en [AuthContext.tsx:126-129](../uis/backoffice/src/auth/AuthContext.tsx#L126-L129)
- **Evidencia:** ◐ Leído.
  - Si `localStorage.removeItem` lanza un error, el `catch` lo ignora y avisa a los oyentes igualmente.
  - `AuthContext` solo da la sesión por terminada si `getToken()` devuelve vacío. El token sigue guardado, así que el usuario sigue dentro.
  - La pantalla no muestra ningún aviso.
- **Impacto:** en un ordenador compartido el usuario cree que cerró la sesión y su token sigue activo hasta que caduque (30 minutos por defecto).
- **Corrección breve:** que `clearToken` indique si pudo borrar, y que `logout` informe del fallo ("No se pudo cerrar la sesión: cierra el navegador").

### S-03 · El registro de eventos del backend no está configurado: los logs de nivel INFO no se ven — **Media**
- **Dónde:** `logging.getLogger(__name__)` en `users/service.py`, `profiles/service.py` y `core/config.py`. No hay ninguna configuración de logging en `services/api`.
- **Evidencia:** ✔ Verificado.
  - No existe `basicConfig` ni `dictConfig` en ningún fichero de la API.
  - Reproduje la situación con un `logger` sin configurar: el `warning` se imprime (por el mecanismo de último recurso de Python), pero el `info` **no aparece**.
  - Por eso no se ve nunca "Bootstrapped first user…" ni "Migrated N legacy user document(s)…".
- **Impacto:** las migraciones de datos al arrancar, que modifican ficheros, ocurren sin ninguna constancia. Los avisos que sí salen no llevan fecha ni nivel.
- **Corrección breve:** llamar a `logging.basicConfig(level=..., format=...)` una vez al arrancar (nivel configurable con una variable de entorno).

### S-04 · Logs sin acción: el servidor arranca igual aunque el aviso describa una situación grave — **Media**
- **Dónde:** [core/config.py:75](../services/api/core/config.py#L75) (`SECRET_KEY` ausente) y [users/service.py:229-233](../services/api/users/service.py#L229-L233) (sin usuarios)
- **Evidencia:** ✔ Verificado por lectura y por S-03.
  - Sin `SECRET_KEY`: `logger.warning` y arranca con una clave aleatoria (E-14).
  - Sin usuarios ni `AUTH_INITIAL_EMAIL`/`AUTH_INITIAL_PASSWORD`: el mensaje dice literalmente "nobody can log in", pero la API arranca. Como el registro público solo crea usuarios con rol `user`, **nadie podrá ser administrador** hasta que alguien lea el log y ejecute `create-user`.
- **Impacto:** el aviso no desencadena nada: ni detiene el arranque ni cambia el comportamiento ni avisa a un humano.
- **Corrección breve:** hacer que el arranque falle (`RuntimeError`) en producción, o que `/health` devuelva un estado "degradado" mientras no haya administrador.

### S-05 · Reparaciones y borrados de datos al arrancar, sin ningún registro — **Media**
- **Dónde:** `sync_profiles` en [users/service.py:211-219](../services/api/users/service.py#L211-L219); `ensure_profile` en [profiles/service.py](../services/api/profiles/service.py), que `/auth/me` llama en cada petición
- **Evidencia:** ◐ Leído.
  - Al arrancar, `sync_profiles` **borra** los perfiles huérfanos (`delete_profile(orphan)`) y **crea** los que faltan, sin escribir una sola línea de log.
  - `/auth/me` "se autorrepara" del mismo modo.
- **Impacto:** si un fallo (un `users/db.json` vacío o corrupto) hace que parezca que sobran perfiles, se borran **datos de personas** y no queda rastro de que ocurrió.
- **Corrección breve:** registrar cada borrado y cada creación (con el `user_id`, nunca con el email ni el nombre) y no borrar si la tabla de usuarios está vacía.

### S-06 · Las funciones de autenticación devuelven `None`/`False` sin distinguir la causa ni registrarla — **Media** (amplía E-16)
- **Dónde:** [auth/security.py:21-25](../services/api/auth/security.py#L21-L25), [security.py:45-56](../services/api/auth/security.py#L45-L56), [auth/service.py:15-22](../services/api/auth/service.py#L15-L22)
- **Evidencia:** ◐ Leído.
  - `verify_password` captura `ValueError` y devuelve `False`. Si el hash guardado de un usuario está dañado, ese usuario no podrá entrar nunca y recibirá "Incorrect email or password", sin que nada quede registrado.
  - `decode_access_token` devuelve `None` para un token caducado, uno manipulado, uno con el algoritmo cambiado o uno sin `exp`. Son situaciones distintas y no se registra ninguna.
- **Impacto:** un token manipulado, que podría ser un intento de ataque, es indistinguible de uno caducado. Una cuenta dañada parece una contraseña olvidada.
- **Corrección breve:** devolver el motivo (o registrar un `warning` por categoría) sin incluir el token ni la contraseña. Mantener la misma respuesta al usuario.

### S-07 · El frontend no registra ningún error y la pantalla de error ignora el error recibido — **Baja**
- **Dónde:** [app/(app)/error.tsx:4](../uis/backoffice/src/app/(app)/error.tsx#L4) y todo `uis/backoffice/src`
- **Evidencia:** ✔ Verificado.
  - No hay ninguna llamada a `console.*` en el frontend.
  - `AppError` recibe `error` (con su `digest`) y no lo usa: la firma lo declara y el cuerpo lo ignora.
  - Los errores solo se muestran al usuario; nunca se registran ni se reportan.
- **Impacto:** si un usuario ve "Algo ha salido mal", el equipo no tiene ni el error ni una referencia para localizarlo en el servidor.
- **Corrección breve:** mostrar `error.digest` ("referencia: …") en esa pantalla y escribir el error con `console.error` en un `useEffect`.

### S-08 · Guardar una tarifa vacía no hace nada y no avisa — **Baja**
- **Dónde:** `submitRate` en [SupplierRow.tsx:32-35](../uis/backoffice/src/components/suppliers/SupplierRow.tsx#L32-L35)
- **Evidencia:** ◐ Leído. `if (!(value > 0)) return;` sale sin mensaje. El campo tiene `min="0.01"` pero no `required`, y el navegador acepta un `type="number"` vacío (`Number("")` es `0`). El usuario pulsa Guardar y no ocurre nada.
- **Corrección breve:** mostrar un mensaje ("Introduce una tarifa mayor que 0") o añadir `required` al campo.

### S-09 · Si se sueltan varios ficheros en la zona de subida, solo se usa el primero y no se avisa — **Baja**
- **Dónde:** `handleFiles` en [CsvUploader.tsx:13-16](../uis/backoffice/src/components/incidents/CsvUploader.tsx#L13-L16)
- **Evidencia:** ◐ Leído. `files?.[0]` descarta el resto sin comentario.
- **Corrección breve:** si `files.length > 1`, mostrar "Solo se analiza un archivo a la vez".

### S-10 · `seed_incidents.py` termina con éxito aunque no haya podido verificar el resultado — **Baja**
- **Dónde:** [scripts/seed_incidents.py:75-79](../scripts/seed_incidents.py#L75-L79)
- **Evidencia:** ◐ Leído. Si la base ya contiene incidencias que no vienen del CSV, imprime "Summary check skipped…" y devuelve `0`. Un script de CI vería "éxito" sin que se haya comprobado nada. (La salida sí es visible en consola, por eso es de severidad baja.)
- **Corrección breve:** devolver un código distinto (por ejemplo `2`) cuando la verificación se omite.

## `catch` vacíos y silenciosos que se consideran aceptables

| Dónde | Por qué es aceptable |
|---|---|
| [token.ts:8-13](../uis/backoffice/src/lib/token.ts#L8-L13) `getToken` | Es un valor de reserva documentado: almacenamiento bloqueado equivale a "sin sesión" |
| [SupplierRow.tsx:36-41](../uis/backoffice/src/components/suppliers/SupplierRow.tsx#L36-L41) `catch {}` | Tiene comentario y el error ya lo muestra `SuppliersPage` antes de relanzarlo |
| [IncidentsPage.tsx:79](../uis/backoffice/src/views/IncidentsPage.tsx#L79) `.catch(() => undefined)` | Tiene comentario: solo rellena desplegables y la lista informa de los errores reales |
| [security.py:55](../services/api/auth/security.py#L55) `return None` | Es el contrato de la función (token válido o nada), aunque conviene registrar la causa (S-06) |
| `seeding.py` y `core.py` (`return ["invalid_date"]`, `_parse_int` → `None`) | No ignoran el error: lo convierten en una regla incumplida que se cuenta y se muestra |

---

# Parte 4 — Errores en crudo

**Criterio:** mensajes técnicos que podrían llegar al usuario: trazas de pila, códigos HTTP, errores de parseo y mensajes internos del servidor.

**Método (de extremo a extremo, con pruebas reales):**
1. Inventario de todos los sitios del frontend que muestran un texto que viene del servidor (`err.message`, `statusText`, `describeError`) y de todos los textos que el backend puede enviar (`detail=`, `str(exc)`, validadores de Pydantic).
2. Provoqué **28 respuestas de error reales** de la API con peticiones incorrectas (ruta inexistente, JSON mal formado, campos que faltan, ficheros erróneos, tokens falsos, permisos) y las guardé.
3. Pasé cada una por el **código real del frontend** (`toApiError` y `describeError`, copiados literalmente) para ver el texto exacto que vería la persona, en cada pantalla.

## Lo que NO llega en crudo (comprobado)

- **Trazas de pila:** ninguna. Un fallo inesperado devuelve únicamente `Internal Server Error`, sin traceback, ruta ni nombre de excepción.
- **Excepciones de JavaScript** (`SyntaxError`, `TypeError`…): nunca se muestran. Todas las pantallas comprueban `err instanceof ApiError` y, si no lo es, usan un texto fijo en español. Por eso un error de parseo de la respuesta (T-03) no se enseña tal cual.
- **Login:** [LoginPage](../uis/backoffice/src/views/LoginPage.tsx) usa dos textos fijos en español y no pinta nada del servidor.
- **Contraseñas y emails** de las rutas `/auth`, `/users` e `/api/incidents`: los 422 no devuelven el valor rechazado.
- **Códigos HTTP como número:** ningún componente muestra `status` al usuario.

## Mapa: lo ya reportado que también es un error en crudo

| Hallazgo | Qué llega en crudo |
|---|---|
| E-01 | El 500 sin controlar: texto plano `Internal Server Error` |
| E-10 | `statusText` vacío con HTTP/2: alerta sin texto |
| E-11, T-01, T-06 | En los scripts de terminal: `KeyError: 'PENDING'`, `UnicodeDecodeError`, `EOFError` con traceback |
| E-19 | Los 422 de proveedores y perfiles devuelven el `input` rechazado |
| S-07 | `error.tsx` ignora la referencia (`digest`) que recibe |

## Hallazgos nuevos

### R-01 · Proveedores y análisis de CSV muestran el texto del servidor sin traducir — **Media**
- **Dónde:** `err.message` en [SuppliersPage.tsx:24,36,46](../uis/backoffice/src/views/SuppliersPage.tsx#L24), [SupplierForm.tsx:64](../uis/backoffice/src/components/suppliers/SupplierForm.tsx#L64) e [IncidentsAnalysisPage.tsx:26,38](../uis/backoffice/src/views/IncidentsAnalysisPage.tsx#L26)
- **Evidencia:** ✔ Verificado. Respuestas reales del servidor pasadas por el frontend:

| Situación | Texto que ve la persona |
|---|---|
| API caída o red cortada | `No response from the server` |
| Fallo inesperado del servidor | `Internal Server Error` (con HTTP/2, vacío) |
| Se suelta un `.txt` en la zona de subida (`accept` solo filtra el selector, no el arrastrar) | `Expected a .csv file, got: notas-juan.txt` |
| CSV sin las columnas esperadas | `Missing required columns: ticket_id, date, client_company, category, description, agent_id, status, customer_email, satisfaction_score` |
| CSV sin filas | `CSV file has a header row but no data rows.` |
| CSV que no es UTF-8 | `File is not valid UTF-8 text.` |
| Descargar tras reiniciar la API | `No analysis has been run yet. Call POST /api/incidents/analyze first.` (menciona **un método HTTP y un endpoint**) |
| Proveedor borrado por otra persona | `Supplier 9999 not found` |

- **Impacto:** la interfaz es en español y estos mensajes salen en inglés, con jerga técnica (`POST /api/incidents/analyze`) y nombres internos de columnas. El caso del 500 y el de la API caída son los más probables.
- **Corrección breve:** usar `describeError` también en estas pantallas, y ampliarla con textos en español para los fallos de CSV (columnas, vacío, formato). Con `status === 0` y `>= 500` ya devuelve mensajes correctos.

### R-02 · Los mensajes de validación de Pydantic llegan al usuario, con el nombre técnico del campo — **Media**
- **Dónde:** `toApiError` en [api.ts:32-43](../uis/backoffice/src/lib/api.ts#L32-L43) (fabrica `campo: mensaje`), [IncidentForm.tsx:101-106](../uis/backoffice/src/components/incidents/IncidentForm.tsx#L101-L106), [RegisterPage.tsx:44-58](../uis/backoffice/src/views/RegisterPage.tsx#L44-L58) y `describeError` (rama por defecto: `return err.message`)
- **Evidencia:** ✔ Verificado con un caso alcanzable con datos normales.
  - Un email como `cliente@empresa.test` (o `ana@nexova.test`) **pasa** la validación del navegador (la expresión regular lo acepta) y **lo rechaza la API**.
  - En el formulario de incidencias aparece, bajo el campo y en el aviso general: `customer_email: value is not a valid email address: The part after the @-sign is a special-use or reserved name that cannot be used with email.`
  - En el registro, bajo el campo email: `value is not a valid email address: The part after the @-sign is a special-use or reserved name that cannot be used with email.`
  - Otros mensajes del mismo tipo salen si la validación del navegador no los cubre: `title: String should have at most 120 characters`, `monthly_rate: Input should be greater than 0`, `supplier_id: Input should be a valid integer, unable to parse string as an integer`.
  - Con un cuerpo JSON mal formado, el nombre del campo sale como un número: `1: JSON decode error`. No es alcanzable desde la interfaz, pero muestra que `toApiError` formatea cualquier cosa.
- **Impacto:** nombres de campo en inglés y frases de la librería de validación, que el usuario no sabe interpretar. En el caso del email, además, **la persona no sabe qué cambiar**.
- **Corrección breve:** traducir por el tipo de error y el campo (la rama `feature/incident-manager` ya tiene `friendlyFieldError` para esto) y alinear la validación del navegador con la del servidor para el email.

### R-03 · La documentación interactiva y el esquema de la API son públicos — **Baja**
- **Dónde:** `FastAPI(title="Nexova API", ...)` en [main.py:36](../services/api/main.py#L36) (documentación activada por defecto)
- **Evidencia:** ✔ Verificado. Sin ninguna sesión, `/docs`, `/redoc` y `/openapi.json` devuelven `200`, y el esquema lista **22 rutas** con sus formatos de entrada, de salida y de error.
- **Impacto:** cualquiera puede ver cómo está construida la API interna, qué campos acepta y cómo responde a cada fallo. Es información que facilita probar ataques, aunque no incluye secretos.
- **Corrección breve:** desactivarlo fuera de desarrollo (`docs_url=None, redoc_url=None, openapi_url=None` cuando una variable de entorno indique producción).

### R-04 · Los textos de las excepciones de dominio son el contrato público de la API — **Baja**
- **Dónde:** el patrón `raise HTTPException(..., detail=str(exc))`, repetido en unos 25 sitios de los routers de `users`, `suppliers`, `incidents` y `profiles`
- **Evidencia:** ✔ Verificado por lectura y por las pruebas. El texto de la excepción (`"Supplier 9999 not found"`, `"A user with email 'admin@nexova.com' already exists"`, `"Cannot demote, deactivate or delete the last active admin"`) sale tal cual por la red y algunos incluyen datos de la petición (un email, un identificador).
- **Impacto:** cambiar la redacción de una excepción cambia lo que ve el cliente, y el frontend no puede traducir un texto libre de forma fiable. Ya obliga a que `RegisterPage` dependa del código `409` en vez de entender el mensaje.
- **Corrección breve:** añadir un `code` estable a cada error (por ejemplo `email_taken`, `supplier_not_found`) junto al texto, para que el frontend elija su propio mensaje en español.

## Qué mensajes están bien resueltos

| Dónde | Por qué |
|---|---|
| `describeError` (códigos `0`, `>=500`, `403`, `404`, `409`) | Convierte el código en una frase en español sin enseñar el número |
| `RegisterPage.fromApiError` (`409`) | Traduce el conflicto a "Ya existe una cuenta con ese email." |
| `LoginPage` | Dos textos fijos; no depende del servidor |
| Pantallas que usan `instanceof ApiError` con texto de reserva | Los errores de JavaScript nunca se enseñan |
| 422 de `/auth`, `/users`, `/api/incidents` | No devuelven el valor rechazado |

---

# Parte 5 — Filtración de datos sensibles

**Criterio:** errores o logs que exponen claves secretas, cadenas de conexión, rutas internas o datos personales.

**Método:**
1. **Repositorio e historial completo** (todas las ramas): ficheros sensibles, patrones de secretos (`SECRET_KEY=`, claves privadas, tokens de GitHub, claves de nube, cadenas de conexión a bases de datos), credenciales de ejemplo y rutas internas.
2. **Capturas de pantalla** subidas al repositorio: las miré una a una.
3. **Servidor real:** arranqué la API con `uvicorn` sobre bases de datos temporales y provoqué fallos para leer lo que escribe en su log. También comprobé qué datos entrega cada endpoint a distintos tipos de cuenta.

## Lo que NO se filtra (comprobado)

| Qué se buscó | Resultado |
|---|---|
| **Secretos en el historial** (todas las ramas) | Ninguno. Lo único que coincide es el marcador `AUTH_INITIAL_PASSWORD='choose-a-password'` de un README antiguo |
| **Cadenas de conexión** | No existen: la API usa ficheros TinyDB, sin URL de base de datos, usuario ni contraseña |
| **Ficheros `.env` o bases de datos subidos** | Ninguno. Solo hay `.env.example` con los valores vacíos. `db.json` y `.env` están ignorados por Git |
| **Hash de contraseña en las respuestas** | Ninguna. Comprobé `/auth/me`, `/users`, `/profiles`, `/users/directory`, `/api/incidents` y el detalle: no aparece `hashed_password` ni ningún `$2b$` |
| **Rutas internas en las respuestas HTTP** | Ninguna en las 28 respuestas de error de la Parte 4 ni en un 500 real |
| **Valor de `SECRET_KEY` en los errores** | No aparece: los mensajes de `get_jwt_secret` solo hablan de la longitud |
| **Contenido del token** | Solo `user_id` y `exp` |
| **Email del cliente en la lista** | Enmascarado (`e***@dominio`) y no se puede buscar por él |
| **Capturas de pantalla** (`docs/screenshots/`) | Limpias: sin emails, nombres ni rutas. Solo se ve el prefijo `codespace:` |
| **`scripts/seed_incidents.py` y `analyze.py`** | Nunca imprimen emails; al rechazar filas solo muestran línea, id y regla incumplida |
| **Línea de comandos `create-user`** | Ya usa `include_input=False` para no mostrar la contraseña en sus errores |

## Hallazgos

### D-01 · La contraseña inicial del administrador se escribe en el log de arranque — **Alta**
- **Dónde:** `bootstrap_first_user` en [users/service.py:234](../services/api/users/service.py#L234), llamada desde el arranque en [main.py](../services/api/main.py)
- **Evidencia:** ✔ Verificado. Arranqué el servidor con `AUTH_INITIAL_PASSWORD='abc'` (demasiado corta) y el log contiene:
  ```
  pydantic_core._pydantic_core.ValidationError: 1 validation error for UserCreate
  password
    String should have at least 8 characters [type=string_too_short, input_value='abc', input_type=str]
  ```
  Pydantic imprime el valor rechazado y la API no captura el error.
- **Impacto:** es la **única credencial real** del sistema y justo en el caso en que alguien la teclea mal (por ejemplo 7 caracteres, casi la correcta) queda en claro en los logs, que suelen enviarse a herramientas compartidas. Los valores cortos salen enteros. Los largos salen recortados por el centro, pero se siguen viendo unos 24 caracteres del principio y otros 24 del final (lo comprobé con una contraseña de 100 caracteres).
- **Corrección breve:** capturar `ValidationError` en `bootstrap_first_user` y relanzar un `RuntimeError("AUTH_INITIAL_PASSWORD no es válida: …")` con `exc.errors(include_input=False)`. La CLI [auth/cli.py](../services/api/auth/cli.py) ya lo hace así. Es el mismo patrón que hay que respetar al implementar la corrección de E-01 (registrar el error de un 500): no escribir `str(exc)` de un error de validación sin quitar el `input`.

### D-02 · Cualquiera que se registre puede leer los emails completos de clientes y empleados — **Alta**
- **Dónde:** `POST /users` público ([users/router.py:47](../services/api/users/router.py#L47)), `GET /api/incidents/{id}` ([incident_router.py:100](../services/api/incidents/incident_router.py#L100)), `HistoryTimeline` en [HistoryTimeline.tsx:39](../uis/backoffice/src/components/incidents/HistoryTimeline.tsx#L39)
- **Evidencia:** ✔ Verificado de extremo a extremo con un desconocido:
  1. Se registra sin aprobación: `201 "Account created. You can sign in now."`, rol `user`, activa al instante.
  2. Pide el detalle de una incidencia: `200`, con `customer_email: maria.garcia@cliente-real.com` **completo** y el historial con `actor: admin@nexova.com` (el email del empleado que la creó).
  3. También recibe `200` en la lista de proveedores y el directorio con los nombres de todos los usuarios.
  4. Solo se le niega lo que exige rol de administrador (`/users` → `403`).
- **Impacto:** los datos personales de los clientes (nombre en el email, empresa) y los emails de los empleados quedan al alcance de **cualquier persona de internet** que cree una cuenta. La lista enmascara el email del cliente, pero esa protección se anula con una sola petición más. Ningún router de incidencias ni de proveedores comprueba el rol (el código lo admite: "there are no roles").
- **Corrección breve:** mantener el email del cliente enmascarado también en el detalle salvo para administradores, no devolver el `actor` completo (usar el nombre o un identificador) y exigir aprobación (`is_active=False` hasta que un administrador lo active) para el registro. Es lo que ya prevé `create_user(is_active=...)`.

### D-03 · El log de accesos registra los filtros de búsqueda, con nombres de clientes y texto libre — **Media**
- **Dónde:** el log de accesos de `uvicorn`, y las rutas `GET /api/incidents?...` ([incident_router.py:74](../services/api/incidents/incident_router.py#L74))
- **Evidencia:** ✔ Verificado. Una consulta de la pantalla de incidencias queda registrada completa:
  ```
  INFO: 127.0.0.1 - "GET /api/incidents?client_company=Acme+Corporation+Real+SL&q=maria.garcia&agent_id=AGT-07 HTTP/1.1" 200 OK
  ```
  El login fallido, en cambio, no deja el usuario (va en el cuerpo, no en la URL): bien resuelto.
- **Impacto:** el texto que alguien escribe en el buscador (un nombre, parte de un email) y las empresas filtradas se guardan en los logs sin ningún control.
- **Corrección breve:** configurar el log de accesos para omitir la parte de la URL a partir de `?` (con un filtro de `logging`), o registrar solo la ruta.

### D-04 · El email del primer administrador se escribe en el log — **Baja**
- **Dónde:** [users/service.py:235](../services/api/users/service.py#L235): `logger.info("Bootstrapped first user %s", user.email)`
- **Evidencia:** ◐ Leído. Hoy no se ve porque el nivel INFO no está configurado (S-03), pero se activará al configurar el logging.
- **Corrección breve:** registrar el `id` del usuario en lugar del email.

### D-05 · Los ficheros con hashes y datos personales no tienen permisos restringidos — **Baja**
- **Dónde:** `users/db.json`, `profiles/db.json`, `incidents/db.json` (TinyDB)
- **Evidencia:** ◐ Leído. No hay ningún `chmod` en el código. TinyDB crea los ficheros con la máscara del proceso, que normalmente deja el fichero legible por otros usuarios del equipo (`644`). Sí están ignorados por Git.
- **Impacto:** en un servidor compartido, otro usuario del sistema podría leer los hashes de contraseña y los datos personales.
- **Corrección breve:** crear los ficheros con permisos `600` (por ejemplo `os.umask(0o077)` al arrancar).

### D-06 · CSV con 100 emails de clientes de apariencia real, duplicado en dos carpetas — **Baja**
- **Dónde:** [data/raw/incidents-nexova.csv](../data/raw/incidents-nexova.csv) y [scripts/incidents-nexova.csv](../scripts/incidents-nexova.csv)
- **Evidencia:** ✔ Verificado. Las dos copias son idénticas y contienen 100 filas con `customer_email` de dominios reales (`icloud.com`, `gmail.com`, `outlook.com`, `hotmail.com`, `protonmail.com`). Son, con toda probabilidad, datos de ejemplo del curso, pero nada en el repositorio lo indica.
- **Impacto:** si algún día fueran datos reales, estarían en el historial de Git de forma permanente y sería muy difícil retirarlos. El seed los copia después a la base en claro.
- **Corrección breve:** indicar en el README que son datos ficticios (o sustituir los dominios por `example.com`) y conservar una sola copia.

### D-07 · Credencial de ejemplo `admin123` en la documentación — **Baja**
- **Dónde:** [aprendiendo con la ia.md:734](../aprendiendo%20con%20la%20ia.md#L734) (`username=admin@nexova.com&password=admin123`) y línea 405
- **Evidencia:** ✔ Verificado. El código afirma que "no hay ninguna contraseña por defecto en ningún sitio", pero la documentación enseña una concreta.
- **Impacto:** quien copie el ejemplo puede crear un administrador con una contraseña adivinable.
- **Corrección breve:** sustituirla por un marcador (`<tu-contraseña>`).

## Relación con hallazgos anteriores

| Hallazgo | Dato sensible implicado |
|---|---|
| E-07 | El registro revela qué emails existen |
| E-17 | `GET /users/directory` expone nombres e identificadores de todos los usuarios activos |
| E-18 | El token de sesión vive en `localStorage` |
| E-19 | Los 422 de `/profiles` y `/suppliers` devuelven el `input` (nombre, teléfono y dirección de la persona) |
| S-06 | No se registran los intentos de acceso sospechosos |

---

# Parte 6 — Interfaz sin estados de carga o de error

**Criterio:** componentes que no muestran carga, no muestran error, se rompen sin avisar o no tienen un plan B seguro.

**Método:** esta es la parte donde más sirve ejecutar, así que probé la interfaz **en un navegador real**.
1. Inventario de todos los componentes con operaciones asíncronas y de qué indicadores de carga y error dispone cada uno.
2. Arranqué la API (con 25 incidencias y 15 proveedores de prueba) y el backoffice en modo desarrollo, y la web pública.
3. Con Playwright y Chromium **provoqué ~35 situaciones** interceptando las llamadas: API lenta, API que no responde nunca, error 500, red caída, respuestas `200` con un JSON incompleto o con HTML, datos con valores raros. En cada una anoté lo que ve la persona (texto, indicadores de carga, avisos, botones) y guardé capturas.

Todo lo de esta parte está **verificado en el navegador**, salvo lo marcado con ◐. Los servidores de prueba se pararon al terminar y no se dejó ningún fichero en el repositorio.

## Lo que está bien resuelto (comprobado)

| Situación probada | Qué ve la persona |
|---|---|
| Proveedores o incidencias con la API lenta | Indicador de carga (spinner) ✔ |
| Incidencias o análisis con un error 500 | Aviso en español sin tecnicismos (`El servidor ha tenido un problema…`) ✔ |
| Red caída en incidencias | `No se pudo conectar con el servidor…` ✔ |
| Detalle de incidencia con un 500 | Aviso **y botón «Reintentar»** ✔ |
| Crear incidencia con un 500 | Aviso y **el texto escrito se conserva** ✔ |
| Cambiar el estado de una incidencia con un 500 | Aviso en español ✔ |
| Respuesta `200` con HTML en lugar de JSON | `No se pudieron cargar las incidencias.` ✔ |
| Formularios mientras guardan | Botón desactivado y spinner ✔ |
| Pantalla de error general | Existe y evita la pantalla en blanco en la mayoría de fallos ✔ |
| Temporizador del contador de la web | Se limpia al desmontar ✔ |

## Hallazgos

### U-01 · Ninguna petición tiene tiempo máximo: si la API no responde, la pantalla se queda cargando para siempre — **Alta**
- **Dónde:** todo `uis/backoffice/src/lib/api.ts` (`fetch` sin `AbortController` ni `timeout`; hay 0 usos en el código de `main`)
- **Evidencia:** ✔ Verificado. Con la API sin responder:

| Pantalla | Lo que se ve tras esperar |
|---|---|
| Proveedores | Spinner girando, sin límite (15 s) |
| Recargar cualquier página | `Comprobando la sesión…` **sin spinner y sin ningún botón** (15 s). La persona **no puede ni cerrar sesión** |
| Análisis de CSV | `Analizando archivo...` con la zona de subida desactivada y sin forma de cancelar (12 s) |
| Login | Spinner en el botón (10 s) |
| Crear incidencia | Botón desactivado con spinner (10 s) y el formulario bloqueado |

- **Impacto:** un servidor lento o bloqueado deja a la persona atrapada sin una salida. El caso de la sesión es el peor: es la pantalla de entrada de toda la aplicación.
- **Corrección breve:** que `apiFetch` use `AbortSignal.timeout(20000)` y que el error resultante se trate como "sin respuesta"; en `RequireAuth`, mostrar un botón «Reintentar» y «Cerrar sesión» pasados unos segundos.

### U-02 · Proveedores: ante un error enseña también un "no hay datos" falso, sin reintento — **Media**
- **Dónde:** [SuppliersPage.tsx:21-27](../uis/backoffice/src/views/SuppliersPage.tsx#L21-L27) y su tabla
- **Evidencia:** ✔ Verificado (captura `C-proveedores-500.png`). Con la API devolviendo 500 se ve a la vez: el aviso rojo `Internal Server Error`, el contador `0 proveedores` y, dentro de la tabla, `No hay proveedores con esos filtros.` No hay botón de reintento.
- **Impacto:** la persona lee "no hay proveedores" cuando el problema es un fallo, y puede concluir que se han borrado.
- **Corrección breve:** si hay error de carga, no pintar la tabla vacía; mostrar solo el aviso con un botón «Reintentar».

### U-03 · Incidencias: un solo fallo deja la página sin contenido, sin reintento — **Media**
- **Dónde:** `Promise.all` en [IncidentsPage.tsx:65-75](../uis/backoffice/src/views/IncidentsPage.tsx#L65-L75)
- **Evidencia:** ✔ Verificado (captura `E-solo-resumen-falla.png`).
  - Si falla la lista: solo se ve el aviso y los filtros. No hay tabla, ni estado vacío ni botón «Reintentar».
  - Si falla **solo el resumen** (la lista estaba bien): **la lista también desaparece**, porque las dos peticiones se esperan juntas.
- **Impacto:** un fallo secundario (el resumen) impide trabajar con lo principal. La única salida es recargar a mano o tocar un filtro.
- **Corrección breve:** cargar el resumen aparte de la lista (lo hace `SummarySection` en la rama) y añadir un botón «Reintentar» junto al aviso.

### U-04 · Una respuesta incompleta rompe la pantalla entera — **Media**
- **Dónde:** `IncidentsPage`, `IncidentSummaryPanel`, `IncidentTable`, `HistoryTimeline`: pintan los datos sin comprobar su forma
- **Evidencia:** ✔ Verificado. En cada caso toda la pantalla pasa a `Algo ha salido mal… Reintentar`:

| Respuesta del servidor | Resultado |
|---|---|
| Lista con otra forma (`{foo: 1}`) | Pantalla completa de error |
| Resumen incompleto (`{total: 3}`) con la lista correcta | Pantalla completa de error: **se pierde también la lista** |
| Una fila de la lista con `created_at: null` | Pantalla completa de error |
| Un evento `edited` del historial sin `fields` | Pantalla completa de error: **se pierde el detalle entero** |

- **Impacto:** un dato defectuoso en una sola fila o evento (una migración antigua, un cambio en la API) deja inutilizable la pantalla. El plan B existe y es seguro, pero tira todo.
- **Corrección breve:** comprobar la forma de la respuesta antes de pintar (como hace `isSummary` en la rama) y envolver el resumen y el historial en su propio *error boundary*, para que un fallo afecte solo a su recuadro.

### U-05 · El `Layout` da por hecho que existe `profile`, y su fallo no está cubierto: sale la página de error de Next en inglés — **Media**
- **Dónde:** `user?.profile.name` en [Layout.tsx:49](../uis/backoffice/src/components/Layout.tsx#L49) y [app/(app)/error.tsx](../uis/backoffice/src/app/(app)/error.tsx)
- **Evidencia:** ✔ Verificado. Con `/auth/me` devolviendo el usuario **sin** el campo `profile`, la consola muestra `Cannot read properties of undefined (reading 'name')` y la persona ve la página por defecto de Next: **`This page couldn't load · Reload to try again, or go back. · Reload · Back`**, en inglés y sin nuestra marca. El `error.tsx` de `(app)` no la recoge porque un `error.tsx` no cubre el `layout.tsx` de su mismo segmento.
- **Impacto:** el fallo del propio esqueleto de la aplicación (menú lateral y guarda de sesión) da la peor pantalla posible. Confirma E-09, que se había marcado solo por el listado de ficheros.
- **Corrección breve:** usar `user?.profile?.name ?? user?.email` y añadir `app/global-error.tsx` (con el mismo mensaje en español).

### U-06 · Cuando una acción falla, el aviso puede quedar fuera de pantalla — **Media**
- **Dónde:** `setError` de [SuppliersPage.tsx:31-50](../uis/backoffice/src/views/SuppliersPage.tsx#L31-L50): el aviso va **arriba de la página**, lejos de la fila donde se hizo clic
- **Evidencia:** ✔ Verificado. Con el cambio de estado fallando en la última fila de la tabla, el aviso aparece a `-907` píxeles del borde superior de la ventana (la página está desplazada 1107 píxeles): **no se ve**.
- **Impacto:** la persona pulsa el botón, el spinner desaparece y no pasa nada visible. Cree que se hizo, o que el botón no funciona.
- **Corrección breve:** mostrar el error junto a la fila, o desplazar la vista al aviso al aparecer (`scrollIntoView`).

### U-07 · Tras un fallo se siguen enseñando los resultados anteriores, como si fueran los de la nueva búsqueda — **Media**
- **Dónde:** [IncidentsPage.tsx:151-175](../uis/backoffice/src/views/IncidentsPage.tsx#L151-L175)
- **Evidencia:** ✔ Verificado (captura `S2-datos-antiguos.png`). La tabla muestra 15 incidencias. Se escribe `zzzz-no-existe` en el buscador y la API falla: **la tabla sigue con las mismas 15 filas** (a plena opacidad) y arriba aparece el aviso rojo.
- **Impacto:** las filas visibles no corresponden al filtro actual y nada lo indica en la propia tabla.
- **Corrección breve:** al fallar, atenuar la tabla y añadir un texto («Mostrando el resultado anterior»), o no enseñarla.

### U-08 · Perfil: si falla la carga, queda un callejón sin salida — **Baja**
- **Dónde:** `loadError` en [ProfilePage.tsx:42-61](../uis/backoffice/src/views/ProfilePage.tsx#L42-L61)
- **Evidencia:** ✔ Verificado. Con `/auth/me` en 500 al abrir `Mi perfil`, solo se ve `No se pudo cargar tu perfil. Recarga la página para intentarlo de nuevo.` No hay formulario ni botón.
- **Impacto:** la persona tiene que recargar a mano; además, al recargar con ese mismo fallo, `AuthContext` la saca a `/login` (E-08, **también verificado** en el navegador).
- **Corrección breve:** añadir un botón «Reintentar» que vuelva a llamar a `refreshUser`.

### U-09 · Valores inesperados salen en blanco o como `Invalid Date` — **Baja**
- **Dónde:** `CATEGORY_LABELS[...]`, `ORIGIN_LABELS[...]`, `StatusBadge` ([StatusBadge.tsx](../uis/backoffice/src/components/incidents/StatusBadge.tsx)) y `new Date(...).toLocaleString` en `IncidentDetailPage`/`HistoryTimeline`
- **Evidencia:** ✔ Verificado.
  - Una fila con categoría, origen y estado desconocidos pinta **tres celdas vacías** (`["NXV-000777","Fila…","","","central","","2024-01-01"]`), sin avisar.
  - Una fecha no válida muestra `Invalid Date`, y `updated_at: null` muestra `1/1/1970, 0:00:00`.
- **Corrección breve:** texto de reserva (`«Desconocido»`, `«—»`) y una función de formato de fecha que devuelva `«—»` si no es válida.

### U-10 · La web pública se queda en blanco si falla el JavaScript — **Baja**
- **Dónde:** [uis/website/index.html](../uis/website/index.html) (`<div id="root"></div>` vacío, sin `<noscript>`) y [main.tsx](../uis/website/src/main.tsx) (sin *error boundary*)
- **Evidencia:** ✔ Verificado. Sin JavaScript, o con el script principal sin descargar, el texto visible es `""` y `#root` no tiene ningún nodo. No hay `ErrorBoundary` en el código (0 coincidencias).
- **Impacto:** quien llegue por buscadores, con un bloqueador o con una conexión inestable, ve una página vacía sin ninguna explicación. Es la cara pública de la empresa.
- **Corrección breve:** añadir un `<noscript>` con el contacto y un *error boundary* alrededor de `<App />`.

### U-11 · Login con una respuesta inesperada dice "contraseña incorrecta" — **Baja**
- **Dónde:** `login()` en [api.ts:69-80](../uis/backoffice/src/lib/api.ts#L69-L80) y [LoginPage.tsx](../uis/backoffice/src/views/LoginPage.tsx)
- **Evidencia:** ✔ Verificado. Con el servidor respondiendo `200` sin `access_token`, la persona ve `Email o contraseña incorrectos, o la cuenta está desactivada.` aunque los datos eran correctos. (Concreta T-03 y T-04 con una prueba real.)
- **Corrección breve:** comprobar que `access_token` es un texto no vacío y, si no, mostrar `No se pudo iniciar sesión. Inténtalo de nuevo.`

## Evidencia nueva sobre hallazgos anteriores

| Hallazgo | Qué se comprobó en el navegador |
|---|---|
| E-04 | Con el formulario de la web completo y válido aparece `¡Gracias por tu interés en Nexova! Hemos recibido tu información…` y **no se hace ninguna petición de red** |
| E-08 | Recargar con `/auth/me` en 500 lleva a la pantalla de login: **se cierra la sesión** |
| E-09 | Un fallo del `Layout` muestra la página de error por defecto de Next (U-05) |
| R-01 | El análisis de un CSV con un estado desconocido (500 real) muestra `Internal Server Error` en inglés |

## Qué corrige ya la rama `feature/incident-manager`

Esa rama no está fusionada en `main`. Por sus commits y su código, corrige parte de lo anterior solo para las rutas `/api/incidents`:

| Hallazgo | Estado en la rama |
|---|---|
| E-01 (500 genérico) | Corregido globalmente: middleware `catch_unhandled_errors` con `error_id`, colocado dentro de CORS. |
| E-05 (documentos ilegibles) | Corregido: se saltan y se registran. Un fichero corrupto sigue siendo un 500. |
| E-10 (mensajes) | Mejorado en las pantallas de incidencias (`describeError`, `friendlyFieldError`). Proveedores y análisis siguen igual. |
| Resumen que tumba la lista | Corregido: `SummarySection` se carga aparte, con aviso de lentitud, tiempo máximo y reintento. |
| E-02, E-03, E-04, E-06 a E-09, E-11 a E-20 | **No tocados** en la rama. |
| T-02 (bases TinyDB) | **Parcial:** según su README, un fichero corrupto sigue siendo un `500`. |
| U-03, U-04 (incidencias) | **Parcial** (según su código y README; no lo ejecuté): `SummarySection` carga el resumen aparte con aviso de lentitud a los 4 s, tiempo máximo a los 20 s y reintento, y valida la forma con `isSummary`. Añade «Reintentar» al aviso de la lista. No valida la forma de la lista, de las filas ni del historial. |
| U-01 (sin tiempo máximo) | **Solo el resumen** (20 s). El resto de peticiones, la sesión y el login siguen sin límite. |
| U-02, U-05 a U-11 | **No corregidos:** `SuppliersPage`, `ProfilePage`, `AuthContext`, la web pública y `StatusBadge` no cambian. `Layout.tsx` cambia 7 líneas y sigue sin proteger `profile` ni tener `global-error.tsx`. |
| D-01 a D-07 (Parte 5) | **No corregidos.** El arranque con `create_user(UserCreate(...))` es idéntico, el router de incidencias no comprueba roles y sigue usando `actor=user.email`. La rama añade además `logger.exception` en los 500, que debe cuidar lo dicho en D-01. |
| R-02 (mensajes de Pydantic) | **Parcial:** `friendlyFieldError` traduce los errores de campo en el formulario de incidencias. El registro, proveedores y el análisis de CSV no lo usan. |
| R-01 (`err.message`) | **No corregido** en proveedores ni en el análisis. El 500 de la rama dice `Internal server error. Please try again later.` (en inglés, pero sin `error_id` visible para el usuario en esas pantallas). |
| R-03, R-04 | **No corregidos:** la documentación sigue pública y los routers siguen usando `str(exc)`. |
| S-03 (logging sin configurar) | **No corregido.** La rama añade logs (`logger.exception` con `error_id` en los 500 y un `warning` al saltar documentos ilegibles) y siguen sin configuración; los de nivel `warning` y `error` sí se ven, pero el `info` no. |
| S-07 (`error.tsx`) | **No corregido.** El fichero es idéntico al de `main`. |
| T-01 a T-08 y C-01 a C-07 (Parte 2) | **No comprobados en la rama.** Sus ficheros afectados (`core.py`, `AuthContext.tsx`, `token.ts`, `api.ts`) no aparecen entre los modificados por los commits que leí, salvo `api.ts`, `errors.ts`, `IncidentForm.tsx` y `StatusActions.tsx`, que sí cambian y habría que revisar de nuevo (C-01, C-03). |

## Lo que está bien

- Login con respuesta idéntica para email desconocido y contraseña incorrecta, y comprobación de hash falso para igualar tiempos.
- JWT con algoritmo fijado, `exp` obligatorio y comprobación de usuario activo en cada petición. Un 401 tardío no cierra una sesión nueva.
- Los 422 de `/auth`, `/users` y `/api/incidents` no devuelven el valor rechazado, de modo que no se filtran contraseñas ni emails.
- `get_jwt_secret()` se llama en el arranque, y un secreto demasiado corto se rechaza.
- `scripts/seed_incidents.py` gestiona bien los errores: no inserta filas inválidas, nunca imprime el email y devuelve códigos de salida claros.
- `RequireAuth` y `AuthContext` gestionan las carreras entre pestañas y los logout tardíos.

## Límites de esta auditoría

- No se han leído los tests ni se han ejecutado las pruebas e2e del navegador.
- No se ha probado el despliegue ni la configuración de producción, que no están en el repositorio.
- Los hallazgos marcados como "Leído" se deducen del código y conviene confirmarlos antes de corregir.
