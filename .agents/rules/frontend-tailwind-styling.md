---
id: frontend-tailwind-styling
description: El código frontend de uis/ se estiliza solo con Tailwind y debe cumplir un mínimo de responsive/accesibilidad.
scope: glob
globs: ["uis/**/*.html", "uis/**/*.css", "uis/**/*.tsx", "uis/**/*.jsx", "uis/**/*.ts", "uis/**/*.js"]
---

# Estilo frontend: solo Tailwind, responsive y accesible

**Alcance: por patrón de archivo** — se carga solo al crear o editar archivos dentro de `uis/` (HTML/CSS/JS/TS/JSX/TSX). No aplica a `services/`, `agents/`, `data/`, etc.

## La regla

1. **Un único sistema de estilos**: usa Tailwind CSS para todo el styling nuevo dentro de `uis/`, tal como pide `CONTEXT.md` para el sitio web y el formulario de registro de talento. No mezcles otro framework de CSS (Bootstrap, Bulma, CSS-in-JS ad hoc) en la misma app sin que el desarrollador lo apruebe explícitamente.
2. **Responsive de verdad**: cualquier vista nueva debe verse correctamente al menos en móvil (~375px) y escritorio — usa las utilidades responsive de Tailwind (`sm:`, `md:`, `lg:`), no solo un diseño fijo de escritorio.
3. **Accesibilidad mínima**: etiquetas `<label>` asociadas a cada campo de formulario, texto alternativo en imágenes, contraste de color suficiente, orden de foco lógico y elementos semánticos (`<nav>`, `<main>`, `<footer>`, encabezados en orden) en vez de `<div>` genéricos para todo.
4. **Validaciones de formulario reales**: cuando el archivo implemente el formulario de registro de talento, las validaciones deben ejecutarse de verdad (JS), no depender solo de atributos HTML (`required`, `type=email`) — ver los mensajes de error exactos en `CONTEXT.md`.

## Por qué

El stakeholder pidió Tailwind explícitamente y el sitio debe ser responsive/accesible/SEO-friendly; introducir un segundo enfoque de estilos o saltarse la accesibilidad genera deuda técnica y no cumple el hito.

## Cómo aplicarla

Antes de dar por terminado un archivo dentro de `uis/`, revisa: (a) que no haya CSS fuera de clases Tailwind salvo un mínimo justificado (p. ej. una animación puntual), (b) que la vista se probó mentalmente o visualmente en ancho móvil, y (c) que cada input tenga su label y mensaje de error asociado.
