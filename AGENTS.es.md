# AGENTS.md

Instrucciones para cualquier agente de programación con IA (Claude Code, Cursor, Copilot, etc.) que trabaje en este repositorio. Lee este archivo primero — da contexto de todo el repositorio para que el agente no tenga que redescubrir la estructura y las convenciones en cada tarea.

_These instructions are also available in [English](./AGENTS.md)._

---

## Qué es este repo

Una plantilla de monorepo para estudiantes del track de Ingeniería de IA de 4Geeks Academy. Un estudiante construye **una empresa ficticia** a lo largo de muchos hitos del curso (Web, Programación, Backend, Telemetría, RAG, Agentes, Workflows, Tiempo real). Cada carpeta corresponde a una capa de un equipo de ingeniería real, no a un número de hito — el trabajo de un hito suele repartirse entre varias carpetas a la vez.

## Fuente de verdad: `CONTEXT.md`

**Lee [`CONTEXT.md`](./CONTEXT.md) antes de escribir o cambiar nada.** Contiene los datos de dominio, nombres de campos y restricciones de la empresa asignada. En este repo la empresa es **Nexova** — una consultora de RR.HH. y adquisición de talento con sede en España/Miami (headhunting ejecutivo, outsourcing de atención al cliente, formación corporativa). Los requisitos específicos de cada hito (campos de formulario, mensajes de validación, copy, marcado Schema.org, etc.) viven ahí — no inventes reglas de dominio que lo contradigan. `company-choice.md` documenta la elección del estudiante de Nexova y dos departamentos de enfoque (Operaciones de Selección, Atención al Cliente); trátalo como intención de fondo, no como spec.

Todo lo que se genere (copy de UI, campos de formulario, prompts de agentes, datos de ejemplo) debe mantenerse consistente con el dominio de `CONTEXT.md`: nombres de campos, reglas de validación, mensajes de error y las dos sedes (Valencia, ES y Miami, FL).

## Mapa del repositorio

| Carpeta | Qué vive aquí | Notas |
| --- | --- | --- |
| `CONTEXT.md` | Briefing de negocio de Nexova — fuente única de verdad del dominio | Leer primero |
| `memory-bank/` | Memoria de trabajo para cualquier agente: `projectbrief.md`, `techContext.md`, `progress.md` | Leer al inicio de cada sesión (ver más abajo); actualizar `progress.md`/`techContext.md` antes de cada commit |
| `.agents/rules/` | Reglas de desarrollo con alcance definido (`always` / `glob` / `agent-requested`) | Ver [`.agents/README.es.md`](./.agents/README.es.md); cargar reglas `always` en cada sesión, `glob` por archivo coincidente, `agent-requested` bajo demanda |
| `uis/` | Apps frontend con las que interactúa un humano (sitio web, backoffice, dashboards) | `uis/website/` (landing del Hito 1) y `uis/backoffice/` (shell del dashboard) ya estructurados — ver `memory-bank/progress.md` |
| `services/` | Un backend FastAPI centralizado para toda la empresa, con routers por dominio | Existe el esqueleto de `services/api/` (solo health check); prefiere añadir routers aquí antes que crear microservicios nuevos |
| `data/raw/`, `data/pipelines/`, `data/process/`, `data/eval/` | Datos fuente → scripts ETL → salidas limpias → conjuntos de calidad/evaluación | Flujo: raw → pipelines → process → consumido por services/uis/agents |
| `agents/` | Subcarpetas de agentes de IA (config, prompts, tools, tests); empieza desde `agents/_template/` | La plantilla incluye `agent.py` + esqueleto de tests |
| `skills/` | Capacidades empaquetadas y reutilizables (`SKILL.md` + scripts) para agentes/humanos en todo el repo | p. ej. `skills/data-analysis/` |
| `mcps/` | Servidores MCP que dan a los agentes acceso en vivo a sistemas (BD, APIs, GitHub) | Úsalo cuando el código estático no baste |
| `workflows/` | Exports de n8n / configs de Make-Zapier / orquestación entre sistemas | Conecta services + pipelines + agents |
| `packages/` | Código versionado compartido por varias apps (`packages/shared` → `@repo/shared-types`) | Todavía no hay runner de workspace en la raíz |
| `shared/` | Recursos compartidos que no son un paquete: esquemas JSON, plantillas de email, specs OpenAPI, design tokens | Demasiado pequeños/no-código para `packages/` |
| `docs/` | Documentación de arquitectura y ADRs transversales | No atada a una sola app/agente |
| `infra/` | Dockerfiles, Terraform, manifiestos K8s, CI/CD | El `docker-compose.yml` en sí va en la raíz del repo (aún no añadido) |
| `scripts/` | Scripts de automatización sueltos y puntuales (setup, seed data, wrappers de lint) | Documenta el propósito/argumentos de cada script |
| `internal/` | Herramientas/CLIs internas estructuradas con sus propias deps y tests | Más robusto que `scripts/` |
| `src/` | Lógica de dominio de Nexova ya implementada en TypeScript: validaciones y transformaciones de candidatos/vacantes, búsqueda, colecciones y modelos compartidos | Todavía no aparece en el README principal — trátalo como el código actual del hito de Programación y mantén cualquier lógica nueva (scoring de candidatos, filtros de vacantes, etc.) consistente con `src/types/models.ts` |

