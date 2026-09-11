# Progress — Nexova

_Última actualización: 2026-09-11 (scaffolding + landing page de `uis/website/`; dashboard shell de `uis/backoffice/`; esqueleto de `services/api/`; fix de `validate-context-alignment` para apps multi-componente; entrega en `feature/agent-memory-bank`)._

## Qué existe hoy

### Documentación y contexto (completo)

- [x] `CONTEXT.md` reemplazado con el briefing real de Nexova (Hito 1: sitio web público).
- [x] `company-choice.md` con la elección de empresa y departamentos del estudiante.
- [x] `AGENTS.md` / `AGENTS.es.md` en la raíz — contexto de repo completo para agentes de código (creado 2026-09-11).
- [x] `README.md` / `README.es.md` actualizados para enlazar `AGENTS.md` y quitar notas obsoletas.
- [x] `memory-bank/` (esta carpeta) con `projectbrief.md`, `techContext.md` y `progress.md`.
- [x] Banco de memoria persistente del agente (fuera del repo) documentando la asignación de empresa, la creación de `AGENTS.md` y los huecos de tooling.

### Código

- [x] `src/` — lógica de dominio de Nexova ya implementada en TypeScript: modelos (`src/types/models.ts`) y utilidades de validación/transformación/colecciones/búsqueda para candidatos y vacantes (`src/utils/*.ts`).
- [x] `packages/shared/` — paquete `@repo/shared-types` con `types/index.ts` (metadata mínima, sin implementación propia todavía más allá del `package.json`).
- [x] **`uis/website/`** — scaffolding a partir de la estructura del template de 4Geeks [`react-hello-webapp`](https://github.com/4GeeksAcademy/react-hello-webapp) (Vite + React + React Router + patrón de estado global), con Tailwind CSS 4 en lugar de Bootstrap. `package.json`/`vite.config.js`/`eslint.cjs` propios (autocontenido, no en workspace de la raíz). `npm run build` y `npm run lint` pasan limpio; verificado corriendo `npm run dev` y capturando screenshots (desktop + mobile) con Playwright.
- [x] **Landing page** (ruta `/`) construida con componentes reutilizables (`Hero`, `Services`/`ServiceCard`, `WhyNexova`/`StatCard`, `Contact`, `Header`, `Footer`) con el contenido y orden exactos de `CONTEXT.md`: Header (logo + nav Inicio/Servicios/Talento/Contacto, con menú móvil) → Hero (titular, subtítulo, CTA) → Servicios (3 columnas) → "Por qué Nexova" (2 columnas, texto literal incluida la mención "mercado latinoamericano") → Contacto → Footer (copyright literal "© 2025" + LinkedIn/Instagram).
- [x] **Marcado Schema.org** tipo `Organization` — bloque JSON-LD exacto de `CONTEXT.md` embebido tal cual en `index.html`.
- [x] Paleta de marca (`brand-*`/`accent-*`) definida vía `@theme` en `src/index.css` — placeholder razonable (indigo + acento ámbar), reemplazable si Carmen Ruiz da guías de marca reales.
- [x] Ruta `/talento` creada como stub (enlazada desde el CTA del Hero y desde el nav) para que la navegación no quede rota — el formulario real es el punto 4 más abajo.
- [ ] **Nada de esto está aún conectado a backend**: no hay backend FastAPI, no hay `package.json`/`tsconfig`/`docker-compose.yml` en la raíz del monorepo (fuera de alcance de este paso).

### `uis/backoffice/` — fuera del alcance de Hito 1, adelantado por pedido explícito

- [x] Scaffolding con el mismo toolchain que `website` (Vite + React + React Router + Tailwind), autocontenido, puerto 3001. `npm run build`/`npm run lint` limpios, verificado con `npm run dev` + screenshot (desktop y mobile) por Playwright.
- [x] **Layout propio** (`src/pages/Layout.jsx` con `Sidebar` + `Topbar`), completamente separado del Layout de `website` (Header + Footer de marketing) — paleta Tailwind distinta (`ink-*` + acento esmeralda vs. `brand-*` + acento ámbar de website).
- [x] Ruta `/` con vista de entrada: mensaje de bienvenida + widget `CompanySnapshot` que muestra datos literales de `CONTEXT.md` (`src/data/company.js`: fundación, sedes, empleados, facturación, líneas de negocio, sectores de cliente) más lógica derivada real (`src/lib/companyStats.js`: años operando calculado desde `foundingYear`, formato de moneda) — visible en la interfaz, no en consola.
- [x] Sidebar con ítems deshabilitados ("Candidatos", "Vacantes", "Formación") marcados "Próx." para dejar visible la estructura futura del backoffice (ver `uis/README.md`) sin construirlos todavía.
- [ ] Todo lo demás (autenticación, CRUD de candidatos/vacantes, tickets, chatbot) sigue sin empezar — ver `company-choice.md` para la visión a mediano plazo.

### `services/api/` — esqueleto del backend centralizado (a pedido explícito, sigue fuera de Hito 1)

- [x] App FastAPI mínima (`app/main.py`) con `GET /` y `GET /health`, estructura `app/routers/` lista para routers de dominio (`candidates.py`, `vacancies.py`, `talent.py`, …) — sigue la convención ya documentada en `AGENTS.md`/`README.md` ("un backend centralizado, routers por dominio, no microservicios").
- [x] Verificado de verdad: entorno virtual, `pip install -r requirements.txt`, `uvicorn app.main:app` levantado y probado con `curl` (`/`, `/health`, `/openapi.json`) — no solo escrito, corrido.
- [x] Autocontenido (`requirements.txt` propio), sin tooling de Python compartido en la raíz — mismo patrón que `uis/website` y `uis/backoffice`.
- [ ] Ningún endpoint de dominio real todavía — nada en `uis/website`/`uis/backoffice` lo llama aún (el formulario de `/talento` sigue simulando el envío).

### `skills/validate-context-alignment/` — corregido para apps multi-componente (React SPA)

- [x] **Bug real encontrado y corregido**: la skill asumía un sitio de un solo archivo HTML estático; contra la SPA de React real de `uis/website` reportaba 51 falsos "faltantes" (Header, Hero, Servicios, etc. — todo ya construido). Causas: (1) texto partido por tags inline (`<strong>...</strong> resto`), (2) `&copy;` sin decodificar, (3) saltos de línea del código fuente que JSX colapsa al renderizar.
- [x] Fix sin nuevas dependencias (`html.unescape`, stdlib): nueva función `_prose_text` (quita tags, decodifica entidades, colapsa espacios) aplicada a todo excepto al bloque Schema.org; nuevo flag `--combine` para tratar varios archivos/directorios como una sola página.
- [x] Verificado que no rompió los criterios de aceptación existentes (`sample_pass.html`/`sample_fail.html` dan exactamente el mismo resultado) y que, corriendo `--combine uis/website/index.html uis/website/src`, ahora solo reporta como faltante lo que de verdad falta: el formulario de `/talento` (punto 4 de abajo) — nada más.
- [x] `SKILL.md` actualizado con el nuevo input, ejemplo de uso y 2 criterios de aceptación nuevos (8 y 9).

## Qué falta (Hito 1 — sitio web público)

1. ~~Elegir y montar el toolchain de `uis/website/`~~ — hecho (Vite + React + React Router + Tailwind, ver arriba).
2. ~~Landing page con las secciones exactas de `CONTEXT.md`~~ — hecho.
3. ~~Marcado Schema.org~~ — hecho.
4. **Formulario de registro de talento** en la página `/talento` (hoy es un stub), con los 11 campos, tipos, validaciones y mensajes de error exactos de `CONTEXT.md` (nombre, email, teléfono, país, años de experiencia, sector, inglés, disponibilidad, LinkedIn opcional, comentarios ≤500 caracteres con contador, checkbox de consentimiento obligatorio).
5. **Mensaje de éxito** al enviar (simulado) y **mensaje de redirección** para empresas que buscan contratar servicios (no candidatos).
6. **Accesibilidad + SEO** con una revisión dedicada (lo hecho hasta ahora es responsive verificado visualmente en desktop/mobile, pero no una auditoría de accesibilidad/SEO formal).
7. **Decisión de idioma**: idioma base fijado como español (todo el contenido implementado está en español, como `CONTEXT.md`); sigue pendiente decidir si se añade inglés como mejora.
8. ~~Documentar la nueva app con su propio README~~ — hecho (`uis/website/README.md` + `README.es.md`).

## Próximos pasos inmediatos (en orden sugerido)

1. Construir el formulario de `/talento` con validaciones reales (no solo `required` de HTML) y los mensajes de error literales especificados en `CONTEXT.md`.
2. Implementar el mensaje de éxito (simulado) y el mensaje de redirección para empresas.
3. Pasar una revisión de accesibilidad/SEO dedicada (contraste, labels de formulario, orden de encabezados, `lang`, meta tags) antes de dar el Hito 1 por terminado.
4. Decidir si se añade inglés como segundo idioma.
5. Actualizar este `progress.md` (marcar casillas, mover "próximos pasos" hacia adelante) al cerrar cada paso — no dejar que quede desactualizado.

## Fuera de alcance del Hito 1 (pero en el radar)

- Backend FastAPI real en `services/` (el formulario del Hito 1 solo *simula* el envío).
- El "Agente Inteligente de Selección y Soporte" descrito en `company-choice.md` — pertenece a hitos posteriores (Agentes/RAG/Backend), pero el modelado de `Candidate`/`Vacancy` en `src/` debería mantenerse compatible con esa visión.
- Resolver los huecos de tooling de raíz (`package.json`, `docker-compose.yml`) más allá de lo estrictamente necesario para `uis/website/`.
