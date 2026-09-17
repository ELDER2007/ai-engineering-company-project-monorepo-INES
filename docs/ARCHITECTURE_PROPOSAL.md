# Propuesta de Arquitectura de Backend — Nexova

**Para:** CTO / liderazgo técnico
**De:** Equipo de ingeniería, proyecto transversal Nexova
**Objetivo:** proponer, con criterio técnico y sin código, la arquitectura del backend antes de empezar a construirlo.

## Resumen ejecutivo

Propongo **arquitectura en capas** (rutas → servicio/caso de uso → acceso a datos) como patrón, frente a MVC y serverless, porque Nexova es una API pura consumida por varios frontends desacoplados y con cargas de trabajo largas y con estado (IA, websockets) — ninguno de los otros dos patrones encaja con esas características. Sobre ese patrón, propongo desplegarlo como **monolito modular**: un único servicio FastAPI, organizado internamente por dominio de negocio (selección de talento, atención al cliente, agente de IA), con fronteras claras entre módulos que permiten extraer cualquiera de ellos como servicio independiente el día que el uso real lo justifique. No propongo microservicios en esta fase ni un monolito sin estructura interna — ambos extremos tienen un costo que hoy no se justifica con lo que sabemos del sistema.

El resto del documento desarrolla por qué esta arquitectura encaja con lo que Nexova está construyendo, cómo organizo módulos, dominios y rutas, qué decisiones técnicas tomo ya, y qué riesgos o ambigüedades hay que resolver antes de escribir el primer endpoint.

---

## 1. Patrón arquitectónico propuesto y por qué

### 1.1 Patrones evaluados frente a las características reales de Nexova

No elijo el patrón por preferencia; lo comparo contra tres características concretas del sistema que hay que construir: **(a)** el backend es una API pura consumida por varios frontends desacoplados (sitio público, portal de candidatos, backoffice, chatbot), no una app que renderiza sus propias vistas; **(b)** hay cargas de trabajo largas y con estado (parsing/scoring de CV con IA, conexiones persistentes de websocket para dashboards en vivo), no solo peticiones cortas y sin estado; **(c)** el equipo es pequeño y construye por hitos sucesivos, no de una vez.

| Patrón | Qué asume sobre el sistema | Por qué encaja o no con Nexova |
|---|---|---|
| **MVC** | El propio backend renderiza vistas para un usuario final (ciclo request → controller → view) | No encaja: Nexova no tiene una sola vista que el backend renderice — tiene varios frontends independientes (`uis/website`, portal, backoffice) que consumen la misma API. Forzar MVC aquí no tiene "View" real que ocupar, y termina mezclando el controlador con lógica de negocio por falta de una capa donde ponerla |
| **Serverless (funciones)** | Invocaciones cortas, sin estado, con tráfico irregular donde pagar solo por ejecución compensa el costo operativo por función | No encaja hoy: el scoring de CV con IA y el chatbot son operaciones potencialmente lentas, y los dashboards en vivo necesitan conexiones de websocket persistentes — ambos casos chocan con el modelo de ejecución corta y el cold start de funciones. Además, gestionar decenas de funciones con sus propios permisos y triggers es más carga operativa para un equipo pequeño que un único servicio, no menos |
| **Arquitectura en capas (elegida)** | Un servicio separa responsabilidades en niveles — presentación (rutas), lógica de negocio (servicios/casos de uso), acceso a datos (repositorios/modelos) — dentro de un mismo deployable | Encaja: permite testear reglas de negocio (scoring, validación del formulario, cálculo de SLA) sin depender del transporte HTTP ni de la base de datos; permite que el agente de IA llame directamente a la capa de servicio de selección y soporte sin pasar por red; y un único deployable es lo que un equipo pequeño puede operar de forma sostenida mientras construye por hitos |

**Patrón elegido: arquitectura en capas**, implementada como un único servicio FastAPI (`services/api/`) con rutas → servicio/caso de uso → acceso a datos, y organizado internamente por dominio de negocio (bounded context). El trabajo pesado o de larga duración (parsing de CV, llamadas a IA, envío de correo) se ejecuta como tareas en background dentro de la misma plataforma, no como servicios aparte.

### 1.2 Una decisión relacionada pero distinta: topología de despliegue

La arquitectura en capas no decide por sí sola si cada dominio se despliega como servicio propio (microservicios) o todos juntos (monolito). Esa es la segunda decisión de este documento — **monolito modular**, no microservicios ni un monolito sin estructura interna — y está justificada en la sección 2 con las mismas características reales de Nexova, no con preferencia genérica.

