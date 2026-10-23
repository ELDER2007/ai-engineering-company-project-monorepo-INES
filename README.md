# Nexova | Full-Stack Operations Platform

**A portfolio project by Ines, developed through the 4Geeks Academy AI Engineering programme.**

[English](README.md) | [Español](README.es.md)

Nexova is an HR consultancy case study used to build a public website and an internal operations platform. The repository brings together authenticated workflows, traceable inventory movements, supplier management, support incidents, and a business-driven telemetry design.

**Core stack:** Python · FastAPI · SQLModel · PostgreSQL / Supabase · React · Next.js · TypeScript · Tailwind CSS.

This is a learning and portfolio project developed from a course template with AI assistance. Implementation status, design proposals, and reproducible measurements are documented separately below.

## Project Highlights

| Area | What the repository demonstrates | Evidence |
| --- | --- | --- |
| Inventory | Stock derived from inbound/outbound orders; authenticated authors; insufficient-stock rejection; PostgreSQL row locking for concurrent withdrawals. | [Business logic](services/api/inventory/service.py) |
| Authentication | JWT bearer authentication, bcrypt password hashing, account/profile separation, permissions, and protected backoffice navigation. | [API documentation](services/api/README.md), [backoffice](uis/backoffice/README.md) |
| Operations | Supplier workflows, incident lifecycle/history, and CSV analysis using shared validation logic. | [Shared package](packages/shared/README.md), [API domains](services/api/README.md) |
| Performance | Documented before/after measurements, root-cause analysis, and experiments that were reverted when evidence did not support them. | [Audit](AUDIT.md), [results](REPORT.md), [raw evidence](docs/performance/) |
| Telemetry design | 40 event contracts: five mandatory and 35 identified opportunities; 12 inventory instrumentation points, privacy rules, correlation, and batch/stream decisions. Not instrumented yet. | [Telemetry plan](docs/telemetry/telemetry-plan.md), [JSON Schema](docs/telemetry/event-schemas.json) |

## Engineering Case Studies

### Traceable Inventory Instead of Editable Stock

Stock is calculated from orders rather than stored as an editable balance. The API records the authenticated author, enforces office consistency, and refuses withdrawals above available stock. PostgreSQL locks the asset row while checking and registering a withdrawal. These choices keep business rules in the backend rather than relying on the browser's displayed balance.

### Performance Improvements With Evidence

The recorded Lighthouse audit shows Performance increasing from **87 to 100** on incidents and **83 to 100** on suppliers. CLS fell from **0.255 to 0.014** and **0.351 to 0**, respectively. These are historical laboratory results for the audited production builds, not live production monitoring, current-run results, or guarantees for every device. See the [measurement method and limitations](REPORT.md).

### Turning Business Questions Into Event Contracts

The [telemetry deliverable](docs/telemetry/README.md) translates an operations RFI into event hypotheses, concrete decisions, owners, priorities, schemas, and acceptance scenarios. Its 40 allowlists are matched against a 50-key typed data dictionary, with per-event privacy treatment and a business rationale for 16 stream and 24 batch events. Frequency controls, risks, and deliberately excluded data are documented. It separates committed orders from clicks, local validation from API rejection, and a locally confirmed talent form from an application actually received by a server. Capture, outbox, ingestion, and dashboards remain future implementation work.

