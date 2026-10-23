# Nexova | Plataforma de Operaciones Full Stack

**Proyecto de portfolio de Inés, desarrollado en el programa de Ingeniería de IA de 4Geeks Academy.**

[Español](README.es.md) | [English](README.md)

Nexova es un caso de estudio de una consultora de recursos humanos con un sitio público y una plataforma interna de operaciones. El repositorio reúne flujos autenticados, movimientos de inventario trazables, gestión de proveedores, incidencias de soporte y un diseño de telemetría orientado a decisiones de negocio.

**Tecnologías principales:** Python · FastAPI · SQLModel · PostgreSQL / Supabase · React · Next.js · TypeScript · Tailwind CSS.

Es un proyecto formativo y de portfolio desarrollado desde una plantilla del curso y con asistencia de IA. Se documentan por separado el estado de implementación, las propuestas de diseño y las mediciones reproducibles.

## Aspectos Destacados

| Área | Qué demuestra el repositorio | Evidencia |
| --- | --- | --- |
| Inventario | Stock derivado de entradas y salidas; autor autenticado; rechazo por stock insuficiente; bloqueo de filas en PostgreSQL para salidas concurrentes. | [Lógica de negocio](services/api/inventory/service.py) |
| Autenticación | JWT bearer, contraseñas con bcrypt, separación cuenta/perfil, permisos y navegación protegida en el backoffice. | [Documentación del API](services/api/README.md), [backoffice](uis/backoffice/README.md) |
| Operaciones | Flujos de proveedores, ciclo de vida e historial de incidencias y análisis CSV con validaciones compartidas. | [Paquete compartido](packages/shared/README.md), [dominios del API](services/api/README.md) |
| Rendimiento | Mediciones antes/después, análisis de causas y experimentos revertidos cuando los datos no justificaban mantenerlos. | [Auditoría](AUDIT.md), [resultados](REPORT.md), [evidencias](docs/performance/) |
| Diseño de telemetría | 40 contratos de evento: cinco obligatorios y 35 oportunidades; 12 puntos de inventario, privacidad, correlación y decisiones batch/stream. Todavía sin instrumentar. | [Plan de telemetría](docs/telemetry/telemetry-plan.md), [JSON Schema](docs/telemetry/event-schemas.json) |

## Casos de Ingeniería

### Inventario Trazable, No Stock Editable

El stock se calcula a partir de órdenes, no se almacena como un saldo editable. El API registra al autor autenticado, comprueba la oficina y rechaza salidas superiores al stock disponible. PostgreSQL bloquea la fila del activo durante la comprobación y el registro de una salida. Así, las reglas se aplican en backend y no dependen del saldo que muestra el navegador.

### Mejoras de Rendimiento Con Evidencia

La auditoría registrada de Lighthouse muestra Performance de **87 a 100** en incidencias y de **83 a 100** en proveedores. El CLS pasó de **0,255 a 0,014** y de **0,351 a 0**, respectivamente. Son resultados históricos de laboratorio sobre las builds de producción auditadas, no monitorización de producción, mediciones ejecutadas ahora ni garantías para cualquier dispositivo. Consulta el [método y sus limitaciones](REPORT.md).

### De Preguntas de Negocio a Contratos de Eventos

La [entrega de telemetría](docs/telemetry/README.md) transforma un RFI de operaciones en hipótesis, decisiones concretas, responsables, prioridades, esquemas y escenarios de aceptación. Sus 40 allowlists se contrastan con un diccionario tipado de 50 claves, con tratamiento de privacidad por evento y justificación de negocio para 16 eventos stream y 24 batch. Documenta control de frecuencia, riesgos y datos excluidos deliberadamente. Separa órdenes confirmadas de clics, validaciones locales de rechazos del API y la confirmación local del formulario de talento de una candidatura recibida por un servidor. Captura, outbox, ingesta y dashboards siguen pendientes de implementación.

