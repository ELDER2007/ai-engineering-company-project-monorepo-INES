# 📘 Aprendiendo con la IA — Diseño del pipeline de desempeño de negocio (Parte 1)

> **Estudiante:** INES
> **Proyecto:** Nexova — pipeline de datos semanal por oficina y programa (`data/pipelines/`, `services/api/reporting/`)
> **Qué es este documento:** el diario del diseño. Cuenta **qué se hizo, qué decisiones se tomaron y cómo se resolvieron los problemas**, incluidos los **errores que cometió la IA** por el camino.
> El entregable oficial es [`data/pipelines/PIPELINE_DESIGN.md`](./data/pipelines/PIPELINE_DESIGN.md) (PR #34). Este cuaderno es el complemento para estudiar. Continúa a [`aprendiendo con la ia - PERF-AUDIT.md`](./aprendiendo%20con%20la%20ia%20-%20PERF-AUDIT.md).

---

## 📑 Índice

1. [El encargo, en palabras sencillas](#1-el-encargo-en-palabras-sencillas)
2. [Conceptos que necesitas antes de empezar](#2-conceptos-que-necesitas-antes-de-empezar)
3. [Paso a paso: qué se hizo](#3-paso-a-paso-qué-se-hizo)
4. [Las decisiones importantes (y por qué)](#4-las-decisiones-importantes-y-por-qué)
5. [Problemas y errores, y cómo se resolvieron](#5-problemas-y-errores-y-cómo-se-resolvieron)
6. [Límites: lo que el diseño no resuelve](#6-límites-lo-que-el-diseño-no-resuelve)
7. [Dónde está cada cosa](#7-dónde-está-cada-cosa)
8. [Glosario](#8-glosario)
9. [Ejercicios para practicar](#9-ejercicios-para-practicar)

---

## 1. El encargo, en palabras sencillas

Ya había telemetría: el backoffice manda eventos a una tabla (`telemetry_events`) y hay un reporte técnico para ingeniería (¿hay errores? ¿es lento?). Pero **Laura (CEO) y Elena (L&D) preguntan otra cosa**: *¿cómo están Valencia y Miami en gasto y entrega de material de formación, programa por programa, semana a semana?*

La parte 1 **no pide código**: pide un **documento de diseño** que explique cómo se respondería esa pregunta con un pipeline nuevo, sin tocar el reporte técnico.

## 2. Conceptos que necesitas antes de empezar

- **Pipeline de datos (ETL):** coge datos de un sitio (**E**xtraer), los calcula (**T**ransformar) y los guarda en otro (**C**argar).
- **Idempotencia:** correrlo dos veces con los mismos datos da el mismo resultado, sin duplicados.
- **Upsert:** «inserta, y si ya existe, actualiza». Se apoya en una clave única.
- **Prefect:** herramienta de orquestación. Un **flow** es el pipeline entero, una **task** es un paso (con reintentos), un **state** es el resultado (`Running`, `Completed`, `Failed`) y un **block** guarda configuración o credenciales.
- **Semana ISO:** lunes a domingo. Cada fila del reporte es una oficina × un programa × una semana.

## 3. Paso a paso: qué se hizo

1. **Leer el briefing** del pipeline: el entregable, los 4 KPIs y la tabla de destino exacta.
2. **Explorar el repo** para documentar el «Estado Actual». Aquí apareció el primer problema (ver §5).
3. **Escribir el diseño por fases**, siguiendo el enunciado: estado actual y brecha → propósito, extracción, diagrama y estrategia de upsert → idempotencia y log → mapeo a Prefect → endpoints.
4. **Responder las 10 preguntas de diseño** con ejemplos y pistas propios, contrastadas con el código real.
5. **Auditar el documento contra la rúbrica** (12 puntos) y cerrar los huecos.
6. **Entregar:** un solo commit con el mensaje exacto del enunciado y un PR con un único archivo.

## 4. Las decisiones importantes (y por qué)

| Decisión | Por qué |
| --- | --- |
| Una sola transacción para cargar | Si falla a mitad hay *rollback*; nunca queda una semana a medias |
| Reemplazar, no sumar (`DO UPDATE SET kpi = EXCLUDED.kpi`) | Sumar duplicaría las cifras en cada reejecución |
| Recalcular la semana completa | Los eventos pueden llegar tarde; recalcular los absorbe |
| Sin checkpoints de datos | Recalcular una semana es más barato y más fiable que guardar un estado intermedio |
| Índice único parcial sobre las corridas `Running` | Una comprobación previa no basta si dos corridas leen a la vez; la garantía tiene que vivir en la base de datos |
| Dos `Secret` blocks (lectura y escritura) | Con permisos de solo lectura sobre `telemetry_events` es imposible escribir ahí |
| Fuente única: `telemetry_events` | Cada evento ya trae oficina, programa, moneda y costo; leer también el inventario crearía dos verdades |
| Endpoints solo llaman a una fachada (`interface.py`) | Así `services/` no tiene SQL ni lógica de ETL |

## 5. Problemas y errores, y cómo se resolvieron

### 🔴 Problema 1: «la telemetría no existe» (error de la IA)
La IA buscó en `main`, no encontró `telemetry_events` y escribió el diseño suponiéndola. **Estaba en 4 ramas sin mergear** (`docs/telemetry-design-plan`, `feature/telemetry-capture`, `-storage`, `-report`), cada una con su PR. Se descubrió al enseñar una captura del enunciado. *Lección:* buscar en **todas las ramas** (`git branch -a`, `git log --all`) antes de afirmar que algo no existe.

### 🔴 Problema 2: nombres de columnas inventados (error de la IA)
El borrador usaba `occurred_at`, `properties` y `total_cost`. La tabla real usa `timestamp`, `tags` y **`total_cost_minor`** (en céntimos). Además descubrió que **no hacía falta ningún campo nuevo** de telemetría. Se corrigió el documento.

### 🟠 Problema 3: se construyó código en una parte que pedía solo diseño
Por indicación de «ve creando el proyecto» se hizo un prototipo. Pero la Parte 1 dice «todavía no hay código». Solución: **separar**: solo el documento va al PR de la entrega; el prototipo va a otra rama, para la Parte 2, y el propio documento avisa de que aún usa nombres antiguos.

### 🟠 Problema 4: un PR con 94 archivos
El primer PR (#33) salía de un `main` local con el merge de telemetría, así que mostraba también todo ese trabajo. Solución: rama nueva desde el `main` de GitHub con **solo el documento** (PR #34) y cierre del #33 con un comentario.

### 🟠 Problema 5: `gh` apuntaba al repositorio equivocado
`gh pr create` quería abrir el PR en el repositorio original de 4Geeks, no en el tuyo. Falló antes de crear nada. Se repitió con `--repo` explícito. *Lección:* en un fork, indica siempre el repositorio.

### 🟡 Problema 6: el sistema bloqueó un push forzado
Se intentó reescribir la rama del PR con `--force-with-lease` y fue bloqueado por destructivo. No se ejecutó nada a medias. Se usó la alternativa segura: rama nueva y push normal.

### 🟡 Problema 7: incoherencias entre secciones del propio documento
Tras añadir cosas, el orden de las tasks no coincidía con el diagrama, y una frase decía que la telemetría estaba «en el `main` local» (solo cierto en el ordenador). Se corrigió al auditar la rúbrica.

## 6. Límites: lo que el diseño no resuelve

- `telemetry_events` **no guarda la hora de llegada**, así que un evento «tardío» no se detecta por llegada.
- La v1 **no conserva los valores anteriores** de una fila: sabe *que* una semana cambió, no *qué decía antes*.
- Los eventos de inventario los emite **el navegador**, no el servidor: los KPIs pueden **subestimar**. El control real sería reconciliar contra `asset_entries` y `asset_exits` (v2).
- `requestId` viaja en el evento pero **no se guarda**: no sirve para correlacionar.
- Los umbrales de volumen (p. ej. 50 %) son propuestas sin línea base real.

## 7. Dónde está cada cosa

| Qué | Dónde |
| --- | --- |
| Diseño (entrega Parte 1) | `data/pipelines/PIPELINE_DESIGN.md` — PR #34 |
| Prototipo (para la Parte 2) | rama `feature/weekly-performance-pipeline` |
| Telemetría usada como fuente | PRs #24, #27, #28, #29 (abiertos, ya revisados) |

## 8. Glosario

- **ETL:** extraer, transformar, cargar.
- **Upsert:** insertar o actualizar según una clave única.
- **Rollback:** deshacer una transacción entera.
- **Backfill:** reprocesar semanas pasadas.
- **Idempotente:** repetir no cambia el resultado.
- **Unidad menor (`_minor`):** importe en céntimos (5000 = 50,00 €).

## 9. Ejercicios para practicar

1. Si un evento de Miami llega con `currency = EUR`, ¿qué task falla y por qué conviene que falle?
2. La corrida del lunes carga 4 de 6 filas y se cae la conexión. ¿Cuántas filas hay después? ¿Y tras reintentar?
3. ¿Por qué `kpi = kpi + nuevo` rompería la idempotencia?
4. Dos corridas de la misma semana arrancan a la vez. ¿Qué mecanismo concreto evita que carguen las dos?
5. Una semana tiene 0 eventos de negocio. ¿Qué dato del log distingue «cero real» de «captura caída»?
