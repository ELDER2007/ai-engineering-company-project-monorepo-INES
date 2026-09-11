# Tech Context — Nexova

## Estructura del monorepo (por capa, no por hito)

Plantilla de 4Geeks Academy organizada por responsabilidad de equipo, no por número de hito — el trabajo de un hito puede tocar varias carpetas a la vez. Ver [`AGENTS.md`](../AGENTS.md) para el mapa completo y el árbol de decisión "¿dónde pongo esto?".

| Capa | Carpeta | Estado actual |
| --- | --- | --- |
| Interfaces de usuario | `uis/` | `uis/website/` con la landing del Hito 1 (falta el formulario de `/talento`); `uis/backoffice/` con el shell del dashboard (fuera de Hito 1) — mismo toolchain (Vite + React + React Router + Tailwind), layouts y temas Tailwind independientes entre sí |
| Backend centralizado | `services/` | `services/api/` con el esqueleto de FastAPI (solo `/health`); routers de dominio (candidatos, vacantes, talento) todavía no existen |
| Datos | `data/{raw,pipelines,process,eval}/` | Vacía (solo READMEs) |
| Agentes de IA | `agents/` | Solo `_template/` (incluye `agent.py` + esqueleto de tests) |
| Skills reutilizables | `skills/` | Solo `skills/data-analysis/` de ejemplo |
| Servidores MCP | `mcps/` | Vacía (solo README) |
| Automatización | `workflows/` | Vacía (solo README) |
| Librerías compartidas | `packages/` | `packages/shared/` con `package.json` (`@repo/shared-types`) y `types/index.ts`, pero sin runner de workspace en la raíz que lo conecte a nada |
| Recursos sueltos | `shared/` | Vacía (solo README) |
| **Lógica de dominio ya escrita** | `src/` | **Código real en TypeScript**, no listado en README hasta que se documentó en `AGENTS.md`: `src/types/models.ts` (modelos de `Candidate`/`Vacancy`) y `src/utils/{validations,transformations,collections,search}.ts` — reglas de negocio de candidatos y vacantes de Nexova |

## Stack elegido / impuesto por el stakeholder (Hito 1)

- **Tailwind CSS** para el diseño del sitio y del formulario — pedido explícito de Carmen Ruiz en `CONTEXT.md`.
- Validaciones de formulario deben implementarse y funcionar de verdad (no solo visual) — email, teléfono con código de país, rango de años de experiencia, URL de LinkedIn opcional, contador de caracteres en comentarios, checkbox de consentimiento obligatorio.
- Responsive, accesible, optimizado para SEO, con marcado Schema.org `Organization` (bloque JSON-LD exacto está en `CONTEXT.md`).
- Idioma base a elegir por quien implemente (español es el idioma de todo el contenido de negocio en `CONTEXT.md`); segundo idioma opcional y nunca a costa de reducir calidad del idioma base.

## Restricciones exactas de contenido y validación (transcritas de `CONTEXT.md`)

Estos datos son literales del briefing — no una paráfrasis — porque el criterio de aceptación del Hito 1 exige los mensajes y campos **exactos**, no equivalentes razonables. La skill [`validate-context-alignment`](../skills/validate-context-alignment/SKILL.md) verifica esto automáticamente parseando `CONTEXT.md` en vivo; esta tabla es para lectura humana rápida.

### Campos del formulario de registro de talento (11, todos definidos en `CONTEXT.md`)

| Campo | Tipo | Validación | Obligatorio | Mensaje de error exacto |
| --- | --- | --- | --- | --- |
| Nombre completo | text | Mínimo 2 palabras | Sí | "El nombre debe contener al menos nombre y apellido" |
| Email | email | Formato válido (`@` + dominio) | Sí | "Ingresa un email válido (ejemplo: nombre@empresa.com)" |
| Teléfono | tel | `+[código país] [número]` (ej. +34 612 345 678) | Sí | "El teléfono debe incluir código de país (ejemplo: +34 612 345 678)" |
| País de residencia | select | España / Estados Unidos / Otro | Sí | "Selecciona tu país de residencia" |
| Años de experiencia | number | Entre 0 y 50 | Sí | "Los años de experiencia deben estar entre 0 y 50" |
| Sector de interés | select | Tecnología / Retail / Servicios Financieros / Consultoría / Otro | Sí | "Selecciona el sector de tu interés" |
| Nivel de inglés | select | Básico / Intermedio / Avanzado / Nativo | Sí | "Indica tu nivel de inglés" |
| Disponibilidad | radio | Inmediata / 1 mes / 2-3 meses / Solo explorando | Sí | "Selecciona tu disponibilidad" |
| LinkedIn (URL del perfil) | url | Debe empezar con `http://` o `https://` si se llena | No | "Si incluyes LinkedIn, debe ser una URL válida" |
| Comentarios adicionales | textarea | Máximo 500 caracteres, con contador visible | No | "Los comentarios no pueden exceder 500 caracteres (quedan X)" — el "X" es dinámico |
| Acepto política de datos | checkbox | Debe estar marcado | Sí | "Debes aceptar la política de tratamiento de datos para continuar" |

