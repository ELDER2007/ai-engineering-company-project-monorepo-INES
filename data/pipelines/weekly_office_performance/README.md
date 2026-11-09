# weekly_office_performance

Pipeline Prefect del "Reporte Semanal de Desempeño por Oficina y Programa". Especificación: [`../PIPELINE_DESIGN.md`](../PIPELINE_DESIGN.md). Punto de entrada: [`../pipeline.py`](../pipeline.py).

| Pieza | Archivo |
| --- | --- |
| Flow + tasks (orquestación) | `data/pipelines/pipeline.py` |
| Cálculos puros (validar, deduplicar, agregar, conciliar) | `data/process/weekly_performance.py` |
| Todo el SQL | `repository.py` |
| Tablas del esquema `reporting`, conexiones | `storage.py`, `sql/001_reporting_schema.sql` |
| Lo único que `services/` puede importar | `interface.py` |
| Datos demo (solo local y tests) | `seed_telemetry.py` |

## Resiliencia (lo que exige el ticket)

| Requisito | Cómo se cumple |
| --- | --- |
| Tolera fallos parciales | Tasks **opcionales** (`count_window_events`, `save_raw_snapshot`, `save_eval_report`): si fallan se anota en `warnings` y la corrida sigue. Las críticas la detienen |
| Reintentos en servicios externos | `extract_kpi_events`, `load_weekly_performance` y el log reintentan 3 veces (5 s, 30 s, 2 min) |
| Corre como script | `python data/pipelines/pipeline.py ...` (código de salida 0 / 1) |
| No repite lo que corrió hace menos de 1 h | Caché de 1 h en `extract_kpi_events` y en las 4 tasks de KPI (`calculate_total_material_cost`, `count_kits_delivered`, `count_shortage_events`, `count_cost_variance_events`); `--refresh` la salta. La carga nunca se cachea |

## Probarlo (desde la raíz del repo)

```bash
cd services/api && uv sync && cd ../..
services/api/.venv/bin/python data/pipelines/pipeline.py
```

Sin argumentos lee la última semana completa. En un clon limpio (sin `DATABASE_URL` y sin telemetría local) lo avisa y usa datos de demostración, para que el comando funcione siempre.

`--demo` fuerza una base de datos desechable (`data/.local/demo.sqlite`) con eventos de ejemplo, nunca la de la aplicación.
Sin `--demo` lee `telemetry_events` de la base de la API (`DATABASE_URL`, o su SQLite local) en modo solo lectura, y por defecto solo del entorno `production`
(`--environment` o `PIPELINE_ENVIRONMENT` para cambiarlo).

Cada corrida deja: una fila en `reporting.pipeline_runs`, la copia de los eventos leídos en `data/raw/` y un informe en `data/eval/`.

Sin servidor Prefect, Prefect levanta uno temporal (unos segundos) en cada corrida.

## Verlo por la API, con cifras (datos de demostración)

En un clon limpio la API arranca, pero `GET /reporting/weekly-office-program-performance` responde `404 No week has been computed yet`: su base de datos no tiene
eventos de telemetría y el pipeline no tiene nada que calcular. Para ver cifras **sin tocar la base de la propia API**, la API puede leer la base de
demostración desechable del pipeline. Dos comandos, desde la raíz del repo:

```bash
# 1) El pipeline en modo demostración: crea data/.local/demo.sqlite con eventos de ejemplo y calcula la semana 2026-10-26.
python data/pipelines/pipeline.py --demo

# 2) La API, leyendo los datos de reporting de ese archivo (el resto de la API sigue con su base de siempre).
DEMO="$(pwd)/data/.local/demo.sqlite"
cd services/api
REPORTING_DATABASE_URL="sqlite:///$DEMO" TELEMETRY_DATABASE_URL="sqlite:///$DEMO" \
AUTH_INITIAL_EMAIL=tu@correo.com AUTH_INITIAL_PASSWORD=elige-una-contraseña \
uvicorn main:app --port 8000
```

