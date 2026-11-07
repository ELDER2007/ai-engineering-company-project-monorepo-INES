# 📘 Aprendiendo con la IA — Pipeline de datos resiliente (Parte 2)

> **Estudiante:** INES
> **Proyecto:** Nexova — implementar el pipeline semanal por oficina y programa (`data/pipelines/pipeline.py`, `services/api/reporting/`)
> **Qué es este documento:** el diario de la implementación. Cuenta **qué se hizo, qué decisiones se tomaron y cómo se resolvieron los problemas**, incluidos los **errores que cometió la IA** por el camino.
> Los entregables oficiales son el código (PR #35) y el diseño [`data/pipelines/PIPELINE_DESIGN.md`](./data/pipelines/PIPELINE_DESIGN.md). Este cuaderno es el complemento para estudiar. Continúa a [`aprendiendo con la ia - PIPELINE-DESIGN.md`](./aprendiendo%20con%20la%20ia%20-%20PIPELINE-DESIGN.md).

---

## 📑 Índice

1. [El encargo, en palabras sencillas](#1-el-encargo-en-palabras-sencillas)
2. [Conceptos nuevos](#2-conceptos-nuevos)
3. [Paso a paso: qué se hizo](#3-paso-a-paso-qué-se-hizo)
4. [Las decisiones importantes (y por qué)](#4-las-decisiones-importantes-y-por-qué)
5. [Problemas y errores, y cómo se resolvieron](#5-problemas-y-errores-y-cómo-se-resolvieron)
6. [Resultados](#6-resultados)
7. [Límites: lo que no está hecho](#7-límites-lo-que-no-está-hecho)
8. [Glosario](#8-glosario)
9. [Ejercicios para practicar](#9-ejercicios-para-practicar)

---

## 1. El encargo, en palabras sencillas

En la Parte 1 escribiste el **plano** del pipeline. Ahora hay que **construirlo**, y hacerlo *resiliente*: un pipeline resiliente no es el que nunca falla, sino el que **falla bien**. Si se cae a mitad, no deja datos rotos ni repetidos, y se puede volver a ejecutar sin miedo.

## 2. Conceptos nuevos

- **Task opcional:** un paso que, si falla, no detiene todo. Se llama con `return_state=True` para que Prefect devuelva el resultado en lugar de lanzar el error.
- **Reintentos (`retries`):** si una task que habla con la base de datos falla, se vuelve a intentar sola unos segundos después.
- **Caché:** si una task ya terminó bien hace menos de una hora, se reutiliza su resultado. Tiene una **clave** (qué la define) y una **caducidad**.
- **Idempotente:** ejecutarlo dos veces deja *exactamente* lo mismo.
- **Hook `on_crashed`:** una función que Prefect llama cuando el proceso muere.
- **Entorno de telemetría:** cada evento está marcado `development`, `test`, `staging` o `production`.

## 3. Paso a paso: qué se hizo

1. **Ajustar el borrador a tu telemetría real** (nombres de columnas, costo en céntimos) y añadir Prefect con `uv add "prefect>=3"`.
2. **Fase 1, flows y tasks:** un flow, 12 tasks por etapas, y 3 pasos opcionales.
3. **Fase 2, resiliencia:** reintentos justificados, un fallo manejado con `return_state=True`, y caché con `cache_key_fn`.
4. **Fase 3, idempotencia:** upsert sobre el constraint único del briefing y log de cada corrida.
5. **Fase 4, script:** que `python data/pipelines/pipeline.py` corra sin errores.
6. **Fase 5, endpoints:** estado, disparo manual y KPIs, en su módulo.
7. **Revisión final:** suite completa, PostgreSQL real, tu Supabase real y la rúbrica.
8. **Entrega:** un commit con el mensaje exacto y un PR.

## 4. Las decisiones importantes (y por qué)

| Decisión | Por qué |
| --- | --- |
| Tasks críticas y opcionales | No hay reporte honesto sin extraer, calcular y cargar; pero guardar una copia de los eventos no debe tumbarlo |
| 3 reintentos (5 s, 30 s, 2 min) | Los fallos pasajeros de una base de datos duran segundos o un par de minutos; más espera solo escondería una caída real |
| Caché en la extracción y la agregación, **nunca** en la carga | Reutilizar lo caro es seguro; saltarse la escritura o el log sería peligroso |
| `refresh` para ignorar la caché | La caché esconde un evento tardío durante una hora; el disparo manual la salta |
| El upsert solo actualiza **si algo cambió** | Si siempre reescribe `computed_at`, la tabla cambia aunque los datos sean los mismos |
| Índice único parcial sobre las corridas `Running` | Una comprobación previa no basta si dos corridas leen a la vez; lo garantiza la base de datos |
| Solo el entorno `production` por defecto | Si no, tus pruebas acaban en el reporte del CEO |
| Sin base configurada, usar datos de demostración | Para que el comando funcione en un clon limpio, avisando; con base configurada nunca se esconde un fallo |
| Todo el router exige sesión; solo lanzar una corrida exige admin | Es la convención de tu API, y una ruta nueva nace protegida |

## 5. Problemas y errores, y cómo se resolvieron

### 🔴 Problema 1: el comando exacto del enunciado fallaba (error de la IA)
Todas las pruebas usaban `--demo`. Al ejecutar `python data/pipelines/pipeline.py` **sin argumentos** en un clon limpio, salía con código 1: buscaba `telemetry_events` en una base local que aún no existía, y además dejaba un archivo vacío. *Lección:* probar siempre el comando **tal cual** lo pide el enunciado.

### 🔴 Problema 2: «idempotente» pero la tabla cambiaba (error de la IA)
El upsert reemplazaba los valores, pero reescribía `computed_at` en cada corrida: dos corridas dejaban filas distintas. Ahora solo actualiza si algún KPI cambió, y la tabla queda idéntica.

### 🔴 Problema 3: el diseño prometía algo que el código no hacía (error de la IA)
El documento decía que existía un hook `on_crashed` y no existía. Se implementó, y se añadió al documento una tabla honesta de **qué está hecho y qué no**.

### 🔴 Problema 4: el pipeline ignoraba el `.env` de la API (error de la IA)
Si tienes tu Supabase en `services/api/.env`, la API lo usaba y el pipeline corría en demo sin que lo supieras. Ahora leen el mismo archivo.

### 🟠 Problema 5: todo probado con SQLite, nada con PostgreSQL
Tu base real es PostgreSQL. Se levantó uno en un contenedor y se comprobó lo importante: idempotencia, candado, *rollback*, tipos y el SQL de referencia. Un test **se colgaba** solo en PostgreSQL por dejar una conexión abierta.

### 🟠 Problema 6: tests que dependían del orden
La caché de Prefect se guarda en tu carpeta de usuario y los tests de caché recibían resultados de sesiones anteriores. Se aisló la caché en cada ejecución de tests.

### 🟡 Problema 7: un número inventado en un mensaje de commit
Un commit decía «66 tests» y eran 51. Lo detecté y te lo dije, pero un commit ya subido no se corrige sin reescribirlo.

### 🟡 Problema 8: un test de telemetría falla, y no es nuestro
Usa un evento con fecha fija (27 de octubre) y el reporte mira «los últimos 7 días». Dejó de pasar solo con el tiempo. El ticket pedía no tocar la telemetría, así que se dejó y se avisó.

## 6. Resultados

- **Tests:** 168 del pipeline y sus endpoints, más 978 del resto del proyecto. Solo falla el test de telemetría del problema 8.
- **PostgreSQL 16:** el comando con `DATABASE_URL` corre dos veces y deja la tabla idéntica; el candado y el *rollback* los impone la base de datos.
- **Tu Supabase real:** terminó `Completed`, creó el esquema `reporting` y dejó el log. Con `production` no había eventos que contar (todos eran `development`); con `--environment development` guardó 2 filas.
- **Los KPIs coinciden con el briefing:** un test los calcula con bucles simples, siguiendo sus definiciones, sobre el conjunto de datos oficial de tu plan de telemetría.

## 7. Límites: lo que no está hecho

- **Prefect:** los `Secret` blocks, el *deployment* con los crons del lunes y del jueves, las alertas y los subflows (Parte 3).
- **Kits entregados:** se cuentan por **pedido de salida**, como dice el briefing, no por unidades.
- **La tabla de destino no lleva el entorno en su clave** (así lo fija el briefing): una corrida normal de una semana retira las filas que dejó una corrida de `development`.
- **La caché** de Prefect vive fuera del repositorio, en tu carpeta de usuario.

## 8. Glosario

- **Resiliente:** que falla bien, sin dejar datos rotos.
- **Idempotente:** repetir no cambia el resultado.
- **Upsert:** insertar o actualizar según una clave única.
- **Rollback:** deshacer una transacción entera.
- **Caché:** reutilizar un resultado reciente en vez de recalcularlo.
- **`return_state=True`:** pedir a Prefect el estado de una task en lugar de que lance su error.
- **Índice único parcial:** una restricción que solo se aplica a algunas filas.

## 9. Ejercicios para practicar

1. Una task opcional falla: ¿termina la corrida? ¿Qué queda anotado y dónde?
2. ¿Por qué la carga no se guarda en caché, aunque la extracción sí?
3. Llega un evento tardío dentro de la hora de caché. ¿Aparece en el reporte? ¿Cómo lo consigues?
4. Dos corridas de la misma semana arrancan a la vez. ¿Qué mecanismo concreto lo impide?
5. ¿Qué pasa con las filas de `development` si después se ejecuta la corrida normal de esa semana?
