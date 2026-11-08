# `data/raw` folder

This folder is intended for **raw data** related to the company: dumps, exports, sample files, event samples, or untransformed datasets.

- **Main purpose**: serve as a landing zone or reference for original data before pipelines process it.
- **Recommendation**: document each dataset’s origin, format, expected size, privacy/PII considerations, and how it is versioned (ideally avoiding sensitive data in the repository).

> _Spanish version: [README.es.md](./README.es.md)._

## Telemetry exports

`telemetry_YYYY-MM-DD.csv` is written here every night by [`scripts/nightly_export.py`](../../scripts/nightly_export.py): the events of that UTC day, straight from `telemetry_events`. It is a **backup** for audit and recovery; no pipeline reads it (they read the database). It is telemetry, so it is git-ignored (`data/raw/telemetry_*.csv`).
