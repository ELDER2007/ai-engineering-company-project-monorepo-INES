# Carpeta `scripts`

Esta carpeta contiene **scripts auxiliares** del monorepo: automatizaciones de desarrollo, utilidades de mantenimiento, tareas repetitivas (setup, lint, migraciones, generación de datos, etc.) y tooling interno.

- **Propósito principal**: agrupar herramientas de soporte que no pertenecen a una app/agente/pipeline específico, pero facilitan el trabajo del equipo.
- **Recomendación**: documenta cada script (qué hace, parámetros, requisitos, ejemplos de uso) y procura que sean reproducibles (y seguros) en distintos entornos.

## Scripts

### `train_sales_forecast.py` — Pronóstico de ventas de Nexova

Entrena y evalúa el pronóstico de ingresos mensuales de [`BRIEFING_NEXOVA_SALES.md`](../BRIEFING_NEXOVA_SALES.md).

- **Qué hace**: carga `data/raw/nexova_sales.csv` y comprueba sus columnas; trata los valores vacíos (nunca con meses posteriores); separa por fecha (8 años para entrenar, los 2 más recientes para probar); construye variables causales; entrena un Random Forest cuyos ajustes se eligen con validación temporal dentro de los años de entrenamiento (por qué Random Forest: [`data/process/sales_model.py`](../data/process/sales_model.py)); evalúa MSE, PSI, Gini y K² Score en los años de prueba; escribe `metrics.json` y la gráfica del pronóstico con su rango en [`data/eval/sales_forecast/`](../data/eval/sales_forecast/README.es.md). La semilla está fijada (42).
- **Requisitos**: [`uv`](https://docs.astral.sh/uv/); las librerías son las del `pyproject.toml` / `uv.lock` de la raíz (Python 3.12).
- **Uso**, desde la raíz del repositorio (alrededor de un minuto):
  ```bash
  uv run python scripts/train_sales_forecast.py
  uv run python scripts/train_sales_forecast.py --compare          # compara además Random Forest con XGBoost (solo años de entrenamiento)
  uv run python scripts/train_sales_forecast.py --data otro.csv --output /tmp/resultados
  uv run pytest tests/pipelines                                    # sus pruebas
  ```

### `evaluate_sales_model.py` — Evaluación formal del pronóstico de ventas

Evalúa el modelo de `train_sales_forecast.py` antes de su paso a *staging*. El reporte que lee sus resultados es [`data/eval/evaluation_report.es.md`](../data/eval/evaluation_report.es.md).

- **Qué hace**: usa **solo los años de entrenamiento (2016-2023)**. Validación cruzada temporal anidada (8 bloques) con comprobación de orden y de fugas; MAE y RMSE; curvas de aprendizaje y de complejidad; análisis del origen del error y comparación de correcciones declaradas de antemano. No cambia el modelo entregado.
- **Escribe**: `diagnosis.json`, `root_cause.json` y las gráficas en [`data/eval/regression_eval/`](../data/eval/regression_eval/README.es.md); la curva de aprendizaje en `data/eval/learning_curve.png` (y `.es.png`). Con `--output` otra carpeta, todo queda allí y no se tocan los archivos del repositorio.
- **Requisitos**: los mismos que el anterior (`pyproject.toml` / `uv.lock` de la raíz).
- **Uso**, desde la raíz del repositorio (unos 10 minutos):
  ```bash
  uv run python scripts/evaluate_sales_model.py
  uv run python scripts/evaluate_sales_model.py --output /tmp/evaluacion     # de prueba
  uv run pytest tests/pipelines/test_sales_diagnosis.py tests/pipelines/test_sales_evaluation_report.py
  ```

### `analyze.py` — Analizador de CSV de incidentes de Nexova

Valida y calcula métricas sobre un CSV de incidentes de soporte de Nexova, según las reglas en [`CONTEXT-nexova.md`](./CONTEXT-nexova.md).

- **Qué hace**: carga el CSV, detecta registros inválidos (campos faltantes o fuera de rango, un tipo de regla por problema), e imprime totales, desglose de inválidos por regla, distribución por categoría/estado con porcentajes, y el promedio de satisfacción de los tickets cerrados. Ofrece exportar los resultados a `results.csv` (una métrica por fila).
- **Requisitos**: Python 3.10+, sin dependencias externas — instala una vez el paquete compartido de validación/métricas en modo editable: `pip install -e packages/shared/incidents_analyzer`.
- **Uso**:
  ```bash
  python scripts/analyze.py data/raw/incidents-nexova.csv
  ```
- **Misma lógica que la API**: el código de validación/métricas vive en [`packages/shared/incidents_analyzer`](../packages/shared/incidents_analyzer) y lo reutiliza tal cual el dominio `incidents` de [`services/api`](../services/api), para que el script y la API nunca diverjan.
- **Privacidad**: nunca imprime, registra ni exporta direcciones de `customer_email`, según la nota de stakeholders en `CONTEXT-nexova.md`.

### `seed_incidents.py` — cargar el histórico CSV en el gestor de incidencias

Carga el export histórico del helpdesk en la base del gestor de incidencias (`services/api/incidents/db.json`).

- **Qué hace**: valida cada fila con las reglas compartidas de `incidents_analyzer`, la transforma (`description → title`, `date → created_at`, mapas de estado y categoría, columna opcional `location`/`ubicacion` → `branch`, por defecto `central`) y la inserta con `origin: "customer"`. Las filas inválidas **no** se insertan: se listan con su línea, id y reglas incumplidas (nunca el email). Idempotente: los ids ya guardados se saltan, nunca se sobrescriben. Termina comprobando que `/api/incidents/summary` coincide con las métricas esperadas del CSV transformado (código de salida `1` si no).
- **Requisitos**: el entorno de la API (pydantic, tinydb…): `cd services/api && python -m venv .venv && .venv/bin/pip install -r requirements.txt`.
- **Uso**:
  ```bash
  services/api/.venv/bin/python scripts/seed_incidents.py              # data/raw/incidents-nexova.csv
  services/api/.venv/bin/python scripts/seed_incidents.py --reset      # borra las incidencias antes
  services/api/.venv/bin/python scripts/seed_incidents.py --csv otro.csv --db /tmp/incidents.json
  ```
- **Detalle y tabla de mapeo**: [`services/api/README.md`](../services/api/README.md#incident-manager). El CONTEXT no define los mapas; viven en [`packages/shared/incidents/contract.json`](../packages/shared/incidents/contract.json).

### `nightly_export.py` — la exportación nocturna de la telemetría (ticket DEV-53)

Cada noche: exporta a un CSV la telemetría del día UTC anterior, lanza el pipeline de datos y registra en la base de datos lo que pasó.

- **Qué hace**: escribe `data/raw/telemetry_YYYY-MM-DD.csv` a partir de `telemetry_events` (solo si el archivo no existe; es una **copia de seguridad** para auditoría y recuperación, no una entrada del pipeline), lanza `data/pipelines/pipeline.py` como subproceso y guarda una fila por ejecución en la tabla `job_runs` (`pending → processing → completed | failed`). El candado, la idempotencia y el tratamiento de ejecuciones zombis: al principio del script y en [`services/api/job_runner/README.md`](../services/api/job_runner/README.md).
- **Un proceso aparte**: no importa FastAPI y nunca se ejecuta dentro de la API. Lo arranca desde fuera, cada noche, el contenedor planificador ([`infra/scheduler/`](../infra/scheduler/README.md), `0 2 * * *` UTC).
- **Requisitos**: el entorno de la API (`services/api/requirements.txt`) y una base de datos: `DATABASE_URL` (también se lee de `services/api/.env`).
- **Uso**:
  ```bash
  python scripts/nightly_export.py                            # ayer, en UTC
  TARGET_DATE=2026-10-30 python scripts/nightly_export.py     # un día pasado concreto, sin cambiar el código
  ```
- **Código de salida**: `0` hecho o saltado (ya estaba hecho / hay otra ejecución en marcha), `1` falló, `2` mal uso, `130` interrumpido.
- **Privacidad**: el CSV es telemetría; `data/raw/telemetry_*.csv` está ignorado por git. Las credenciales que traiga un error nunca llegan a la tabla ni al log.

## Códigos de salida

`0` = funcionó. `1` = falló (entrada ausente o ilegible, datos dañados); `2` = uso incorrecto de la línea de comandos (`analyze.py`). El mensaje va a stderr. Un script nunca termina con `0` después de fallar.
