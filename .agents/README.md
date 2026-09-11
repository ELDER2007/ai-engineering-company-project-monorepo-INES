# `.agents/` — scoped development rules

Granular, machine-readable development rules for AI coding agents (Claude Code, Cursor, Copilot, etc.), as a complement to [`AGENTS.md`](../AGENTS.md). `AGENTS.md` is the onboarding doc read once at the start of a session; the rules here are smaller, individually-scoped units an agent applies (or fetches) depending on what it's about to do.

_Versión en español: [README.es.md](./README.es.md)._

## Layout

```
.agents/
└── rules/
    ├── nexova-domain-source-of-truth.md
    ├── frontend-tailwind-styling.md
    └── pre-commit-checklist.md
```

Each file in `rules/` is one rule: a short frontmatter header plus the rule body in plain language.

## Rule scope — pick exactly one

Every rule declares a `scope` in its frontmatter. This decides *when* the rule enters an agent's context:

| `scope` | Meaning | When to use it |
| --- | --- | --- |
| `always` | Loaded in every session, regardless of what file is being touched. | Business/domain constraints, repo-wide conventions — cheap to keep in context and costly to violate by accident. |
| `glob` | Loaded only when working on a file matching one of the rule's `globs` patterns. | Rules specific to a stack/folder (e.g. frontend styling rules that only matter inside `uis/`). |
| `agent-requested` | Not loaded automatically; the agent must decide, from the rule's `description`, that it's relevant and fetch it on demand. | Rules tied to an action rather than a file (e.g. "what to do before committing") — noisy if always-on, useless if tied to a glob. |

### Frontmatter schema

```yaml
---
id: kebab-case-unique-id
description: One sentence — what the rule enforces and, for agent-requested rules, when to pull it in.
scope: always | glob | agent-requested
globs: ["uis/**/*.{html,tsx,jsx}"]   # required only when scope: glob
---
```

- `id` and `description` are required for every rule.
- `globs` is required (and only meaningful) when `scope: glob`; omit it otherwise.
- Keep one rule per concern — prefer adding a new file over growing an existing rule into an unrelated topic.

## How an agent should use this folder

1. At the start of a session, load every rule with `scope: always` alongside the `memory-bank/` read described in `AGENTS.md`.
2. When about to create or edit a file, check `rules/` for any `scope: glob` rule whose pattern matches that file, and load it.
3. Before performing an action a rule's `description` clearly maps to (e.g. committing, adding a dependency), scan the `agent-requested` rules' descriptions and load the matching one.
4. When adding a new constraint that should survive across sessions, add a new file here instead of only stating it inline in a reply — pick the narrowest scope that still guarantees the rule gets seen when it matters.