### Otros textos literales obligatorios

- **Mensaje de éxito** (3 líneas exactas, ver `CONTEXT.md` § "Mensaje de éxito"): "¡Gracias por tu interés en Nexova!" + párrafo de seguimiento + invitación a seguir en LinkedIn.
- **Restricción de audiencia**: el formulario es para candidatos, no para empresas que buscan contratar. Si aplica, mostrar: "¿Eres una empresa buscando talento? Escríbenos a contacto@nexova.com".
- **Contacto**: `contacto@nexova.com`, Valencia `+34 960 123 456`, Miami `+1 305 555 0191`.
- **Schema.org**: bloque JSON-LD `Organization` exacto en `CONTEXT.md` § "Schema.org markup requerido" (nombre, fundación 2011, direcciones Valencia/Miami, teléfono `+34-960-123-456`, redes sociales) — se embebe tal cual, sin modificar claves ni valores.

### Inconsistencia detectada en el briefing (marcar, no "corregir" sin confirmación)

La sección "Por qué Nexova" de `CONTEXT.md` dice **"12 años de experiencia en el mercado latinoamericano"**, pero la sección "Tu empresa" dice que Nexova opera en **Valencia (España) y Miami (Florida)**, no en Latinoamérica, y que fue fundada en **2011** (≈15 años a 2026, no 12). Esto es una posible inconsistencia del propio brief, no un error de este repo. Por la regla de rutas restringidas de `AGENTS.md`, `CONTEXT.md` no se edita sin confirmación explícita del desarrollador — así que el texto se implementa tal cual está escrito, y esta discrepancia queda documentada aquí para que quien lo lea decida si vale la pena preguntarle a "Carmen Ruiz" (o al instructor) antes de publicar.

## Decisiones de arquitectura tomadas hasta ahora

1. **Backend centralizado, no microservicios**: un solo FastAPI en `services/` con routers por dominio; evitar dividir en servicios separados salvo que un worker en background lo justifique.
2. **AGENTS.md como contexto de agente de primer nivel**: se creó `AGENTS.md` / `AGENTS.es.md` en la raíz (2026-09-11) para que cualquier agente de código (Claude Code, Cursor, etc.) tenga de entrada el mapa de carpetas, las convenciones y el puntero a `CONTEXT.md`, en vez de tener que redescubrirlo cada sesión. Se prefirió esto sobre solo ajustar permisos de `.claude/settings.json`.
3. **Convención de documentación bilingüe**: docs principales en inglés (`README.md`, `AGENTS.md`) con hermano `*.es.md` en español; mantener ambos sincronizados al editar cualquiera. (El contenido específico de negocio — `CONTEXT.md`, `company-choice.md` — está solo en español porque así se recibió el briefing.)
4. **`src/` se trata como el código vigente del hito de Programación**: cualquier lógica nueva de scoring de candidatos, filtros de vacantes, etc. debe mantenerse consistente con `src/types/models.ts` en vez de redefinir modelos paralelos.

## Restricciones técnicas / huecos de tooling (importante antes de programar)

- **No existe `package.json`, `tsconfig.json`, lockfile ni `docker-compose.yml` en la raíz del repo**, pese a que `README.md` documenta `docker-compose.yml` como perteneciente a la raíz. Hay que crearlos explícitamente al empezar a implementar — no asumir que ya están.
- `packages/shared/package.json` existe pero no está enganchado a ningún workspace runner todavía.
- `src/` no tiene build ni test runner propio (sin `package.json`/`tsconfig` local) — antes de reusarlo desde `uis/website` o `services/api`, decidir cómo se importa (¿se mueve a `packages/shared`? ¿se le da su propio `package.json`? ¿se referencia por path relativo desde una app con su propio tsconfig?).
- Ningún workspace de npm/pnpm está configurado — si se elige monorepo con workspaces, hay que definirlo desde cero.

## Decisión técnica tomada: stack de `uis/website/`

Resuelta el 2026-09-11, confirmada con el usuario: se siguió la estructura del template de 4Geeks [`react-hello-webapp`](https://github.com/4GeeksAcademy/react-hello-webapp) (Vite + React + React Router + patrón de estado global con `useReducer`/Context), reemplazando Bootstrap por Tailwind CSS 4 (`@tailwindcss/vite`) por el requisito explícito del stakeholder. Se subió Vite de la v4 del template a la v5 porque `@tailwindcss/vite` exige Vite ^5. El toolchain vive de forma autocontenida en `uis/website/` (su propio `package.json`/`node_modules`), sin workspace de npm en la raíz — ese wiring con `packages/shared` y `src/` sigue sin resolverse y no bloquea el Hito 1. Detalle completo en `uis/website/README.md`.

## Próxima decisión técnica pendiente

Ninguna bloqueante para el Hito 1. A futuro: si se reutiliza `src/` o `packages/shared` desde `uis/website/`, decidir cómo se referencia (workspace de npm en la raíz vs. import relativo).
