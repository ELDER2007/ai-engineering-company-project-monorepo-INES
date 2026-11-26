# AGENTS.md

Instructions for any AI coding agent (Claude Code, Cursor, Copilot, etc.) working in this repository. Read this file first — it gives full-repository context so the agent doesn't need to rediscover structure and conventions on every task.

_Versión en español: [AGENTS.es.md](./AGENTS.es.md)._

---

## What this repo is

A student monorepo template for 4Geeks Academy's AI Engineering career track. One student builds **one fictional company** across many course milestones (Website, Programming, Backend, Telemetry, RAG, Agents, Workflows, Real-time). Every folder maps to a layer of a real engineering team, not to a milestone number — a given milestone's work usually lands across several folders at once.

## Source of truth: `CONTEXT.md`

**Read [`CONTEXT.md`](./CONTEXT.md) before writing or changing anything.** It holds the assigned company's domain data, field names, and constraints. For this repo the company is **Nexova** — a Spain/Miami HR consultancy and talent-acquisition firm (executive headhunting, customer-support outsourcing, corporate training). Milestone-specific requirements (form fields, validation messages, copy, Schema.org markup, etc.) live there — don't invent domain rules that contradict it. `company-choice.md` records the student's own rationale for choosing Nexova and two focus departments (Selection Operations, Customer Support); treat it as background intent, not a spec.

Everything generated (UI copy, form fields, agent prompts, sample data) must stay consistent with `CONTEXT.md`'s domain: field names, validation rules, error messages, and the two office locations (Valencia, ES and Miami, FL).

## Repository map

| Folder | What lives here | Notes |
| --- | --- | --- |
| `CONTEXT.md` | Nexova's business briefing — single source of domain truth | Read first |
| `memory-bank/` | Working memory for any agent: `projectbrief.md`, `techContext.md`, `progress.md` | Read at the start of every session (see below); update `progress.md`/`techContext.md` before each commit |
| `.agents/rules/` | Scoped development rules (`always` / `glob` / `agent-requested`) | See [`.agents/README.md`](./.agents/README.md); load `always` rules every session, `glob` rules per matching file, `agent-requested` rules on demand |
| `uis/` | Frontend apps a human clicks through (website, backoffice, dashboards) | `uis/website/` (Hito 1 landing) and `uis/backoffice/` (dashboard shell) scaffolded — see `memory-bank/progress.md` |
| `services/` | One centralized FastAPI backend for the whole company, routers per domain | `services/api/` skeleton exists (health check only); prefer adding routers here over new microservices |
| `data/raw/`, `data/pipelines/`, `data/process/`, `data/eval/` | Source data → ETL scripts → cleaned outputs → quality/eval sets | Flow: raw → pipelines → process → consumed by services/uis/agents |
| `agents/` | AI agent subfolders (config, prompts, tools, tests); start from `agents/_template/` | Template includes `agent.py` + tests scaffold |
| `skills/` | Reusable packaged capabilities (`SKILL.md` + scripts) agents/humans reuse repo-wide | e.g. `skills/data-analysis/` |
| `mcps/` | MCP servers giving agents live access to systems (DB, APIs, GitHub) | Use when static code isn't enough |
| `workflows/` | n8n exports / Make/Zapier configs / cross-system orchestration | Links services + pipelines + agents |
| `packages/` | Versioned code shared by multiple apps (`packages/shared` → `@repo/shared-types`) | No root workspace runner yet |
| `shared/` | Non-package shared resources: JSON schemas, email templates, OpenAPI specs, design tokens | Too small/non-code for `packages/` |
| `docs/` | Cross-cutting architecture docs and ADRs | Not tied to one app/agent |
| `infra/` | Dockerfiles, Terraform, K8s manifests, CI/CD | `docker-compose.yml` itself belongs at repo root (not yet added) |
| `scripts/` | One-off, loose automation scripts (setup, seed data, lint wrappers) | Document each script's purpose/args |
| `internal/` | Structured internal dev tools/CLIs with their own deps + tests | Heavier than `scripts/` |
| `src/` | Nexova domain logic already implemented in TypeScript: candidate/vacancy validations, transformations, search, collections, and shared models | Not yet listed in the top-level README — treat as the current Programming-milestone code and keep new domain logic (candidate scoring, vacancy filters, etc.) consistent with `src/types/models.ts` |

### Where do I put this?

```
Has screens/buttons?                 → uis/
Runs as a server/API/queue?          → services/
Raw or transformed data?             → data/raw/ or data/process/
Moves data between systems?          → data/pipelines/
Measures AI/pipeline quality?        → data/eval/
An AI assistant with a goal?         → agents/
A reusable instruction/capability?   → skills/
AI needs to call external tools/APIs?→ mcps/
Scheduled/n8n-style automation?      → workflows/
Code imported by 2+ folders?         → packages/
Schema/template/asset, not a lib?    → shared/
Team-wide architecture/docs?         → docs/
Docker/deploy/cloud config?          → infra/
A one-off script?                    → scripts/
A CLI with its own package?          → internal/
```