---

## 2. Por qué esta topología (monolito modular) encaja con lo que Nexova está construyendo

El backend tiene que soportar, según `CONTEXT.md` y la propuesta de departamentos en `company-choice.md`, dos dominios con necesidades distintas que **comparten datos y un mismo agente de IA**:

| Dominio | Qué necesita | Por qué importa para la arquitectura |
|---|---|---|
| Selección de talento | Alta de candidato, carga y scoring de CV, búsqueda con filtros, portal de estado, dashboard de consultores | Procesamiento asíncrono (parsing/IA) + datos personales sensibles |
| Atención al cliente | Chatbot, tickets, dashboard de supervisores en vivo, detección de sentimiento | Conversación con IA + actualizaciones en tiempo real |
| Agente de IA único | Combina selección y soporte | Necesita leer/escribir sobre candidatos **y** tickets en la misma operación lógica |

Tres hechos del contexto de Nexova empujan directamente hacia el monolito modular y no hacia microservicios:

1. **El agente cruza los dos dominios.** Si `selection` y `support` fueran servicios separados, el agente tendría que resolver consistencia entre servicios (llamadas de red, fallos parciales, reintentos) para algo que en un monolito es una llamada de función. Se pagaría el costo de la distribución sin ganar nada a cambio, porque no hay necesidad de escalar selección y soporte de forma independiente todavía.
2. **El proyecto se construye por hitos, no de una vez** (Backend, Telemetría, RAG, Agentes, Workflows, Real-time llegan en momentos distintos). Una arquitectura que exige decidir límites de servicio y contratos de red desde el hito 1 —cuando solo existe el alta de candidato del sitio web— fuerza a adivinar fronteras antes de tener uso real. El monolito modular permite construir `candidates/` ahora y añadir `selection/`, `support/`, `agent/`, `realtime/` en hitos sucesivos sin reescribir lo anterior.
3. **El equipo es pequeño.** Microservicios exigen despliegue independiente, observabilidad distribuida y gestión de contratos entre servicios; ese costo operativo compite directamente con el tiempo de construir producto, y hoy no hay señal de qué componente necesitaría escalar por separado.

El monolito modular no es una renuncia a escalar después: al aislar cada dominio detrás de una capa de servicio (sección 3.1), el día que el scoring de CVs con IA resulte ser el cuello de botella real, se extrae *ese* módulo como worker independiente sin tocar el resto.

Se descarta también el monolito **sin** estructura interna (rutas de FastAPI con lógica y queries SQL directamente en el handler) porque impide testear reglas de negocio (scoring, validaciones del formulario, cálculo de SLA) sin levantar la app entera, y porque acopla el contrato HTTP al modelo de datos, así que un cambio de esquema rompe la API pública.

---

## 3. Organización de módulos, dominios y rutas

### 3.1 Criterio de separación: dos ejes, no uno

La estructura combina **dos criterios de separación distintos**, cada uno resolviendo un problema diferente:

- **Eje horizontal — por dominio de negocio (bounded context):** cada carpeta de primer nivel dentro de `services/api/` representa una capacidad de negocio de Nexova (candidatos, selección, soporte, agente), no una categoría técnica. El criterio para trazar esta línea es "¿quién en el negocio es dueño de esta regla?" — quien decide cómo se calcula un score no es quien decide un SLA de ticket, así que van en carpetas distintas aunque ambas sean "lógica de negocio".
- **Eje vertical — por responsabilidad técnica (capas), dentro de cada dominio:** dentro de cada carpeta de dominio, los archivos se separan por el tipo de responsabilidad que cumplen frente al patrón en capas de la sección 1 — `router.py` es la capa de presentación (HTTP), `schemas.py` es el contrato de entrada/salida, `service.py` es la lógica de negocio, `models.py` es la persistencia. El criterio aquí es "¿qué cambia junto y qué cambia por separado?" — el contrato HTTP de un endpoint puede cambiar sin tocar cómo se persiste el dato, y viceversa.

Se descarta agrupar por tipo técnico a nivel de proyecto (una carpeta `routers/` con todas las rutas, otra `models/` con todos los modelos) porque, para un cambio de negocio real —"cambiar cómo se calcula el score de un candidato"— esa organización obliga a tocar cuatro carpetas dispersas en vez de una sola. El criterio de dominio prioriza que el código que cambia junto viva junto.

