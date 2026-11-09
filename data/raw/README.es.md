# Carpeta `data/raw`

Esta carpeta está pensada para almacenar **datos en bruto** (raw) relacionados con la compañía: dumps, exports, archivos de ejemplo, muestras de eventos, o datasets sin transformar.

- **Propósito principal**: servir como zona de aterrizaje o referencia de datos originales antes de ser procesados por pipelines.
- **Recomendación**: documenta el origen de cada dataset, formato, tamaño esperado, consideraciones de privacidad/PII y cómo se versiona (idealmente evitando subir datos sensibles al repositorio).

## Exportaciones de telemetría

`telemetry_AAAA-MM-DD.csv` lo escribe aquí cada noche [`scripts/nightly_export.py`](../../scripts/nightly_export.py): los eventos de ese día UTC, directos de `telemetry_events`. Es una **copia de seguridad** para auditoría y recuperación; ningún pipeline la lee (leen la base de datos). Es telemetría, así que git la ignora (`data/raw/telemetry_*.csv`).
