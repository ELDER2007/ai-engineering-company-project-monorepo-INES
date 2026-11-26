---
id: pre-commit-checklist
description: Checklist a solicitar por el agente justo antes de ejecutar o proponer un git commit.
scope: agent-requested
---

# Checklist antes de commitear

**Alcance: solicitada por el agente** — no se carga automáticamente en cada sesión ni está atada a un patrón de archivo; el agente debe reconocer, por su propia iniciativa, que está a punto de commitear (o que el desarrollador lo pidió) y traer esta regla en ese momento. Es el mismo flujo de 5 pasos definido en `AGENTS.md` bajo "Flujo obligatorio antes de cada commit" — este archivo existe para que un agente pueda pedirlo puntualmente sin tener todo `AGENTS.md` repetido en cada sesión.

## La regla

Antes de correr `git commit`:

1. Compara el diff (`git diff`) contra `CONTEXT.md` y `memory-bank/projectbrief.md` — nada debe contradecir el dominio, el copy o las validaciones requeridas.
2. Ejecuta lint/typecheck/tests de lo que tocaste; si no existen todavía para esa área, dilo explícitamente en vez de omitir el paso en silencio.
3. Actualiza `memory-bank/progress.md` (y `memory-bank/techContext.md` si cambiaste stack/arquitectura/restricciones).
4. Si tocaste `README.md`, `AGENTS.md` o un README de carpeta, replica el cambio en su hermano `*.es.md`. Verifica la sincronización con la skill [`bilingual-docs-sync`](../../skills/bilingual-docs-sync/SKILL.md): `python3 skills/bilingual-docs-sync/scripts/check_bilingual_sync.py . --files $(git diff --name-only --cached)`.
5. Verifica que no tocaste ninguna ruta de la lista "requieren confirmación explícita" de `AGENTS.md` sin ese visto bueno; solo entonces haz `git add` + commit con un mensaje que explique qué cambió y por qué.

## Por qué

Commitear sin este paso previo deja el banco de memoria desactualizado (rompe el propósito de `memory-bank/`), puede colar una discrepancia con `CONTEXT.md`, o tocar una ruta sensible sin aprobación.

## Cómo aplicarla

En cuanto detectes que el siguiente paso lógico de la tarea es un commit (el desarrollador lo pide, o el trabajo de la tarea actual está terminado), recorre los 5 puntos en orden antes de proponerlo o ejecutarlo.
