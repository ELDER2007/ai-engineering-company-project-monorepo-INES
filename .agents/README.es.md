# `.agents/` — reglas de desarrollo con alcance definido

Reglas de desarrollo granulares y legibles por agentes de IA (Claude Code, Cursor, Copilot, etc.), como complemento a [`AGENTS.md`](../AGENTS.md). `AGENTS.md` es el documento de onboarding que se lee una vez al inicio de sesión; las reglas de aquí son unidades más pequeñas y con alcance individual que un agente aplica (o solicita) según lo que esté a punto de hacer.

_These instructions are also available in [English](./README.md)._

## Estructura

```
.agents/
└── rules/
    ├── nexova-domain-source-of-truth.md
    ├── frontend-tailwind-styling.md
    └── pre-commit-checklist.md
```

Cada archivo dentro de `rules/` es una regla: una cabecera frontmatter breve más el cuerpo de la regla en lenguaje natural.

## Alcance de la regla — elige exactamente uno

Cada regla declara un `scope` en su frontmatter. Esto decide *cuándo* entra la regla al contexto de un agente:

| `scope` | Significado | Cuándo usarlo |
| --- | --- | --- |
| `always` (siempre activa) | Se carga en cada sesión, sin importar qué archivo se esté tocando. | Restricciones de negocio/dominio, convenciones de todo el repo — baratas de mantener en contexto y costosas de violar por accidente. |
| `glob` (por patrón de archivo) | Se carga solo cuando se trabaja en un archivo que coincide con alguno de los patrones `globs` de la regla. | Reglas específicas de un stack/carpeta (p. ej. reglas de estilo frontend que solo importan dentro de `uis/`). |
| `agent-requested` (solicitada por el agente) | No se carga automáticamente; el agente debe decidir, a partir de la `description` de la regla, que es relevante y pedirla explícitamente. | Reglas ligadas a una acción más que a un archivo (p. ej. "qué hacer antes de commitear") — ruidosas si siempre están activas, inútiles si se atan a un glob. |

### Esquema del frontmatter

```yaml
---
id: identificador-unico-en-kebab-case
description: Una frase — qué exige la regla y, para reglas agent-requested, cuándo hay que traerla.
scope: always | glob | agent-requested
globs: ["uis/**/*.{html,tsx,jsx}"]   # obligatorio solo cuando scope: glob
---
```

- `id` y `description` son obligatorios en toda regla.
- `globs` es obligatorio (y solo tiene sentido) cuando `scope: glob`; omítelo en los demás casos.
- Mantén una regla por tema — prefiere añadir un archivo nuevo antes que hacer crecer una regla existente hacia un tema no relacionado.

## Cómo debe usar esta carpeta un agente

1. Al inicio de sesión, carga toda regla con `scope: always` junto con la lectura de `memory-bank/` descrita en `AGENTS.md`.
2. Antes de crear o editar un archivo, revisa `rules/` en busca de alguna regla `scope: glob` cuyo patrón coincida con ese archivo, y cárgala.
3. Antes de realizar una acción a la que la `description` de una regla claramente corresponda (p. ej. commitear, añadir una dependencia), revisa las descripciones de las reglas `agent-requested` y carga la que aplique.
4. Al añadir una restricción nueva que deba sobrevivir entre sesiones, crea un archivo nuevo aquí en vez de solo mencionarla en una respuesta — elige el alcance más estrecho que aun así garantice que la regla se vea cuando importa.