## Conventions

- **Bilingual docs**: primary docs are English (`README.md`, `CONTEXT.md`, this file); a `*.es.md` sibling carries the Spanish translation. Keep both in sync when editing either.
- **No root workspace runner yet**: only `packages/shared/package.json` exists. Don't assume a root `package.json`, lockfile, or `docker-compose.yml` — check before referencing them, and if you add one, wire it up rather than assuming it's already there.
- **Don't dump work in the repo root.** Every new app/service/agent/pipeline gets its own subfolder plus a README, following the pattern already used by every top-level folder (`README.md` + `README.es.md`).
- **FastAPI backend stays centralized**: add routers/modules to one `services/` app rather than spinning up new microservices, unless a worker genuinely needs to run separately.
- **UI styling**: when `CONTEXT.md` specifies a framework (currently Tailwind for the website + talent-registration form), use it rather than introducing a second styling approach.

## Memory bank — read at the start of every session

Before touching any file, read the three [`memory-bank/`](./memory-bank/) docs, in this order:

1. [`memory-bank/projectbrief.md`](./memory-bank/projectbrief.md) — the business, the project's goals, and the problem being solved.
2. [`memory-bank/techContext.md`](./memory-bank/techContext.md) — the tech stack, architecture decisions already made, and technical constraints.
3. [`memory-bank/progress.md`](./memory-bank/progress.md) — current development status and the planned next steps.

This is the project's working memory: it persists across sessions even when conversation context doesn't. If something in these files contradicts what you actually find in the code, trust the code, flag the mismatch to the developer, and correct the stale doc as part of the commit flow below — don't silently keep working from an outdated memory bank.

Alongside the memory bank, [`.agents/rules/`](./.agents/README.md) holds smaller, individually-scoped development rules. Load every `scope: always` rule at session start too; load a `scope: glob` rule when you touch a matching file; fetch a `scope: agent-requested` rule when its description matches what you're about to do (e.g. the pre-commit checklist below).

## Mandatory flow before every commit

Never treat `git commit` as a bare last step — go through this sequence first, in order:

1. **Re-check against the source of truth.** Diff your changes (`git diff`) against `CONTEXT.md` and `memory-bank/projectbrief.md`; confirm nothing contradicts the assigned domain, required copy, field names, or validation rules.
2. **Run the relevant checks for what you touched.** Lint/typecheck/tests for that area of the repo (e.g. a TypeScript check for `src/`, the test suite for a `services/` change). If no automated check exists yet for that area, say so explicitly in your summary instead of skipping the step silently.
3. **Update the memory bank.** Reflect the change in `memory-bank/progress.md` (mark items done, move the next-steps list forward), and also update `memory-bank/techContext.md` if the change affects the stack, an architecture decision, or a constraint.
4. **Keep bilingual docs in sync.** If you edited `README.md`, `AGENTS.md`, or any folder `README.md`, mirror the same change in its `*.es.md` sibling in the same commit.
5. **Confirm no restricted path (below) was touched without explicit developer sign-off**, then stage and commit with a message describing what changed and why.

## Paths that require explicit developer confirmation before modifying

Don't create, edit, or delete any of these on your own initiative — propose the change and get an explicit yes first, even if a task seems to imply it:

- `CONTEXT.md` / `CONTEXT.es.md` — the business source of truth; only the developer redefines the assigned company's domain.
- `company-choice.md` — the student's own record of their company/department choice; a personal statement, not a spec to edit.
- `infra/`, `docker-compose.yml` (once it exists), and any CI/CD configuration — deployment/infra changes have a blast radius beyond a single task.
- Any secrets or credentials file (`.env*`, API keys, tokens) — never create, edit, or commit one.
- Root-level tooling once it exists (`package.json`, `tsconfig.json`, lockfiles) — propose dependency or script changes before applying them.
- Published shared contracts already consumed elsewhere (`packages/shared/types/index.ts` and anything else under `packages/`) — breaking changes there ripple across every consumer.
- `.git/` internals, git hooks, and any `.gitignore` change that would stop tracking files already committed.

When in doubt about whether a path counts as "restricted," ask rather than assume.

## Before you start a task

1. Complete the memory-bank read above if you haven't already this session.
2. Re-read `CONTEXT.md` for the domain rules relevant to your task.
3. Open the `README.md` of the specific folder you're about to touch — each one has folder-specific guidance beyond what's summarized here.
4. Place new work in the correct folder per the map above; add a subfolder README if you're introducing a new app/agent/pipeline/service.