```
services/api/
├── main.py                    # instancia FastAPI, registro de routers, middlewares
├── core/                      # transversal: config, seguridad, logging, excepciones — no pertenece a ningún dominio
├── db/                        # sesión de base de datos, migraciones — infraestructura, no negocio
├── candidates/                 # alta de candidatos (lo que exige el Hito 1 hoy)
│   ├── router.py / schemas.py / service.py / models.py
├── selection/                  # CV, scoring, ranking, búsqueda de candidatos
│   ├── router.py / schemas.py / service.py / models.py
│   └── scoring/                # subcomponente aislado, candidato a extraerse a worker
├── support/                     # tickets, sentimiento
│   ├── router.py / schemas.py / service.py / models.py
├── agent/                       # orquesta el agente combinado; llama a selection.service y support.service, nunca a sus modelos
├── realtime/                    # websockets para dashboards — cruza dominios, por eso vive aparte y no dentro de selection/ o support/
├── notifications/                # correos de seguimiento — utilidad compartida, no dueña de ninguna regla de negocio
└── workers/                      # tareas en background (parsing CV, envíos async) — mismo criterio que notifications/: infraestructura compartida
```

| Carpeta | Responsabilidad | Por qué es su propio módulo y no parte de otro |
|---|---|---|
| `candidates/` | Alta y datos base del candidato | Es el dueño de las reglas de validación del formulario (Hito 1); otros dominios lo consumen pero no lo modifican |
| `selection/` | CV, scoring, ranking, búsqueda | Concentra la lógica de negocio más sensible (scoring explicable, sección 4) — aislarla facilita auditarla y, si hace falta, extraerla |
| `support/` | Tickets, sentimiento, SLA | Reglas de negocio propias (cálculo de SLA) que no tienen relación con cómo se califica a un candidato |
| `agent/` | Orquestación del agente de IA combinado | No tiene datos propios — su única responsabilidad es coordinar `selection` y `support`; separarlo evita que su lógica de orquestación se mezcle con las reglas de negocio de los dominios que consume |
| `realtime/` | Canales de websocket para dashboards | Sirve tanto a `selection` como a `support`; ponerlo dentro de cualquiera de los dos crearía una dependencia cruzada innecesaria |
| `core/`, `db/` | Configuración, seguridad, sesión de base de datos | Infraestructura transversal sin reglas de negocio — separada explícitamente de los dominios para que no se filtre lógica de negocio dentro de código de arranque |

**Regla de frontera entre dominios:** un módulo solo llama a la capa de servicio de otro módulo, nunca a sus modelos ni a su acceso a datos. Es la regla que hace posible extraer `selection/scoring/` como worker independiente sin tocar `agent/` ni `support/` el día que haga falta, y la consecuencia directa de haber separado por dominio en el eje horizontal.

### 3.2 Endpoints y routers de FastAPI por dominio

**Criterio de agrupación:** cada módulo de dominio expone **un `APIRouter` propio**, registrado en `main.py` con un prefijo `/api/v1/<dominio>` y un tag de OpenAPI igual al nombre del dominio — así la documentación autogenerada queda agrupada exactamente como el código. Dentro de un dominio, cuando hay más de un recurso con **consumidores distintos** (por ejemplo, el candidato que sube su CV frente al consultor que lo busca), ese dominio se divide en **sub-routers por recurso**, no se mezclan en uno solo — el criterio es "¿quién llama a esto y con qué permisos?", el mismo eje público/interno que ya se usa para el resto de la organización.

**`candidates`** (router único; hoy es el único dominio con código real, Hito 1):

| Método | Ruta | Propósito |
|---|---|---|
| `POST` | `/api/v1/candidates` | Alta de candidato desde el formulario público del sitio |
| `GET` | `/api/v1/candidates/{id}` | Consulta de sus propios datos (portal del candidato, con token de acceso propio, no rol interno) |

**`selection`** (dos sub-routers, porque el candidato y el consultor no deben compartir el mismo grupo de endpoints):

| Sub-router | Método | Ruta | Propósito |
|---|---|---|---|
| `cvs` (público, del candidato) | `POST` | `/api/v1/selection/cvs` | Subir CV asociado a un candidato ya registrado |
| `cvs` | `GET` | `/api/v1/selection/cvs/{id}/status` | Consultar el estado del scoring (para el portal del candidato) |
| `candidates` (interno, del consultor) | `GET` | `/api/v1/selection/candidates` | Buscar/filtrar candidatos (sector, idioma, disponibilidad) |
| `candidates` | `GET` | `/api/v1/selection/candidates/{id}` | Detalle de un candidato con su score explicado |
| `candidates` | `GET` | `/api/v1/selection/candidates/ranking` | Ranking ordenado por score para una búsqueda dada |

