# 📘 Aprendiendo con la IA — AUTH‑03: recuperar y cambiar la contraseña

> **Estudiante:** INES
> **Proyecto:** Nexova — API (`services/api`) y backoffice (`uis/backoffice`)
> **Qué es este documento:** el diario de la tarea AUTH‑03. Cuenta **qué se construyó**, **por qué se decidió así** y **qué problemas aparecieron** (con los errores reales, incluidos los míos) para que puedas aprender de cada uno.
> Es la continuación de [`aprendiendo con la ia.md`](./aprendiendo%20con%20la%20ia.md) y de [AUTH‑02](./aprendiendo%20con%20la%20ia%20-%20AUTH-02.md).

---

## 📑 Índice

1. [El encargo, en palabras sencillas](#1-el-encargo-en-palabras-sencillas)
2. [Conceptos que necesitas antes de empezar](#2-conceptos-que-necesitas-antes-de-empezar)
3. [Cómo se trabajó](#3-cómo-se-trabajó)
4. [Lo que se construyó, pieza a pieza](#4-lo-que-se-construyó-pieza-a-pieza)
5. [Las decisiones importantes (y por qué)](#5-las-decisiones-importantes-y-por-qué)
6. [Problemas que aparecieron y cómo se resolvieron](#6-problemas-que-aparecieron-y-cómo-se-resolvieron)
7. [Seguridad: lo que hay que tener claro](#7-seguridad-lo-que-hay-que-tener-claro)
8. [Archivos que se tocaron](#8-archivos-que-se-tocaron)
9. [Cómo verlo funcionando](#9-cómo-verlo-funcionando)
10. [Lo que NO está hecho (sé honesta con lo pendiente)](#10-lo-que-no-está-hecho)
11. [Glosario](#11-glosario)
12. [Ejercicios para practicar](#12-ejercicios-para-practicar)

---

## 1. El encargo, en palabras sencillas

Ya se podía entrar (login), registrarse y ver el perfil. Faltaban dos cosas que toda web real tiene:

| Situación | Qué se pidió |
|---|---|
| **"Olvidé mi contraseña"** | Pedir un enlace por correo y elegir una contraseña nueva |
| **"Quiero cambiarla"** (ya estoy dentro) | Escribir la actual, la nueva y repetirla |

Y todo **de punta a punta**: la API, las pantallas y **el envío del correo**.

Las reglas que más importaron (las dio la tarea):

- El enlace del correo **caduca** y **solo sirve una vez**.
- **Nunca** se debe revelar si un email está registrado.
- Las **claves de API** (Resend, SendGrid…) solo en variables de entorno, nunca en el código.

---

## 2. Conceptos que necesitas antes de empezar

### ✉️ El enlace de recuperación es como una llave de un solo uso
Cuando dices "olvidé mi contraseña", la web no puede preguntarte "¿eres tú?" (precisamente no sabes la contraseña). Así que **demuestras que eres tú porque controlas tu correo**: te mandan un enlace con una llave (el *token*). Quien abre ese enlace puede poner una contraseña nueva. Por eso la llave tiene que ser:

- **Imposible de adivinar** (larga y aleatoria).
- **De caducidad corta** (30 minutos).
- **De un solo uso** (si no, un correo antiguo sería una puerta abierta para siempre).

### 🔏 JWT firmado
Un JWT es un texto con datos dentro (quién eres, cuándo caduca) y una **firma** hecha con la clave secreta del servidor (`SECRET_KEY`). Si alguien cambia un solo carácter, la firma deja de cuadrar y el servidor lo rechaza. No se puede falsificar sin conocer la clave.

### #️⃣ Hash
Un *hash* es una "huella" de un texto: de `hola` sale siempre la misma huella, pero **de la huella no se puede volver a `hola`**. Se usa para guardar contraseñas (bcrypt) y, aquí, para guardar los tokens de recuperación: la base de datos guarda solo la huella, así que quien la lea **no puede usar** los enlaces.

### 🕵️ Enumeración de usuarios
Si la web responde "ese email no existe" a unos y "te hemos enviado un correo" a otros, un atacante puede **descubrir quién tiene cuenta** probando emails. Por eso la respuesta tiene que ser **idéntica** en los dos casos. Es lo que más cuidado exigió.

### 🌱 Variables de entorno y `.env`
Son ajustes que viven **fuera del código**: claves, direcciones, modos. Se escriben en el archivo `services/api/.env`, que **git ignora** para que nadie suba por error una clave. En el repositorio solo está `.env.example`, una plantilla con los huecos vacíos.

### 📨 Servicio de correo transaccional
Enviar correos que lleguen a la bandeja (y no a spam) es difícil. Servicios como **Resend** o **SendGrid** lo hacen por ti: tú les envías el mensaje con una **API key** y ellos lo entregan.

---

## 3. Cómo se trabajó

1. **Leer antes de escribir.** Se revisó cómo estaba hecho el login (JWT, TinyDB, tests) para seguir el mismo estilo y no inventar otro.
2. **Primero la API, luego las pantallas.** La parte de seguridad es la que no admite errores; las pantallas dependen de ella.
3. **Tests a la vez que el código.** Cada regla (caduca, un solo uso, siempre 200…) tiene su test. Al final: **206 tests** de la API.
4. **Probar en un navegador de verdad** con Playwright (el test `e2e:password`), no solo mirar el código.
5. **Revisar el resultado con capturas de pantalla** de cada pantalla.

> 💡 **Lección:** un test que nunca ha fallado no demuestra nada. Varias veces se comprobó que un test **fallaría** si la regla se rompiera.

---

## 4. Lo que se construyó, pieza a pieza

### 4.1 La API (`services/api`)

| Endpoint | ¿Hace falta sesión? | Qué hace |
|---|---|---|
| `POST /auth/forgot-password` | No | Recibe `{email}`. **Siempre responde 200** con el mismo mensaje. Si la cuenta existe y está activa, envía el correo. |
| `POST /auth/reset-password` | No | Recibe `{token, new_password}`. Cambia la contraseña y gasta el token. **400** si está caducado, falsificado o ya usado. |
| `POST /auth/change-password` | **Sí** | Recibe `{current_password, new_password}`. **400** si la actual es incorrecta. |

El camino completo de "olvidé mi contraseña":

```
1. forgot-password  → la API crea un token firmado y guarda SU HUELLA
2. correo           → llega un enlace  /reset-password?token=...
3. reset-password   → la API comprueba firma + caducidad + que no esté usado
4. nueva contraseña → se guarda con bcrypt, el token se borra
5. aviso            → llega un segundo correo: "tu contraseña ha cambiado"
```

### 4.2 El token de recuperación

Está en `auth/security.py`. Es un JWT con cuatro datos:

```python
claims = {
    "user_id": str(user_uuid),   # de quién es
    "purpose": "password_reset", # para qué sirve (¡importante, ver problema 2!)
    "jti": secrets.token_urlsafe(16),  # identificador aleatorio único
    "exp": expires,              # cuándo caduca (30 min por defecto, entre 15 y 60)
}
```

Y se guarda **solo su huella** (`SHA-256`) en un archivo propio, `auth/db.json`, junto a la fecha de caducidad. "Un solo uso" funciona así: al usarlo, la huella se borra; si alguien lo intenta otra vez, la huella ya no está → **400**.

### 4.3 El envío de correos (`core/mailer.py`)

Tiene tres "modos", elegidos con `EMAIL_BACKEND`:

| Modo | Para qué |
|---|---|
| `console` (por defecto) | **Desarrollo**: el correo no se envía, se **imprime en la terminal** de la API |
| `resend` | Envío real con la API de Resend (`RESEND_API_KEY`) |
| `smtp` | Cualquier proveedor por SMTP (sirve para SendGrid) |

Detalles que importan:

- Si eliges `resend` y falta la clave, **la API no arranca** (mejor fallar al empezar que el día que alguien olvida su contraseña).
- Los correos se envían **después de responder** al navegador (una *tarea en segundo plano*).
- Si el envío falla por algo pasajero (red, límite de Resend), **reintenta dos veces** (1 s y 3 s después).
- Si falla, el log dice **por qué** (por ejemplo `Resend answered 403: ...`) pero **nunca** imprime el enlace ni la clave.

### 4.4 Las pantallas (`uis/backoffice`)

| Ruta | Qué hace |
|---|---|
| `/login` | Nuevo enlace **"¿Olvidaste tu contraseña?"** |
| `/forgot-password` | Pide el email. Muestra *"Si esa dirección está registrada, recibirás un enlace en breve."* y **desactiva el formulario** |
| `/reset-password?token=…` | Lee el token de la URL, pide la contraseña dos veces, y si va bien **redirige a `/login`** con un mensaje verde. Si falla, error claro + enlace a `/forgot-password` |
| `/account/change-password` | Contraseña actual + nueva + repetir. **Comprueba que coinciden antes de llamar a la API** |

Las reglas de la contraseña (mínimo 8 caracteres, máximo 72 bytes) están en un solo archivo, `src/lib/password.ts`, que usan el registro y las dos pantallas nuevas. Así no hay tres copias que puedan acabar diferentes.

---

## 5. Las decisiones importantes (y por qué)

**1. Token firmado + huella guardada (las dos cosas).**
El JWT firmado permite rechazar falsificaciones **sin tocar la base de datos**. La huella guardada permite lo que un JWT por sí solo no puede: **gastarlo** (un JWT, una vez emitido, es válido hasta que caduca). Cada técnica cubre lo que le falta a la otra.

**2. Guardar la huella (hash), no el token.**
Si alguien lee `auth/db.json`, solo ve huellas. No puede construir enlaces válidos.

**3. Siempre `200` en `forgot-password`.**
Así no se revela quién tiene cuenta. Y también se unificó el **tiempo**: toda la búsqueda y el envío ocurren *después* de responder.

**4. El enlace sale de `FRONTEND_URL`, no de la petición.**
Si el enlace se construyera con la cabecera `Host` de quien lo pide, un atacante podría pedir un correo "para otra persona" cuyo enlace apunte a **su propia web**. Por eso la dirección viene de la configuración.

**5. Un correo de recuperación por cuenta y minuto.**
Para que nadie pueda llenar el buzón de otra persona con la ruta pública.

**6. Si la contraseña nueva no cumple las reglas, el token NO se gasta.**
Un error de formato no debería obligarte a pedir otro correo. (Decisión nuestra, no venía en la tarea.)

**7. Contraseña de cambio ≠ contraseña actual.**
`change-password` rechaza una nueva igual a la actual (422). Si no, "cambiar" no cambiaría nada.

**8. Contraseña actual incorrecta = `400`, no `401`.**
`401` significa "no tienes sesión válida", y el frontend responde cerrándote la sesión. Si te equivocas al teclear la contraseña actual **no debe expulsarte**. Por eso es `400`.

**9. El token solo vale mientras la contraseña no cambie.**
Cada token guarda una "huella de la contraseña vigente" al crearse. Si cambias la contraseña por otra vía, los enlaces pendientes **mueren solos**.

**10. Aviso por correo tras cada cambio.**
Si alguien entra en tu cuenta y cambia la clave, tú te enteras.

**11. Un archivo aparte para los tokens (`auth/db.json`).**
Un test del proyecto exige que los documentos de usuario tengan siempre los mismos campos. Mejor no tocar esa regla y guardar los tokens en otro sitio.

**12. `console` como modo por defecto.**
Así cualquiera puede desarrollar **sin cuenta de ningún servicio**: copia el enlace de la terminal. Y en producción hay que elegir otro modo a propósito.

---

## 6. Problemas que aparecieron y cómo se resolvieron

### Problema 1 — La especificación llegó por partes (y yo ya había decidido por mi cuenta)
**Qué pasó:** se pidió "implementa todo" sin la lista de requisitos. Se implementó con decisiones razonables (respuesta `202`, token aleatorio, 30 minutos). Cuando llegó la lista real, pedía **`200`**, token **firmado** y caducidad **entre 15 y 60 minutos**.
**Solución:** se ajustó: `202 → 200`, token aleatorio → JWT firmado, y la configuración rechaza valores fuera de 15–60.
**Lo que se aprende:** cuando falta información, avisar de lo que se ha supuesto. Y escribir el código para que cambiar una decisión sea barato (las constantes `MIN`/`MAX` están en `core/config.py`).

### Problema 2 — ¡El enlace del correo abría una sesión! (el más grave)
**Qué pasó:** al pasar el token a JWT, se comprobó `GET /auth/me` con el token del correo… y devolvió **200**. Los tokens de sesión solo exigían `user_id` y `exp`, y el de recuperación también los tenía. Resultado: **quien tuviera el enlace podía entrar sin contraseña**.
**Solución:** el token de recuperación lleva `purpose: "password_reset"`, y la comprobación de sesión **rechaza cualquier token que tenga `purpose`**. Y al revés: el de recuperación solo se acepta si trae ese propósito. Hay tests en las dos direcciones.
**Lo que se aprende:** cuando reutilizas un mecanismo (JWT) para algo nuevo, pregúntate **"¿puede esto confundirse con lo antiguo?"**. Esto se encontró **porque se probó a propósito**, no por casualidad.

### Problema 3 — Se podía adivinar qué emails existían por el tiempo de respuesta
**Qué pasó:** aunque la respuesta era idéntica, con un email **existente** la API tardaba ~1,5 ms más (crear el token, escribir en el archivo). Medido, no supuesto.
**Solución:** todo lo que depende de si la cuenta existe se hace **después** de responder, en segundo plano.
**Matiz honesto:** después de moverlo, el cronómetro del test ya no sirve (el cliente de pruebas espera a la tarea). La mejora está razonada y el test comprueba el contenido idéntico, pero **no se volvió a medir el tiempo real**.
**Lo que se aprende:** la seguridad no es solo lo que dice la respuesta, también **cuánto tarda**.

### Problema 4 — Un script de edición falló a medias y rompió 19 tests
**Qué pasó:** un script cambiaba varios archivos. Una de las sustituciones no encontró su texto, el script **se paró**… pero antes ya había guardado otros archivos. Quedó el código a medias y fallaron 19 tests.
**Solución:** se leyó el error, se vio qué faltaba y se aplicó lo pendiente. Los 196 tests volvieron a pasar.
**Lo que se aprende:** los errores de un test **leen como una lista de tareas pendientes**. Y los cambios automáticos deben comprobar que encuentran lo que buscan (`assert`) en lugar de continuar en silencio.

### Problema 5 — Un test fallaba por culpa del propio test
**Qué pasó:** se comprobaba que la contraseña `"short"` no aparecía en la respuesta de error. Pero el mensaje de FastAPI contiene `string_too_short`… que incluye la palabra *short*. El test se asustaba de su propio texto.
**Solución:** usar una contraseña de prueba que no coincida con palabras del mensaje (`"abc-12"`).
**Lo que se aprende:** cuando un test falla, **dos opciones**: el código está mal o el test está mal. Hay que mirar cuál.

### Problema 6 — El navegador de pruebas no arrancaba
**Qué pasó:** Playwright descargó Chromium, pero al lanzarlo dio `libatk-1.0.so.0: cannot open shared object file`. Faltaban librerías del sistema en el Codespace.
**Solución:** `npx playwright install-deps chromium`.
**Lo que se aprende:** "se instaló" y "funciona" no son lo mismo; el mensaje de error nombra exactamente la pieza que falta.

### Problema 7 — Los tests del navegador fallaban, pero la app estaba bien
**Qué pasó:** dos fallos del e2e eran del **test**: (a) el enlace del correo lleva la URL pública del Codespace y el test esperaba `localhost`; (b) tras renombrar una ruta, quedaba **una línea con la ruta antigua**.
**Solución:** el test ahora usa la ruta y el token del enlace, y se buscó la ruta antigua en todo el proyecto con `grep`.
**Lo que se aprende:** al renombrar algo, **busca todas las apariciones**. Y no toques la app para "arreglar" un fallo que es del test.

### Problema 8 — Renombrar una ruta (`/account/password` → `/account/change-password`)
**Qué pasó:** la lista de requisitos nombraba `/account/change-password` y yo había creado `/account/password`.
**Solución:** se renombró la carpeta y se actualizaron el menú, los README y el test.
**Lo que se aprende:** una pequeña diferencia de nombre entre lo pedido y lo entregado es un fallo en una evaluación.

### Problema 9 — Pegar valores en el `.env`
**Qué pasó:** se pegaron las líneas `SECRET_KEY=…` al principio o al final del archivo, y la API seguía sin ver los valores.
**Solución y explicación:** las variables **ya existían, vacías**; había que **escribir el valor después del `=` en esa misma línea** y guardar (Ctrl+S). Una línea que empieza por `#` es un comentario y se ignora, por eso para activar `EMAIL_FROM` y `RESEND_API_KEY` hay que **quitar el `# `**.
**Detalles que confunden a todo el mundo:**
- La API solo lee el `.env` **al arrancar**: tras cambiarlo, reiníciala (Ctrl+C y a lanzarla de nuevo).
- El comando `.venv/bin/uvicorn …` solo funciona **desde `services/api`**, porque `.venv` está ahí. Desde la raíz da `No such file or directory`.

### Problema 10 — El PR no se podía crear
**Qué pasó:** `gh pr create` falló con "No commits between main and feature/password-reset", aunque la rama sí tenía commits.
**Causa:** tu repositorio es un **fork** de otro (`4GeeksAcademy/...`), y la herramienta apuntaba por defecto al original.
**Solución:** indicar el repositorio con `--repo ELDER2007/...`. Al diagnosticar se creó un PR con el texto "test"; **se sustituyó enseguida** por la descripción real.
**Lo que se aprende:** cuando un error no tiene sentido, **comprueba lo que supones** (¿a qué repositorio está apuntando?) antes de reintentar lo mismo.

### Problema 11 — "Could not send the email" sin decir por qué
**Qué pasó:** en tu terminal salió `Could not send the email` después de cambiar la contraseña. Probablemente falló el correo de aviso. Pero el mensaje **no decía el motivo**, y yo no podía ver tu terminal.
**Qué se hizo:**
1. Se **reprodujo** el envío con tu configuración: funcionó. Así que no era un fallo fijo, sino puntual (red o límite de Resend). **No se pudo confirmar la causa.**
2. Se mejoró el código para que, la próxima vez, el log diga **el motivo exacto** de Resend.
3. Se añadieron los **reintentos** para los fallos pasajeros.
**Lo que se aprende:** un mensaje de error sin causa es un problema por sí mismo. **Mejorar los mensajes** es arreglar.

### Problema 12 — El PR #13 aparecía cerrado
Se detectó al revisar el proyecto: estaba cerrado sin fusionar. Al intentar crear uno nuevo, GitHub dijo que ya había uno abierto: se había reabierto. Lo importante: **comprobar el estado real antes de actuar**, no suponerlo.

---

## 7. Seguridad: lo que hay que tener claro

| Regla | Cómo se cumple |
|---|---|
| El token caduca | `exp` dentro del JWT (15–60 min) **y** fecha guardada. Hay un test que aísla cada una |
| No se reutiliza | Se guarda la huella y se borra al usar |
| Nunca revelar si un email existe | Misma respuesta, mismo cuerpo, y el trabajo va después de responder |
| La clave de API solo en el entorno | Se lee con `os.environ`; `.env` está en `.gitignore`; se buscaron claves en el repositorio y no hay |
| El token no sirve como sesión | Claim `purpose` rechazado por la comprobación de sesión |
| Contraseñas nunca en claro | bcrypt, como el resto del proyecto |
| El 422 no devuelve tu contraseña | El manejador de errores quita el campo `input` en rutas `/auth` |

**⚠️ Una clave de API es como una contraseña:** no la pegues en un chat, en el código ni en un commit. Si se te escapa, bórrala en el panel del servicio y crea otra.

---

## 8. Archivos que se tocaron

**API (`services/api`)**
- `auth/router.py` — los tres endpoints nuevos
- `auth/service.py` — la lógica (crear/validar tokens, cambiar contraseña)
- `auth/security.py` — creación y verificación del token firmado
- `auth/schemas.py` — formatos de entrada
- `auth/emails.py` — el texto de los correos (texto plano + HTML, con el nombre escapado)
- `core/mailer.py` — **nuevo**: envío por `console` / `resend` / `smtp`, con reintentos
- `core/config.py` — caducidad (15–60), `FRONTEND_URL`, ruta de `auth/db.json`
- `users/service.py` — `set_password` (cambiar contraseña sin pedir la actual, solo para el reset)
- `main.py` — comprobaciones al arrancar
- `tests/test_password.py` — **nuevo**: los tests de todo esto
- `.env.example`, `.gitignore`, `README.md`

**Backoffice (`uis/backoffice`)**
- `src/views/ForgotPasswordPage.tsx`, `ResetPasswordPage.tsx`, `ChangePasswordPage.tsx` — **nuevos**
- `src/app/(public)/forgot-password`, `reset-password` y `src/app/(app)/account/change-password` — las rutas
- `src/components/AuthShell.tsx` — la tarjeta común de las páginas públicas
- `src/lib/password.ts` — reglas de contraseña compartidas
- `src/lib/api.ts`, `LoginPage.tsx`, `Layout.tsx`, `RegisterPage.tsx`
- `e2e/password.e2e.mjs` — **nuevo**: prueba en un navegador real

**Commits en la rama `feature/password-reset`:** `474fc8d` (API), `49ccbd6` (pantallas), `6da0ac5` (reintentos y motivo del fallo), `a471646` (validación del analizador, web pública y documentación).

---

## 9. Cómo verlo funcionando

**Terminal 1 — la API** (desde `services/api`):
```bash
cd services/api
.venv/bin/uvicorn main:app --reload --port 8000
```

**Terminal 2 — la web** (desde la raíz):
```bash
npm run dev:backoffice
```

**Probar la recuperación:**
1. En `/login`, pulsa **"¿Olvidaste tu contraseña?"**.
2. Escribe tu email y pulsa **Enviar enlace**.
3. Con `EMAIL_BACKEND=console`, el correo **aparece en la terminal de la API**; con `resend`, llega a tu bandeja (mira también en spam).
4. Abre el enlace, escribe la contraseña nueva dos veces y guarda.
5. Te lleva a `/login` con un mensaje verde. Entra con la nueva.

**Correr los tests:**
```bash
cd services/api && .venv/bin/python -m pytest -q      # 206 tests de la API
cd uis/backoffice && npm run e2e:password             # en un navegador real (API y web arrancadas)
```

**Para usar Resend de verdad**, en `services/api/.env`:
```
EMAIL_BACKEND=resend
RESEND_API_KEY=re_…tu clave…
EMAIL_FROM=onboarding@resend.dev
```
(Con ese remitente de pruebas, Resend solo te deja enviar **al email de tu propia cuenta**.)

---

## 10. Lo que NO está hecho

Saber qué falta es tan importante como saber qué hay:

- **Correo real con SendGrid:** no existe un modo propio (se puede usar `smtp` con `smtp.sendgrid.net`, pero no se ha probado). Resend sí se probó contra un servidor real, y el envío al correo de tu cuenta funcionó.
- **Cambiar la contraseña no cierra las sesiones ya abiertas.** El JWT de sesión es "sin estado": vale hasta que caduca (30 min). Cerrarlas exigiría un cambio de diseño.
- **No hay límite de intentos** en el login ni en `change-password`. En `forgot-password` solo se limita el número de **correos por cuenta**, no el de peticiones.
- **El registro (`POST /users`) sigue diciendo `409` si el email ya existe**, lo que sí revela que la cuenta existe. Arreglarlo cambia cómo funciona el alta.
- **El remitente `onboarding@resend.dev`** hace que los correos caigan fácilmente en spam. Para producción hay que **verificar un dominio propio**.

---

## 11. Glosario

| Palabra | Significa |
|---|---|
| **Token** | Texto que actúa de "llave" o "pulsera" |
| **JWT** | Token con datos dentro y una firma que impide falsificarlo |
| **Hash / huella** | Resumen irreversible de un texto |
| **bcrypt** | Forma lenta y segura de hacer el hash de contraseñas |
| **Enumeración de usuarios** | Descubrir quién tiene cuenta por cómo responde la web |
| **Un solo uso** | Un token que deja de valer en cuanto se usa |
| **Tarea en segundo plano** | Algo que se hace *después* de responder al navegador |
| **Variable de entorno** | Ajuste que vive fuera del código (en `.env`) |
| **API key** | Contraseña de tu programa para usar un servicio externo |
| **Backend de correo** | La forma elegida de enviar emails (`console`, `resend`, `smtp`) |
| **SMTP** | Protocolo estándar para enviar correo |
| **Fork** | Copia de un repositorio ajeno en tu cuenta |
| **PR (Pull Request)** | Petición para fusionar tu rama en `main` |
| **e2e** | Prueba "de punta a punta", con un navegador real |
| **401 / 400 / 422 / 200 / 204** | Sin sesión / petición mala / datos inválidos / OK con cuerpo / OK sin cuerpo |

---

## 12. Ejercicios para practicar

1. **Cambia la caducidad.** Pon `PASSWORD_RESET_EXPIRE_MINUTES=15` en el `.env`, pide un enlace y comprueba que el correo dice "15 minutos". Prueba con `10`: ¿qué pasa al arrancar la API y por qué?
2. **Rómpelo a propósito.** Pide un enlace, úsalo, y vuelve a abrirlo. ¿Qué ves? Cambia una letra del token y ábrelo: ¿qué ves y por qué es el mismo mensaje?
3. **Mira la huella.** Pide un enlace y abre `services/api/auth/db.json`. ¿Puedes reconstruir el enlace con lo que hay ahí? ¿Por qué es bueno que no se pueda?
4. **Compara respuestas.** Con `curl`, llama a `forgot-password` con tu email y con uno inventado. ¿En qué se parecen las respuestas?
5. **Lee un test.** Abre `tests/test_password.py` y busca `test_a_session_token_is_not_a_reset_token_and_the_other_way_round`. Con tus palabras: ¿qué fallo grave evita?
6. **Reto de diseño.** El registro dice `409` si el email existe, lo que revela cuentas. ¿Cómo lo cambiarías sin que el usuario pierda la información de que "ese email ya está usado"? (Pista: piensa en qué podría decirse **por correo** en vez de en pantalla.)
7. **Pregúntate siempre:** *"¿Y si alguien quisiera abusar de esto?"* Aplícalo al `change-password`: ¿qué pasaría si no pidiera la contraseña actual?

---

> 🌟 **Lo más importante de toda la tarea:** el mayor fallo (el enlace que abría una sesión) **no lo encontró un test que ya existía**: se encontró porque alguien se preguntó *"¿y si usara este token donde no debe?"* y lo **probó**. Aprende a desconfiar de tu propio código con cariño.