`AUTH_INITIAL_EMAIL` / `AUTH_INITIAL_PASSWORD` solo crean el primer usuario cuando **todavía no hay ninguno**; si la API ya tiene cuentas, usa una de ellas.

Después, en `http://localhost:8000/docs`, *Authorize* con ese correo y contraseña y `GET /reporting/weekly-office-program-performance`: cinco filas (dos oficinas, tres
programas) de la semana 2026-10-26. `GET /reporting/pipeline-runs/latest` muestra la corrida y `POST /reporting/pipeline-runs` (admin) la repite.

> **No** ejecutes `seed_telemetry.py` contra la base de la propia API: **borra todas las filas de `telemetry_events`** antes de cargar los eventos de demostración.
> Es solo para archivos desechables, que es lo que usa `--demo`.

## Con tu base real: ¿por qué sale vacío?

El comando sin argumentos lee solo eventos del entorno `production`, porque un reporte que lee el liderazgo no debe mezclar pruebas. Si en tu base los eventos son de otro entorno (lo normal mientras desarrollas es `development`), el reporte sale con **0 filas** y la corrida termina bien: no es un error, es el filtro funcionando.

Para ver tus datos de prueba, di el entorno **y la semana** de tus eventos:

```bash
python data/pipelines/pipeline.py --environment development --week-start 2026-10-26
```

**Cuidado con una cosa:** la tabla de destino no lleva el entorno en su clave (así lo fija el briefing) y cada corrida reemplaza la semana completa. Por eso una corrida de `production` sobre una semana en la que antes corriste `development` **retira** esas filas (y al revés). No es un fallo: es la regla de reemplazo. Si quieres conservar las filas de prueba, no ejecutes `production` sobre esa misma semana.

## En producción: programarlo, guardar las credenciales y recibir avisos

Todo esto es **opcional**: sin nada de esto, el comando de arriba funciona igual que siempre.

| Qué | Cómo | Dónde está |
| --- | --- | --- |
| Que corra solo (lunes 05:00 UTC y corrección el jueves 05:00 UTC) | `python data/pipelines/deploy.py --work-pool nexova-reporting` y un worker: `prefect worker start --pool nexova-reporting`. `--dry-run` muestra el plan sin servidor | `../deploy.py` |
| Credenciales en `Secret` blocks en lugar de variables de entorno | `python -m data.pipelines.weekly_office_performance.blocks` los crea (imprime solo los nombres) y `PIPELINE_SECRET_BLOCKS=1` los activa | `blocks.py` |
| Aviso cuando falla, se cae o los datos pueden estar mal | `PIPELINE_ALERT_WEBHOOK_URL` (o el block `pipeline-alert-webhook`): un *webhook* compatible con Slack. Sin él no hace nada | `alerts.py` |

Qué está comprobado y qué no, en `../PIPELINE_DESIGN.md` (secciones 4.5, 4.6 y 8b): los tests usan un servidor de Prefect temporal y un *webhook* local; no se ha registrado en un servidor real ni se ha enviado un aviso a un Slack real.

## Roles de la base de datos (mínimo privilegio): paso a paso para quien administre Supabase

`sql/002_roles.sql` crea dos roles: **`pipeline_reader`** (solo lee `telemetry_events`) y **`pipeline_writer`** (solo lee y escribe las dos tablas de `reporting`). Con ellos, el pipeline no puede tocar la telemetría ni por error.

