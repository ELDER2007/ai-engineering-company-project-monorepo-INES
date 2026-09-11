---
name: bilingual-docs-sync
description: Verifica que cada documento bilingüe (X.md / X.es.md) del repo mantenga la misma estructura de encabezados, para detectar traducciones desincronizadas antes de commitear.
---

# bilingual-docs-sync

_Versión en español de este SKILL — el repo es bilingüe pero esta skill nació de una convención documentada en español (`AGENTS.es.md`), así que se documenta en español; adapta si tu equipo prefiere inglés._

## Tarea recurrente que resuelve

Este repo sigue la convención de docs bilingües descrita en [`AGENTS.md`](../../AGENTS.md) / [`AGENTS.es.md`](../../AGENTS.es.md): todo doc principal (`README.md`, `AGENTS.md`, cada `README.md` de carpeta) tiene un hermano `*.es.md`, y el **paso 4 del flujo obligatorio antes de cada commit** exige mantenerlos sincronizados. Comparar dos documentos a mano cada vez que se edita uno es exactamente el tipo de tarea repetitiva, mecánica y fácil de olvidar que debe automatizarse — de ahí esta skill.

## Objetivo único

**Detectar automáticamente cuándo un par `X.md` / `X.es.md` se desincronizó estructuralmente** (se añadió, quitó o cambió de nivel un encabezado en un idioma sin reflejarlo en el otro), para que un commit nunca deje una traducción a medias sin que quede evidencia explícita de ello.

Esta skill **no** traduce contenido ni juzga la calidad de la traducción — solo la estructura (cantidad y nivel de encabezados Markdown, en el mismo orden). Es una skill de verificación, no de generación.

## Cuándo usarla

- Como parte del paso 4 del checklist de pre-commit (`AGENTS.md` / [`.agents/rules/pre-commit-checklist.md`](../../.agents/rules/pre-commit-checklist.md)), cada vez que un commit toque `README.md`, `AGENTS.md`, o cualquier `README.md` de una subcarpeta.
- Bajo demanda, para auditar todo el repo de una vez (por ejemplo, después de una sesión larga de edición de documentación).

## Inputs documentados

| Input | Obligatorio | Descripción |
| --- | --- | --- |
| `repo_root` (primer argumento posicional) | No — por defecto el directorio actual | Carpeta desde la que se buscan recursivamente los pares `*.es.md` / `*.md`. |
| `--files <ruta> [<ruta> ...]` | No | Lista de rutas (p. ej. la salida de `git diff --name-only --cached`) para acotar el chequeo solo a los pares que tocan alguno de esos archivos, en vez de escanear todo el repo. |

No requiere variables de entorno, credenciales, ni dependencias de terceros — solo la librería estándar de Python 3.9+.

**Convención asumida** (heredada de `AGENTS.md`): el doc en inglés es `X.md` y su hermano en español es `X.es.md`, en la misma carpeta.

## Cómo ejecutarla

```bash
# Auditar todo el repo
python3 skills/bilingual-docs-sync/scripts/check_bilingual_sync.py

# Acotar a lo que cambió en este commit
python3 skills/bilingual-docs-sync/scripts/check_bilingual_sync.py . \
  --files $(git diff --name-only --cached)
```

## Output

Una línea por par evaluado:

- `OK    <en> <-> <es>` — estructura de encabezados idéntica.
- `FAIL  <en> <-> <es>` seguido de una o más líneas `- ...` describiendo cada discrepancia concreta (encabezado, nivel, archivo).
- `SKIP  <en> <-> <es>  (known exception, ...)` — par declarado explícitamente como excepción (ver `KNOWN_EXCEPTIONS` en el script; hoy solo `CONTEXT.md`, porque `CONTEXT.es.md` es un placeholder que apunta a otros briefings, no una traducción).

## Criterios de aceptación (explícitos y verificables)

1. **Sin dependencias externas**: `python3 scripts/check_bilingual_sync.py` corre con Python estándar, sin `pip install` previo.
2. **Determinismo**: ejecutarlo dos veces seguidas sobre el mismo estado del repo produce exactamente el mismo output y el mismo código de salida.
3. **Código de salida como gate**: termina con `0` si todos los pares evaluados coinciden en estructura (o están en `KNOWN_EXCEPTIONS`); termina con `1` si al menos uno falla — apto para usarse como paso de CI o hook de pre-commit sin parseo adicional del output.
4. **Detección real de discrepancias**: si un heading se agrega, se borra, o cambia de nivel (`##` → `###`) en un solo lado del par, el reporte debe listar explícitamente cuál encabezado y en qué archivo — verificado insertando un encabezado de más en un `.es.md` de prueba y confirmando que el script lo reporta con `FAIL` y sale con código `1` (ver historial de esta skill).
5. **Estado limpio del repo = éxito**: ejecutado contra el estado actual de este monorepo (todos los pares `*.md`/`*.es.md` existentes), el script debe terminar en código `0` con una línea `OK` (o `SKIP` para la excepción documentada) por cada par — sin ningún `FAIL`.
6. **Filtro `--files` funcional**: al pasar `--files AGENTS.md`, el script solo evalúa el par `AGENTS.md`/`AGENTS.es.md` e ignora el resto, terminando en `0` si ese par está sincronizado.

## Limitaciones conocidas (fuera de alcance a propósito)

- No verifica que el *contenido* de cada encabezado sea una traducción fiel — solo que la estructura (cantidad/nivel/orden) coincida.
- No revisa enlaces internos rotos ni bloques de código — si se necesita, es una skill aparte.
- `CONTEXT.md`/`CONTEXT.es.md` está en una lista de excepciones fija en el script (`KNOWN_EXCEPTIONS`); si en el futuro `CONTEXT.es.md` deja de ser un placeholder y pasa a ser la traducción real del briefing de Nexova, hay que quitarlo de esa lista.