**`support`** (dos sub-routers, por el mismo criterio: cliente/candidato hablando con el chatbot frente al supervisor gestionando tickets):

| Sub-router | Método | Ruta | Propósito |
|---|---|---|---|
| `chat` (público) | `POST` | `/api/v1/support/chat/messages` | Enviar un mensaje al chatbot y recibir respuesta |
| `tickets` (interno) | `POST` | `/api/v1/support/tickets` | Crear un ticket (manual, o generado desde `chat`/`agent` al escalar) |
| `tickets` | `GET` | `/api/v1/support/tickets` | Listar tickets para el dashboard de supervisor, con filtros de estado/SLA |
| `tickets` | `PATCH` | `/api/v1/support/tickets/{id}` | Actualizar estado o asignación de un ticket |

**`agent`** (un único router; su forma final depende de resolver la ambigüedad de la sección 5.2 sobre quién habla con el agente):

| Método | Ruta | Propósito |
|---|---|---|
| `POST` | `/api/v1/agent/query` | Punto de entrada de la conversación del agente combinado; internamente decide si el caso pertenece a `selection` o `support` y llama a su capa de servicio |

**`realtime`** (fuera del árbol REST, no es un `APIRouter` de HTTP sino de websocket):

| Canal | Propósito |
|---|---|
| `WS /ws/dashboard/selection` | Eventos en vivo para consultores: nuevo candidato, cambio de score, cambio de estado |
| `WS /ws/dashboard/support` | Eventos en vivo para supervisores: nuevo ticket, cambio de SLA, alerta de sentimiento negativo |

### 3.3 Criterios generales que atraviesan todos los routers

- **Versión desde el día uno** (`/api/v1`): la API la van a consumir a la vez el sitio público, el portal de candidatos, el dashboard interno y el agente; sin versión, un cambio de contrato rompe a todos los consumidores simultáneamente.
- **Público vs. interno como eje explícito**, no solo el dominio: las rutas públicas (formulario, carga de CV, chatbot) llevan rate limiting y validación estricta de input porque cualquiera en internet puede llamarlas; las internas (dashboards, búsqueda, gestión de tickets) llevan autenticación y autorización por rol, aplicada como dependencia sobre el grupo de router entero, no repetida en cada handler. Es el mismo criterio que separa los sub-routers dentro de `selection` y `support`.
- **Tiempo real fuera del árbol REST** (`/ws/...`): el ciclo de vida de una conexión persistente (auth al conectar, no por mensaje) es distinto al de una request HTTP y mezclarlos genera ambigüedad sobre qué contrato aplica.

---

## 4. Decisiones técnicas iniciales

Estas son decisiones que se toman ya, con su justificación — no se difieren a "ya se verá":

| Decisión | Elección | Por qué |
|---|---|---|
| **Framework** | FastAPI | Ya es la convención del repo; además su tipado + Pydantic encaja directamente con la validación estricta que exige el formulario de candidatos (`CONTEXT.md`), y su soporte async es necesario para IA y websockets sin bloquear el proceso |
| **Base de datos** | PostgreSQL único, para todos los dominios | Candidatos, CVs, scores y tickets tienen relaciones entre sí (integridad referencial real); mantener un solo motor reduce la carga operativa de un equipo pequeño frente a usar una base distinta por dominio |
| **Búsqueda semántica (RAG del chatbot, matching de CV)** | `pgvector` sobre el mismo Postgres, no un vector store aparte | Evita introducir una segunda pieza de infraestructura antes de tener volumen que la justifique; se puede migrar a un vector store dedicado después si hace falta, sin tocar el resto del esquema |
| **Almacenamiento de CVs** | Object storage (compatible S3), no como blob en la base de datos | Mantiene la base de datos liviana y permite escaneo/validación de archivos como paso independiente antes de servirlos |
| **Tareas en background** | Cola ligera (ej. Redis + worker simple) desde el primer endpoint que suba un CV, no `BackgroundTasks` en el mismo proceso | El parsing/scoring puede tardar; si corre en el mismo worker que atiende HTTP, un pico de cargas degrada la latencia de *toda* la API. Empezar ya con cola evita reescribir ese endpoint cuando llegue el primer pico real |
| **Tiempo real** | WebSockets con Redis pub/sub como canal de broadcast desde el inicio, aunque hoy corra una sola instancia | El estado de conexiones en memoria de un solo proceso deja de funcionar en cuanto haya más de una instancia (necesario para cualquier despliegue con redundancia); resolverlo desde el primer dashboard evita una reescritura posterior |
| **Autenticación interna** | JWT con un campo de rol (consultor / supervisor / admin) sobre un único modelo de usuario interno | No hay hoy necesidad de SSO/OAuth externo; un modelo de roles simple cubre la diferencia de permisos entre dashboards de selección y de soporte sin añadir un proveedor de identidad externo |
| **Scoring de candidatos** | El endpoint de scoring devuelve puntaje **y razones explicables**; ninguna ruta ejecuta descarte automático de un candidato | Restricción de arquitectura, no de producto: dejar el descarte fuera del alcance técnico del módulo evita que se implemente por accidente una decisión de alto riesgo legal (ver 5.1) |

