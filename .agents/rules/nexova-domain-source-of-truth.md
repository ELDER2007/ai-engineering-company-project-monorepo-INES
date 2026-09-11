---
id: nexova-domain-source-of-truth
description: CONTEXT.md es la única fuente de verdad del dominio de Nexova; nada generado puede contradecirlo.
scope: always
---

# CONTEXT.md manda sobre el dominio

**Alcance: siempre activa** — aplica en cualquier sesión, sin importar el archivo que se esté tocando, porque una violación de esta regla produce contenido incorrecto sobre el negocio en cualquier capa (UI, backend, agentes, datos de ejemplo).

## La regla

Todo lo que se genere para este repo — copy de landing page, campos y mensajes de error de formularios, prompts de agentes, datos de ejemplo, modelos de dominio — debe ser consistente con `CONTEXT.md` en:

- **Nombres de campos y tipos** (p. ej. el formulario de registro de talento tiene exactamente 11 campos definidos, con sus tipos y obligatoriedad).
- **Mensajes de error literales** — no parafrasear ni "mejorar" el texto que `CONTEXT.md` especifica; se usa tal cual.
- **Copy de negocio** (titulares, subtítulos, textos de sección) cuando `CONTEXT.md` los define de forma explícita.
- **Datos de la empresa**: dos sedes (Valencia, ES y Miami, FL), líneas de negocio, marcado Schema.org `Organization`.
- **La restricción de audiencia del formulario de talento**: es para profesionales que buscan empleo, no para empresas que buscan contratar servicios de Nexova.

Si una tarea pide algo que no está cubierto en `CONTEXT.md` (p. ej. copy nuevo no especificado), se puede generar contenido razonable, pero debe declararse explícitamente como una decisión de diseño no dictada por el brief — nunca presentarlo como si viniera del cliente.

## Por qué

`CONTEXT.md` es el brief real de un stakeholder (Carmen Ruiz). Un agente que "arregla" o reinterpreta esos datos produce un entregable que no sirve para el hito, aunque el código funcione perfectamente.

## Cómo aplicarla

Antes de escribir o revisar cualquier texto/campo visible para el usuario final, compáralo línea por línea contra la sección correspondiente de `CONTEXT.md`. Si hay una discrepancia entre esta regla y una instrucción puntual del desarrollador, pregunta antes de proceder — no asumas que el desarrollador quiere contradecir el brief.