### ¿Dónde pongo esto?

```
¿Tiene pantallas/botones?                  → uis/
¿Corre como servidor/API/cola?             → services/
¿Es dato crudo o transformado?             → data/raw/ o data/process/
¿Mueve datos entre sistemas?               → data/pipelines/
¿Mide calidad de IA/pipelines?             → data/eval/
¿Es un asistente de IA con un objetivo?    → agents/
¿Es una capacidad/instrucción reutilizable?→ skills/
¿La IA necesita llamar tools/APIs externas?→ mcps/
¿Es automatización programada/n8n?         → workflows/
¿Código importado por 2+ carpetas?         → packages/
¿Es esquema/plantilla/asset, no librería?  → shared/
¿Es arquitectura/docs de todo el equipo?   → docs/
¿Es config de Docker/deploy/cloud?         → infra/
¿Es un script puntual?                     → scripts/
¿Es una CLI con su propio paquete?         → internal/
```

## Convenciones

- **Docs bilingües**: los docs principales están en inglés (`README.md`, `CONTEXT.md`, este archivo); un archivo hermano `*.es.md` lleva la traducción al español. Mantén ambos sincronizados al editar cualquiera de los dos.
- **Todavía no hay runner de workspace en la raíz**: solo existe `packages/shared/package.json`. No asumas que hay `package.json`, lockfile o `docker-compose.yml` en la raíz — compruébalo antes de referenciarlos, y si añades uno, cablealo en vez de asumir que ya existe.
- **No amontones trabajo en la raíz del repo.** Cada app/servicio/agente/pipeline nuevo va en su propia subcarpeta con su README, siguiendo el patrón que ya usa cada carpeta de primer nivel (`README.md` + `README.es.md`).
- **El backend FastAPI se mantiene centralizado**: añade routers/módulos a una sola app en `services/` en vez de crear microservicios nuevos, salvo que un worker realmente necesite correr por separado.
- **Estilo de UI**: cuando `CONTEXT.md` especifique un framework (actualmente Tailwind para el sitio web + el formulario de registro de talento), úsalo en vez de introducir un segundo enfoque de estilos.

## Banco de memoria — leer al inicio de cada sesión

Antes de tocar cualquier archivo, lee los tres documentos de [`memory-bank/`](./memory-bank/), en este orden:

1. [`memory-bank/projectbrief.md`](./memory-bank/projectbrief.md) — el negocio, los objetivos del proyecto y el problema que resuelve.
2. [`memory-bank/techContext.md`](./memory-bank/techContext.md) — el stack tecnológico, las decisiones de arquitectura ya tomadas y las restricciones técnicas.
3. [`memory-bank/progress.md`](./memory-bank/progress.md) — el estado actual del desarrollo y los próximos pasos previstos.