---

## 5. Riesgos y puntos de confusión anticipados

### 5.1 Riesgos técnicos y legales

- **Datos personales y cumplimiento.** Nexova opera en España (GDPR) y Miami (transferencia entre jurisdicciones); se van a almacenar CVs, teléfonos y, si el scoring usa IA, inferencias sobre idoneidad de la persona. Falta definir retención/borrado y qué consentimiento cubre qué uso — el checkbox actual del formulario cubre el registro, no necesariamente el uso del CV para scoring automatizado.
- **Scoring automatizado como decisión de alto riesgo.** Rankear candidatos sin humano en el circuito es un riesgo legal y reputacional (sesgo, falta de explicabilidad; en la UE el scoring de empleo es "alto riesgo" bajo el AI Act). Ya mitigado a nivel de diseño en la sección 4 (score explicable, sin descarte automático), pero requiere que el flujo de producto respete esa restricción.
- **IA conversacional sin control de alcance.** El chatbot y el agente combinado pueden alucinar o gestionar mal un cliente insatisfecho detectado por sentimiento. Se necesita una ruta de escalado obligatoria a un ticket humano cuando el sentimiento cruza un umbral, y respuestas ancladas a una base de conocimiento acotada (RAG), no generación libre.
- **Acoplamiento entre scoring pesado y disponibilidad de la API**, si no se respeta la frontera de la sección 3.1/4 desde el primer endpoint de carga de CV.
- **Ambición del alcance vs. capacidad del equipo.** Lo declarado (scoring con IA, portal en tiempo real, chatbot, tickets con SLA, agente combinado) es mucho mayor que el Hito 1 actual (sitio + captura de leads). Mitigado por construir `candidates/` primero y el resto por hitos, pero es un riesgo de calendario, no solo técnico.

### 5.2 Puntos de confusión que hay que resolver con el negocio antes de construir (no son decisiones técnicas)

- **¿Quién usa el agente de IA?** `company-choice.md` no deja claro si el candidato/cliente habla directamente con el agente, o si es un copiloto interno para consultores/supervisores. La respuesta cambia por completo si `agent/` expone rutas públicas o solo internas — es una decisión de producto que bloquea el diseño de esa superficie de rutas.
- **¿"Consultor" y "supervisor" son el mismo portal con permisos distintos, o dos aplicaciones separadas?** Afecta si `selection` y `support` comparten un único dashboard interno o dos, y por tanto cuántos canales de websocket y esquemas de rol hacen falta.
- **Definición operativa de "estado en tiempo real" del candidato.** Sin una lista cerrada de estados y qué evento dispara cada transición, el módulo `selection` no puede definir su modelo de datos ni el contrato de `realtime/`.
- **Definición de SLA de tickets**, incluida la diferencia horaria entre la oficina de Valencia y la de Miami — sin esto, `support.service` no puede calcular cuándo un ticket está en riesgo de incumplimiento.
- **Alcance de idioma del agente/chatbot.** `CONTEXT.md` deja el multiidioma como opcional para el sitio, pero no dice si la base de conocimiento del chatbot y el scoring de CVs deben operar en español, inglés, o ambos — afecta directamente el diseño del RAG en `pgvector`.

---

## 6. Próximo paso

Antes de escribir el primer endpoint, resolver los puntos de la sección 5.2 con el stakeholder correspondiente (Carmen Ruiz u otro según el dominio): son ambigüedades de producto, no de arquitectura, pero determinan detalles del modelo de datos de `candidates/` y `support/` que sí son costosos de cambiar una vez construidos.