1. **Antes de empezar:** comprueba que el esquema `reporting` y sus tablas existen (se crean con `sql/001_reporting_schema.sql` o con una primera corrida del pipeline hecha con tu usuario administrador).
2. **Ejecuta el script:** Supabase → *SQL Editor* → pega el contenido de `sql/002_roles.sql`. **Antes de ejecutarlo, cambia las dos contraseñas** (`CHANGE-ME-...`) por contraseñas largas y distintas. No las pegues en el chat ni las guardes en el repositorio.
3. **Comprueba el resultado:** ejecuta la consulta de comprobación que lleva el script al final: `pipeline_reader` debe tener solo `SELECT` sobre `telemetry_events`, y `pipeline_writer` solo `SELECT, INSERT, UPDATE, DELETE` sobre las dos tablas de `reporting`.
4. **Seguridad por filas (RLS):** el script ya incluye una política que deja al lector hacer `SELECT` de todas las filas de `telemetry_events` y nada más. Hace falta porque, con RLS activada y sin política, el lector vería 0 filas **sin ningún error** y la corrida reemplazaría el reporte por uno vacío. Si ya ejecutaste una versión del script sin esa política, ejecuta solo la línea `create policy pipeline_reader_select ...`.
5. **Comprueba los roles y, si quieres, ejecuta el pipeline con ellos** (sin escribir ninguna cadena de conexión a mano):

   ```bash
   python data/pipelines/verify_roles.py                  # solo comprueba; no escribe nada
   python data/pipelines/verify_roles.py --run --environment development --week-start 2026-10-26   # comprueba y ejecuta
   ```

   El script usa tu `DATABASE_URL` (del entorno o de `services/api/.env`) y construye las dos cadenas cambiando **solo el usuario** (`pipeline_reader` / `pipeline_writer`, conservando el `.ID_DEL_PROYECTO` de Supabase) y la contraseña. Te pide las dos contraseñas **sin mostrarlas**, no las imprime ni las guarda, y funcionan aunque lleven caracteres raros. Las comprobaciones son de solo lectura: las de "¿puede escribir?" usan `delete ... where false`, que no borra nada ni aunque esté permitido. Comprueba que el lector lee la telemetría, que **no** puede escribir ni ver `reporting`, que el escritor lee y escribe `reporting` pero **no** puede leer la telemetría, y que la RLS no deja al lector leyendo 0 filas en silencio. Si algo falla, no ejecuta nada.
6. **Úsalos de forma permanente:** añade `--write-env` y el script guarda las dos conexiones en tu `services/api/.env`, sin mostrarlas:

   ```bash
   python data/pipelines/verify_roles.py --write-env
   ```

   Solo escribe si **todas** las comprobaciones pasan; se niega si el archivo no está ignorado por git (una contraseña nunca debe llegar a un commit) y **nunca sobrescribe**: si `TELEMETRY_DATABASE_URL` o `REPORTING_DATABASE_URL` ya están en el archivo, no toca nada y te lo dice. Desde entonces, el comando normal `python data/pipelines/pipeline.py` lee con el lector y escribe con el escritor. Para dejar de usarlos, borra esas dos líneas del `.env`.

   **Qué cambia y qué no:** esas dos variables solo las leen el pipeline y la parte de `reporting` de la API (que con el escritor sigue pudiendo leer y escribir sus tablas). La telemetría, el inventario y los usuarios de la API usan solo `DATABASE_URL` y no cambian. Comprobado con la API arrancada con las dos variables en su `.env`: los endpoints de reporting, de telemetría y de inventario responden, y el pipeline lanzado desde la API (`POST /reporting/pipeline-runs`) funciona con los roles.

**Aviso:** la API del backoffice sigue usando su propia conexión (`DATABASE_URL`) para leer el reporte; estos roles son solo para el pipeline.

## Tests

Tests del pipeline (en la raíz del proyecto, no necesitan la API):

```bash
python -m pytest tests/pipelines                       # todos
python -m pytest tests/pipelines/test_pipeline.py      # unitarios de las tasks de transformación (sin base de datos, 1-2 s)
python -m pytest tests/pipelines/test_subflows.py      # cada subflow por separado
python -m pytest tests/pipelines/test_cli.py           # la línea de comandos del pipeline y su documentación
```

Tests de comportamiento del pipeline y de sus endpoints (necesitan la API):

```bash
cd services/api && uv run pytest tests/test_pipeline_*.py tests/test_reporting*.py tests/test_weekly_performance.py
```
