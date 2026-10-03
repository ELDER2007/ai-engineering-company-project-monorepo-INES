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

> **Este documento es tuyo.** Una buena auditoría no consiste en encontrar muchos fallos, sino en **demostrarlos, explicarlos y ordenarlos** para que alguien los pueda arreglar. 🔍