The [evaluation matrix](docs/telemetry/telemetry-plan.md#matriz-de-la-rubrica-de-evaluacion) maps the ten assignment criteria to concrete design evidence and distinguishes local validation from instructor approval and future implementation.

## Architecture and Trade-Offs

```text
Public website: React + Vite          Internal backoffice: Next.js
			     FastAPI API
		Inventory: SQLModel + PostgreSQL / Supabase
	Accounts, profiles, suppliers, incidents: TinyDB
```

- **Modular monolith:** one API with domain routers and service-layer business logic, rather than premature microservices.
- **Two persistence layers:** relational inventory plus existing TinyDB domains. TinyDB limits multi-worker operation and is not presented as a scalable production database.
- **Shared contracts:** incident rules are reused across the API, CLI, and backoffice to reduce validation drift.
- **Explicit security boundary:** browser guards improve navigation; API authentication and authorization enforce access.

See the [architecture proposal](docs/ARCHITECTURE_PROPOSAL.md) and [backend documentation](services/api/README.md) for implementation details and constraints.

## Run Locally

Prerequisites: Node.js 22.12+ with npm, Python 3.10+, and uv. Run these commands from a local clone; do not commit credentials.

Backend, starting from the repository root:

```bash
cd services/api
uv sync
cp -n .env.example .env
```

Before starting, configure `SECRET_KEY` and first-run `AUTH_INITIAL_EMAIL` / `AUTH_INITIAL_PASSWORD` locally, following the [API configuration guide](services/api/README.md#configuration). Set `DATABASE_URL` for Supabase; without it, inventory uses the development-only SQLite fallback. Keep TinyDB-backed domains on a single API worker.

```bash
uv run uvicorn main:app --reload --port 8000
```

In a second terminal at the repository root:

```bash
npm install
npm run dev:backoffice
```

In a third terminal at the repository root:

```bash
npm run dev
```

Default local URLs: website `http://localhost:5173`, backoffice `http://localhost:5174`, API documentation `http://localhost:8000/docs`. Proxy configuration and end-to-end prerequisites are explained in the [backoffice guide](uis/backoffice/README.md).

## Validation and Reproducibility

Available checks from the repository root:

```bash
npm run typecheck
npm run typecheck:backoffice
npm run test:shared
npm run test:backoffice
```

For backend tests, run `uv run pytest` from the API directory. This README lists available checks, not a claim that every suite currently passes. Setup, fixtures, coverage scope, and end-to-end requirements are documented in [TESTING.md](TESTING.md) and the [testing plan](docs/testing-plan.md). Telemetry schema validation is documented in its [README](docs/telemetry/README.md).

## Scope and Next Steps

Implemented: public website, authenticated backoffice, API domains, relational inventory, shared incident rules, and test suites. Documented: performance evidence and telemetry design. Pending: telemetry instrumentation and storage, production hardening, and future AI integrations. The current talent form only confirms locally; it does not persist applications to the API. Do not infer deployed RAG, agents, or automated workflows from template directories.

## Explore the Work

- [Business briefing](nexova-BRIEFING.es.md) and [architecture](docs/ARCHITECTURE_PROPOSAL.md).
- [Learning journal](aprendiendo%20con%20la%20ia.md): decisions, mistakes, solutions, and the role of AI assistance.
- [Authentication case study](aprendiendo%20con%20la%20ia%20-%20AUTH-02.md) and [performance case study](aprendiendo%20con%20la%20ia%20-%20PERF-AUDIT.md).
- [Public website source](uis/website/) and [backoffice source](uis/backoffice/).

## Credits

Developed as part of the 4Geeks Academy AI Engineering programme, from its company-project template. Original template attribution and historical guidance are preserved below. The learning journal documents implementation decisions, verification, and AI-assisted work.

<details>
<summary>Historical Course Template and Earlier Milestone Notes</summary>

The following material is preserved for provenance. Its template-only status statements and earlier milestone snapshots do not describe the current project.

# Nexova — AI Engineering Company Project

## Current Project: Inventory Telemetry Design

Nexova's monorepo contains the public website (`uis/website`), internal backoffice (`uis/backoffice`), centralized FastAPI API (`services/api`), shared packages, scripts, and cross-cutting documentation. The inventory API already derives stock from inbound/outbound orders; this milestone designs telemetry for training materials, certifications, and onboarding equipment without changing the running applications.

Start with the [telemetry project README](docs/telemetry/README.md), the [telemetry plan](docs/telemetry/telemetry-plan.md), and the [event schemas and examples](docs/telemetry/event-schemas.json). Requirements come from the [Nexova briefing](nexova-BRIEFING.es.md). Decisions, findings, and verification are recorded in the [learning journal](aprendiendo%20con%20la%20ia.md#telemetria-plan-de-diseno).

The expanded management RFI covers 40 event types: five explicitly classified as mandatory and 35 identified opportunities across inventory, authentication, navigation, flow abandonment, suppliers, incidents, website interactions, technical health, and internal processes. Phase 1 maps the complete inventory workflow with 12 instrumentation points, including rejected direct stock edits, failed validations, and minimum-stock crossings. The plan assigns hypotheses, decisions, owners, priorities, and batch/stream processing; it also covers section loading and client-side validation failures. Schema 2.0.0 adopts the requested session/correlation envelope and includes eight examples.

This milestone delivers design documentation only. No new server, collector, database, or dashboard has been deployed. No PR has been created or merged. The original template guide and previous milestones remain below as historical/reference material; its template-only status does not describe the current implemented applications.

[![4Geeks Academy](https://img.shields.io/badge/4Geeks-Academy-blue)](https://4geeksacademy.com)
[![AI Engineering](https://img.shields.io/badge/track-AI%20Engineering-green)](https://4geeksacademy.com/es/programas-de-carrera/ingenieria-ia)

_Base template for transversal projects in the AI Engineering Career Program — 4Geeks Academy._

_Estas instrucciones tambien estan disponibles en [espanol](./README.es.md)._

---

## 📦 Delivery: performance audit (Lighthouse)

Everything of the audit is in this repository, on `main`:

| What | Where |
|---|---|
| **Audit**: baseline scores, root cause of every problem, duplication cases, what the agent skills identify | [`AUDIT.md`](./AUDIT.md) |
| **Report**: every improvement, before/after scores, impact of each commit, INP, what had most impact | [`REPORT.md`](./REPORT.md) |
| **Lighthouse screenshots** | [`audit/before/`](./audit/before/) · [`audit/after/`](./audit/after/) |
| Raw evidence (Lighthouse JSON, per-commit results, INP, A/B runs) | [`docs/performance/`](./docs/performance/) |
| Study notes (how it was done, decisions, mistakes) | [`aprendiendo con la ia - PERF-AUDIT.md`](./aprendiendo%20con%20la%20ia%20-%20PERF-AUDIT.md) |

In one line: all four Lighthouse categories went to 100 on the website (mobile and desktop) and on the backoffice, the backoffice's layout shifts (CLS 0.255 and 0.351) were fixed (Performance 87 and 83 → 100), and every commit fixes one problem and was measured. How to reproduce it: [`REPORT.md` §8](./REPORT.md#8-cómo-reproducir).

---

## Purpose

This repository is the **starter template** for transversal projects. You will work on real company scenarios (Brasaland, TrackFlow, Nexova), building deliverables that map to course milestones (Web, Programming, Backend, Telemetry, RAG, Agents, Workflows, Real-time).

- Create a template from this repository.
- Replace the placeholder `CONTEXT.md` with your assigned company context.
- Use `skills/` and the directory-level `README.md` files as working guidance.

---

## How to start

1. **Use this repository as a template** and create your own project repo.
2. **Clone** your repository (or open it in Codespaces).
3. **Replace** `CONTEXT.md` with the full context for your assigned company.
4. **Read this folder guide** and open the `README.md` of the folder you are working in.
5. **Start implementing** in the right folder — do not dump everything in the root.
6. **Document** what you add: each new app, service, agent, or pipeline gets a subfolder + README.

---

## How to think about this monorepo

You are building **one company** across many milestones and projects. Each top-level folder has a **single responsibility** — like a real engineering team repo.

| Layer               | Folders                           | What lives here                                                  |
| ------------------- | --------------------------------- | ---------------------------------------------------------------- |
| **Company context** | `CONTEXT.md`                      | Domain facts, field names, constraints for your assigned company |
| **User-facing**     | `uis/`, `services/`               | Frontends and backends users (or operators) interact with        |
| **Data**            | `data/`                           | Raw files, pipelines, processed datasets, evaluation sets        |
| **AI**              | `agents/`, `skills/`, `mcps/`     | Agents, reusable agent capabilities, MCP tool servers            |
| **Automation**      | `workflows/`                      | n8n flows and cross-system orchestration                         |
| **Reuse**           | `packages/`, `shared/`            | Shared types, SDKs, schemas, templates                           |
| **Operations**      | `infra/`, `scripts/`, `internal/` | Docker, deploy configs, one-off scripts, internal CLIs           |
| **Documentation**   | `docs/`                           | Architecture, decisions, conventions for the whole repo          |

**Rule of thumb:** if it has a UI → `uis/`. If it exposes an API or runs in the background → `services/`. If it moves or transforms data → `data/`. If an AI model does the work → `agents/` (+ `skills/` or `mcps/` as needed).

---

## Current status of the template

> 💡 This repository currently provides a **base folder structure and documentation skeleton** only. It does not include runnable apps or global scripts yet.
>
> - `CONTEXT.md` is a placeholder and must be replaced with your assigned company context.
> - There is no root `AGENTS.md` yet.
> - Shared package metadata exists in `packages/shared/package.json` (`@repo/shared-types`), but no workspace runner is configured at root.

---

## Folder guide — what goes where

Read the linked `README.md` inside each folder before you start coding there.

### Root files

| Path                         | Purpose                                                                   | What you do here                                                                                              |
| ---------------------------- | ------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| [`CONTEXT.md`](./CONTEXT.md) | Single source of truth for your company (Brasaland, TrackFlow, or Nexova) | **First step:** copy your assigned company briefing here so every app, agent, and prompt uses the same domain |
| `docker-compose.yml`         | Local dev orchestration for the whole stack                               | Keep at repo root — wires `services/`, databases, and other containers from one place                         |
| `README.md` / `README.es.md` | This guide                                                                | Orientation — you are here                                                                                    |

### `uis/` — user interfaces

**Purpose:** All frontend applications — anything a human sees and clicks.

**Put here:**

- Public website (`website/`)
- Internal admin / backoffice (`backoffice/`)
- Customer portals, loyalty apps, Streamlit/Gradio tools, dashboards with a UI

**Examples:** corporate landing page, operations backoffice, loyalty portal, telemetry dashboard UI

→ See [`uis/README.md`](./uis/README.md)

### `services/` — centralized company API (FastAPI)

**Purpose:** One **centralized FastAPI backend** for the whole company — a single entry point that keeps complexity low as the project grows.

**Put here:**

- One main FastAPI app (e.g. `api/`) with routers/modules per domain (locations, menus, sales, telemetry, etc.)
- Background workers only when they truly need to run separately from the API

**Recommendation:** avoid splitting into many microservices early. Add endpoints to the same FastAPI app; extract a worker only when necessary.

**Examples:** `/locations`, `/menus`, `/sales/reports`, webhook handlers, scheduled jobs

→ See [`services/README.md`](./services/README.md)

### `data/` — datasets, pipelines, and evaluation

**Purpose:** Everything data-related, from raw files to production-ready tables.

| Subfolder                                       | Purpose                      | What you do here                                                          |
| ----------------------------------------------- | ---------------------------- | ------------------------------------------------------------------------- |
| [`data/raw/`](./data/raw/README.md)             | Untouched source data        | Store dumps, exports, sample CSVs/JSON — document origin and PII rules    |
| [`data/pipelines/`](./data/pipelines/README.md) | ETL/ELT jobs                 | Write ingestion, cleaning, and transformation scripts                     |
| [`data/process/`](./data/process/README.md)     | Clean / intermediate outputs | Save artifacts produced by pipelines (features, aggregates, clean tables) |
| [`data/eval/`](./data/eval/README.md)           | Quality measurement          | Golden sets, RAG/agent eval datasets, experiment metrics                  |

**Flow:** `raw` → `pipelines` → `process` → consumed by `services/`, `uis/`, or `agents/`. Use `eval` to prove quality.

### `agents/` — AI agents

**Purpose:** Autonomous or semi-autonomous AI assistants for the company.

**Put here:**

- One subfolder per agent (e.g. `support-agent/`, `onboarding-agent/`)
- Agent config, prompts, tools wiring, tests
- Start from [`agents/_template/`](./agents/_template/README.md) when creating a new agent

**Examples:** customer support bot, employee onboarding copilot, training assistant

→ See [`agents/README.md`](./agents/README.md)

### `skills/` — reusable agent capabilities

**Purpose:** Packaged instructions + scripts that agents (or you in Cursor) reuse across the repo.

**Put here:**

- Skills for data analysis, code review, scraping, research, etc.
- Each skill = a folder with `SKILL.md`, optional scripts and resources

**Example included:** `skills/data-analysis/` (pandas cleaning script + metrics reference)

→ See [`skills/README.md`](./skills/README.md)

### `mcps/` — Model Context Protocol servers

**Purpose:** Bridge AI models to your systems — databases, APIs, GitHub, custom tools.

**Put here:**

- One subfolder per MCP server (e.g. `database-mcp/`, `github-mcp/`)
- Tool definitions, resources, and server config

**When to use:** when an agent needs live access to data or actions your codebase alone cannot provide

→ See [`mcps/README.md`](./mcps/README.md)

### `workflows/` — automation and orchestration

**Purpose:** Connect systems without writing full apps — scheduled jobs, webhooks, notifications.

**Put here:**

- n8n workflow exports, Make/Zapier configs, or orchestration docs
- Flows that link `services/`, `data/pipelines/`, and `agents/`

**Examples:** new-order → Slack alert, nightly ETL trigger, lead → CRM sync

→ See [`workflows/README.md`](./workflows/README.md)

### `packages/` — shared libraries

**Purpose:** Versionable code reused by multiple apps, agents, or pipelines.

**Put here:**

- Shared TypeScript types (`packages/shared/` → `@repo/shared-types`)
- UI component libraries, API clients, analytics SDKs

**Rule:** if `uis/` and `services/` both need the same interface → extract it here

→ See [`packages/README.md`](./packages/README.md)

### `shared/` — loose shared assets

**Purpose:** Resources that are not a full package — schemas, templates, static assets, short docs.

**Put here:**

- JSON schemas, email templates, OpenAPI specs, design tokens
- Anything reused but too small or non-code for `packages/`

→ See [`shared/README.md`](./shared/README.md)

### `docs/` — cross-cutting documentation

**Purpose:** Architecture and decisions that span the whole company project.

**Put here:**

- System architecture diagrams, ADRs, security/observability guides
- Conventions not tied to one app or agent

→ See [`docs/README.md`](./docs/README.md)

### `infra/` — infrastructure and deployment

**Purpose:** How the company project runs in Docker, cloud, or CI.

**Put here:**

- Dockerfiles, Terraform, K8s manifests, Nginx configs, CI/CD pipelines

**Keep at repo root:** `docker-compose.yml` — orchestrates local dev for `services/`, databases, and other containers from one place.

→ See [`infra/README.md`](./infra/README.md)

### `scripts/` — helper scripts

**Purpose:** Small, repeatable automation — not full apps.

**Put here:**

- Setup scripts, seed data generators, lint wrappers, one-off migrations
- Document each script: what it does, args, and how to run it

**Difference from `internal/`:** scripts are usually single files; `internal/` tools are structured projects with their own deps and tests.

→ See [`scripts/README.md`](./scripts/README.md)

### `internal/` — internal developer tools

**Purpose:** Robust utilities for the engineering team.

**Put here:**

- CLIs, packaged migration tools, prompt evaluators
- Tools with their own `package.json`, tests, and install steps

→ See [`internal/README.md`](./internal/README.md)

---

## Where should I put this?

Quick decision guide:

```text
Does it have buttons and screens?          → uis/
Does it run on a server / API / queue?     → services/
Is it raw or transformed data?             → data/raw/ or data/process/
Does it move data between systems?         → data/pipelines/
Do you measure AI/pipeline quality?        → data/eval/
Is it an AI assistant with a goal?         → agents/
Is it a reusable AI capability/instruction?→ skills/
Does AI need to call external tools/APIs?  → mcps/
Is it n8n / scheduled automation?          → workflows/
Will 2+ folders import the same code?      → packages/
Is it a schema/template/asset, not a lib?  → shared/
Is it architecture or team-wide docs?      → docs/
Is it docker-compose for local dev?        → repo root
Is it Docker / deploy / cloud config?      → infra/
Is it a one-off script?                    → scripts/
Is it a CLI tool with its own package?     → internal/
```

---

## Repository structure (tree)

```text
ai-engineering-company-project-monorepo/
├── README.md / README.es.md   # This guide
├── CONTEXT.md                 # ← Replace with your company briefing
├── docker-compose.yml         # ← Local dev orchestration (repo root)
├── uis/                       # Frontends (website, backoffice, dashboards)
├── services/                  # Centralized FastAPI company API
├── data/
│   ├── raw/                   # Source datasets
│   ├── pipelines/             # ETL/ELT jobs
│   ├── process/               # Clean / intermediate outputs
│   └── eval/                  # Evaluation sets and metrics
├── agents/                    # AI agents (+ _template/ starter)
├── skills/                    # Reusable agent skills
├── mcps/                      # MCP servers for tool access
├── workflows/                 # n8n and automation flows
├── packages/                  # Shared libraries (@repo/shared-types, …)
├── shared/                    # Schemas, templates, loose assets
├── docs/                      # Architecture and cross-cutting docs
├── infra/                     # Docker, Terraform, deployment
├── scripts/                   # Helper scripts
└── internal/                  # Internal CLIs and dev tools
```

---

## Links

- [4Geeks Academy — AI Engineering](https://4geeksacademy.com/es/programas-de-carrera/ingenieria-ia)
- [How to start a coding project](https://4geeks.com/lesson/how-to-start-a-project)

---

## Contributors

This template was built as part of the 4Geeks Academy AI Engineering Career Program by [@marcogonzalo](https://www.linkedin.com/in/marcogonzalo) and [@alezanchezr](https://x.com/alesanchezr) and many other contributors. Find out more about our [AI Engineering Course](https://4geeksacademy.com/en/career-programs/ai-engineering), and [other courses](https://4geeksacademy.com/en/program-comparison).

You can find other templates and resources like this at the [4Geeks Academy GitHub page](https://github.com/4geeksacademy).

_This template is maintained by 4Geeks Academy for the AI Engineering track. For exclusive use in the programme._

</details>
