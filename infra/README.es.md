# Carpeta `infra`

Esta carpeta contiene las **configuraciones de infraestructura** para el monorepo (por ejemplo: Dockerfiles, scripts de Terraform, manifiestos de despliegue, configuraciones de Nginx, etc.).

- **Propósito principal**: centralizar la definición de la infraestructura necesaria para ejecutar las aplicaciones y servicios de la compañía.
- **Recomendación**: documenta cómo aprovisionar y desplegar la infraestructura.

### Tarea nocturna (`scheduler`)

| Servicio | Puerto | Notas |
| --- | --- | --- |
| `scheduler` | ninguno | ejecuta `scripts/nightly_export.py` cada noche a las 02:00 UTC. **Apagado por defecto**: `docker compose --profile scheduler up -d scheduler`. Detalles y razones de esta decisión: [`infra/scheduler/`](./scheduler/README.md) |