Esta es la memoria de trabajo del proyecto: persiste entre sesiones aunque el contexto de la conversación no lo haga. Si algo en estos archivos contradice lo que realmente encuentras en el código, confía en el código, señala la discrepancia al desarrollador y corrige el documento desactualizado como parte del flujo de commit de abajo — no sigas trabajando en silencio sobre un banco de memoria obsoleto.

Junto al banco de memoria, [`.agents/rules/`](./.agents/README.es.md) contiene reglas de desarrollo más pequeñas y con alcance individual. Carga también toda regla `scope: always` al inicio de sesión; carga una regla `scope: glob` cuando toques un archivo que coincida con su patrón; y solicita una regla `scope: agent-requested` cuando su descripción coincida con lo que estás a punto de hacer (p. ej. el checklist de pre-commit de abajo).

## Flujo obligatorio antes de cada commit

Nunca trates `git commit` como un último paso suelto — recorre esta secuencia primero, en orden:

1. **Revisa contra la fuente de verdad.** Compara tus cambios (`git diff`) contra `CONTEXT.md` y `memory-bank/projectbrief.md`; confirma que nada contradiga el dominio asignado, el copy requerido, los nombres de campos o las reglas de validación.
2. **Ejecuta las verificaciones relevantes para lo que tocaste.** Lint/typecheck/tests de esa parte del repo (p. ej. un chequeo de TypeScript para `src/`, la suite de tests para un cambio en `services/`). Si todavía no existe una verificación automática para esa área, dilo explícitamente en tu resumen en vez de saltarte el paso en silencio.
3. **Actualiza el banco de memoria.** Refleja el cambio en `memory-bank/progress.md` (marca lo terminado, adelanta la lista de próximos pasos), y actualiza también `memory-bank/techContext.md` si el cambio afecta al stack, a una decisión de arquitectura o a una restricción.
4. **Mantén los docs bilingües sincronizados.** Si editaste `README.md`, `AGENTS.md` o el `README.md` de alguna carpeta, replica el mismo cambio en su hermano `*.es.md` dentro del mismo commit.
5. **Confirma que no tocaste ninguna ruta restringida (abajo) sin aprobación explícita del desarrollador**, y luego haz `git add`/commit con un mensaje que describa qué cambió y por qué.

## Rutas que requieren confirmación explícita del desarrollador antes de modificarlas

No crees, edites ni borres nada de esto por iniciativa propia — propón el cambio y consigue un sí explícito primero, aunque una tarea parezca implicarlo:

- `CONTEXT.md` / `CONTEXT.es.md` — la fuente de verdad del negocio; solo el desarrollador redefine el dominio de la empresa asignada.
- `company-choice.md` — el registro propio del estudiante sobre su elección de empresa/departamentos; es una declaración personal, no una spec para editar.
- `infra/`, `docker-compose.yml` (cuando exista) y cualquier configuración de CI/CD — los cambios de despliegue/infraestructura tienen un radio de impacto mayor que una sola tarea.
- Cualquier archivo de secretos o credenciales (`.env*`, claves de API, tokens) — nunca crear, editar ni commitear uno.
- El tooling de la raíz una vez que exista (`package.json`, `tsconfig.json`, lockfiles) — propón los cambios de dependencias o scripts antes de aplicarlos.
- Contratos compartidos ya publicados y consumidos en otros sitios (`packages/shared/types/index.ts` y cualquier otra cosa bajo `packages/`) — los cambios que rompan compatibilidad ahí afectan a todos los consumidores.
- Los internos de `.git/`, los git hooks y cualquier cambio en `.gitignore` que deje de rastrear archivos ya commiteados.

Ante la duda de si una ruta cuenta como "restringida", pregunta en vez de asumir.

## Antes de empezar una tarea

1. Completa la lectura del banco de memoria de arriba si todavía no lo has hecho en esta sesión.
2. Vuelve a leer `CONTEXT.md` para las reglas de dominio relevantes a tu tarea.
3. Abre el `README.md` de la carpeta específica que vas a tocar — cada una tiene guías propias más allá de lo resumido aquí.
4. Coloca el trabajo nuevo en la carpeta correcta según el mapa de arriba; añade un README de subcarpeta si estás introduciendo una app/agente/pipeline/servicio nuevo.