La [matriz de evaluación](docs/telemetry/telemetry-plan.md#matriz-de-la-rubrica-de-evaluacion) relaciona los diez criterios del enunciado con evidencias concretas y distingue validación local, aprobación docente e implementación futura.

## Arquitectura y Decisiones

```text
Sitio público: React + Vite          Backoffice interno: Next.js
			     API FastAPI
		Inventario: SQLModel + PostgreSQL / Supabase
	Cuentas, perfiles, proveedores e incidencias: TinyDB
```

- **Monolito modular:** un API con routers por dominio y reglas en servicios, sin introducir microservicios antes de necesitarlos.
- **Dos persistencias:** inventario relacional y dominios existentes en TinyDB. TinyDB limita el funcionamiento con varios workers y no se presenta como una base escalable de producción.
- **Contratos compartidos:** las reglas de incidencias se reutilizan en API, CLI y backoffice para reducir diferencias de validación.
- **Frontera de seguridad explícita:** las guardas del navegador mejoran la navegación; autenticación y autorización en el API controlan el acceso real.

La [propuesta de arquitectura](docs/ARCHITECTURE_PROPOSAL.md) y la [documentación del backend](services/api/README.md) explican los detalles y restricciones.

## Ejecución Local

Requisitos: Node.js 22.12+ con npm, Python 3.10+ y uv. Ejecutar desde un clon local; no subir credenciales al repositorio.

Backend, empezando en la raíz:

```bash
cd services/api
uv sync
cp -n .env.example .env
```

Antes de arrancar, configura localmente `SECRET_KEY` y las credenciales iniciales `AUTH_INITIAL_EMAIL` / `AUTH_INITIAL_PASSWORD`, siguiendo la [guía del API](services/api/README.md#configuration). Para Supabase, configura `DATABASE_URL`; sin ella, el inventario usa SQLite solo para desarrollo. Los dominios TinyDB requieren un único worker del API.

```bash
uv run uvicorn main:app --reload --port 8000
```

En una segunda terminal, desde la raíz:

```bash
npm install
npm run dev:backoffice
```

En una tercera terminal, desde la raíz:

```bash
npm run dev
```

Direcciones locales por defecto: sitio público `http://localhost:5173`, backoffice `http://localhost:5174` y documentación del API `http://localhost:8000/docs`. La configuración del proxy y los requisitos end-to-end se explican en la [guía del backoffice](uis/backoffice/README.md).

## Validación y Reproducibilidad

Comprobaciones disponibles desde la raíz:

```bash
npm run typecheck
npm run typecheck:backoffice
npm run test:shared
npm run test:backoffice
```

Para backend, ejecutar `uv run pytest` desde la carpeta del API. Esta lista identifica comandos disponibles, no afirma que todas las suites estén pasando actualmente. Preparación, fixtures, alcance de cobertura y requisitos end-to-end están en [TESTING.md](TESTING.md) y el [plan de pruebas](docs/testing-plan.md). La validación de esquemas de telemetría se explica en su [README](docs/telemetry/README.md).

## Alcance y Siguientes Pasos

Implementado: sitio público, backoffice autenticado, dominios del API, inventario relacional, reglas compartidas de incidencias y suites de pruebas. Documentado: evidencias de rendimiento y diseño de telemetría. Pendiente: instrumentación y almacenamiento de telemetría, endurecimiento para producción e integraciones futuras de IA. El formulario de talento actual solo confirma en el navegador, sin guardar candidaturas en el API. Las carpetas de plantilla no implican que existan RAG, agentes o workflows automatizados desplegados.

## Explorar el Trabajo

- [Briefing de negocio](nexova-BRIEFING.es.md) y [arquitectura](docs/ARCHITECTURE_PROPOSAL.md).
- [Cuaderno de aprendizaje](aprendiendo%20con%20la%20ia.md): decisiones, errores, soluciones y papel de la asistencia de IA.
- [Caso de autenticación](aprendiendo%20con%20la%20ia%20-%20AUTH-02.md) y [caso de rendimiento](aprendiendo%20con%20la%20ia%20-%20PERF-AUDIT.md).
- [Código del sitio público](uis/website/) y [código del backoffice](uis/backoffice/).

## Créditos

Desarrollado dentro del programa de Ingeniería de IA de 4Geeks Academy, desde su plantilla de proyecto de compañía. Se conserva debajo la atribución original y la guía histórica. El cuaderno documenta las decisiones de implementación, la verificación y el trabajo asistido por IA.

<details>
<summary>Plantilla del Curso y Notas de Entregas Anteriores</summary>

El contenido siguiente se conserva como referencia de procedencia. Las afirmaciones sobre una plantilla vacía y las notas de entregas previas no describen el estado actual del proyecto.

# Nexova — Proyecto de Ingenieria de IA

## Proyecto actual: diseno de telemetria de inventario

El monorepo contiene el sitio publico (`uis/website`), el backoffice (`uis/backoffice`), la API central FastAPI (`services/api`), paquetes compartidos, scripts y documentacion. El inventario ya calcula stock mediante entradas y salidas; esta entrega disena la telemetria de material formativo, certificaciones y equipos de incorporacion sin modificar las aplicaciones.

Consulta el [README de la entrega](docs/telemetry/README.md), el [plan de telemetria](docs/telemetry/telemetry-plan.md) y los [esquemas con ejemplos](docs/telemetry/event-schemas.json). La fuente de requisitos es el [briefing de Nexova](nexova-BRIEFING.es.md). El trabajo, las decisiones y las comprobaciones se explican en el [cuaderno de aprendizaje](aprendiendo%20con%20la%20ia.md#telemetria-plan-de-diseno).

La ampliacion responde al RFI de gestion con 40 tipos de evento, clasificados individualmente en cinco Obligatorio y 35 Oportunidad identificada. La Fase 1 mapea el flujo completo de inventario con 12 puntos, incluidos stock directo rechazado, validaciones fallidas y cruces de minimo. Tambien cubre autenticacion, navegacion, abandono, proveedores, incidencias, website, salud tecnica, carga de secciones, validacion local y procesos internos. Cada tipo tiene hipotesis, decision, responsable, prioridad y modo batch/stream. El schema 2.0.0 incorpora el envelope solicitado con sesion/correlacion y ocho ejemplos.

Esta fase entrega solo documentacion de diseno: no se ha desplegado ningun servidor, colector, base de datos ni dashboard nuevo. No se ha creado ni fusionado ninguna PR. Se conserva debajo la guia original de plantilla y las entregas anteriores como referencia historica; el apartado que describe una plantilla vacia no representa el estado de las aplicaciones actuales.

[![4Geeks Academy](https://img.shields.io/badge/4Geeks-Academy-blue)](https://4geeksacademy.com)
[![AI Engineering](https://img.shields.io/badge/track-AI%20Engineering-green)](https://4geeksacademy.com/es/programas-de-carrera/ingenieria-ia)

_Plantilla base para proyectos transversales del Programa de Carrera en Ingeniería de IA — 4Geeks Academy._

_These instructions are also available in [English](./README.md)._

---

## 📦 Entrega: auditoría de rendimiento (Lighthouse)

Todo lo de la auditoría está en este repositorio, en `main`:

| Qué | Dónde |
|---|---|
| **Auditoría**: puntuaciones iniciales, causa raíz de cada problema, casos de duplicación, qué identifican las skills de agente | [`AUDIT.md`](./AUDIT.md) |
| **Informe**: cada mejora, puntuaciones antes/después, impacto de cada commit, INP, qué tuvo mayor impacto | [`REPORT.md`](./REPORT.md) |
| **Capturas de Lighthouse** | [`audit/before/`](./audit/before/) · [`audit/after/`](./audit/after/) |
| Evidencia en bruto (JSON de Lighthouse, resultados por commit, INP, comparaciones A/B) | [`docs/performance/`](./docs/performance/) |
| Apuntes de estudio (cómo se hizo, decisiones, errores) | [`aprendiendo con la ia - PERF-AUDIT.md`](./aprendiendo%20con%20la%20ia%20-%20PERF-AUDIT.md) |

En una línea: las cuatro categorías de Lighthouse quedan en 100 en el website (móvil y escritorio) y en el backoffice, se corrigieron los desplazamientos de diseño del backoffice (CLS 0,255 y 0,351; Performance 87 y 83 → 100), y cada commit corrige un problema y está medido. Cómo reproducirlo: [`REPORT.md` §8](./REPORT.md#8-cómo-reproducir).

---

## Propósito

Este repositorio es la **plantilla de inicio** para los proyectos transversales. Trabajarás con escenarios de empresas reales (Brasaland, TrackFlow, Nexova) construyendo entregables que se corresponden con los hitos del curso (Web, Programación, Backend, Telemetría, RAG, Agentes, Workflows, Tiempo real).

- Crea una plantilla a partir de este repositorio.
- Reemplaza el `CONTEXT.md` placeholder por el contexto de tu empresa asignada.
- Usa `skills/` y los `README.md` por carpeta como guía de trabajo.

---

## Cómo empezar

1. **Usa este repositorio como plantilla** y crea tu propio repo de proyecto.
2. **Clona** tu repositorio (o ábrelo en Codespaces).
3. **Reemplaza** `CONTEXT.md` con el contexto completo de tu empresa asignada.
4. **Lee esta guía de carpetas** y abre el `README.md` de la carpeta en la que estés trabajando.
5. **Empieza a implementar** en la carpeta correcta — no tires todo en la raíz.
6. **Documenta** lo que añadas: cada app, servicio, agente o pipeline nuevo lleva subcarpeta + README.

---

## Cómo entender este monorepo

Estás construyendo **una sola empresa** a lo largo de muchos hitos y proyectos. Cada carpeta de primer nivel tiene **una responsabilidad clara** — como en un repositorio real de un equipo de ingeniería.

| Capa                    | Carpetas                          | Qué vive aquí                                                               |
| ----------------------- | --------------------------------- | --------------------------------------------------------------------------- |
| **Contexto de empresa** | `CONTEXT.md`                      | Datos del dominio, nombres de campos y restricciones de tu empresa asignada |
| **Cara al usuario**     | `uis/`, `services/`               | Frontends y backends con los que interactúan usuarios u operadores          |
| **Datos**               | `data/`                           | Archivos crudos, pipelines, datasets procesados y conjuntos de evaluación   |
| **IA**                  | `agents/`, `skills/`, `mcps/`     | Agentes, capacidades reutilizables para agentes y servidores MCP            |
| **Automatización**      | `workflows/`                      | Flujos n8n y orquestación entre sistemas                                    |
| **Reutilización**       | `packages/`, `shared/`            | Tipos compartidos, SDKs, esquemas, plantillas                               |
| **Operaciones**         | `infra/`, `scripts/`, `internal/` | Docker, despliegue, scripts puntuales, CLIs internas                        |
| **Documentación**       | `docs/`                           | Arquitectura, decisiones y convenciones de todo el repo                     |

**Regla rápida:** si tiene interfaz visual → `uis/`. Si expone una API o corre en segundo plano → `services/`. Si mueve o transforma datos → `data/`. Si el trabajo lo hace un modelo de IA → `agents/` (+ `skills/` o `mcps/` según haga falta).

---

## Estado actual de la plantilla

> 💡 Actualmente el repositorio ofrece solo una **estructura base de carpetas y documentación**. Todavía no incluye aplicaciones ejecutables ni scripts globales en la raíz.
>
> - `CONTEXT.md` es un placeholder y debe sustituirse por el contexto de la empresa asignada.
> - No existe todavía un `AGENTS.md` en la raíz.
> - Existe metadata del paquete compartido en `packages/shared/package.json` (`@repo/shared-types`), pero aún no hay runner de workspace en raíz.

---

## Guía de carpetas — qué va en cada una

Lee el `README.md` enlazado dentro de cada carpeta antes de empezar a programar ahí.

### Archivos en la raíz

| Ruta                         | Propósito                                                            | Qué haces aquí                                                                                               |
| ---------------------------- | -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| [`CONTEXT.md`](./CONTEXT.md) | Fuente única de verdad de tu empresa (Brasaland, TrackFlow o Nexova) | **Primer paso:** copia aquí el briefing de tu empresa para que apps, agentes y prompts usen el mismo dominio |
| `docker-compose.yml`         | Orquestación local de todo el stack                                  | Mantener en la raíz del repo — conecta `services/`, bases de datos y otros contenedores desde un solo lugar  |
| `README.md` / `README.es.md` | Esta guía                                                            | Orientación — estás aquí                                                                                     |

### `uis/` — interfaces de usuario

**Propósito:** Todas las aplicaciones frontend — todo lo que un humano ve y en lo que hace clic.

**Pon aquí:**

- Sitio web público (`website/`)
- Admin interno / backoffice (`backoffice/`)
- Portales de clientes, apps de fidelización, herramientas Streamlit/Gradio, dashboards con UI

**Ejemplos:** landing corporativa, backoffice de operaciones, portal de fidelización, UI de dashboard de telemetría

→ Ver [`uis/README.md`](./uis/README.md)

### `services/` — API centralizada de la empresa (FastAPI)

**Propósito:** Un **backend FastAPI centralizado** para toda la empresa — un solo punto de entrada que reduce la complejidad a medida que crece el proyecto.

**Pon aquí:**

- Una app FastAPI principal (p. ej. `api/`) con routers/módulos por dominio (ubicaciones, menús, ventas, telemetría, etc.)
- Workers en background solo cuando de verdad necesiten correr separados de la API

**Recomendación:** evita dividir en muchos microservicios al inicio. Añade endpoints a la misma app FastAPI; extrae un worker solo cuando sea necesario.

**Ejemplos:** `/locations`, `/menus`, `/sales/reports`, webhooks, jobs programados

→ Ver [`services/README.md`](./services/README.md)

### `data/` — datasets, pipelines y evaluación

**Propósito:** Todo lo relacionado con datos, desde archivos crudos hasta tablas listas para producción.

| Subcarpeta                                      | Propósito                     | Qué haces aquí                                                                  |
| ----------------------------------------------- | ----------------------------- | ------------------------------------------------------------------------------- |
| [`data/raw/`](./data/raw/README.md)             | Datos fuente sin tocar        | Guardar dumps, exports, CSV/JSON de ejemplo — documentar origen y reglas de PII |
| [`data/pipelines/`](./data/pipelines/README.md) | Jobs ETL/ELT                  | Escribir scripts de ingesta, limpieza y transformación                          |
| [`data/process/`](./data/process/README.md)     | Salidas limpias / intermedias | Guardar artefactos de pipelines (features, agregados, tablas limpias)           |
| [`data/eval/`](./data/eval/README.md)           | Medición de calidad           | Golden sets, datasets de evaluación RAG/agentes, métricas de experimentos       |

**Flujo:** `raw` → `pipelines` → `process` → consumido por `services/`, `uis/` o `agents/`. Usa `eval` para demostrar calidad.

### `agents/` — agentes de IA

**Propósito:** Asistentes de IA autónomos o semi-autónomos para la empresa.

**Pon aquí:**

- Una subcarpeta por agente (p. ej. `support-agent/`, `onboarding-agent/`)
- Config del agente, prompts, herramientas, tests
- Empieza desde [`agents/_template/`](./agents/_template/README.md) al crear un agente nuevo

**Ejemplos:** bot de soporte al cliente, copiloto de onboarding, asistente de formación

→ Ver [`agents/README.md`](./agents/README.md)

### `skills/` — capacidades reutilizables para agentes

**Propósito:** Instrucciones empaquetadas + scripts que agentes (o tú en Cursor) reutilizan en todo el repo.

**Pon aquí:**

- Skills de análisis de datos, code review, scraping, investigación, etc.
- Cada skill = carpeta con `SKILL.md`, scripts y recursos opcionales

**Ejemplo incluido:** `skills/data-analysis/` (script de limpieza pandas + referencia de métricas)

→ Ver [`skills/README.md`](./skills/README.md)

### `mcps/` — servidores Model Context Protocol

**Propósito:** Conectar modelos de IA con tus sistemas — bases de datos, APIs, GitHub, herramientas propias.

**Pon aquí:**

- Una subcarpeta por servidor MCP (p. ej. `database-mcp/`, `github-mcp/`)
- Definiciones de tools, resources y config del servidor

**Cuándo usarlo:** cuando un agente necesita acceso en vivo a datos o acciones que el código solo no puede dar

→ Ver [`mcps/README.md`](./mcps/README.md)

### `workflows/` — automatización y orquestación

**Propósito:** Conectar sistemas sin escribir apps completas — jobs programados, webhooks, notificaciones.

**Pon aquí:**

- Exports de workflows n8n, configs de Make/Zapier u orquestación documentada
- Flujos que enlazan `services/`, `data/pipelines/` y `agents/`

**Ejemplos:** nuevo pedido → alerta Slack, trigger ETL nocturno, lead → sync CRM

→ Ver [`workflows/README.md`](./workflows/README.md)

### `packages/` — librerías compartidas

**Propósito:** Código versionable reutilizado por varias apps, agentes o pipelines.

**Pon aquí:**

- Tipos TypeScript compartidos (`packages/shared/` → `@repo/shared-types`)
- Librerías de componentes UI, clientes API, SDKs de analytics

**Regla:** si `uis/` y `services/` comparten la misma interfaz → extráela aquí

→ Ver [`packages/README.md`](./packages/README.md)

### `shared/` — recursos sueltos compartidos

**Propósito:** Recursos que no son un paquete completo — esquemas, plantillas, assets estáticos, docs cortas.

**Pon aquí:**

- Esquemas JSON, plantillas de email, specs OpenAPI, design tokens
- Cualquier cosa reutilizada pero demasiado pequeña o no-código para `packages/`

→ Ver [`shared/README.md`](./shared/README.md)

### `docs/` — documentación transversal

**Propósito:** Arquitectura y decisiones que abarcan todo el proyecto de la empresa.

**Pon aquí:**

- Diagramas de arquitectura, ADRs, guías de seguridad/observabilidad
- Convenciones no atadas a una sola app o agente

→ Ver [`docs/README.md`](./docs/README.md)

### `infra/` — infraestructura y despliegue

**Propósito:** Cómo corre el proyecto en Docker, cloud o CI.

**Pon aquí:**

- Dockerfiles, Terraform, manifiestos K8s, configs Nginx, pipelines CI/CD

**Mantener en la raíz del repo:** `docker-compose.yml` — orquesta el entorno local de `services/`, bases de datos y otros contenedores desde un solo lugar.

→ Ver [`infra/README.md`](./infra/README.md)

### `scripts/` — scripts de ayuda

**Propósito:** Automatización pequeña y repetible — no apps completas.

**Pon aquí:**

- Scripts de setup, generadores de seed data, wrappers de lint, migraciones puntuales
- Documenta cada script: qué hace, argumentos y cómo ejecutarlo

**Diferencia con `internal/`:** los scripts suelen ser archivos sueltos; las tools de `internal/` son proyectos estructurados con deps y tests propios.

→ Ver [`scripts/README.md`](./scripts/README.md)

### `internal/` — herramientas internas para desarrolladores

**Propósito:** Utilidades robustas para el equipo de ingeniería.

**Pon aquí:**

- CLIs, herramientas de migración empaquetadas, evaluadores de prompts
- Tools con su propio `package.json`, tests y pasos de instalación

→ Ver [`internal/README.md`](./internal/README.md)

---

## ¿Dónde pongo esto?

Guía rápida de decisión:

```text
¿Tiene botones y pantallas?                → uis/
¿Corre en servidor / API / cola?           → services/
¿Es dato crudo o transformado?             → data/raw/ o data/process/
¿Mueve datos entre sistemas?               → data/pipelines/
¿Mides calidad de IA/pipelines?            → data/eval/
¿Es un asistente de IA con un objetivo?    → agents/
¿Es una capacidad/instrucción reutilizable?→ skills/
¿La IA necesita llamar tools/APIs externas?→ mcps/
¿Es n8n / automatización programada?       → workflows/
¿2+ carpetas importan el mismo código?     → packages/
¿Es esquema/plantilla/asset, no librería?  → shared/
¿Es arquitectura o docs de todo el equipo? → docs/
¿Es docker-compose para dev local?         → raíz del repo
¿Es Docker / deploy / config cloud?        → infra/
¿Es un script puntual?                     → scripts/
¿Es una CLI con su propio paquete?         → internal/
```

---

## Estructura del repositorio (árbol)

```text
ai-engineering-company-project-monorepo/
├── README.md / README.es.md   # Esta guía
├── CONTEXT.md                 # ← Reemplazar con el briefing de tu empresa
├── docker-compose.yml         # ← Orquestación local (raíz del repo)
├── uis/                       # Frontends (website, backoffice, dashboards)
├── services/                  # API FastAPI centralizada de la empresa
├── data/
│   ├── raw/                   # Datasets fuente
│   ├── pipelines/             # Jobs ETL/ELT
│   ├── process/               # Salidas limpias / intermedias
│   └── eval/                  # Conjuntos de evaluación y métricas
├── agents/                    # Agentes de IA (+ plantilla _template/)
├── skills/                    # Skills reutilizables para agentes
├── mcps/                      # Servidores MCP para acceso a tools
├── workflows/                 # Flujos n8n y automatizaciones
├── packages/                  # Librerías compartidas (@repo/shared-types, …)
├── shared/                    # Esquemas, plantillas, assets sueltos
├── docs/                      # Arquitectura y docs transversales
├── infra/                     # Docker, Terraform, despliegue
├── scripts/                   # Scripts de ayuda
└── internal/                  # CLIs y herramientas internas de desarrollo
```

---

## Enlaces

- [4Geeks Academy — Ingeniería de IA](https://4geeksacademy.com/es/programas-de-carrera/ingenieria-ia)
- [Cómo empezar un proyecto de código](https://4geeks.com/lesson/how-to-start-a-project)

---

## Contribuidores

Esta plantilla fue creada como parte del Programa de Carrera de Ingeniería de IA de 4Geeks Academy por [@marcogonzalo](https://www.linkedin.com/in/marcogonzalo) y [@alezanchezr](https://x.com/alesanchezr), junto a otros muchos colaboradores. Descubre más sobre nuestro [Curso de Ingeniería de IA](https://4geeksacademy.com/es/programas-de-carrera/ingenieria-ia) y sobre [otros cursos](https://4geeksacademy.com/es/comparar-programas).

Puedes encontrar otras plantillas y recursos similares en la [página de GitHub de 4Geeks Academy](https://github.com/4geeksacademy).

_Esta plantilla la mantiene 4Geeks Academy para el track de Ingeniería de IA. Uso exclusivo del programa._

</details>
