# 📘 Aprendiendo con la IA — Auditoría de gestión de errores

> **Estudiante:** INES
> **Qué es este documento:** el diario de la auditoría de gestión de errores del monorepo. Aquí está **qué se hizo, por qué, qué decisiones se tomaron y qué problemas aparecieron** por el camino, con lo que se aprende de cada uno.
> Es la continuación de tu cuaderno general, [`aprendiendo con la ia.md`](./aprendiendo%20con%20la%20ia.md). El informe que se entregó está en [`docs/AUDITORIA-gestion-errores.md`](./docs/AUDITORIA-gestion-errores.md).

---

## 📑 Índice

1. [El encargo, en palabras sencillas](#1-el-encargo-en-palabras-sencillas)
2. [Conceptos que necesitas antes de leer el informe](#2-conceptos-que-necesitas-antes-de-leer-el-informe)
3. [Cómo se trabajó: el método](#3-cómo-se-trabajó-el-método)
4. [Las decisiones importantes (y por qué)](#4-las-decisiones-importantes-y-por-qué)
5. [Problemas que aparecieron y cómo se resolvieron](#5-problemas-que-aparecieron-y-cómo-se-resolvieron)
6. [Los hallazgos explicados con ejemplos](#6-los-hallazgos-explicados-con-ejemplos)
7. [Qué NO se hizo (y por qué)](#7-qué-no-se-hizo-y-por-qué)
8. [Glosario](#8-glosario)
9. [Ejercicios para practicar](#9-ejercicios-para-practicar)
10. [Segunda pasada: `try/catch` ausente y `catch` demasiado amplio](#10-segunda-pasada-trycatch-ausente-y-catch-demasiado-amplio)
11. [Tercera pasada: fallos silenciosos](#11-tercera-pasada-fallos-silenciosos)
12. [Cuarta pasada: errores en crudo](#12-cuarta-pasada-errores-en-crudo)
13. [Quinta pasada: filtración de datos sensibles](#13-quinta-pasada-filtración-de-datos-sensibles)
14. [Sexta pasada: interfaz sin estados de carga ni de error](#14-sexta-pasada-interfaz-sin-estados-de-carga-ni-de-error)
15. [Séptima pasada: errores sin acción y scripts sin código de salida](#15-séptima-pasada-errores-sin-acción-y-scripts-sin-código-de-salida)
16. [Octava pasada: ¿cumple la auditoría los criterios del tech lead?](#16-octava-pasada-cumple-la-auditoría-los-criterios-del-tech-lead)
17. [Pasada final: ¿hemos mirado todo el monorepo?](#17-pasada-final-hemos-mirado-todo-el-monorepo)
18. [Última pasada: la rúbrica de evaluación](#18-última-pasada-la-rúbrica-de-evaluación)
19. [La entrega: rama, push y pull request](#19-la-entrega-rama-push-y-pull-request)

---

## 1. El encargo, en palabras sencillas

Hay que actuar como un **ingeniero senior que revisa el código de otros** (una *auditoría*) buscando solo una cosa: **qué pasa cuando algo sale mal**.

- Qué ve el usuario si la API se cae.
- Qué pasa si sube un fichero raro.
- Si hay agujeros de seguridad.
- Si el programa aguanta datos estropeados o se rompe entero.

Las reglas del encargo eran estas:

| Regla | Qué significa |
|---|---|
| **Solo reportar** | No se modifica ni una línea de código |
| **Sin funcionalidades nuevas** | Nada de "y si añadimos…" |
| **Sin refactorizar** | No se reorganiza código que no esté roto |
| **Correcciones breves** | Cada problema lleva una sugerencia corta, no un rediseño |
| **Cuatro ejes** | Resiliencia, manejo de errores, mensajes al usuario y seguridad |

> 💡 **Aprendizaje:** una auditoría **no es arreglar**. Es *encontrar, demostrar y explicar*. Quien arregla es otra persona (o tú, en otro momento) con el informe delante.

---

## 2. Conceptos que necesitas antes de leer el informe

### 🚦 Los códigos de respuesta HTTP

Cuando el navegador pregunta algo a la API, esta responde con un número. Los grupos importan:

| Código | Quién ha fallado | Ejemplo |
|---|---|---|
| **2xx** | Nadie, todo bien | `200` OK, `201` creado |
| **4xx** | **El cliente** (quien pregunta) | `400` petición mal hecha, `401` no sé quién eres, `403` no tienes permiso, `404` no existe, `409` conflicto, `422` datos inválidos, `429` demasiadas peticiones |
| **5xx** | **El servidor** (nuestro código) | `500` fallo inesperado |

Un **500 es siempre un fallo nuestro**. Un buen servidor devuelve 4xx con un mensaje claro cuando el problema es del usuario, y reserva el 500 para lo realmente inesperado.

### 🌐 CORS, explicado con una portería

El navegador tiene una regla de seguridad: una web no puede leer respuestas de **otro dominio** salvo que esa respuesta traiga una cabecera que lo permita (`access-control-allow-origin`). Es como un portero que solo deja pasar el paquete si lleva el sello correcto.

El problema que se encontró: cuando la API fallaba con un 500 **sin sello**, el portero (navegador) tiraba el paquete a la basura y la web solo veía "no hay respuesta". Parecía un fallo de conexión cuando el servidor sí había contestado.

### 🧱 Middleware

Una función que se ejecuta **entre la petición y la respuesta**, como un filtro o un guardia en la entrada. Sirve para cosas que afectan a todas las rutas: CORS, capturar errores, registrar logs.

### 🏃 Condición de carrera (*race condition*)

Dos acciones que ocurren a la vez y se pisan. Ejemplo del proyecto: dos personas se registran **a la vez** con el mismo email.

```
Persona A: ¿existe el email? → no
Persona B: ¿existe el email? → no     ← aún no ha insertado A
Persona A: inserta
Persona B: inserta                     ← ¡dos cuentas con el mismo email!
```

La solución es un **lock** (cerrojo): mientras A comprueba+inserta, B espera.

### 🔄 Event loop bloqueado

Una API con `async def` funciona como **un camarero que atiende muchas mesas** pasando de una a otra. Si en una mesa se queda 2 segundos parado haciendo una tarea pesada (calcular un hash de contraseña, leer un fichero), **todas las demás mesas esperan**. Por eso el trabajo pesado y síncrono no debe ir dentro de `async def`.

### 🕵️ Enumeración de usuarios y fuerza bruta

- **Enumeración:** averiguar *qué emails están registrados*. Si el registro dice "ese email ya existe", un atacante puede probar miles y hacer una lista.
- **Fuerza bruta:** probar contraseñas una tras otra. Se frena limitando los intentos por minuto (devolviendo `429`).

---

## 3. Cómo se trabajó: el método

El orden vale para cualquier revisión de código:

1. **Entender qué se pide.** Primero se buscó si existían "criterios del tech lead" en el repositorio. No existían, así que se **preguntó** (ver [decisión 1](#4-las-decisiones-importantes-y-por-qué)).
2. **Explorar antes de juzgar.** Se listaron los ficheros por tamaño y se leyeron los de más riesgo: arranque de la API, configuración, autenticación, servicios, routers, scripts y las pantallas del frontend.
3. **Formular sospechas.** Al leer, se apuntaba "esto podría romperse si…".
4. **Comprobar las sospechas ejecutándolas.** Aquí está lo más valioso: **no se afirma lo que no se ha probado**. Se escribieron pequeños programas de prueba que mandaban a la API entradas malas y se miraba qué contestaba.
5. **Etiquetar la evidencia.** Cada hallazgo lleva una marca:
   - ✔ **Verificado**: lo ejecuté y pasó exactamente eso.
   - ◐ **Leído**: lo deduzco del código, pero no lo ejecuté.
6. **Escribir el informe** con severidad, ubicación, impacto y corrección breve.
7. **Comprobar que no se tocó código**: `git status` mostró solo un fichero nuevo, el informe.

> 💡 **Aprendizaje:** la diferencia entre "creo que falla" y "falla, mira la prueba" es la diferencia entre una opinión y un hallazgo. Un informe lleno de opiniones se discute; uno lleno de pruebas se arregla.

---

## 4. Las decisiones importantes (y por qué)

### Decisión 1 — Preguntar por los criterios en lugar de inventarlos

El encargo hablaba de "los criterios del tech lead". Se buscó en `docs/`, los README y los CONTEXT: **no estaban**. En vez de inventarlos, se pidieron. Después llegó un texto con el objetivo (resiliencia, errores, mensajes, seguridad) y se usó **ese** como guía, dejando escrito en el informe que no había criterios más detallados.

> **Por qué:** si hubiera inventado criterios, el informe habría medido el código contra una vara que nadie pidió.

### Decisión 2 — Auditar `main` y no la rama `feature/incident-manager`

`main` es lo entregado; la rama tiene trabajo sin fusionar. Se auditó `main` y se añadió **una tabla aparte** con lo que la rama ya arregla. Así el tech lead ve el estado real y también el avance.

### Decisión 3 — Dejar el informe en un fichero nuevo, sin tocar nada más

`docs/AUDITORIA-gestion-errores.md`. Un fichero nuevo no es "modificar código", así que cumple la regla de solo reportar.

### Decisión 4 — Probar contra copias temporales, no contra el proyecto

Para ejecutar la API hacía falta instalar sus dependencias. Se hizo en un **entorno virtual temporal fuera del repositorio**, y las pruebas usaron **bases de datos temporales**. Resultado: el repositorio quedó intacto.

### Decisión 5 — Ordenar por severidad, no por carpeta

Se agruparon en **Alta / Media / Baja**. Al tech lead le importa *qué arreglar primero*, no en qué carpeta está cada fallo.

| Severidad | Criterio que se usó |
|---|---|
| **Alta** | Pérdida de datos, mensaje falso al usuario, caída o fuga entre usuarios |
| **Media** | Degrada la experiencia o la seguridad, pero hay salida |
| **Baja** | Riesgo pequeño o que solo importa si el código cambia |

### Decisión 6 — Reconocer también lo que está bien

El informe termina con **"Lo que está bien"** (login que no revela si el email existe, JWT con algoritmo fijado, etc.). Una auditoría que solo critica pierde credibilidad y no dice qué hay que *conservar*.

### Decisión 7 — Admitir los límites

Se escribió qué no se hizo: no se leyeron los tests, no se ejecutaron las pruebas del navegador, no se probó producción. Decir lo que no sabes es parte de ser fiable.

---

## 5. Problemas que aparecieron y cómo se resolvieron

### 🔴 1. Empecé a trabajar sin tener el proyecto

**Síntoma:** al principio empecé a leer código y a preparar notas del Gestor de Incidencias; tú me dijiste: *"todavía no te he pasado el proyecto"*.

**Causa:** asumí que sabía qué se iba a pedir, en vez de esperar.

**Solución:** paré, deshice lo que había preparado (una copia temporal del código) y comprobé con `git status` que no había cambiado nada. Después pregunté.

**Aprendizaje:** **cuando falta información, se pregunta antes de construir.** Equivocarse en la dirección cuesta mucho más que una pregunta.

### 🔴 2. Los criterios del tech lead no existían

**Síntoma:** buscar "criterios", "tech lead" o "gestión de errores" solo devolvió documentos de arquitectura, nada de errores.

**Solución:** pedirlos explícitamente y, al recibir el objetivo, citarlo en el informe como la base usada.

### 🔴 3. La búsqueda dio un error de herramienta

**Síntoma:** al buscar un texto largo en `App.tsx`, `ugrep` respondió *"exceeds complexity limits"*.

**Causa:** `App.tsx` tiene **líneas larguísimas** (el formulario entero en pocas líneas) y la expresión regular con `.{0,120}` era demasiado compleja.

**Solución:** cambiar de herramienta. Se usó un pequeño script de Python que busca la palabra y muestra el texto de alrededor. Así apareció la frase *"Hemos recibido tu información"*.

**Aprendizaje:** si una herramienta falla, no insistas con lo mismo: cambia de método. Y de paso, un fichero con líneas kilométricas es **difícil de revisar** (¡también un hallazgo de calidad!).

### 🔴 4. No había entorno para ejecutar la API

**Síntoma:** al probar, `from fastapi.testclient import TestClient` falló: no existía `services/api/.venv`.

**Solución:** crear un entorno virtual **fuera del repositorio** e instalar `requirements.txt`, `httpx` y el paquete compartido `incidents_analyzer` en modo editable.

```bash
python3 -m venv <carpeta-temporal>/venv
<carpeta-temporal>/venv/bin/pip install -r requirements.txt httpx
<carpeta-temporal>/venv/bin/pip install -e ../../packages/shared/incidents_analyzer
```

**Aprendizaje:** un entorno virtual es una "caja" de librerías aislada. Para probar sin ensuciar el proyecto, se usa una caja aparte.

### 🔴 5. Una prueba mal diseñada dio un resultado confuso

**Síntoma:** probé un proveedor con tarifa `1e999` y recibí un 500, pero había puesto a propósito una categoría inválida (`"IT"`).

**Causa:** el 500 no venía de la tarifa en sí, sino de que la API **intentaba fabricar el mensaje de error 422** y no podía convertir `infinito` a JSON.

**Solución:** en el informe se describió **exactamente lo que se vio** (el 500 está verificado) y se marcó como "leído" lo que solo se deduce (que con una categoría válida el infinito podría llegar a guardarse).

**Aprendizaje:** cuando una prueba no aísla la causa, hay que decirlo. Mejor "esto pasa, y esto otro lo sospecho" que mezclar ambas cosas.

### 🔴 6. Una de mis pruebas no probaba lo que creía

**Síntoma:** en la primera prueba de proveedores mandé el cuerpo JSON **sin la cabecera `Content-Type: application/json`**, y la API respondió que no era un objeto válido.

**Solución:** repetirla con la cabecera correcta en una segunda prueba y descartar la primera como no válida.

**Aprendizaje:** antes de culpar al código, comprueba que **tu prueba** está bien hecha.

---

## 6. Los hallazgos explicados con ejemplos

Aquí tienes los más importantes **en lenguaje llano**. El detalle técnico está en el [informe](./docs/AUDITORIA-gestion-errores.md).

### E-01 · Los errores inesperados salen "desnudos"

```
Qué pasó:    La API falla por algo imprevisto.
Qué responde: 500, texto plano "Internal Server Error", sin cabeceras CORS.
Qué ve el usuario: "No se pudo conectar con el servidor" (¡mentira!).
```

**Arreglo breve:** un middleware que capture cualquier excepción y devuelva un JSON limpio con un `error_id`; el detalle técnico va al **log**, no al usuario. Así, si el usuario dice "me salió el error ab12cd34", se busca esa referencia y se encuentra la causa.

> 💡 Un mensaje de error bueno **no enseña tripas** (rutas, trazas) al usuario, pero **deja una pista** al equipo.

### E-02 · Un CSV puede tumbar o saturar la API

Se probó subir un CSV con una celda de 200.000 caracteres → **500**. Y uno de unos 20 MB con 400.000 filas → **aceptado y procesado entero en memoria**.

**Arreglo breve:** poner un tamaño máximo (`413`) y capturar el error del lector de CSV para devolver un `400` con un mensaje claro.

> 💡 **Regla de oro:** *nunca confíes en lo que te manda el usuario*. Tamaño, formato, contenido… todo se valida.

### E-03 · Un usuario podía descargar el análisis de otro

La API guardaba "el último análisis" en **una variable global**. Se comprobó: A analiza un fichero, y B (otra cuenta) lo descarga.

```python
_last_result = None      # ← UNA sola para todos los usuarios
```

**Arreglo breve:** guardarlo **por usuario**, o devolver el CSV en la misma respuesta del análisis.

> 💡 Una variable global en un servidor es compartida por **todas** las personas que lo usan.

### E-04 · La web decía "recibido" sin haber enviado nada

```ts
const submit = (event) => {
  ...
  if (!Object.keys(e).length) setSent(true);   // ← solo cambia una variable
};
```

No hay `fetch`: **ningún dato sale del navegador**, pero se muestra "Hemos recibido tu información". Un candidato podría creer que su perfil llegó.

> 💡 Una interfaz que **miente** es peor que una que falla. Si algo es simulado, que no afirme lo contrario.

### E-05 · Un solo registro malo rompía todo el panel

Se metió en la base un documento al que le faltaban campos → `GET /api/incidents` y `/summary` devolvieron **500 para todos**.

**Arreglo breve:** al leer, **saltarse el registro defectuoso y apuntarlo en el log**, en vez de dejar que arrastre a los demás.

> 💡 Esto se llama **degradación elegante**: si una pieza falla, el resto sigue funcionando.

### E-08 · Una caída momentánea cerraba tu sesión

Al recargar la página, el frontend pregunta `/auth/me` para confirmar la sesión. Si esa pregunta fallaba **por cualquier motivo** (incluso un fallo de red de un segundo), borraba el token. Es decir: un parpadeo = te echa.

**Arreglo breve:** borrar el token **solo si la respuesta es 401** (token inválido). Ante otros errores, ofrecer "Reintentar".

### E-11 · El script mostraba trazas feas

`scripts/analyze.py` con un fichero que no es UTF-8, o sin teclado disponible (CI), terminaba con un `Traceback` de Python en vez de un mensaje. Se comprobó ejecutándolo.

**Arreglo breve:** capturar `UnicodeDecodeError`, `EOFError` y el error de escritura, con un mensaje claro y un código de salida.

---

## 7. Qué NO se hizo (y por qué)

| No se hizo | Por qué |
|---|---|
| Corregir ningún fallo | La regla del encargo era solo reportar |
| Proponer nuevas funcionalidades | Fuera del alcance |
| Reorganizar el código | "Sin refactorizaciones fuera del alcance" |
| Leer ni ejecutar los tests e2e | Se centró en el código de producción; está anotado como límite |
| Auditar producción | No está en el repositorio |
| Fusionar o tocar la rama `feature/incident-manager` | Solo se leyó para ver qué arreglaba |

---

## 8. Glosario

| Término | Significado simple |
|---|---|
| **Auditoría** | Revisar algo con criterio para encontrar problemas y documentarlos, sin arreglarlos |
| **Resiliencia** | Capacidad de seguir funcionando (o fallar bien) cuando algo sale mal |
| **Severidad** | Lo grave que es un problema: alta, media, baja |
| **Evidencia** | La prueba de que el problema existe (algo ejecutado, no solo una sospecha) |
| **Traceback / traza** | El volcado técnico de un error de Python. Útil para el equipo, **mal para el usuario** |
| **Middleware** | Filtro que se ejecuta entre la petición y la respuesta |
| **CORS** | Regla del navegador sobre qué dominios pueden leer respuestas de otros |
| **Rate limiting** | Límite de peticiones por tiempo, para frenar abusos (devuelve `429`) |
| **Lock (cerrojo)** | Mecanismo para que dos procesos no modifiquen lo mismo a la vez |
| **Error boundary** | Pieza de React que muestra una pantalla de error en lugar de dejar la página en blanco |
| **Degradación elegante** | Que una pieza rota no tumbe todo lo demás |
| **Entorno virtual (venv)** | Caja aislada de librerías Python, separada del sistema y del proyecto |
| **Código muerto** | Código que existe pero nadie usa (como `src/` de la raíz) |

---

## 9. Ejercicios para practicar

1. **Explica con tus palabras** por qué un 500 sin cabeceras CORS se ve como "no hay conexión" en el navegador.
2. **Reproduce E-03 a mano:** arranca la API, crea dos usuarios, que uno suba un CSV a `/api/incidents/analyze` y que el otro llame a `/api/incidents/results/export`. ¿Qué ves? ¿Cómo lo arreglarías?
3. **Clasifica:** ¿alta, media o baja? Justifícalo. (a) El token está en `localStorage`. (b) El formulario web dice "recibido" sin enviar. (c) El directorio de usuarios lo ve cualquier sesión.
4. **Escribe un mensaje de error** para el usuario cuando falla la subida de un CSV demasiado grande. Debe estar en español, decir qué hacer y **no** enseñar ningún detalle técnico.
5. **Detecta tú sola:** abre `uis/backoffice/src/views/SuppliersPage.tsx` y busca qué mensajes de error ve el usuario. ¿Alguno está en inglés?
6. **Piensa:** ¿por qué el informe separa "Verificado" de "Leído"? ¿Qué pasaría si todo se presentara como verificado?

---

## 10. Segunda pasada: `try/catch` ausente y `catch` demasiado amplio

Después del primer informe llegaron **dos criterios más concretos** para revisar **cada archivo**. El resultado está en la *Parte 2* del [informe](./docs/AUDITORIA-gestion-errores.md) (14 hallazgos nuevos, con códigos `T-xx` y `C-xx`).

### 10.1 Los dos criterios, explicados

**Criterio 1 — `try/catch` ausente.** Cualquier cosa que pueda fallar *desde fuera de tu código* necesita protección: una llamada a la API (`fetch`), leer un fichero, convertir texto a JSON, o un `await`. Si falla y nadie lo captura, el programa se rompe o muestra un mensaje inútil.

```ts
// ❌ Si el servidor devuelve HTML en lugar de JSON, esto lanza SyntaxError y nadie lo explica
return response.json();

// ✅ Capturas solo esa línea y das un mensaje claro
try {
  return await response.json();
} catch {
  throw new ApiError("Respuesta no válida del servidor", response.status);
}
```

**Criterio 2 — `catch` demasiado amplio.** El problema contrario: un `try` que envuelve **demasiado código** captura errores que no esperabas y les pone el mensaje equivocado.

```ts
// ❌ El try incluye también onSaved(). Si onSaved falla, sale "No se pudo crear"
//    aunque la incidencia YA se creó. El usuario reintenta y crea un duplicado.
try {
  onSaved(await createIncident(payload));
} catch {
  setError("No se pudo crear la incidencia.");
}

// ✅ El try solo envuelve lo que puede fallar por la API
let created;
try {
  created = await createIncident(payload);
} catch {
  setError("No se pudo crear la incidencia.");
  return;
}
onSaved(created);
```

> 💡 **Regla práctica:** el `try` debe envolver **lo mínimo** (la operación que falla) y el `catch` debe capturar **solo los errores que sabes tratar**. Un `try` gigante es como un cartel de "algo ha ido mal" en la puerta de todo un edificio.

### 10.2 Cómo se hizo la pasada

1. **Inventario con búsquedas:** se buscaron todas las operaciones de riesgo (`fetch`, `await`, `.json()`, `JSON.parse`, `open`, `read_text`, `json.loads`, `csv`, `TinyDB(`, `int(`) y todos los `try/catch/except`. Así no depende de la memoria o de la suerte.
2. **Lectura de cada bloque**, mirando *qué envuelve* y *qué captura*.
3. **Comprobación ejecutando** las sospechas más graves (ver los problemas de abajo).
4. **Tabla de "ficheros sin hallazgos"**: también se apunta lo que está **bien**, y qué ejemplo seguir (por ejemplo, la lectura del CSV en `seed_incidents.py`).

### 10.3 Decisiones de esta pasada

| Decisión | Por qué |
|---|---|
| Añadir una **Parte 2** en el mismo informe en lugar de uno nuevo | Un solo documento para el tech lead, con un resumen unificado |
| Códigos nuevos `T-xx` (try ausente) y `C-xx` (catch amplio) | Se distingue de un vistazo qué criterio incumple cada hallazgo |
| No volver a contar lo ya reportado: C-02 **amplía** E-08 | Evita inflar la cifra de hallazgos con el mismo problema |
| Marcar `catch {}` vacío de `SupplierRow` como **aceptable** | Tiene comentario y el error ya lo muestra otra parte de la pantalla: un `catch` vacío no siempre es malo |
| Revisar otra vez la rama para ver si ya arregla algo | Evita pedir correcciones que ya existen |

### 10.4 Lo que se descubrió (los más importantes)

**T-01 — Una fila con un estado raro tumba todo el análisis (Alta).** El validador del CSV no comprueba que el estado sea `OPEN`, `CLOSED` o `DISCARDED`, pero el análisis usa el estado como clave de un diccionario:

```python
status_counts[status] += 1     # KeyError si status == "PENDING"
```

Se ejecutó y se confirmó: el script termina con `KeyError: 'PENDING'` y la API responde `500`. La corrección: que el validador cuente esa fila como **inválida** (el *seed* ya lo hacía, solo faltaba en el validador).

> 💡 **Aprendizaje:** cuando un dato "no válido" llega a una operación que asume que es válido, hay un hueco entre la validación y el uso. Se arregla validando **lo mismo que luego se usa**.

**T-02 — Las bases de datos se abren sin ninguna protección (Alta).** Se crearon ficheros `db.json` estropeados a propósito:
- Con `users/db.json` corrupto, **nadie puede hacer login** (`500`).
- Con `suppliers/db.json` corrupto, **la API ni siquiera arranca** (falla al importar el módulo).

> 💡 Los ficheros también se corrompen (corte de luz, edición a mano). Todo lo que lee un fichero necesita un plan para cuando el fichero está mal.

**T-04 — "Contraseña incorrecta" cuando la contraseña era correcta (Media).** Si el navegador no deja guardar el token (modo privado), `setToken` falla en silencio. Después la web pide tus datos sin token y recibe un `401`, que la pantalla traduce como *"Email o contraseña incorrectos"*. El usuario cree que se equivoca.

> 💡 **Un `catch` que se traga un error puede producir un mensaje falso más adelante.** El error real (no se pudo guardar) se perdió y apareció otro distinto (credenciales).

**C-01 — Mensaje de error aunque se guardó bien (Media).** Es el ejemplo del recuadro de arriba: el `try` incluye la acción posterior a guardar.

### 10.5 Problemas que aparecieron en esta pasada

#### 🔴 1. Mi comprobación no mostró nada
**Síntoma:** ejecuté tres CSV de prueba y la salida salió vacía, sin errores ni resultados.
**Causa:** la carpeta temporal con el entorno virtual **se había borrado entre una respuesta y otra**, y mi `grep` ocultaba el mensaje de "no existe el ejecutable".
**Solución:** mirar la salida *sin filtrar* (apareció `No such file or directory`), ver qué quedaba en la carpeta temporal y rehacer el entorno.
**Aprendizaje:** **un resultado vacío no significa "todo bien"**. Si una comprobación no muestra nada, hay que sospechar de la propia comprobación antes de sacar conclusiones.

#### 🔴 2. No hacía falta el entorno virtual para todo
**Síntoma:** repetir la instalación de librerías para probar el script.
**Solución:** `scripts/analyze.py` solo usa la biblioteca estándar de Python, así que se ejecutó con el `python3` del sistema. El entorno virtual solo se rehízo para las pruebas de la API.
**Aprendizaje:** antes de instalar nada, comprueba **qué necesita realmente** lo que vas a probar.

#### 🔴 3. Dos de mis ediciones se interrumpieron
**Síntoma:** al actualizar el informe, dos modificaciones se rechazaron y paraste el proceso.
**Solución:** esperé tu indicación (*"continúa"*) y rehice las ediciones sin cambiar el plan.
**Aprendizaje:** si alguien interrumpe, se **para y se espera**, no se insiste ni se busca otra vía.

### 10.6 Ejercicios de esta parte

1. Busca en `uis/backoffice/src/components/suppliers/SupplierForm.tsx` el `try/catch` y reescríbelo para que `onCreated` quede **fuera** del `try`.
2. Crea tú un CSV con `status = PENDING` y ejecuta `python scripts/analyze.py tu.csv`. ¿Qué error ves? ¿Qué línea de `core.py` lo provoca?
3. Explica con tus palabras por qué un `catch {}` **vacío** puede ser aceptable en `SupplierRow` pero peligroso en `setToken`.
4. Estropea un `db.json` (con `{corrupt`) en una copia del proyecto y arranca la API. ¿Qué ves? ¿Qué mensaje le darías al administrador?
5. **Pregunta de reflexión:** ¿cuál es mejor, un `try` grande que lo captura todo, o varios `try` pequeños? Pon un ejemplo de cada caso donde uno sea preferible.

---

## 11. Tercera pasada: fallos silenciosos

El tercer criterio es el más traicionero: **errores que ocurren, se capturan y nadie se entera.** El resultado está en la *Parte 3* del [informe](./docs/AUDITORIA-gestion-errores.md) (10 hallazgos nuevos, códigos `S-xx`).

### 11.1 Qué es un fallo silencioso

Un error **ruidoso** (un 500, una pantalla roja) es molesto, pero se arregla porque se ve. Un error **silencioso** no se ve, y por eso dura meses. Hay tres formas típicas:

```ts
// 1) catch vacío: el error desaparece
try { localStorage.removeItem("token"); } catch { }

// 2) except: pass (Python): lo mismo
try:
    borrar_fichero()
except Exception:
    pass

// 3) log sin acción: se escribe el aviso y todo sigue como si nada
logger.warning("SECRET_KEY no definida")   # ...y el servidor arranca igual
```

> 💡 **La pregunta clave** ante cualquier `catch`: *"si esto falla, ¿quién se entera y qué cambia?"*. Si la respuesta es "nadie y nada", es un fallo silencioso.

### 11.2 Cómo se buscó

1. **Inventario con búsquedas** de cada `catch`, `.catch(`, `except`, `pass`, `logger.*`, `print` y `console.*`.
2. **Clasificar cada uno** en tres grupos: *ruidoso* (avisa al usuario o relanza), *aceptable* (silencioso pero justificado) y *peligroso*.
3. **Comprobar lo que se podía ejecutar** (ver el problema 1 de abajo).
4. **Enlazar con lo ya reportado**: varios hallazgos anteriores (E-04, E-14, T-04…) también eran silenciosos. Se hizo una tabla de mapa para no contarlos dos veces.

### 11.3 Lo que se encontró

**Resultado del inventario (las buenas noticias primero):**
- En Python **no hay ningún `except: pass`**. Todos los `except` relanzan el error, lo convierten en una respuesta HTTP o devuelven algo con sentido.
- En el frontend hay 7 `catch` que **no recogen el error**. 4 tienen el cuerpo vacío y solo un comentario.

**Los hallazgos más importantes:**

**S-03 — Los logs de nivel INFO no se ven nunca (verificado).** El backend escribe "Migrated N legacy users…" con `logger.info`, pero **nadie configuró el logging**. Se reprodujo con un programa mínimo:

```
WARNING: SECRET_KEY is not set (visible?)     ← aparece
(la línea INFO no aparece)
root handlers: []  | root level: WARNING
```

Python, sin configuración, solo muestra `WARNING` o superior. Así, las migraciones que **modifican ficheros** al arrancar no dejan ninguna constancia.

> 💡 **Aprendizaje:** escribir un `logger.info(...)` no basta; hay que **configurar** a dónde va y con qué nivel. Un log que nadie puede leer es tan inútil como no tenerlo.

**S-04 — Un aviso que no hace nada.** Cuando no hay ningún usuario y no se han definido las variables del primer administrador, el código escribe *"nobody can log in"*… y la API arranca igual. Como el registro público solo crea usuarios normales, **nadie podrá ser administrador** hasta que alguien lea ese aviso.

> 💡 Un log sin acción es una nota en una botella. Si la situación es grave, el programa debe **parar o cambiar su comportamiento**, no solo escribir.

**S-02 — "Cerrar sesión" que no cierra.** Si el navegador no deja borrar el token, el `catch` vacío lo ignora y la web sigue con la sesión abierta. En un ordenador compartido, el usuario cree que salió y no es así.

**S-05 — Se borran datos sin dejar rastro.** Al arrancar, `sync_profiles` **borra** los perfiles huérfanos y crea los que faltan, sin escribir un solo log. Si por un fallo un fichero de usuarios estuviera vacío, se borrarían perfiles de personas reales sin constancia.

**S-01 — Se pierde la causa del error.** `apiFetch` cambia cualquier fallo de red por *"No response from the server"* y tira el error original. Así se confunden un corte de internet, el 500 sin CORS que ya vimos (E-01) y un error de configuración.

### 11.4 Decisiones de esta pasada

| Decisión | Por qué |
|---|---|
| Separar **"catch aceptable"** de **"catch peligroso"** | No todo `catch` silencioso es un fallo: `getToken` devolviendo `null` si el almacenamiento está bloqueado es un valor de reserva razonable |
| Poner una tabla con los **aceptables** | El tech lead ve que se miraron y por qué se dieron por buenos |
| Reconocer que **en Python no hay `except: pass`** | Un informe justo cuenta también lo que está bien |
| No inventar severidad **Alta** nueva | El fallo silencioso más grave (E-04, los datos que se pierden) ya estaba reportado como Alta |
| Enlazar con la rama | Comprobar con `git grep` que la rama añade logs pero sigue sin configuración (S-03) |

### 11.5 Problemas que aparecieron en esta pasada

#### 🔴 1. Mi primera idea de un hallazgo podía estar equivocada
**Síntoma:** pensé que "solo los logs de WARNING se ven" pero no estaba seguro de si los `info` aparecían.
**Solución:** en vez de suponer, ejecuté un `logger.info` y un `logger.warning` sin configurar. El `info` no salió; el `warning` sí.
**Aprendizaje:** si dudas de cómo se comporta algo, **pruébalo** en 5 líneas. Es más rápido que discutirlo.

#### 🔴 2. Dos hallazgos que parecían graves no lo eran
**Síntoma:** pensé que el rango de fechas inválido en el filtro de incidencias era un fallo silencioso (la lista no se actualiza), y que el botón de guardar el perfil sin cambios no hacía nada.
**Solución:** al leer el resto del código vi que el filtro **sí muestra** un mensaje ("La fecha «Desde» no puede ser posterior a «Hasta»") y que el botón de perfil está **desactivado** cuando no hay cambios.
**Aprendizaje:** antes de reportar un fallo, **busca el otro extremo**: a veces otra parte del código ya lo avisa. Lo descarté y no está en el informe.

#### 🔴 3. Conté mal los `catch` en el primer borrador
**Síntoma:** escribí "6 `catch {}` vacíos" y al revisar los números de línea no cuadraban.
**Causa:** mezclé `catch` **vacíos** con `catch` **sin variable** que sí hacen algo (lanzan otro error o devuelven un valor).
**Solución:** separar el recuento: 7 sin variable, de los cuales 4 vacíos de verdad.
**Aprendizaje:** **verifica las cifras que escribes** antes de entregar. Un número incorrecto resta credibilidad a todo el informe. También corregí varios números de línea que había puesto de memoria, comprobándolos con `grep -n`.

### 11.6 Ejercicios de esta parte

1. En `uis/backoffice/src/lib/token.ts`, ¿qué diferencia hay entre el `catch` de `getToken` y el de `clearToken`? ¿Por qué uno es aceptable y el otro es peligroso?
2. Ejecuta tú el experimento de `logging`: crea un fichero con `logger.info("hola")` y `logger.warning("adiós")` sin configurar nada. ¿Cuál se ve? Después añade `logging.basicConfig(level=logging.INFO)` y vuelve a probar.
3. Reescribe el `submitRate` de `SupplierRow.tsx` para que, cuando el valor sea inválido, muestre un mensaje en lugar de no hacer nada.
4. **Pregunta de reflexión:** ¿cuándo es correcto que un `catch` esté vacío? Escribe tres casos reales y explica cómo lo justificarías con un comentario.
5. Clasifica como *ruidoso*, *aceptable* o *peligroso*: (a) `catch { return null }` al leer `localStorage`; (b) `except: pass` al borrar un fichero temporal; (c) `logger.warning("sin usuarios")` y seguir arrancando.

---

## 12. Cuarta pasada: errores en crudo

El cuarto criterio mira el **otro lado de la pantalla**: lo que ve la persona que usa la aplicación. El resultado está en la *Parte 4* del [informe](./docs/AUDITORIA-gestion-errores.md) (4 hallazgos nuevos, códigos `R-xx`).

### 12.1 Qué es un error "en crudo"

Es un mensaje pensado **para programadores** que acaba delante de un **usuario**. Cuatro tipos:

| Tipo | Ejemplo | Por qué es un problema |
|---|---|---|
| **Stack trace** | `Traceback (most recent call last): File "core.py", line 199…` | Enseña rutas y código interno; asusta y no ayuda |
| **Código HTTP** | `404`, `Method Not Allowed` | Al usuario le da igual el número; quiere saber qué hacer |
| **Error de parseo** | `Unexpected token < in JSON at position 0` | Es un fallo interno de JavaScript, no del usuario |
| **Mensaje interno del servidor** | `value is not a valid email address: The part after the @-sign is a special-use or reserved name…` | Está en inglés, usa jerga y no dice qué cambiar |

> 💡 **Un buen mensaje de error responde a tres preguntas:** ¿qué ha pasado?, ¿es culpa mía?, ¿qué hago ahora? ("El email no es válido. Usa uno como nombre@empresa.com.")

### 12.2 Cómo se hizo (la parte más interesante)

En vez de adivinar qué verían los usuarios, se **simuló el recorrido completo**:

1. **Inventario:** se buscaron todos los sitios del frontend que pintan texto que viene del servidor.
2. **Provocar errores reales:** con un script se mandaron **28 peticiones incorrectas** a la API (ruta que no existe, JSON roto, campos que faltan, ficheros erróneos, tokens falsos…) y se guardaron las respuestas.
3. **Pasarlas por el código real del frontend:** se copiaron literalmente las funciones `toApiError` y `describeError` a un pequeño programa de Node y se ejecutaron con esas 28 respuestas.
4. **Leer el resultado** como lo leería el usuario.

Así se obtuvo una tabla con el texto exacto que sale en pantalla, en lugar de suposiciones.

> 💡 **Aprendizaje:** para saber qué ve el usuario, **reproduce lo que ve el usuario**. Leer el código te dice qué *debería* pasar; ejecutarlo te dice qué *pasa*.

### 12.3 Lo que se encontró

**R-02 — El caso más claro (verificado).** Escribes un email como `cliente@empresa.test`. El navegador lo da por bueno (su expresión regular solo mira que tenga `@` y un punto). Pero la API usa una librería más estricta que rechaza dominios reservados como `.test`. Resultado en pantalla:

```
customer_email: value is not a valid email address: The part after the
@-sign is a special-use or reserved name that cannot be used with email.
```

Está en inglés, usa el nombre interno del campo (`customer_email`) y **no le dice al usuario qué hacer**. Es un caso de **dos validaciones que no coinciden**: la del navegador y la del servidor.

**R-01 — Mensajes en inglés y con jerga en proveedores y análisis de CSV.** Algunos ejemplos reales que se vieron:

| Situación | Texto en pantalla |
|---|---|
| API caída | `No response from the server` |
| Fallo del servidor | `Internal Server Error` |
| Sueltas un `.txt` en la zona de subida | `Expected a .csv file, got: notas-juan.txt` |
| Descargas tras reiniciar la API | `No analysis has been run yet. Call POST /api/incidents/analyze first.` |

El último menciona **un método HTTP y un endpoint** a una persona que solo quería descargar un fichero.

**R-03 — La documentación de la API es pública.** Sin iniciar sesión, `/docs` y `/openapi.json` responden, y el esquema lista las 22 rutas internas. No hay secretos, pero es un mapa para quien quiera atacar.

### 12.4 Lo bueno que también se comprobó

Este informe es justo con lo que está bien hecho:
- **Ningún traceback llega al navegador.** Un fallo inesperado solo devuelve `Internal Server Error`.
- **Los errores de JavaScript nunca se muestran.** Todas las pantallas hacen `err instanceof ApiError ? … : "texto en español"`.
- **El login solo usa dos mensajes fijos.**
- **`describeError` ya traduce bien** los códigos 0, 5xx, 403, 404 y 409. El problema es que **solo una parte de las pantallas la usa**.

### 12.5 Decisiones de esta pasada

| Decisión | Por qué |
|---|---|
| Hacer una sección de **"lo que NO llega en crudo"** | Demostrar lo que se comprobó y está bien |
| Reportar solo los casos **alcanzables** | Para no inflar el informe con situaciones que la interfaz no permite; los hipotéticos se marcan como tales |
| Poner la **tabla situación → texto exacto** | Un tech lead entiende un ejemplo real más rápido que una descripción |
| No contar dos veces lo ya reportado | E-01, E-10, E-11 y E-19 también eran errores en crudo; van en una tabla de mapa |
| Severidad **Media** para R-01 y R-02 | Afectan a personas reales con datos normales (un email, una subida de fichero) |

### 12.6 Problemas que aparecieron en esta pasada

#### 🔴 1. Mi tabla mezclaba combinaciones que no ocurren
**Síntoma:** el programa de prueba imprimía, para cada respuesta, dos textos: el de `err.message` y el de `describeError`. Al leerlo, algunas combinaciones eran absurdas (por ejemplo, "email duplicado" pasado por `describeError`, que diría "la incidencia ha cambiado de estado").
**Causa:** las dos funciones se usan en **pantallas distintas**; cada respuesta solo pasa por una de ellas.
**Solución:** en el informe solo puse las combinaciones **reales** (qué pantalla usa qué función) y dejé fuera las demás.
**Aprendizaje:** una herramienta que te da todos los resultados no te dice cuáles importan. **El filtro lo pones tú.**

#### 🔴 2. Un número de línea mal copiado
**Síntoma:** cité `main.py:41` para la creación de la aplicación.
**Solución:** lo comprobé con `grep -n` y era la línea 36. También ajusté otro rango en `api.ts`.
**Aprendizaje:** otra vez, **verificar lo que escribes**. Es la segunda pasada en que ocurre; por eso ahora compruebo las líneas citadas antes de dar nada por terminado.

#### 🔴 3. Dudaba de si el email era realmente un problema
**Síntoma:** sospechaba que el navegador y el servidor tenían reglas distintas para el email, pero no estaba seguro.
**Solución:** probé la expresión regular del navegador con tres emails y comprobé que acepta los tres, y la API rechaza `.test` (respuesta real guardada).
**Aprendizaje:** las sospechas se convierten en hallazgos cuando tienen **una prueba de dos líneas** detrás.

### 12.7 Ejercicios de esta parte

1. Abre `uis/backoffice/src/lib/errors.ts`. ¿Qué haría falta para que `describeError` también explicara los fallos de un CSV (columnas que faltan, fichero vacío)? Escribe los textos en español.
2. Escribe tú el mensaje que le darías al usuario del caso `customer_email` con un dominio reservado. Debe decir qué ha pasado y qué hacer, sin nombres de campo internos.
3. Arranca la API y abre `http://localhost:8000/docs`. ¿Qué información puedes ver sin iniciar sesión? ¿Cuál te parece más sensible?
4. Clasifica: ¿**trazas**, **código HTTP**, **parseo** o **mensaje interno**? (a) `Method Not Allowed`; (b) `KeyError: 'PENDING'`; (c) `1: JSON decode error`; (d) `Supplier 9999 not found`.
5. **Pregunta de reflexión:** el servidor podría mandar un código estable (`email_taken`) además del texto. ¿Qué ventaja tiene para el frontend frente a leer el texto en inglés?

---

## 13. Quinta pasada: filtración de datos sensibles

El quinto criterio pregunta: **¿qué información que debería ser secreta acaba escrita o enviada donde no debe?** El resultado está en la *Parte 5* del [informe](./docs/AUDITORIA-gestion-errores.md) (7 hallazgos nuevos, códigos `D-xx`, dos de ellos **altos**).

### 13.1 Los cuatro tipos de dato sensible

| Tipo | Ejemplo | Dónde suele colarse |
|---|---|---|
| **Claves secretas** | `SECRET_KEY`, contraseñas | Logs, mensajes de error, el propio repositorio |
| **Cadenas de conexión** | `postgres://usuario:clave@servidor/db` | Código, ficheros de configuración, errores de conexión |
| **Rutas internas** | `/home/servidor/app/services/api/main.py` | Tracebacks, mensajes de error |
| **Datos personales** | emails, nombres, teléfonos | Logs de acceso, respuestas de la API, ficheros de datos |

> 💡 **Qué es un "log":** el diario que escribe el servidor (qué peticiones recibe, qué errores tiene). Lo leen personas del equipo y, a menudo, herramientas externas de monitorización. **Todo lo que se escribe en un log hay que tratarlo como "lo puede leer más gente de la que crees".**

### 13.2 Cómo se hizo

1. **Repositorio e historial completo:** se buscaron patrones de secretos (claves privadas, tokens de GitHub, claves de la nube, cadenas de conexión) en **todas las ramas y commits**, no solo en lo actual. Un secreto borrado hoy sigue estando en el historial.
2. **Ficheros peligrosos:** se comprobó que `.env` y las bases de datos (`db.json`) están ignorados por Git y que solo hay `.env.example` vacío.
3. **Imágenes:** se abrieron las capturas de `docs/screenshots/` para ver si mostraban emails o rutas.
4. **Servidor de verdad:** se arrancó la API con `uvicorn` sobre bases de datos temporales y se **provocaron fallos para leer qué escribe el log**.
5. **Probar como un desconocido:** se creó una cuenta nueva sin ningún permiso especial y se miró a qué datos podía acceder.

### 13.3 Lo que se encontró

**D-01 — La contraseña del administrador, escrita en el log (Alta).** Se arrancó la API con `AUTH_INITIAL_PASSWORD='abc'` (demasiado corta). El log mostró:

```
String should have at least 8 characters [type=string_too_short, input_value='abc', input_type=str]
```

La librería de validación (Pydantic) **imprime el valor que ha rechazado**, y el código no captura ese error. Si alguien escribe una contraseña casi correcta, queda en claro en el log.

> 💡 **Un dato curioso:** la herramienta de línea de comandos `create-user` **ya evitaba esto** (`include_input=False`). El mismo problema estaba resuelto en un sitio y olvidado en otro. Cuando hay una buena solución, hay que **aplicarla en todas partes**.

**D-02 — Cualquiera podía leer los emails de los clientes (Alta).** La cadena completa, comprobada paso a paso:

1. Un desconocido se registra en `/users` (es público): `201`, cuenta activa **al instante**, sin aprobación.
2. Pide el detalle de una incidencia: `200`, con el **email completo del cliente** (`maria.garcia@cliente-real.com`) y el email del empleado que la creó.
3. La lista sí enmascaraba el email (`m***@…`), pero **esa protección se anulaba con una sola petición más**.

> 💡 **Aprendizaje:** una protección vale lo que vale su **punto más débil**. Enmascarar el dato en la lista no sirve si el detalle lo da entero. Y "estar autenticado" no es lo mismo que "tener permiso": cualquiera puede crear una cuenta.

**D-03 — El log de accesos guarda lo que buscas (Media).** Cada petición queda registrada con su dirección completa, incluida la parte de después del `?`:

```
GET /api/incidents?client_company=Acme+Corporation+Real+SL&q=maria.garcia&agent_id=AGT-07
```

Lo que alguien escribe en un buscador (un nombre, parte de un email) acaba en el log sin control. En cambio, el **login fallido no deja el usuario** porque viaja en el cuerpo de la petición y no en la dirección: eso estaba bien.

### 13.4 Lo que se comprobó que está bien

Un informe justo cuenta también esto:
- **Ningún secreto real en todo el historial.** Solo un marcador `choose-a-password`.
- **No hay cadenas de conexión**: la API usa ficheros, no un servidor de base de datos.
- **El hash de la contraseña nunca sale** en ninguna respuesta (se comprobaron seis endpoints).
- **Las rutas internas no salen** en las respuestas de error.
- **Las capturas de pantalla están limpias.**
- **El token solo lleva `user_id` y la caducidad.**

### 13.5 Decisiones de esta pasada

| Decisión | Por qué |
|---|---|
| Dos hallazgos **Altos**, solo para lo demostrado de extremo a extremo | D-01 y D-02 se probaron con ejecuciones reales; los demás, que solo se deducen del código, se quedan en Baja |
| Incluir la tabla **"Lo que NO se filtra"** al principio | El tech lead ve qué se revisó y está bien, y no vuelve a buscarlo |
| Marcar D-05 (permisos de ficheros) como **leído** y no como verificado | Mi entorno de pruebas tenía una configuración de permisos distinta; no podía asegurar el resultado real |
| Explicar el **límite** de la protección de Pydantic | Recorta los valores largos pero deja ver unos 24 caracteres del principio y del final: no es una garantía |
| Avisar de que la corrección de E-01 debe cuidar esto | Al registrar los errores 500 con `logger.exception` se podría repetir el mismo problema |

### 13.6 Problemas que aparecieron en esta pasada

#### 🔴 1. Esperaba una filtración y el log estaba limpio
**Síntoma:** corrompí un usuario y una incidencia para ver si el log mostraba el hash de la contraseña o un email. Esperaba encontrarlos.
**Causa:** Pydantic **recorta** los diccionarios largos por el centro (`input_value={'id': '2f32…Z'}`), así que el hash y el email quedaron fuera de la parte visible. Y en la incidencia el fallo era otro (un campo que faltaba, sin datos personales).
**Solución:** **no reportarlo** como filtración. Sí reporté el caso real (D-01, la contraseña corta, que no se recorta) y expliqué en el informe por qué.
**Aprendizaje:** una sospecha que la prueba no confirma **se descarta**. Un informe lleno de "podría pasar" pierde credibilidad.

#### 🔴 2. Mi comando devolvió "Exit code 143"
**Síntoma:** la prueba del desconocido terminó con un error de salida, aunque imprimió todos los resultados.
**Causa:** al final apago el servidor con `kill` y luego espero a que termine (`wait`); un proceso terminado así devuelve el código 143, que es normal.
**Solución:** comprobar que los resultados impresos estaban completos y tratar el 143 como una señal inocua.
**Aprendizaje:** **un código de salida distinto de 0 no siempre es un error del programa**; hay que mirar qué lo provocó.

#### 🔴 3. El cálculo de los permisos de los ficheros no era fiable
**Síntoma:** los ficheros de datos aparecían con permisos `rw-r--rw-` (escribibles por todos), algo que el código no hace.
**Causa:** mi entorno de pruebas aplicaba otra máscara de permisos que la configuración habitual.
**Solución:** en lugar de reportar un dato que no podía garantizar, lo marqué como **"leído"** (no hay ningún `chmod`) y dije que normalmente quedarían en `644`.
**Aprendizaje:** **conoce los límites de tu entorno de pruebas** y no presentes como un hecho lo que solo ocurre en él.

#### 🔴 4. Casi cito mal tres líneas de código
**Síntoma:** puse `users/router.py:46`, `incident_router.py:101` y `:62-77`.
**Solución:** las comprobé con `grep -n`: eran 47, 100 y 74. (Es la tercera pasada en la que corrijo líneas, así que ya lo hago siempre antes de cerrar.)

### 13.7 Ejercicios de esta parte

1. Arranca la API con `AUTH_INITIAL_PASSWORD=abc` y mira el log. ¿Dónde aparece `abc`? Ahora escribe cómo cambiarías `bootstrap_first_user` para que aparezca un mensaje útil **sin** la contraseña.
2. Regístrate con una cuenta nueva y abre una incidencia por `GET /api/incidents/NXV-000001`. ¿Qué datos personales ves? ¿Cuál tendría que ver solo un administrador?
3. Explica con tus palabras por qué la contraseña viaja en el **cuerpo** de la petición del login y no en la dirección (`/auth/login?password=…`). ¿Qué pasaría en el log de accesos?
4. Busca en el repositorio un dato que **parezca real pero sea de ejemplo** (pista: `data/raw/`). ¿Cómo dejarías claro a quien lo vea que es ficticio?
5. **Pregunta de reflexión:** en un log de errores, ¿qué es más útil para encontrar el fallo: el valor que falló o el *nombre del campo* y la *regla incumplida*? ¿Por qué la segunda opción es más segura?

---

## 14. Sexta pasada: interfaz sin estados de carga ni de error

El sexto criterio mira lo que ve la persona **mientras algo tarda o cuando algo falla**. El resultado está en la *Parte 6* del [informe](./docs/AUDITORIA-gestion-errores.md) (11 hallazgos nuevos, códigos `U-xx`, uno de ellos **alto**).

### 14.1 Los estados de una pantalla

Una pantalla que pide datos a una API no tiene un solo aspecto, tiene **cuatro**. Si falta alguno, la persona se pierde:

| Estado | Qué debe ver la persona | Si falta… |
|---|---|---|
| **Cargando** | Un indicador (spinner, "Cargando…") | Cree que la pantalla está rota o vacía |
| **Con datos** | La información | — |
| **Vacío** | "Todavía no hay incidencias" | Ve una tabla vacía sin explicación |
| **Error** | Un aviso claro y un botón **"Reintentar"** | Se queda sin salida |

> 💡 **Error ≠ vacío.** Una de las cosas que se encontraron es justo mezclar los dos: mostrar "No hay proveedores" cuando en realidad la API había fallado.

Y hay un **quinto** concepto, el **plan B seguro** (*fallback*): qué se enseña si llegan datos raros o si el propio código de la pantalla falla.

### 14.2 Cómo se hizo (lo más completo hasta ahora)

Esta vez **no se leyó el código y se supuso: se usó la aplicación de verdad.**

1. **Inventario:** una tabla de qué componente hace peticiones y qué indicadores de carga y error tiene.
2. **Arrancar todo:** la API con datos de prueba (25 incidencias, 15 proveedores), el backoffice y la web pública.
3. **Un navegador automático** (Playwright con Chromium) que abre las pantallas y **sabotea las peticiones a propósito**:
   - API lenta (3-4 segundos),
   - API que **no responde nunca**,
   - error 500,
   - red caída,
   - respuesta `200` pero con un JSON incompleto o con HTML.
4. **Anotar lo que se ve** en cada caso: texto, spinners, avisos y botones, y guardar capturas de pantalla.
5. **Apagar todo y dejar el repositorio limpio.**

> 💡 **Aprendizaje:** esto se llama *prueba de caos* a pequeña escala: en lugar de esperar a que el fallo ocurra, **lo provocas tú en un entorno de prueba** y miras qué pasa. Así descubres problemas que nunca verías con la aplicación funcionando bien.

### 14.3 Lo que se encontró

**U-01 — Sin tiempo máximo (Alta).** Ninguna petición tiene un límite de espera. Si la API no responde, la pantalla **se queda cargando para siempre**. El caso más serio: al recargar la página con la API colgada, la persona ve solo `Comprobando la sesión…`, **sin spinner y sin ningún botón**. Ni siquiera puede cerrar sesión.

```ts
// Hoy
const response = await fetch(url);                       // espera lo que haga falta, sin límite

// Con un tiempo máximo (la corrección breve)
const response = await fetch(url, { signal: AbortSignal.timeout(20000) });   // se rinde a los 20 s
```

**U-02 — "No hay proveedores" cuando en realidad hay un error (Media).** La captura lo muestra: arriba el aviso rojo `Internal Server Error`, y debajo, en la tabla, *"No hay proveedores con esos filtros"*. La persona puede creer que se han borrado.

**U-03 — Un fallo secundario oculta lo principal (Media).** La pantalla de incidencias pide a la vez la lista y el resumen con `Promise.all`. Si falla **solo el resumen**, **la lista también desaparece**, aunque estuviera bien.

> 💡 `Promise.all` es "todo o nada": si una promesa falla, falla el conjunto. Lo que es secundario debe cargarse aparte para que su fallo no se lleve por delante lo importante.

**U-06 — El aviso estaba fuera de pantalla (Media).** En la tabla de proveedores se pulsa el botón de una fila lejana; la acción falla y el aviso se pinta **arriba de la página, a 907 píxeles de lo que se está viendo**. La persona no ve nada y concluye que el botón no funciona.

**U-07 — Resultados antiguos disfrazados de nuevos (Media).** Se busca algo, la API falla, y la tabla **sigue mostrando las 15 filas de antes**. El aviso rojo está arriba, pero las filas parecen la respuesta a lo buscado.

**U-04 y U-05 — El plan B es seguro, pero demasiado grande.** Un dato defectuoso en una sola fila (por ejemplo `created_at: null`) hace que **toda la pantalla** se sustituya por "Algo ha salido mal". Y un fallo en el `Layout` (el menú y la guarda de sesión) no lo recoge ese plan B: aparece la pantalla por defecto de Next, **en inglés**.

**U-10 — La web pública, en blanco (Baja).** Sin JavaScript (o si el script no se descarga) el texto visible es `""` y la página queda vacía, sin ningún `<noscript>`.

### 14.4 Lo que se comprobó que está bien

Un informe justo cuenta esto también:
- **Carga:** proveedores e incidencias muestran spinner con la API lenta.
- **Errores en español** y sin tecnicismos en incidencias.
- **Detalle de una incidencia:** aviso y botón "Reintentar".
- **Crear una incidencia** con un 500: aviso, y **lo escrito se conserva**.
- **Respuesta `200` con HTML** en lugar de JSON: mensaje correcto.
- **Existe una pantalla de error general**, que evita la pantalla en blanco en la mayoría de los fallos.

### 14.5 Decisiones de esta pasada

| Decisión | Por qué |
|---|---|
| **Ejecutar** la interfaz en un navegador en lugar de solo leer el código | Un estado de carga o de error es algo que se **ve**; leer `if (loading)` no te dice si se ve bien |
| Probar siempre **dos extremos**: "lento" y "nunca responde" | Son fallos distintos: uno necesita un spinner, el otro necesita un **tiempo máximo** |
| Marcar todo como **verificado**, salvo lo que no se ejecutó | Cada hallazgo de esta parte se vio con los ojos de la persona usuaria |
| Una tabla de **"evidencia nueva sobre hallazgos anteriores"** | Cuatro hallazgos (E-04, E-08, E-09, R-01) pasaron de "leído" a **comprobado en el navegador** |
| No instalar nada en el sistema **sin permiso** | Había `sudo` disponible, pero no lo usé: bajé las librerías que faltaban a una carpeta temporal |
| Dejar el repositorio **tal como estaba** | Borré los ficheros que genera el servidor de desarrollo (`.next`, cachés) y comprobé con `git status` |

### 14.6 Problemas que aparecieron en esta pasada

#### 🔴 1. Chromium no arrancaba (el mismo problema que en AUTH-02)
**Síntoma:** `error while loading shared libraries: libatk-1.0.so.0: cannot open shared object file`.
**Causa:** el navegador necesita librerías del sistema (accesibilidad, gráficos, sonido) que este entorno no trae.
**Solución sin permisos de administrador:**
1. Preparar un **índice de `apt` en una carpeta temporal** (`-o Dir::State=…`), sin tocar el del sistema.
2. **Descargar** (no instalar) los 12 paquetes `.deb` que faltaban.
3. **Extraerlos** con `dpkg -x` en otra carpeta temporal.
4. Indicar su ubicación con `LD_LIBRARY_PATH`.

**Aprendizaje:** un mensaje de error de "librería no encontrada" se resuelve pidiéndole al sistema **la lista exacta de lo que falta** (`ldd …| grep "not found"`) y no instalando cosas al azar. Y **hay vías que no requieren ser administrador**.

#### 🔴 2. Mis primeras pruebas no probaban lo que yo creía
**Síntoma:** varios escenarios devolvían resultados que no tenían sentido: sin avisos, o el mensaje de éxito sin aparecer.
**Causas (tres distintas):**
- En la web pública **faltaba marcar una opción obligatoria**, así que el formulario nunca se enviaba. Mi conclusión inicial ("no hace peticiones") era **inválida** porque la prueba no había enviado nada.
- En el formulario de incidencias **olvidé rellenar el campo "Sucursal"**; la validación lo impedía.
- El modo desarrollo de React **ejecuta los efectos dos veces**, de modo que mi regla "falla la segunda llamada" rompía la primera carga.

**Solución:** descubrir los campos reales de cada formulario con un script, rellenar todo lo obligatorio, y cambiar la regla por un **interruptor** (`failing = true` solo cuando la pantalla ya está cargada).
**Aprendizaje:** **antes de fiarte de un "no pasa nada", comprueba que tu prueba llegó a hacer lo que querías** (¿se envió el formulario? ¿había datos en la tabla?). Una prueba que falla por su propio diseño no demuestra nada.

#### 🔴 3. Mi comando se mató a sí mismo (otra vez)
**Síntoma:** `Exit code 144` al intentar apagar los servidores.
**Causa:** usé `ps | grep … | xargs kill` con patrones como `next dev`; el propio comando de mi terminal contenía esas palabras, así que **se encontró y se mató a sí mismo**. Ya me había pasado con `pkill -f`.
**Solución:** apagar por **número de proceso guardado** (`kill $(cat servidor.pid)`) y comprobar los puertos con `ss -ltn`, en comandos separados.
**Aprendizaje:** al matar procesos por nombre, **tu propio comando contiene ese nombre**. Guarda el PID al arrancarlos.

#### 🔴 4. Un hallazgo salió con un matiz distinto del que esperaba
**Síntoma:** esperaba que el login con respuesta sin `access_token` dejara guardado el texto `"undefined"` en el almacenamiento del navegador.
**Realidad:** no quedó guardado (la siguiente llamada, con un `401`, lo borró). Lo que sí se comprobó es que **el mensaje que ve la persona es "contraseña incorrecta"**, que es falso.
**Solución:** reportar **solo lo que se vio**: el mensaje engañoso. No el almacenamiento.
**Aprendizaje:** una hipótesis puede cambiar de forma al probarla. Lo que cuenta es lo observado.

#### 🔴 5. Los números de línea (por cuarta vez)
Seis de los siete rangos que cité de memoria estaban desplazados una o dos líneas; los comprobé con `grep -n`. Es ya un hábito: **nunca entrego referencias sin verificarlas.**

### 14.7 Ejercicios de esta parte

1. En `SuppliersPage.tsx`, ¿qué debería mostrar la tabla cuando `error` tiene un valor? Escribe el cambio en pseudocódigo (sin tocar el fichero).
2. Escribe la función `fetchWithTimeout(url, ms)` usando `AbortSignal.timeout`. ¿Qué mensaje en español le darías a la persona cuando salta el tiempo máximo?
3. Explica con tus palabras por qué `Promise.all([lista, resumen])` es una mala idea si el resumen es secundario. ¿Qué usarías en su lugar? (Pista: `Promise.allSettled`, o cargar cada cosa en su propio `useEffect`.)
4. Haz tú una prueba de caos con las **herramientas de desarrollo del navegador** (pestaña *Red* → "Sin conexión" o "Lento 3G"): abre las incidencias y mira qué ocurre.
5. **Pregunta de reflexión:** un `error.tsx` que sustituye **toda** la pantalla es seguro, pero poco amable. ¿Cómo lo harías más pequeño para que un fallo afecte solo a un recuadro? (Pista: *error boundary* alrededor de cada tarjeta.)

---

## 15. Séptima pasada: errores sin acción y scripts sin código de salida

El séptimo criterio tiene **dos mitades** que se ven muy distinto. El resultado está en la *Parte 7* del [informe](./docs/AUDITORIA-gestion-errores.md) (7 hallazgos nuevos: `A-xx` para la interfaz y `P-xx` para los scripts de Python).

### 15.1 Mitad A: la llamada a la acción

Un mensaje de error **informa**; una buena pantalla de error además **ayuda a salir**. Esa ayuda se llama *llamada a la acción* (en inglés, *call to action*, o CTA). Hay tres formas:

| Forma | Ejemplo | Cuándo |
|---|---|---|
| **Botón de reintentar** | `[Reintentar]` | Fallos pasajeros: red, servidor ocupado |
| **Enlace a inicio** | `Volver al inicio` | Cuando no hay nada más que hacer en esta pantalla |
| **Instrucción clara** | "Sube un CSV con las columnas: fecha, estado…" | Cuando el problema lo puede arreglar la persona |

Comparación de dos mensajes del proyecto:

```
❌ "Missing required columns: ticket_id, date, client_company, ..."
   → En inglés, sin botón, sin decir qué hacer.

✅ "Incidencia no encontrada. No existe ninguna incidencia con el identificador X."
   + enlace [← Volver a incidencias]
   → Dice qué pasó y ofrece una salida.
```

> 💡 **Regla práctica:** si en un mensaje de error aparece "inténtalo de nuevo", tiene que haber **al lado un botón que lo haga**. Un texto que te pide que reintentes sin darte cómo es una instrucción a medias.

### 15.2 Cómo se midió

En vez de mirar pantalla por pantalla "a ojo", se **automatizó la medición**:

1. Se provocaron **19 situaciones de error** (API caída, 500, 404, datos rotos, fallos de la web pública…).
2. En cada una, un script preguntó al navegador: *¿hay un botón cuyo texto sea "reintentar"? ¿hay un enlace a la página de inicio? ¿qué dice el aviso?*
3. Los resultados se volcaron en una **tabla** de 19 filas, que es mucho más fácil de leer y de discutir que 19 párrafos.

Resultado: **7 de las 19 situaciones están bien resueltas** y el resto necesita una acción. Los peores son los análisis de CSV (sin ninguna ayuda), la comprobación de sesión (sin nada) y la web pública sin JavaScript (en blanco).

> 💡 **Aprendizaje:** una tabla de evidencias convierte "creo que faltan botones" en "faltan en estas 8 pantallas, y estas 7 están bien".

### 15.3 Mitad B: el código de salida de un script

Cada programa, cuando termina, deja un número en el sistema: el **código de salida** (*exit code*). Es la forma que tiene un programa de decir "todo fue bien" o "algo falló" a quien lo lanzó.

| Código | Significado habitual |
|---|---|
| `0` | Todo ha ido bien |
| `1` | Ha ocurrido un error |
| `2` | Se usó mal el programa (argumentos incorrectos) |

Puedes verlo en la terminal con `echo $?` justo después de ejecutar algo:

```bash
$ python scripts/analyze.py no-existe.csv
Error: file not found: no-existe.csv
$ echo $?
1
```

¿Quién lee ese número? **Otros programas**: un CI (comprobación automática), un cron (tarea programada) o un script que encadena varios comandos con `&&`. Si un script **falla pero devuelve 0**, todos ellos creen que fue bien y siguen adelante.

En Python hay dos formas de fijar el código:

```python
import sys
sys.exit(1)                          # sale con código 1

raise SystemExit("Mensaje de error") # imprime el mensaje en la pantalla de errores y sale con código 1
```

Y un patrón muy limpio, que ya usan dos scripts del proyecto:

```python
def main() -> int:
    ...
    return 1        # cuando algo falla
    ...
    return 0        # cuando todo va bien

if __name__ == "__main__":
    raise SystemExit(main())     # el valor de main() se convierte en el código de salida
```

### 15.4 Lo que se encontró

Se ejecutaron **los 4 scripts** con entradas que fallan y se anotó el código real de cada uno.

**P-01 — `analyze.py`: cuatro fallos que terminan "bien" (Media).** Con un CSV vacío, con solo la cabecera, con columnas equivocadas o con todas las filas inválidas, el script imprime un informe de ceros y termina con **código 0**. La API, con esas mismas entradas, responde con un error.

**P-02 — `seed_incidents.py`: "Summary check OK" con 0 incidencias (Media).** Cuando todas las filas se rechazan, el script dice `inserted 0` y después `Summary check OK`, y sale con 0. Compara 0 con 0 y lo presenta como una comprobación superada. En otro caso decía *"other incidents exist"* cuando la base estaba **vacía**: un mensaje falso.

> 💡 **Comprobar que "no hay diferencia" no es lo mismo que comprobar que "ha funcionado".** Si esperas 100 y encuentras 0, algo va mal; pero si esperas 0 y encuentras 0 porque todo se rechazó, también.

**Lo que está bien:** `create-user` y `seed` devuelven siempre un código distinto de 0 cuando fallan. `create-user` usa `raise SystemExit("mensaje")`, que es el patrón que conviene copiar.

### 15.5 Decisiones de esta pasada

| Decisión | Por qué |
|---|---|
| **Ejecutar** los scripts con entradas que fallan, no leer su código | El código de salida se ve solo ejecutando; en el código es fácil equivocarse al leerlo |
| Probar **siempre con una base de datos temporal** | Para no cargar datos de prueba en la base real del proyecto |
| Separar "falla con código 0" (grave) de "falla con código 1 pero con traceback" (feo, pero detectable) | El primero engaña a la automatización; el segundo no |
| Contar a `create-user` y `seed` como ejemplo **positivo** | Una auditoría debe decir también qué imitar |
| No contar como fallo "carga con 4 filas rechazadas" | Es lo esperado del dataset, pero lo anoto como mejora (P-03): no se distingue de un éxito limpio |
| Medir los avisos **dentro del contenido**, no en el menú lateral | Si no, el enlace "Inicio" del menú tapa el problema en todas las pantallas |

### 15.6 Problemas que aparecieron en esta pasada

#### 🔴 1. Mi primera prueba de "carpeta de solo lectura" apuntaba a un sitio que no existía
**Síntoma:** el primer intento devolvió `file not found` en lugar de `PermissionError`.
**Causa:** ejecuté la prueba **antes** de crear la carpeta. El orden de mis comandos estaba mal.
**Solución:** repetirla después de crear la carpeta con permisos `555` (solo lectura), y en el informe usar **solo el resultado bueno**.
**Aprendizaje:** una prueba que falla por una razón distinta a la que quieres comprobar no sirve. Fíjate en **qué mensaje** da, no solo en que falle.

#### 🔴 2. Creí que mi fila de ejemplo era válida y no lo era
**Síntoma:** con una fila "buena" el script dijo `inserted 0`.
**Causa:** mi identificador de ejemplo era `T1`, pero el modelo exige el formato `NXV-000001`. La fila se rechazó (`schema:id`).
**Solución:** ver por qué se rechazó, en vez de dar por buena mi suposición. Y de ahí salió el hallazgo real: el script **da una explicación falsa** ("other incidents exist") cuando la base estaba vacía.
**Aprendizaje:** que un resultado te sorprenda es una buena señal de que **hay algo que mirar**. Aquí la sorpresa era el hallazgo.

#### 🔴 3. Mi comando fue rechazado a mitad de la preparación
**Síntoma:** al lanzar la medición de las 19 pantallas, se interrumpió antes de ejecutarse.
**Solución:** comprobé primero que los tres servidores **seguían en marcha** (con un `curl` a cada uno) y repetí exactamente la misma medición.
**Aprendizaje:** tras una interrupción, **comprueba el estado actual** antes de seguir; no supongas que quedó todo como lo dejaste.

#### 🔴 4. Los servidores no se apagaron con el primer intento
**Síntoma:** después de `kill $(cat servidor.pid)` seguían abiertos los puertos 5173 y 5174.
**Causa:** el PID que guardé era el del comando que **lanza** el servidor, y el servidor real es un proceso **hijo** con otro número.
**Solución:** preguntar al sistema **qué proceso ocupa cada puerto** (`ss -ltnp`) y detener ese. Luego comprobé que los tres puertos estaban libres y borré los ficheros generados.
**Aprendizaje:** el PID de un comando no siempre es el del programa que arranca. Para cerrar un servidor por su puerto, usa `ss -ltnp` y no un nombre.

### 15.7 Ejercicios de esta parte

1. Ejecuta `python scripts/analyze.py datos.csv` con un CSV que solo tenga la cabecera y luego `echo $?`. ¿Qué número ves? ¿Qué debería ser?
2. Escribe en pseudocódigo el cambio que harías en `analyze.py` para que devuelva `1` cuando falten columnas. ¿Qué función ya existente podrías reutilizar? (Pista: la usa la API.)
3. Explica con tus palabras por qué un `cron` que lanza un script cada noche **necesita** que el script devuelva un código distinto de 0 cuando falla.
4. Elige la pantalla de error que te parezca peor de la tabla (el análisis de CSV, por ejemplo) y escribe el mensaje, el botón y el enlace que le pondrías.
5. **Pregunta de reflexión:** si una carga rechaza 4 filas de 100, ¿debería terminar con `0`, con `1` o con otro código? Argumenta tu respuesta pensando en quién lo va a leer.

---

## 16. Octava pasada: ¿cumple la auditoría los criterios del tech lead?

Esta vez no se buscó un tipo nuevo de fallo. El tech lead dio **ocho criterios que la auditoría debe garantizar** y la pregunta fue: *¿lo hemos garantizado de verdad, o solo lo hemos dado por hecho?* El resultado está al final del [informe](./docs/INFORME-AUDITORIA.md#cobertura-de-los-criterios-del-tech-lead).

### 16.1 Qué es una matriz de cumplimiento

Es una tabla donde cada fila es **un requisito** y se anota: *¿se cumple?, ¿cómo lo hemos comprobado?, ¿qué prueba hay?* Sirve para que alguien que no ha visto tu trabajo pueda decidir si fiarse de él.

| Criterio | Estado |
|---|---|
| Ningún error rompe la aplicación | ✘ No conforme |
| Toda operación asíncrona tiene cargando / éxito / error | ~ Parcial |
| Mensajes legibles y no técnicos | ✘ No conforme |
| Los errores ofrecen una salida clara | ✘ No conforme |
| Excepciones capturadas en el ámbito correcto | ~ Parcial |
| No se filtra información sensible | ✘ No conforme |
| Scripts con códigos de salida apropiados | ~ Parcial |
| No se introduce funcionalidad nueva | ✔ Conforme |

> 💡 **Aprendizaje:** "no conforme" no significa que tu trabajo sea malo. Significa que **el proyecto auditado** no cumple el criterio. Que la auditoría lo diga con pruebas es justo lo que se pedía.

### 16.2 Dónde estaba la cobertura más débil y cómo se reforzó

Al revisar los criterios contra lo ya hecho, había tres puntos flojos. Para cada uno se hizo una prueba nueva:

**1. "Ningún error rompe la aplicación"** → dos pruebas de estrés:
- **Fuzzing de la API:** se leyó el esquema de la API (su `openapi.json`) y se generó automáticamente **1.046 peticiones hostiles**: números enormes, `NaN`, textos de 5.000 caracteres, caracteres nulos, JSON roto, ficheros extraños. Resultado: **solo dos causas de 500**. Es una buena noticia sobre el backend, y un dato valioso.
- **Matriz de la interfaz:** 5 pantallas × sus peticiones × 11 formas de fallar = **121 combinaciones**, cada una clasificada según lo que ve la persona.

**2. "Cargando / éxito / error"** → hasta ahora se había medido "cargando" y "error", pero no **"éxito"**. Se ejecutaron 7 operaciones correctas en el navegador para ver qué confirmación recibe la persona (otras 2 se comprobaron leyendo el código, porque mi guion no llegó a completarlas).

**3. "No se introduce funcionalidad nueva"** → se revisaron **las propias recomendaciones** del informe. Ver el apartado 16.4.

> 💡 **Fuzzing** (*prueba de fuzz*) es mandar a un programa entradas absurdas o aleatorias para ver si se rompe. Es como probar una puerta tirando del pomo en todas direcciones, no solo girándolo.

### 16.3 Lo que se descubrió

**Un hallazgo que se ensanchó.** El `NaN` en un JSON no rompía solo la tarifa de un proveedor: rompía **cinco** endpoints. Se vio al hacer fuzzing, no al leer el código. Un ejemplo de por qué probar con muchas entradas encuentra cosas que la lectura no ve.

**Un hallazgo que subió de gravedad.** Antes, "una caída de `/auth/me` te cierra la sesión" parecía un problema medio. La matriz mostró que **30 de las 121 combinaciones** (la cuarta parte) terminan así: cualquier fallo, que no sea "token caducado", te echa al login. Con esa evidencia pasó a **ALTO**.

**Un hallazgo que no se había visto.** La pantalla de análisis muestra etiquetas como `Missing client_company` y códigos como `TECHNICAL` o `OPEN`, en inglés. Se vio **al revisar de forma deliberada el criterio 3**, no por el código de los errores.

### 16.4 La parte más importante: revisar tus propias recomendaciones

El criterio 8 dice *"no se introduce ninguna funcionalidad nueva"*. Hay que leerlo con cuidado: el informe **recomienda correcciones**, y algunas de ellas, sin querer, eran funcionalidad nueva. Ejemplos que había escrito:

| Mi recomendación | Por qué era funcionalidad nueva |
|---|---|
| "Que las altas queden pendientes de aprobación" | Crea un flujo de aprobación que no existe |
| "Límite de intentos de login" | Es una pieza nueva de infraestructura |
| "Añadir un campo `code` a los errores de la API" | Cambia el contrato de la API |
| "Opción `--strict` en los scripts" | Es una opción nueva de línea de comandos |
| "Botón «Elegir otro archivo»" | Es un control de interfaz nuevo |

La solución fue **reducir cada recomendación a corregir el defecto** (por ejemplo, para el email expuesto: "enmascararlo salvo para administradores", que usa el rol que ya existe) y mover las ideas a una sección aparte, **"Propuestas fuera de alcance"**, a la espera de que producto decida.

> 💡 **Aprendizaje:** una auditoría **corrige lo que está mal**, no **diseña lo que falta**. Cuando notes que una sugerencia añadiría algo que antes no existía, sepárala: "esto lo arreglaría tal cual" frente a "esto sería una decisión de producto".

### 16.5 Decisiones de esta pasada

| Decisión | Por qué |
|---|---|
| Hacer una **matriz de 8 filas** con estado y evidencia | El tech lead lee un criterio y ve enseguida si se cumple y por qué |
| Probar con **fuzzing y con una matriz**, no leyendo más código | Para los criterios de "nunca se rompe" hace falta provocar, no suponer |
| **Subir la gravedad** de E-08 cuando la evidencia lo justificó | La severidad es un juicio sobre la evidencia, y la evidencia cambió |
| Poner la **tabla de 19 operaciones** (cargando/éxito/error) | Convierte "toda operación tiene los tres estados" en algo comprobable fila por fila |
| **No tocar código** y demostrarlo con `git diff main..HEAD` | Cumplir el criterio 8 con una prueba, no con una promesa |
| Sacar a otra sección lo que sea **funcionalidad nueva** | Para no incumplir el criterio que se está auditando |

### 16.6 Problemas que aparecieron en esta pasada

#### 🔴 1. Mi primera prueba de estrés decía "0 problemas"
**Síntoma:** 972 peticiones enviadas y **cero** resultados problemáticos.
**Causa:** me resultó sospechoso, porque ya sabía que había varios 500. Mi prueba tenía **huecos**: enviaba los cuerpos sin la cabecera `Content-Type: application/json`, no incluía `NaN` de verdad (solo la palabra "NaN") ni un CSV con un estado raro.
**Solución:** corregir esos huecos y comprobar que la prueba **ya detectaba los fallos conocidos** antes de fiarme de sus resultados.
**Aprendizaje:** una prueba que no encuentra nada puede estar rota. **Antes de creer un "todo bien", verifica que tu prueba sabe encontrar un fallo que ya conoces.**

#### 🔴 2. Unos `ReadError` que parecían un fallo nuevo
**Síntoma:** varios errores `ReadError` en mi cliente, que parecían servidores que se caen.
**Causa:** tras un 500, el servidor cierra la conexión y la **siguiente** petición que la reutiliza falla. Era un efecto de mis pruebas, no un fallo del servidor. Lo comprobé mirando el log del servidor: solo 6 excepciones reales.
**Aprendizaje:** antes de reportar un fallo, contrasta **los dos lados**: lo que ve el cliente y lo que cuenta el servidor.

#### 🔴 3. El entorno se reinició a mitad de trabajo
**Síntoma:** mi guion de pruebas y los servidores habían desaparecido (`MODULE_NOT_FOUND`, puertos cerrados).
**Solución:** comprobar el estado real (rama, commits, ficheros) antes de seguir; **no volver a levantar todo**, sino terminar las dos medidas que faltaban leyendo el código y marcarlas como tales.
**Aprendizaje:** si el entorno cambia, **comprueba primero qué se ha perdido** y decide cuánto vale la pena reconstruir.

#### 🔴 4. Tres cifras mal contadas en mi propia tabla
**Síntoma:** al releer la matriz que acababa de escribir, vi que decía "71 acaban mal" (eran 60: otras 11 son un 401 correcto), "9 operaciones completas" (eran 6) y "2 con carencias graves" (eran 5).
**Solución:** recontar con el código en lugar de a ojo, y corregirlo antes de entregar.
**Aprendizaje:** **relee y recuenta tus propias tablas**, sobre todo las que resumen. Es donde más fácil es equivocarse y donde más se confía.

### 16.7 Ejercicios de esta parte

1. Elige un criterio de la matriz y escribe, con tus palabras, **qué prueba harías** para comprobarlo (no cómo arreglarlo).
2. Explica qué es el *fuzzing* y por qué una prueba que da "0 problemas" puede ser mala señal.
3. Mira la tabla de 19 operaciones. ¿Cuál te parece la **más grave**? Justifica la elección.
4. Para cada una de estas ideas, di si es **corregir un defecto** o **funcionalidad nueva**: (a) añadir un tiempo máximo a las peticiones; (b) permitir exportar el informe a PDF; (c) mostrar «Cambios guardados» tras editar; (d) enviar un correo cuando falla un script.
5. **Pregunta de reflexión:** ¿por qué subió de gravedad un hallazgo sin que el código cambiara? ¿Qué papel juega la evidencia al decidir una severidad?

---

## 17. Pasada final: ¿hemos mirado todo el monorepo?

La última instrucción fue: *analiza el monorepo completo y entrega un informe exhaustivo, priorizado por severidad*. Casi todo el informe ya existía; lo que faltaba era **demostrar que no se había quedado nada sin mirar** y entregarlo de forma que se pueda actuar sobre él. El resultado es el [informe final](./docs/INFORME-AUDITORIA.md).

### 17.1 Cómo se comprueba que no falta nada

Una auditoría puede ser muy buena y aun así dejarse una carpeta entera. Para evitarlo se hace un **inventario de cobertura**:

1. Listar **todos** los ficheros que Git tiene registrados (`git ls-files`).
2. Agruparlos por carpeta y quitar los que no son código (`README`, imágenes).
3. Para cada carpeta, anotar uno de tres estados: **auditada**, **sin código** o **fuera de alcance (con motivo)**.

Esto es lo que se encontró:

| Resultado | Qué significa |
|---|---|
| La mayor parte del repositorio (`services`, `uis`, `scripts`, `packages`, `src`) | Ya estaba auditada |
| `infra`, `internal`, `mcps`, `workflows`, `shared` | Solo contienen `README`: **no hay código que auditar** |
| `agents/_template/agent.py` | Está **vacío** (0 bytes) |
| `skills/data-analysis/scripts/pandas_clean.py` | **Un script que no se había revisado** → 2 hallazgos nuevos |

> 💡 **Aprendizaje:** un inventario no solo ayuda a encontrar lo que se escapó (aquí, un script). También te permite **decir con seguridad lo que NO hay**: "las carpetas `infra` y `mcps` no tienen código" es una afirmación que ahora tiene una prueba detrás.

### 17.2 Los dos hallazgos del script olvidado

El script `pandas_clean.py` es una plantilla de limpieza de datos. Se ejecutó sin tener `pandas` instalado y falló con un error (`ModuleNotFoundError`) y código de salida 1. De ahí salió:

- **P-04:** el script abre `data.csv` sin ningún `try`; y **`pandas` no está en ninguna lista de dependencias del repositorio**, así que quien lo ejecute se encuentra el fallo.
- **D-08:** al final hace `print(df.head())`, que **imprime las primeras filas del fichero**. Si alguien lo aplica al CSV de incidencias, mostraría los emails de los clientes, justo lo que la norma del proyecto prohíbe.

Son hallazgos de severidad baja, pero son un buen ejemplo de **cómo un hallazgo de seguridad puede esconderse en una plantilla inocente** ("Safe snippet for basic pandas cleaning").

### 17.3 Priorizar: el resumen ejecutivo

Un informe con 78 hallazgos no se puede arreglar "de arriba abajo". Hace falta **un orden**. El informe final empieza con un resumen ejecutivo de cuatro pasos:

| Paso | Qué | Por qué en ese orden |
|---|---|---|
| 1 | **Críticos** (D-01, D-02) | Exponen una credencial y datos personales reales: no se puede esperar |
| 2 | **Altos** (sesión, 500 sin controlar, datos dañados, CSV, web pública) | Rompen la aplicación o pierden datos |
| 3 | **Medios** (mensajes, estados de la interfaz, logging, códigos de salida) | Degradan la experiencia y la trazabilidad |
| 4 | **Bajos** | Detalles y código histórico |

También se añadió una tabla **por componente**: de un vistazo se ve que el 80 % de los hallazgos está en dos sitios (`uis/backoffice` y `services/api`). Eso ayuda a repartir el trabajo.

> 💡 **Aprendizaje:** priorizar es decir **qué NO hacer todavía**. Un informe sin orden es una lista de la compra; con orden, es un plan.

### 17.4 Decisiones de esta pasada

| Decisión | Por qué |
|---|---|
| No repetir pruebas ya hechas | Todo el código de producción ya estaba cubierto con ejecución real; solo faltaba comprobar los márgenes |
| Añadir una sección **"Cobertura del monorepo"** | Que el tech lead vea qué se miró y qué no, con el motivo |
| Dejar los **tests** como "no auditados como código" | El criterio es el comportamiento de producción; sí se revisó cómo terminan los e2e |
| Añadir un **resumen ejecutivo** al principio | Es lo único que leerá quien tenga cinco minutos |
| Mantener **un único informe** como entrega final | Evita que haya dos versiones con cifras distintas |

### 17.5 Problemas que aparecieron en esta pasada

#### 🔴 1. Una cifra del informe que no podía sostener
**Síntoma:** al escribir la tabla de cobertura puse "ejecutados con 22 entradas que fallan" para los scripts.
**Causa:** era una cifra que había calculado de memoria.
**Solución:** recontar (10 casos en `analyze.py` y 11 en `seed_incidents.py`) y cambiar la frase por *"más de 20 entradas"*, que sí es verdad. De paso corregí otras dos descripciones demasiado precisas ("7 dominios", "5 pantallas").
**Aprendizaje:** **si no puedes demostrar una cifra, usa una frase que sí puedas demostrar.** "Más de 20" es menos bonito que "22", pero es cierto.

#### 🔴 2. Un comando que terminó con un error en el último paso
**Síntoma:** mi comprobación del script de `pandas` acabó con `pwd: error retrieving current directory`.
**Causa:** la carpeta temporal en la que estaba trabajando **la borré en el mismo comando** (`rm -rf` con `cd` dentro), así que el sistema ya no sabía dónde estaba.
**Solución:** los resultados importantes ya se habían impreso antes del error, así que no hubo que repetir nada.
**Aprendizaje:** no borres la carpeta en la que estás. Sal primero (`cd /`) y luego borra.

### 17.6 Ejercicios de esta parte

1. Ejecuta `git ls-files | grep -v README | awk -F/ '{print $1}' | sort | uniq -c`. ¿Qué carpeta tiene más ficheros? ¿Coincide con la que más hallazgos tiene?
2. Elige una carpeta que el informe dice **"sin código"** y compruébalo tú: ¿qué contiene realmente?
3. Explica por qué `print(df.head())` puede ser un problema de seguridad aunque el script parezca inofensivo.
4. Ordena estos cuatro hallazgos del más al menos urgente y justifica el orden: la contraseña inicial en el log (D-01), el `NaN` que da 500 (E-12), las etiquetas en inglés (R-05) y el código histórico sin guardas (E-20).
5. **Pregunta de reflexión:** el informe dice "no auditados como código" sobre los tests. ¿Estás de acuerdo con esa decisión? ¿Qué razones habría para auditarlos también?

---

## 18. Última pasada: la rúbrica de evaluación

Te enseñaron **la lista con la que van a evaluar el trabajo**: ocho puntos, y una nota que dice que se evalúa *la corrección y la consistencia de los patrones de gestión de errores*, no si se añadieron funcionalidades. La pregunta fue la misma que en la pasada 16: *¿la auditoría responde de verdad a cada punto?* El resultado está en la sección «Rúbrica de evaluación» del [informe](./docs/INFORME-AUDITORIA.md#rúbrica-de-evaluación).

### 18.1 Leer una rúbrica antes de entregar

Una **rúbrica** es la lista de lo que el evaluador va a mirar. Lo más útil que se puede hacer con ella es **comparar cada línea con lo que ya tienes**, y marcar tres cosas: lo que ya cubres, lo que cubres a medias y lo que **no has mirado**.

| Punto de la rúbrica | ¿Estaba cubierto? |
|---|---|
| Operaciones con tres estados | Sí (pasadas 6 y 16) |
| Mensajes legibles con llamada a la acción | Sí (pasadas 4 y 7) |
| `try/catch` acotados | Sí (pasada 2) |
| **`finally` para limpiar el estado de carga** | **A medias**: lo había visto sin medirlo |
| **`optional chaining` y valores por defecto ante `undefined`** | **No como tal** |
| **Backend con errores estructurados y códigos correctos** | **No de forma sistemática** |
| Sin información sensible en los errores | Sí (pasada 5) |
| Scripts con códigos de salida | Sí (pasada 7) |

> 💡 **Aprendizaje:** los tres huecos eran justo los puntos más "técnicos" de la rúbrica. Cuando una lista de evaluación usa palabras muy concretas (*finally*, *optional chaining*), probablemente quien evalúa **va a buscar exactamente eso**.

### 18.2 Qué es el *optional chaining* y por qué importa

En JavaScript, si un dato **no existe** (`undefined`) y tratas de entrar en él, el programa se rompe:

```ts
const nombre = usuario.perfil.nombre;     // ❌ si perfil no existe: "Cannot read properties of undefined"
const nombre = usuario?.perfil?.nombre;   // ✅ devuelve undefined en vez de romperse
const nombre = usuario?.perfil?.nombre ?? "—";   // ✅ y además pone un texto de reserva
```

- **`?.`** ("encadenamiento opcional") significa: *"si lo de la izquierda no existe, para aquí y devuelve `undefined`"*.
- **`??`** significa: *"si lo de la izquierda es `undefined` o `null`, usa esto otro"*.

Ya habíamos visto este fallo una vez: `user?.profile.name` en el menú tenía el primer `?.` pero **le faltaba el segundo**. Pero ¿cuánto se repetía en todo el proyecto?

### 18.3 Cómo se midió: una prueba de mutación

Para medirlo no basta con buscar `?.` en el código. Se hizo una prueba más ingeniosa, que se llama **prueba de mutación de datos**:

1. Se pide a la API **una respuesta real** (por ejemplo, la lista de incidencias).
2. Para **cada campo**, se hace una copia de la respuesta **sin ese campo** (y otra con ese campo a `null`).
3. Se carga la pantalla con esa respuesta alterada y se mira **si se rompe o si enseña cosas raras**.

Se hicieron **238 pruebas**. Resultado: **55 (23 %) fallan**:

| Qué pasa | Cuántas | Ejemplo |
|---|---|---|
| Se sustituye **toda la pantalla** por "Algo ha salido mal" | 33 | Falta `created_at` en una fila de la lista |
| Aparece texto raro en pantalla | 20 | `undefined activas`, `NaN%`, tarifa `NaN`, `Invalid Date` |
| Sale la página de error de Next, en inglés | 2 | `/auth/me` sin `profile` |

Además, solo hay **19 `?.` y 22 `??`** en todo el frontend.

> 💡 **Aprendizaje:** para saber si un código es robusto frente a datos que faltan, **no mires el código: estropea los datos y observa**. Es lo mismo que una prueba de resistencia, pero con datos en lugar de con peso.

### 18.4 El `finally` y el estado de carga

El patrón correcto es este:

```ts
setLoading(true);
try {
  await llamarALaApi();
} catch (err) {
  setError("No se pudo cargar");
} finally {
  setLoading(false);      // se ejecuta SIEMPRE, haya ido bien o mal
}
```

Si `setLoading(false)` se pusiera dentro del `try`, un error dejaría el indicador de carga girando para siempre. Se revisaron todos los sitios: **10 de los 11 ficheros con estado de carga lo hacen bien** (con `try/finally` o con `.finally()`). La excepción es `AuthContext`, que lo resuelve en dos sitios distintos (`then` y `catch`).

**Una buena noticia que hay que contar:** esta parte está bien resuelta. Un informe justo cuenta lo que funciona.

### 18.5 Los errores del backend: estructura y códigos

Un backend ordenado debería responder a todos los errores con **la misma forma** y con **el código HTTP que toca**. Se hizo un **censo de 38 errores reales** de la API, agrupados en 10 familias (no existe, validación, subida de CSV, autenticación, permisos…):

| Qué se midió | Resultado |
|---|---|
| Forma del error | **Dos distintas**: `detail` como texto (19) y como lista de objetos (15), más 2 que **no son JSON** |
| Códigos | En una **misma familia** salen códigos distintos: la subida de CSV da **400, 422 y 500** |
| Datos del usuario devueltos en el error | **5 de 38** devuelven el valor rechazado (`input`) |

> 💡 **Aprendizaje (consistencia):** el problema no es tanto que un error esté "mal", sino que **dos errores parecidos se traten de forma diferente**. Quien consume la API (el frontend) tiene que escribir un caso especial por cada forma.

### 18.6 Decisiones de esta pasada

| Decisión | Por qué |
|---|---|
| Añadir una sección **«Rúbrica de evaluación»** con los 8 puntos tal cual | Quien evalúa busca esas frases exactas; mejor que las encuentre en el informe |
| Medir `undefined` con **mutación de datos** | Un recuento de `?.` no demuestra nada sobre si algo se rompe |
| Hacer un **censo** de los errores del backend, no una lista de ejemplos | Para hablar de consistencia hay que contar: "19 de una forma, 15 de otra" |
| Añadir una **tabla de consistencia** | La rúbrica dice "consistencia": hay que mostrar qué patrones son uniformes y cuáles no |
| **Contar lo que está bien** (`finally`) | Evita que el informe parezca una lista de quejas |
| No tocar el código | La instrucción sigue siendo solo auditar |

### 18.7 Problemas que aparecieron en esta pasada

#### 🔴 1. Mi entorno de pruebas se había borrado otra vez
**Síntoma:** al ir a lanzar el censo no existía ni el entorno de Python, ni el navegador, ni las librerías.
**Solución:** reconstruirlo por partes: dependencias de la API, Chromium y las librerías del sistema (descargadas a una carpeta temporal, sin permisos de administrador).
**Aprendizaje:** si tu entorno se puede perder, **apunta los pasos para reconstruirlo**. Hacerlo la segunda vez fue más rápido porque ya sabía qué faltaba.

#### 🔴 2. La instalación de dependencias falló por una ruta relativa
**Síntoma:** `is not a valid editable requirement` al instalar `requirements.txt`.
**Causa:** el fichero contiene `-e ../../packages/shared/incidents_analyzer`, una ruta **relativa a donde está el fichero**, y yo lo ejecutaba desde otra carpeta.
**Solución:** lanzar el comando **desde `services/api`**.
**Aprendizaje:** una ruta relativa depende de **dónde estás**. Si falla con "no encuentro eso", mira primero en qué carpeta ejecutas.

#### 🔴 3. El primer censo se cortó con "Connection reset by peer"
**Síntoma:** a mitad de la lista de pruebas, el cliente dejó de funcionar con `ReadError`.
**Causa:** tras un error 500 el servidor **cierra la conexión**, y mi cliente intentaba reutilizarla. Ya me había pasado en otra pasada.
**Solución:** pedir una **conexión nueva en cada petición** (`Connection: close`).
**Aprendizaje:** cuando un error se repite, **déjalo resuelto en la herramienta** para no volver a tropezar.

#### 🔴 4. Dos "200" que parecían un fallo de la API y eran un fallo de mi prueba
**Síntoma:** pedí una transición de estado no permitida y una edición de una incidencia final, y el servidor respondió `200` en lugar de `409`.
**Causa:** en esta versión del proyecto, una incidencia resuelta **se puede reabrir**; mi escenario asumía las reglas de otra versión.
**Solución:** no contarlos como fallo y decirlo en el análisis.
**Aprendizaje:** antes de decidir que el sistema se equivoca, **comprueba que tu expectativa es la correcta**.

#### 🔴 5. Otro dato de prueba inválido
**Síntoma:** al sembrar incidencias de prueba, `KeyError: 'id'`.
**Causa:** una incidencia de origen `branch` con sucursal `central` es inválida en esta versión (hay que nombrar una sucursal real). El servidor devolvió un 422 y mi script no lo comprobó.
**Solución:** usar una sucursal real y **comprobar el código de respuesta** (`assert r.status_code == 201`).
**Aprendizaje:** al preparar datos de prueba, **verifica que se han creado** antes de usarlos.

### 18.8 Ejercicios de esta parte

1. Reescribe esta línea con `?.` y `??` para que nunca se rompa y muestre "—" si falta algo: `usuario.perfil.telefono.toUpperCase()`.
2. Explica con tus palabras qué es una **prueba de mutación de datos** y por qué encuentra cosas que un recuento de `?.` no ve.
3. Escribe el `try/catch/finally` de una función que carga una lista y que **siempre** deja de mostrar "Cargando…". ¿Qué pasaría si pusieras `setLoading(false)` solo dentro del `try`?
4. En el censo del backend, ¿qué ventaja tendría para el frontend que **todos** los errores tuvieran la misma forma?
5. **Pregunta de reflexión:** la rúbrica pide "consistencia". ¿Es peor un patrón que se aplica **mal en todas partes** o uno que se aplica **bien en unos sitios y mal en otros**? Justifica tu respuesta.

---

## 19. La entrega: rama, push y pull request

Para entregar el trabajo había que **subir la rama `feature/error-handling-audit` a GitHub y compartir la URL del pull request**. Esta es la entrega: **[Pull request #14](https://github.com/ELDER2007/ai-engineering-company-project-monorepo-INES/pull/14)**.

### 19.1 Los conceptos

| Concepto | Qué es |
|---|---|
| **Rama** (*branch*) | Una línea de trabajo paralela a `main`. Así tu auditoría no toca lo que ya estaba entregado |
| **Push** | Subir tus commits locales a GitHub, para que otras personas los vean |
| **Pull request** (PR) | Una petición para **unir** tu rama a `main`. Sirve también para que otra persona **revise** tu trabajo antes de unirlo |
| **Remoto** (`origin`) | La copia del repositorio que está en GitHub |

El orden fue siempre el mismo: **trabajar en una rama → commit → push → pull request**. Nunca se trabajó directamente sobre `main`.

### 19.2 Lo que se hizo, paso a paso

1. **Comprobar el terreno:** a qué repositorio apunta `origin`, si la herramienta de GitHub (`gh`) está identificada como tú, y que **la rama con ese nombre no existiera ya** en el remoto.
2. **Renombrar la rama.** Mi rama de trabajo se llamaba `docs/error-handling-audit` y la entrega pedía `feature/error-handling-audit`. Se renombró con `git branch -m` (aún no estaba subida, así que no rompía nada).
3. **Commit** de lo que quedaba pendiente.
4. **Push** con `git push -u origin feature/error-handling-audit` (el `-u` deja la rama enlazada con su copia remota).
5. **Comprobar que el remoto tiene mi último commit** (el identificador de `local` y de `remoto` coinciden).
6. **Crear el pull request** contra `main`, con una descripción que explica qué es, dónde leerlo, el resultado y los límites.
7. **Verificar el PR:** abierto, sin conflictos (`mergeable: clean`), 5 commits y **4 ficheros, todos de documentación**.

> 💡 **Qué es un buen PR:** un título claro, una descripción que **dice lo que hay y lo que no hay**, y pocos ficheros relacionados entre sí. Aquí además se dice explícitamente "no se ha modificado ningún fichero de código".

### 19.3 Decisiones

| Decisión | Por qué |
|---|---|
| Entregar **un solo PR** con todo el trabajo | Es lo que pide la entrega; las cinco commits cuentan la historia |
| Escribir la descripción **en español** y con una tabla | Quien evalúa lee primero el resumen; la tabla de la rúbrica le dice el resultado en 10 segundos |
| **Verificar tras cada paso** (remoto, estado del PR) | Un push o un PR "que parece que ha ido bien" no es lo mismo que uno comprobado |
| Pedir el cambio de nombre **antes** de subir | Cambiar el nombre de una rama ya publicada obliga a borrarla y volver a subirla |

### 19.4 Problemas que aparecieron

#### 🔴 1. El primer `git push` falló con un error de "Git LFS"
**Síntoma:** `error: failed to push some refs`, con un mensaje de `git-lfs` que decía *"We couldn't respond to your request in time"*.
**Causa:** `git-lfs` es una herramienta para ficheros grandes. Se ejecuta **antes de cada push** y consulta a GitHub; esa consulta tuvo un **timeout momentáneo**. El repositorio no tiene ningún fichero LFS, así que no tenía nada que ver con mi trabajo.
**Solución:** leer **el registro completo** (`git lfs logs last`) para entender la causa y **repetir el push**. Funcionó a la segunda.
**Aprendizaje:** un error de red de un servicio externo **no es un error tuyo**. Lee el mensaje entero antes de tocar nada, y comprueba si basta con reintentar.

#### 🔴 2. `gh pr create` fallaba con un error raro
**Síntoma:** `Head sha can't be blank, Base sha can't be blank, No commits between main and feature/error-handling-audit`. Pero el push sí había funcionado.
**Causa probable:** GitHub tarda unos segundos en "ver" una rama recién subida (retraso de indexación) y, después, la herramienta `gh` siguió fallando por su vía (*GraphQL*) con el permiso con el que está identificada.
**Cómo se investigó:** se pidió a la API de GitHub que **comparase `main` con la rama** (`compare`): respondió *"5 commits por delante, 0 por detrás"*, es decir, **la rama estaba bien subida**. El problema era solo la herramienta.
**Solución:** crear el PR directamente con la **API REST** de GitHub (`gh api .../pulls`), que funcionó a la primera.
**Aprendizaje:** cuando una herramienta falla, **busca otra vía que te dé la misma información** (aquí, la API REST). Y si dudas de si algo está subido, **pregúntale a GitHub directamente** (compare), en lugar de suponer.

#### 🔴 3. Casi dejo un fichero temporal en `/tmp`
**Síntoma:** para pasar el texto de la descripción a la API guardé un fichero (`pr_body.md`).
**Solución:** lo borré en cuanto se creó el PR.
**Aprendizaje:** **limpia lo que creas** para una tarea puntual.

### 19.5 Ejercicios

1. Abre el [PR #14](https://github.com/ELDER2007/ai-engineering-company-project-monorepo-INES/pull/14) en GitHub. Pestaña **Files changed**: ¿cuántos ficheros ves y de qué tipo? ¿Coincide con "solo documentación"?
2. Explica con tus palabras la diferencia entre **commit**, **push** y **pull request**.
3. ¿Qué habría pasado si hubieras trabajado directamente en `main` y hubieras hecho push? ¿Por qué es mejor una rama?
4. Ejecuta `git log --oneline main..feature/error-handling-audit`. ¿Qué te muestra?
5. **Pregunta de reflexión:** el PR #14 dice "no se ha modificado ningún fichero de código". ¿Cómo lo **demostrarías** a quien lo duda? (Pista: `git diff --name-only main`.)

---

## 20. De informe a código: aplicar las correcciones

Pediste «el trabajo completo»: no solo el informe, también arreglar el código. Lo hice **en la misma rama y el mismo PR**, sin añadir funcionalidad nueva.

### 20.1 Decisiones
- **Tres commits por fases** (backend y scripts → frontend → documentación): si algo falla, se sabe en qué fase.
- **Una capa común en el frontend** (`lib/errors`, `lib/guards`, `lib/format`, `components/feedback`): así todas las pantallas muestran cargando / éxito / error de la misma forma, en vez de arreglar 20 pantallas con 20 estilos distintos.
- **El `try` solo rodea la llamada a la API.** Lo que pasa después (cerrar el formulario, avisar a la página) va fuera: si falla, no se debe decir «no se pudo guardar» cuando sí se guardó.
- **Mensajes en español sin códigos** (nada de «500» o «422») y siempre una salida: «Reintentar» o «Volver al inicio».
- **Lo que NO se arregló**: el formulario de talento de la web (E-04) sigue simulando el envío porque conectarlo sería una funcionalidad nueva.

### 20.2 Problemas que aparecieron
- `getLevelNamesMapping` solo existe en Python 3.11+ y el proyecto admite 3.10 → lo cambié por otra comprobación.
- Un fichero de datos dañado no daba error al abrirlo (se lee «perezosamente») → forcé una lectura dentro del `try`.
- Un test existente exigía que un aviso de `seed_incidents` devolviera 0 → respeté ese contrato; solo los fallos reales devuelven 1.
- **El test nuevo (`test_error_handling.py`) se ejecutó al final y encontró un fallo real:** enviar `Infinity` como tarifa de un proveedor devolvía 200 y dejaba la tarifa en `null`. Lo arreglé con `allow_inf_nan=False` en el esquema. Los otros dos fallos eran errores del propio test (columnas del CSV en otro orden y una comprobación demasiado estricta del log). **Aprendizaje:** un test sin ejecutar no demuestra nada; al correrlo apareció un error que yo no había visto.

### 20.3 Cómo lo comprobé
302 tests de la API (268 existentes + 34 nuevos) ✅ · 9 tests de `packages/shared` ✅ · `tsc` del backoffice y de la web ✅ · `next build` ✅. Los 6 e2e con navegador (Playwright) también pasan; tuve que actualizar 3 aserciones que esperaban mensajes técnicos en inglés, porque ahora el usuario ve mensajes en español.

### 20.3b Cierre de los tres pendientes
1. **Test ejecutado:** encontró un error real (`Infinity` como tarifa).
2. **E-04:** el formulario de talento ya no dice «recibido»; dice la verdad y da una salida (email). Lo comprobé en el navegador: 0 peticiones enviadas.
3. **Conciliación de los 82 hallazgos:** 61 corregidos, 8 parciales y 13 no aplicados, cada uno con su motivo en `docs/INFORME-AUDITORIA.md`. Los «no aplicados» son funcionalidad nueva o decisiones de producto/despliegue; **no los he arreglado a propósito** porque el tech lead pidió no añadir funcionalidad.
4. **Playwright:** reconstruí Chromium sin permisos de administrador (descargando las librerías con `apt-get download` y extrayéndolas con `dpkg -x`) y pasaron los 6 e2e.
5. Pequeños arreglos extra que salieron al conciliar: aviso si la tarifa está vacía (S-08), aviso si se sueltan varios CSV (S-09), confirmaciones de éxito en proveedores (U-12), instrucción en el login si la cuenta está desactivada (A-03) y permisos 600 en los ficheros de datos (D-05).

### 20.4 Ejercicios
1. Abre `StatusActions.tsx`: ¿qué hay dentro del `try` y qué fuera? ¿Por qué?
2. Provoca un error de red (apaga la API) y mira qué ve el usuario en Proveedores. ¿Hay salida?
3. Ejecuta `python scripts/analyze.py` sin argumentos y mira el código de salida con `echo $?`.

---

> **Este documento es tuyo.** Una buena auditoría no consiste en encontrar muchos fallos, sino en **demostrarlos, explicarlos y ordenarlos** para que alguien los pueda arreglar. 🔍
