# 📘 Aprendiendo con la IA — Proyecto Nexova

> **Estudiante:** INES  
> **Proyecto:** Nexova — Consultora de RRHH y Adquisición de Talento  
> **Propósito:** Este documento recoge TODO lo que hemos hecho, las decisiones tomadas, los problemas resueltos y cómo se ha construido cada pieza. Es tu cuaderno de aprendizaje.

---

## 📑 Índice

1. [¿Qué es este proyecto?](#1-qué-es-este-proyecto)
2. [Arquitectura general](#2-arquitectura-general)
3. [El monorepo: un solo repo para todo](#3-el-monorepo-un-solo-repo-para-todo)
4. [Frontend 1: El sitio web (website)](#4-frontend-1-el-sitio-web-website)
5. [Frontend 2: El panel interno (backoffice)](#5-frontend-2-el-panel-interno-backoffice)
6. [Backend: La API](#6-backend-la-api)
7. [El Hero rediseñado](#7-el-hero-rediseñado)
8. [Problemas que encontramos y cómo los resolvimos](#8-problemas-que-encontramos-y-cómo-los-resolvimos)
9. [Tecnologías usadas](#9-tecnologías-usadas)
10. [Comandos útiles](#10-comandos-útiles)
11. [Glosario para estudiante](#11-glosario-para-estudiante)
12. [Consejos finales](#12-consejos-finales)

➡️ **Continuación:** [AUTH‑02 — login, registro y rutas protegidas](./aprendiendo%20con%20la%20ia%20-%20AUTH-02.md) (todo lo hecho, decisiones y problemas resueltos).

---

## Telemetria: plan de diseno

### Encargo y trabajo realizado

Esta entrega comienza leyendo completo [nexova-BRIEFING.es.md](nexova-BRIEFING.es.md), no levantando un servidor. Nexova necesita observar el inventario de formacion, certificaciones y equipos de incorporacion. Se han creado [docs/telemetry/README.md](docs/telemetry/README.md), [telemetry-plan.md](docs/telemetry/telemetry-plan.md) y [event-schemas.json](docs/telemetry/event-schemas.json). Tambien se han actualizado los README generales para enlazar esta fase sin borrar el historial del proyecto.

El plan recoge las entidades Product, InboundOrder, OutboundOrder, oficina y programa; incluye los cinco eventos obligatorios, sus metricas y los responsables de negocio. El JSON es un contrato Draft 2020-12, no una lista informal de nombres: obliga a incluir los campos necesarios y contiene un ejemplo sintetico por evento.

### Que encontramos y como lo resolvimos

Al contrastar los modelos y el servicio de inventario comprobamos que ya hay trazabilidad de ordenes y stock calculado, pero no programa, precios, minimos ni la misma clasificacion del briefing. Las oficinas actuales se escriben `Valencia`/`Miami`, mientras el contrato exige `valencia`/`miami`. La solucion en esta fase es documentar el adaptador y los prerrequisitos, no cambiar el backend fuera del alcance ni afirmar que la captura ya existe.

El briefing menciona metricas pero no define todos sus calculos. Por eso el plan fija reglas comprobables: que significa cantidad en un rechazo, cuando se cruza un minimo, como se calcula el historico de costes, que pasa en un rollback y como evitar duplicados. Tambien distingue lo que valida JSON Schema de lo que solo puede comprobar el servicio con datos y transacciones.

### Decisiones y motivos

| Decision | Motivo y solucion |
| --- | --- |
| Fuente de verdad en backend | Un clic no demuestra una entrega; emitir eventos de exito solo con orden confirmada. |
| Outbox transaccional propuesta | Guardar orden y evento juntos evita perder el evento si el proceso cae tras confirmar la orden. No esta implementada. |
| Alerta solo al cruzar el minimo | Evita repetir alertas por cada salida cuando ya hay poco stock; una reposicion rearma el cruce. |
| Historico de cinco entradas comparables y umbral > 10% | Define un baseline reproducible por producto/proveedor/oficina/moneda; no comparar monedas ni proveedores diferentes. Es una decision de diseno que negocio debe aprobar. |
| Costes en centimos | Evita errores de decimales financieros; Valencia EUR y Miami USD, sin conversion en telemetria. |
| Cantidad cero en un rechazo | No hubo movimiento fisico; no copiar un valor arbitrario enviado por el usuario. |
| Campos cerrados y autor HMAC | Evita exportar nombres, destinatarios y UUID originales; la seudonimizacion no elimina las obligaciones de privacidad. |
| UUID por evento y deduplicacion | Los reintentos no deben aumentar las compras, entregas ni alertas del informe. |
| Matriculas/finalizacion fuera de estas metricas | Entregar un kit no demuestra que una persona se matricule o complete un curso. Haran falta otras fuentes. |
| Conservar documentacion anterior | Los README de raiz orientan sobre la entrega nueva sin eliminar apuntes y entregas anteriores. |

### Verificacion y limites

Las comprobaciones de esta entrega deben validar sintaxis JSON, conformidad del schema, los cinco ejemplos y casos negativos como moneda incorrecta, campos personales extra o propiedades obligatorias ausentes. El comando reproducible para contrato y ejemplos esta en el [README de telemetria](docs/telemetry/README.md#validacion-local-sin-servidor). La validacion del contrato no demuestra instrumentacion en produccion.

Resultado ejecutado en esta entrega: contrato Draft 2020-12 valido, cinco ejemplos aceptados y 90 casos invalidos rechazados. Se comprobaron las seis propiedades comunes y las propiedades especificas obligatorias, moneda/oficina, cantidades negativas, tipo y version desconocidos, fecha invalida y campos extra en envelope y propiedades. Tambien se comprobaron las igualdades de coste y stock y el cruce de umbral de los ejemplos con aserciones adicionales al schema. Se uso `jsonschema` ya disponible, sin instalar dependencias. Estos casos se ejecutaron como comprobacion local; el comando del README reproduce la validacion del contrato y los cinco ejemplos, no toda la bateria negativa.

No se ha arrancado ningun servidor ni alterado modelos, endpoints o dependencias. Quedan para otra fase el enriquecimiento del catalogo, la captura, outbox, almacenamiento, semillas y pruebas de integracion. La retencion, el calendario ejecutivo y el baseline se han marcado como propuestas para aprobacion, no requisitos atribuidos al briefing.

### Ampliacion: responder al RFI completo

El segundo enunciado amplia el alcance: los cinco eventos obligatorios son el piso, no todo el plan. La primera entrega cubria el inventario y no incluia `sessionId`; ademas usaba nombres de envelope distintos. Se ha corregido el contrato antes de instrumentar, no mediante cambios en la aplicacion.

Se ha ampliado el [plan](docs/telemetry/telemetry-plan.md) a 38 tipos que cubren inventario, login/registro/perfil, navegacion y embudos, proveedores, incidencias/analisis, formulario de talento, HTTP, dependencias, errores, procesos internos y fallos de entrega de telemetria. Cada fila expresa hipotesis, decision concreta, responsable, prioridad y batch/stream. Las oportunidades futuras (LMS, lead time, devoluciones, snapshots, Web Vitals, releases e IA) se documentan separadas: no se aceptan como eventos activos sin fuente y contrato.

Se adopta envelope 2.0.0 con `eventId`, `timestamp`, `sessionId`, `userId`, `event_type`, `schemaVersion`, `requestId` y `properties`, mas entorno/fuente. El salto de version deja claro que no es compatible con la primera propuesta. Usuario desconocido y jobs usan null cuando corresponde; inventario conserva autor obligatorio. La correlacion usa cabeceras validadas y no tokens. La sesion analitica rota por cambios de identidad y por inactividad.

Decisiones adicionales: abandono derivado tras 30 minutos sin pasos, provisional hasta 24 horas; procesamiento stream para alertas y batch para tendencias; no recopilar textos buscados ni datos de formularios; el monitor de telemetria debe usar un canal independiente para no producir recursion si falla su propio sink.

Se han revisado puntos concretos del API, login, validacion, sesion y formulario de talento. Encontramos que talento solo confirma en memoria, sin envio al servidor: su evento mide validacion local, no candidatos recibidos. Tambien comprobamos que no existe edicion de productos/stock; `product_updated` queda P2 y un 405 no se interpreta como intento probado de editar stock. Los estados de incidencias se ajustan a open/in_progress/resolved/discarded, sin inventar closed en el gestor operativo.

Verificacion intermedia: 38 variantes validas, 456 casos invalidos rechazados y coincidencia de los 38 nombres entre Markdown y schema; 16 enlaces locales resueltos. Una primera comprobacion fallo porque el generador de datos de prueba omitio las propiedades comunes al combinar `allOf`; se corrigio el generador y se repitio la comprobacion, sin relajar el schema. Los cinco ejemplos iniciales se amplian a ocho para mostrar tambien login anonimo, navegacion sin usuario y job sin sesion. Los resultados de la primera version (90 rechazos) se conservan arriba como historial, no como cobertura del contrato nuevo.

Resultado final de la ampliacion: ocho ejemplos aceptados, 38 variantes validas y 807 casos invalidos rechazados, con coincidencia exacta del catalogo Markdown/JSON. Se retiraron una a una las propiedades obligatorias de envelope y payload; se probaron campos extra, moneda incorrecta, cantidades/tiempos negativos, version anterior, fecha invalida, evento no catalogado, ausencia de sesion en navegador y ausencia de usuario en eventos de inventario. Otro ajuste del generador consistio en no exigir autor a un error tecnico solo por venir de `inventory_api`: modulo de origen no equivale a evento de negocio. Estas comprobaciones se ejecutaron localmente con `jsonschema` existente, sin crear instrumentacion ni dependencias. El README reproduce schema y ocho ejemplos, no la bateria completa de 807 casos ni pruebas funcionales de la aplicacion.

No se han escrito emisores, middleware, colectores ni migraciones. No se ha iniciado servidor ni creado rama, commit o PR. La instruccion del curso de fusionar tras aprobacion se documenta como flujo posterior: no demuestra que exista una PR aprobada para fusionar ahora.

### Revision de Fase 1 a partir de la captura del enunciado

La captura exige hacer visibles dos cosas que antes estaban implicitas: clasificar cada evento por su origen y mapear el recorrido de inventario de principio a fin. Por eso se ha agregado una matriz individual al inicio del plan y un diagrama con 12 puntos (I01-I12) en la seccion 6. No se ha confundido prioridad P0 con requisito obligatorio: hay oportunidades P0 que propone el plan, pero solo cinco eventos proceden del briefing.

Se han leido los formularios reales de entrada y salida para localizar `handleSubmit`, sus validaciones, la llamada al API y la confirmacion. Hallazgo importante: una cantidad mayor al stock mostrado solo avisa, pero se envia para que el servidor compruebe el saldo real. Un aviso no es un rechazo. Ademas, el refresco de stock posterior no debe convertir una orden ya persistida en una orden fallida ni duplicar su evento.

El catalogo pasa de 38 a 40 tipos con dos oportunidades fundamentadas: `section_load_completed` permite saber cuanto tarda el contenido principal y elegir si mejorar cliente o API; `form_validation_failed` observa submits que el navegador bloquea y que, por tanto, nunca llegan a la validacion del servidor. Ambos tienen payload cerrado, restricciones de fuente y sesion, hipotesis, decision, prioridad y modo de procesamiento. No se registra texto de campos ni errores libres. Si coincide con el evento especifico de talento, no se suman como dos intentos.

Validacion ejecutada: schema Draft 2020-12 valido, ocho ejemplos existentes aceptados, dos fixtures nuevos validos y 17 casos invalidos rechazados para los dos tipos nuevos (propiedades ausentes, campos extra, sesion nula, fuente incorrecta y medidas invalidas). Comprobacion documental: 40 nombres coincidentes entre schema/catalogo/clasificacion, exactamente cinco obligatorios iguales a la seccion de metricas del briefing, 35 oportunidades, 12 puntos unicos y 40 filas justificadas. La extraccion inicial del briefing incluia cabeceras/entidades; se limito a la seccion de metricas antes de repetir la comprobacion. Los resultados anteriores de 807 rechazos quedan como historial de las 38 variantes, no como una bateria reejecutada sobre las 40.

Se mantienen las entidades e identificadores de Nexova, y se documentan sus diferencias respecto al backend sin renombrar las entidades operacionales. Se han actualizado los README de raiz y de la entrega. No se ha escrito instrumentacion ni iniciado un servidor: esta fase sigue siendo un diseno para revision.

### README Bilingue Para Portfolio y Busqueda de Empleo

La nueva peticion es presentar el proyecto de forma profesional en espanol e ingles, util para buscar trabajo. Se han actualizado [README.es.md](README.es.md) y [README.md](README.md) con portadas equivalentes: problema de negocio, funcionalidades, tecnologias, tres casos de ingenieria, arquitectura y decisiones, ejecucion local, validacion, alcance, evidencias y creditos.

Problema detectado: los README seguian describiendo el repositorio como una plantilla vacia, lo que ocultaba las aplicaciones ya construidas. Solucion: anteponer una presentacion de portfolio y conservar toda la guia anterior en un bloque desplegable de referencia historica, incluida su atribucion. No se han borrado entregas previas ni presentado una propuesta como una capacidad desplegada.

Los tres casos elegidos se apoyan en evidencias existentes: inventario trazable y control de concurrencia, auditoria de rendimiento con resultados antes/despues y diseno de telemetria de 40 eventos. Las cifras Lighthouse se han contrastado con REPORT.md y se identifican como resultados historicos de laboratorio, no como una medicion realizada ahora ni una garantia de produccion. El proyecto se identifica como formativo de 4Geeks y asistido por IA, sin inventar experiencia laboral, contactos o enlaces de una demo publica.

Los comandos npm se han contrastado con package.json, la preparacion Python con pyproject.toml y las guias del API/backoffice. Se describen los requisitos de credenciales, el fallback SQLite y las limitaciones de TinyDB. La documentacion distingue pruebas disponibles de pruebas ejecutadas: no se han instalado dependencias ni arrancado servicios para esta tarea documental.

Validacion ejecutada: estructura equivalente de ocho secciones en ambos idiomas, 56 enlaces locales resueltos, comandos npm presentes en los scripts reales y un bloque historico desplegable correctamente abierto/cerrado en cada README. Queda guardada la preferencia para proximos proyectos: README en espanol e ingles, enfocados a portfolio y busqueda de empleo, ademas de mantener este registro de decisiones.

### Revision de Fases 2 y 3: Contratos Completos y Estrategia de Entrega

La siguiente captura pide mas que un envelope valido y una etiqueta stream/batch: exige allowlist por evento, detalle de nombre/tipo/presencia/descripcion de las propiedades, tratamiento de datos sensibles y justificacion individual de entrega, ademas de frecuencia, riesgos y exclusiones.

El contrato ya tenia 40 variantes cerradas, pero esa informacion estaba dispersa. Se ha agregado la seccion 15 al plan con un diccionario de 50 claves de payload y una matriz de 40 filas que enlaza evento, categoria, allowlist exacta, perfil PII, modo de entrega y razon operativa. Todas las propiedades actuales del payload son obligatorias para el evento que las admite; userId/sessionId pueden ser null en ciertos contextos pero sus claves del envelope no se omiten. Las descripciones de los diez campos del envelope tambien se han incorporado al propio JSON. Son anotaciones, no cambios de comportamiento ni una nueva version del contrato.

Se conserva Draft 2020-12 porque permite cerrar payloads compuestos con allOf/ref mediante unevaluatedProperties. Usar draft-07 sin adaptar el contrato podria ignorar esa proteccion. La allowlist no basta si un nombre se introduce como ID: el futuro emisor debe resolver IDs autorizados, construir un objeto nuevo y validar antes de emitir. Tampoco se debe guardar en cuarentena el payload invalido completo, pues podria contener el dato que queremos excluir.

Decision de privacidad: HMAC no equivale a anonimato. Todos los eventos pueden ser datos personales seudonimizados o vinculables por usuario/sesion/peticion; incidencias y proveedor pueden enlazar a registros sensibles, y precios son informacion comercial. Los perfiles B/S/U/O/T especifican minimizacion y sanitizacion adicional por evento, ademas del control de acceso y retencion.

Decision de entrega: 16 eventos stream para intervenir durante recepciones, bloqueos, problemas de acceso o fallos tecnicos; 24 batch para mejorar catalogos, perfiles, navegacion y conversion con tendencias. El modo se justifica por urgencia, no por elegir una herramienta. Un envio de red cada cinco segundos no convierte el informe diario en stream.

La seccion 16 documenta debounce trailing de 500 ms en busquedas, deduplicacion de navegacion/hitos, agrupacion de notificaciones sin borrar eventos, buffer cliente limitado y backpressure. Ordenes y seguridad no se descartan para reducir costes. La telemetria del navegador puede perderse por consentimiento, cierre o saturacion: hay que reconocer el sesgo, no llamarlo abandono demostrado. Los gauges/contadores internos no son nuevos event_type aceptados por este schema.

Se agregan riesgos con impacto, mitigacion y comprobacion, y ocho grupos de candidatos descartados: pulsaciones/grabacion, requests/excepciones crudos, texto de busqueda, IP/fingerprinting, actualizacion directa de stock, duplicado de latencia, detalle por recurso y abandono por cierre de pestaña. Se explica que dato/decision alternativa conservamos y por que privacidad, coste o duplicacion justifican excluirlos.

Verificacion ejecutada: schema Draft 2020-12 valido; diez campos del envelope descritos; ocho ejemplos validos y 16 casos extra de campos no permitidos rechazados. Otra comprobacion resuelve los ref/allOf y contrasta las 40 allowlists y required contra las 40 filas del plan; las 50 claves del diccionario coinciden exactamente con la union de propiedades; diez categorias, perfil PII y justificacion de entrega presentes en todos los eventos, con reparto 16 stream/24 batch. No es prueba de instrumentacion ni de cumplimiento legal en produccion. Se actualizan README en espanol e ingles y se conserva el historial de comprobaciones anteriores.

### Reparto de Tareas Para Preparar la Entrega

Se ha pedido distinguir que debe hacer la estudiante y completar lo que corresponde a Copilot. Se ha agregado al README de telemetria una lista operativa: el trabajo tecnico documental esta preparado; la estudiante debe revisar/comprender el plan, confirmar canal/fecha con el docente, autorizar publicacion si quiere que se haga desde aqui y enviar el enlace cuando exista. No necesita configurar servidores, Supabase ni ejecutar de nuevo pruebas para esta fase de diseno.

Comprobacion de estado al preparar esta lista: cambios locales en README.md, README.es.md, este cuaderno y docs/telemetry; rama actual main, sin commit de esta entrega. Hay remoto origin del repositorio ELDER2007 y upstream de la plantilla. La consulta inicial de PR con GitHub CLI no pudo determinar estado porque no hay repositorio predeterminado configurado; eso no demuestra ausencia de PR ni falta de credenciales. No se cambia esa configuracion ni se publica nada de forma implicita.

Se aclara que aprobar retencion, umbrales y calendario es revision de decisiones, no pedir a la estudiante que construya un pipeline fuera de alcance. Las personas del briefing son personajes del caso: en el curso se contrastan propuestas con el docente. Tambien se evita inventar fecha limite o asumir que una PR ya esta aprobada.

Trabajo completado en esta revision: prueba de las 40 variantes con fixtures sinteticos validos, ocho ejemplos aceptados y 637 casos invalidos rechazados al retirar cada clave obligatoria de envelope/payload o anadir un campo email no permitido en ambos niveles. La clasificacion coincide con el catalogo y se resuelven 20 enlaces de la entrega. Esta bateria no es la misma que los 807 casos anteriores, de modo que no se suman ni se atribuye identica cobertura. Se ha usado el validador existente, sin instalar ni arrancar servicios.

La extension de GitHub si muestra una PR abierta titulada "monorepo-nexova 15/8/26". El resultado no proporciona numero, URL ni ramas, y no se ha verificado aprobacion o pertenencia a los cambios locales de telemetria. No se presenta como PR nueva de esta entrega, no se modifica ni se fusiona. La publicacion de los documentos locales sigue pendiente de autorizacion explicita; la lista del README explica como pedirla sin que la estudiante tenga que ejecutar los comandos Git por su cuenta.

### Revision Contra los Diez Criterios de Evaluacion

La captura final aporta la rubrica, no una nueva fase de instrumentacion. Se ha revisado su correspondencia con el plan y agregado una matriz E01-E10 en la seccion 14: cada criterio remite a evidencia concreta y explicita que se comprueba localmente y que queda pendiente de implementacion o aprobacion docente. Los README en espanol e ingles enlazan esa matriz sin prometer nota ni aprobacion.

La revision detecto una incoherencia real: product_created compartia productPayload con product_updated y, por ello, admitia change_kind=classification o threshold, aunque el catalogo define catalogue para un alta. Se ha agregado una constante especifica a la variante de alta, conservando los valores de edicion en product_updated. Es una alineacion del contrato de diseno no instrumentado; no cambia modelos, API, nombres de eventos ni allowlists.

Prueba focal ejecutada: alta con catalogue aceptada, altas con classification/threshold rechazadas, ambas variantes de edicion aceptadas y ocho ejemplos existentes validos. Se mantiene la distincion entre validacion de estructura y reglas transaccionales: el schema no prueba un commit ni el stock real. No se han creado servicios, migraciones, ramas, commits o una PR de esta entrega.

La comprobacion cruzada posterior tambien pasa: diez criterios E01-E10 presentes, cinco obligatorios iguales al briefing, 40 variantes con sus allowlists/required coincidentes, 50 claves del diccionario y perfil PII/justificacion por evento, 16 stream/24 batch, ocho ejemplos y 639 casos invalidos rechazados. Los 639 son la bateria de 637 claves ausentes/extra reejecutada sobre las 40 variantes mas dos regresiones de alta. El historial de 807 de otra bateria permanece separado. Esta autoevaluacion documenta evidencias y limites, no promete nota ni reemplaza la revision docente.

### Preparacion de la Publicacion Para la Entrega

La captura de "Como Entregar" pide una PR contra main titulada exactamente `docs: telemetry design plan`, con numero de eventos obligatorios/adicionales, categorias y una frase sobre la decision de diseno mas dificil. Se ha leido la guia de creacion de PR y se ha pedido confirmacion antes de crear rama, commit o publicar. La estudiante ha autorizado expresamente publicar los seis documentos en su repositorio, sin hacer merge.

Comprobacion previa: main local y origin/main coinciden en e09d564, con cero commits de diferencia. El destino es ELDER2007/ai-engineering-company-project-monorepo-INES, no el remoto upstream de 4Geeks. Se limita el staging a README.md, README.es.md, este cuaderno y los tres archivos de docs/telemetry; no se incluyen archivos de aplicacion ni credenciales.

La descripcion de PR presentara 40 eventos: cinco obligatorios y 35 oportunidades; diez categorias; envelope, allowlists, privacidad, batch/stream, riesgos y comprobaciones. La decision mas dificil se resume como separar hechos confirmados en backend de senales de navegador potencialmente incompletas sin perder trazabilidad ni exponer datos personales. Se han actualizado las notas de autorizacion/publicacion actuales, conservando las anotaciones anteriores como historial.

### Conceptos aprendidos

- Evento: hecho de negocio ocurrido; metrica: calculo agregado sobre esos hechos.
- Envelope: campos comunes que identifican y contextualizan todos los eventos.
- JSON Schema: contrato verificable de estructura y tipos, no motor de reglas transaccionales.
- Outbox: registro persistente de eventos pendiente de entrega, guardado junto con la operacion.
- Idempotencia: repetir una operacion o entrega sin duplicar su efecto.
- Baseline: referencia historica definida para comparar un precio nuevo.

---

## 1. ¿Qué es este proyecto?

Nexova es una **consultora de recursos humanos** fundada en 2011 en Valencia, España, con oficina en Miami. Tiene 3 líneas de negocio:

- **Headhunting ejecutivo** — buscar talento para empresas
- **Outsourcing de atención al cliente** — equipos para empresas tech
- **Formación corporativa** — cursos de liderazgo y soft skills

Nosotros hemos construido:

| Pieza | ¿Qué es? | Para quién |
|---|---|---|
| **Website** | La página web corporativa que ve el público | Clientes y candidatos |
| **Backoffice** | Un panel interno con herramientas | Empleados de Nexova |
| **API** | El "cerebro" que procesa datos y da respuestas | Los dos frontends la usan |

Todo esto forma un **monorepo** (un solo repositorio con varios proyectos dentro).

---

## 2. Arquitectura general

### 🏗️ ¿Cómo se conecta todo?

```
Usuario navegando  ──▶  Website (:5173) ──▶  API (:8000) ──▶  TinyDB (base de datos)
Empleado Nexova    ──▶  Backoffice (:5174) ──▶  API (:8000) ──▶  TinyDB
```

**Patrón usado: Frontend + Backend separados (API REST)**

Esto significa que:
- El frontend (lo que ves en el navegador) es **independiente** del backend (donde están los datos)
- Se comunican por HTTP (como cuando visitas una web, pero entre programas)
- El backend expone **endpoints** (URLs tipo `/auth/login`, `/suppliers`, etc.)
- El frontend llama a esos endpoints con `fetch()` (JavaScript)

### 🧩 Decisiones de arquitectura importantes

| Decisión | Por qué |
|---|---|
| **API en capas** (rutas → servicio → datos) | Separa responsabilidades: las rutas reciben peticiones, los servicios tienen la lógica, y el acceso a datos solo guarda/lee |
| **Monolito modular** | Un solo backend pero organizado por temas (auth, users, suppliers...). Más simple que microservicios |
| **JWT sin sesiones** | El token viaja en cada petición. No hay sesión en el servidor. Más escalable |
| **TinyDB** | Base de datos en archivo JSON. Perfecta para empezar sin instalar PostgreSQL |
| **Vite como bundler** | Next-gen tool para React. Más rápido que Webpack |

---

## 3. El monorepo: un solo repo para todo

### 📁 Estructura de carpetas

```
ai-engineering-company-project-monorepo-INES/
├── uis/                    # Las interfaces de usuario (frontends)
│   ├── website/            # Sitio web público
│   └── backoffice/         # Panel interno
├── services/
│   └── api/                # Backend FastAPI
├── packages/
│   ├── incidents_analyzer/ # Lógica compartida (la usa CLI y API)
│   └── shared/             # Tipos TypeScript compartidos
├── scripts/                # Utilidades (analyze.py)
├── docs/                   # Documentación
├── infra/                  # Cosas de infraestructura
├── package.json            # El package.json RAÍZ del monorepo
└── CONTEXT.md              # El documento con los REQUISITOS del cliente
```

### 📦 ¿Por qué un monorepo?

- Todo está en **un solo lugar** → fácil de encontrar
- Los cambios se ven **todos juntos**
- Compartimos código entre proyectos (ej: `incidents_analyzer`)
- Un solo `npm install` instala todas las dependencias

### 🎯 El package.json raíz

```json
{
  "name": "nexova-monorepo",
  "private": true,
  "workspaces": ["uis/website", "uis/backoffice"]
}
```

**`workspaces`** es la clave mágica de npm: le dice "estos subproyectos comparten dependencias". Así no duplicamos React en cada uno.

---

## 4. Frontend 1: El sitio web (website)

### 🧱 Tecnologías

- **React 19** — Biblioteca para construir interfaces
- **TypeScript** — JavaScript con tipos (menos errores)
- **Vite** — El que "empaqueta" todo para producción
- **Tailwind CSS** — Framework de CSS utility-first
- **Lucide React** — Iconos bonitos

### 📄 Estructura del website

```
uis/website/src/
├── main.tsx        # Punto de entrada: monta React en el DOM
├── App.tsx         # Componente principal: toda la web
├── Hero.tsx        # El Hero (cabecera principal rediseñada)
├── router.tsx      # Enrutador SPA (navegación sin recargar)
├── index.css       # Estilos globales + animaciones
└── vite-env.d.ts   # Tipos para Vite
```

### 🔄 Flujo de una visita al website

1. `index.html` carga `main.tsx`
2. `main.tsx` monta el componente `<App />` en el `<div id="root">`
3. `App.tsx` renderiza: Header → Hero → Servicios → Por qué Nexova → Contacto → Footer
4. Si navegas a `/talento`, App cambia y muestra el formulario en lugar de las secciones

### 📡 Enrutador SPA (Single Page Application)

El archivo `router.tsx` es **nuestro propio enrutador** (no usamos React Router). ¿Por qué? Porque la web es simple y no necesitamos una librería entera.

```tsx
// router.tsx
export const TALENT_PATH = "/talento";

export function Link({ to, onNavigate, children }) {
  const click = (event) => {
    event.preventDefault();
    window.history.pushState(null, "", to); // Cambia la URL sin recargar
    onNavigate();                           // Avisa a App que cambie lo que muestra
  };
  return <a href={to} onClick={click}>{children}</a>;
}
```

**Cómo funciona:** Cuando haces clic en un enlace, en lugar de ir a otra página (que recargaría todo), cambiamos la URL con `pushState` y actualizamos solo el contenido. ¡Más rápido para el usuario!

### 🧪 El formulario de talento

El formulario tiene **11 campos** con validaciones específicas:

```tsx
const validate = () => {
  const errors = {};
  if (data.fullName.trim().split(/\s+/).length < 2)
    errors.fullName = "El nombre debe contener al menos nombre y apellido";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email))
    errors.email = "Ingresa un email válido (ejemplo: nombre@empresa.com)";
  // ... más validaciones
  return errors;
};
```

**Aprendizaje clave:** Las validaciones se hacen **en el frontend** para dar feedback instantáneo al usuario, pero **también en el backend** por seguridad. ¡Nunca confíes solo en el frontend!

### 🏷️ Schema.org para SEO

```json
{
  "@context": "https://schema.org",
  "@type": "Organization",
  "name": "Nexova",
  "description": "Consultora de recursos humanos..."
}
```

Esto es **datos estructurados** que Google entiende. Mejora el SEO (cómo apareces en buscadores). Se inyecta como un `<script type="application/ld+json">` en el HTML.

---

## 5. Frontend 2: El panel interno (backoffice)

> 🔄 **Actualización (AUTH‑02):** el backoffice se **migró de Vite + React Router a Next.js 16 (App Router)**. Esta sección muestra la estructura nueva; los fragmentos de código de más abajo son la **versión original**, más simple, y siguen sirviendo para entender la idea. El detalle de la migración está en [aprendiendo con la ia - AUTH-02.md](./aprendiendo%20con%20la%20ia%20-%20AUTH-02.md#12-segunda-parte-migración-a-nextjs).

### 🧱 Tecnologías

**Next.js 16** (App Router) con React 19, Tailwind y **TypeScript 5.9** (Next.js aún no funciona con TypeScript 7), y **Playwright** para tests e2e.

### 📄 Estructura

```
uis/backoffice/src/
├── app/                     # Rutas de Next.js (cada carpeta = un trozo de la URL)
│   ├── layout.tsx           # Layout raíz: <html> + <AuthProvider>
│   ├── globals.css          # Estilos
│   ├── (public)/            # login/ y register/ (sin sesión)
│   ├── (app)/               # layout.tsx con el portero + inicio, incidents/, suppliers/, account/profile/
│   └── not-found.tsx        # URL desconocida → inicio
├── auth/
│   ├── AuthContext.tsx       # Estado global de autenticación
│   └── RequireAuth.tsx       # Protege rutas (redirige si no logueado)
├── components/
│   ├── Layout.tsx            # Plantilla con header/sidebar
│   ├── incidents/
│   │   ├── CsvUploader.tsx   # Subir CSV de incidentes
│   │   └── MetricsSummary.tsx # Mostrar métricas
│   └── suppliers/
│       ├── SupplierForm.tsx  # Formulario de proveedor
│       └── SupplierRow.tsx   # Fila de proveedor editable
├── lib/
│   ├── api.ts               # Llamadas a la API (fetch con token)
│   ├── token.ts             # Gestión del JWT en localStorage
│   ├── returnTo.ts          # ?next= seguro tras el login
│   └── profileFields.ts     # Límites de los campos del perfil
├── views/                   # Las páginas (componentes de cliente)
│   ├── HomePage.tsx          # Página principal del backoffice
│   ├── LoginPage.tsx         # Login
│   ├── RegisterPage.tsx      # Registro
│   ├── ProfilePage.tsx       # Mi perfil
│   ├── IncidentsAnalysisPage.tsx # Analizador de incidentes
│   └── SuppliersPage.tsx     # Directorio de proveedores
└── types/
    ├── auth.ts
    ├── incidents.ts
    └── suppliers.ts
```

### 🔐 Autenticación (AuthContext + JWT)

El backoffice usa **tokens JWT** para autenticación:

1. El usuario introduce email y contraseña
2. El frontend envía `POST /auth/login` con esos datos
3. La API devuelve un `access_token` (JWT)
4. El frontend guarda el token en `localStorage`
5. En cada llamada a la API, envía el token en el header `Authorization: Bearer <token>`

```tsx
// AuthContext.tsx - El "estado global" de sesión
export function AuthProvider({ children }) {
  const [status, setStatus] = useState("anonymous"); // loading | anonymous | authenticated
  const [user, setUser] = useState(null);

  // Al recargar la página, intenta restaurar la sesión desde el token guardado
  useEffect(() => {
    if (!getToken()) return;
    fetchMe()
      .then(me => { setUser(me); setStatus("authenticated"); })
      .catch(() => { clearToken(); setStatus("anonymous"); });
  }, []);
}
```

### 🛡️ RequireAuth — Proteger rutas

```tsx
// RequireAuth.tsx
function RequireAuth() {
  const { status } = useAuth();
  if (status === "loading") return <Spinner />;
  if (status === "anonymous") return <Navigate to="/login" />;
  return <Outlet />; // Muestra la ruta protegida
}
```

**Patrón de diseño:** Envoltura que verifica autenticación antes de mostrar contenido.

### 📞 Cómo se comunica con la API

El archivo `lib/api.ts` tiene **una función genérica** para llamar a la API:

```tsx
async function apiFetch(path: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  if (response.status === 401 && token) clearToken(); // Token expirado
  return response;
}
```

**Aprendizaje:** Un solo punto de entrada para todas las llamadas. Así:
- Ponemos el token automáticamente
- Detectamos 401 (token expirado) en un solo lugar
- Podemos cambiar la URL base fácilmente

---

## 6. Backend: La API

### 🧱 Tecnologías

- **Python 3.14** — El lenguaje
- **FastAPI** — Framework web moderno y rápido
- **Uvicorn** — Servidor ASGI (el que "corre" la API)
- **TinyDB** — Base de datos JSON (sin instalar nada)
- **python-jose** — Para crear y verificar JWT
- **libpass[bcrypt]** — Para hashear contraseñas
- **pytest** — Para tests

### 📄 Estructura

```
services/api/
├── main.py              # Punto de entrada: crea la app FastAPI
├── pyproject.toml       # Dependencias Python
├── seed.py              # Poblar la base de datos inicial
├── requirements.txt     # Dependencias (alternativa a pyproject)
├── auth/
│   ├── router.py        # Rutas de autenticación (/login, /me)
│   ├── schemas.py       # Modelos de datos (Pydantic)
│   ├── security.py      # Hashing de contraseñas + creación JWT
│   ├── service.py       # Lógica de autenticación
│   ├── dependencies.py  # Funciones reutilizables (get_current_user)
│   └── cli.py           # Comando para crear usuarios desde terminal
├── core/
│   ├── config.py        # Configuración (variables de entorno)
│   └── errors.py        # Manejadores de errores
├── users/
│   ├── router.py        # CRUD de usuarios
│   ├── schemas.py       # Modelo User (Pydantic)
│   └── service.py       # Lógica de usuarios
├── profiles/
│   ├── router.py        # Rutas de perfiles
│   ├── schemas.py       # Modelo Profile
│   └── service.py       # Lógica de perfiles
├── suppliers/
│   ├── router.py        # CRUD de proveedores
│   ├── schemas.py       # Modelo Supplier
│   ├── service.py       # Lógica de proveedores
│   ├── seed_data.py     # Datos iniciales (15 proveedores)
│   └── CONTEXT-suppliers.md  # Documento con requisitos
├── incidents/
│   ├── router.py        # Análisis de incidentes
│   ├── schemas.py       # Modelos
│   └── service.py       # Lógica
└── tests/
    ├── conftest.py      # Configuración de tests (fixtures)
    ├── test_auth.py
    ├── test_users.py
    ├── test_profiles.py
    ├── test_suppliers_endpoints.py
    ├── test_suppliers_validation.py
    └── test_architecture.py
```

### 🏗️ Cómo se crea la app (main.py)

```python
# main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(_: FastAPI):
    # Esto se ejecuta ANTES de que la app empiece a responder
    users_service.bootstrap_first_user()  # Crea admin si no existe
    users_service.migrate_legacy_users()  # Migra datos antiguos
    profiles_service.sync_profiles()      # Sincroniza perfiles
    yield  # La app empieza a funcionar
    # Esto se ejecuta cuando la app se apaga

app = FastAPI(title="Nexova API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], ...)

# Registrar rutas (cada dominio es independiente)
app.include_router(auth_router, prefix="/auth")
app.include_router(users_router, prefix="/users")
app.include_router(suppliers_router, prefix="/suppliers")
```

**Aprendizaje:** FastAPI usa el patrón de **lifespan** para código que corre al inicio/cierre. Los routers se "montan" con un prefijo.

### 🔐 Autenticación (security.py)

```python
# security.py
from passlib.hash import bcrypt
from jose import jwt

def hash_password(password: str) -> str:
    return bcrypt.hash(password)  # Convierte "admin123" en un hash

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.verify(password, hashed)  # Compara sin revelar el hash

def create_access_token(user_id: str) -> str:
    claims = {"user_id": user_id, "exp": datetime.utcnow() + timedelta(minutes=30)}
    return jwt.encode(claims, SECRET_KEY, algorithm="HS256")
```

### 📦 Modelos Pydantic

Los modelos definen **qué forma tienen los datos**:

```python
# suppliers/schemas.py
class SupplierCreate(BaseModel):
    name: str
    country: str  # Solo "Spain" o "USA"
    categories: list[str]  # Mínimo 1
    monthly_rate: float = Field(gt=0)  # Mayor que 0
    currency: str  # "EUR" para Spain, "USD" para USA
    status: str = "active"  # "active" o "suspended"
```

**Ventaja:** FastAPI valida automáticamente los datos que llegan. Si alguien envía `monthly_rate: -100`, devuelve error 422 automáticamente.

### 🔄 Proxy de Vite (Cómo se comunican frontend y backend)

> 🔄 **Actualización:** tras la migración a Next.js, el backoffice hace esto con los **rewrites** de `next.config.mjs`; el website sigue usando el proxy de Vite. La idea es la misma.

```ts
// vite.config.ts del backoffice
export default defineConfig({
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/auth": "http://localhost:8000",
    },
  },
});
```

Esto hace que cuando el frontend llama a `/api/suppliers`, Vite lo reenvía a `http://localhost:8000/api/suppliers`. Así:
- El frontend puede usar rutas relativas (`/api/...`)
- **No hay problemas de CORS** (el navegador lo ve como mismo origen)

### 📝 Tests (pytest)

Tenemos **155 tests** que verifican TODO:

```python
# tests/test_suppliers_validation.py
def test_supplier_must_have_valid_currency():
    """Si el país es Spain, la moneda debe ser EUR"""
    response = client.post("/suppliers", json={
        "name": "Test", "country": "Spain", "currency": "USD",  # ❌ ¡Mal!
        ...
    })
    assert response.status_code == 422  # Error de validación
```

**Aprendizaje clave:** Los tests son como un **seguro**. Si cambias algo y los tests pasan, sabes que no has roto nada. Si un test falla, sabes exactamente qué se rompió.

---

## 7. El Hero rediseñado

### 🎨 La petición

> "Rediseña el hero de nexova con acabado profesional nivel agencia (estilo Stripe/Linear)"

### 🧠 Decisiones de diseño

| Decisión | Por qué |
|---|---|
| **Grid 2 columnas** | Columna izquierda: contenido. Derecha: tarjeta con métricas. Así el ojo del usuario ve primero el mensaje |
| **clamp() en tipografía** | `font-size: clamp(2.25rem, 5vw, 4.5rem)` → El texto se adapta al tamaño de pantalla SIN media queries |
| **Gradient text** | La palabra "excepcionales" tiene gradiente cyan → atrae la atención |
| **Glassmorphism** | La tarjeta derecha tiene `backdrop-filter: blur(12px)` → efecto cristal esmerilado |
| **Grid pattern + glow** | Fondo con cuadrícula sutil + glow radial → textura premium |
| **Animated counter** | "+500" cuenta desde 0 hasta 500 → efecto visual impactante |
| **Animaciones escalonadas** | Cada elemento aparece con un pequeño retraso → la página "respira" |

### 🧩 Componentes del Hero

**AnimatedCounter** — El contador animado:

```tsx
function AnimatedCounter({ target }) {
  const [count, setCount] = useState(0);
  useEffect(() => {
    // Si el usuario prefiere no animación, vamos directo al target
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (mq.matches) { setCount(target); return; }
    // Animación: incrementa cada 16ms (60fps) hasta llegar al target
    const duration = 2000;
    const step = Math.ceil(target / (duration / 16));
    let current = 0;
    const timer = setInterval(() => {
      current += step;
      if (current >= target) { setCount(target); clearInterval(timer); }
      else setCount(current);
    }, 16);
  }, [target]);
  return <span>{count.toLocaleString()}</span>;
}
```

**Aprendizaje:** Respetamos `prefers-reduced-motion` para usuarios con sensibilidad a movimientos. ¡Accesibilidad!

### 🎨 CSS personalizado (index.css)

```css
/* Variables de diseño (design tokens) */
:root {
  --color-brand-400: #67e8f9;   /* Cyan claro */
  --color-brand-500: #22d3ee;   /* Cyan medio */
  --color-brand-600: #0891b2;   /* Cyan oscuro */
  --color-surface: #020617;     /* Fondo casi negro */
}

/* Fondo con cuadrícula (como Stripe) */
.hero-grid-bg {
  background-image:
    linear-gradient(rgba(255,255,255,.02) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,.02) 1px, transparent 1px);
  background-size: 48px 48px;
}

/* Efecto vidrio (glassmorphism) */
.glass-card {
  background: rgba(15, 23, 42, .65);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(103, 232, 249, .15);
  border-radius: 2rem;
}

/* Texto con gradiente */
.gradient-text {
  background: linear-gradient(135deg, var(--color-brand-400), var(--color-brand-600));
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}
```

---

## 8. Problemas que encontramos y cómo los resolvimos

### 🔴 Problema 1: Servicios no funcionaban

**Síntoma:** `localhost:8000` no respondía, los puertos no aparecían en Codespaces

**Causa:** Los servicios no estaban iniciados, y cuando lo estaban, escuchaban solo en `127.0.0.1`

**Solución:**
```bash
# No basta con poner el puerto, hay que decirle que escuche en TODAS las interfaces
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Para Vite (frontend):
npx vite --host
```

**Aprendizaje:** `127.0.0.1` solo es accesible desde dentro de la máquina. `0.0.0.0` es accesible desde fuera. En Codespaces necesitas `0.0.0.0`.

---

### 🔴 Problema 2: ModuleNotFoundError: uvicorn

**Síntoma:** `pip install` no encontraba uvicorn aunque lo habíamos instalado

**Causa:** Estábamos instalando en el Python del sistema, no en el `.venv` del proyecto

**Solución:**
```bash
# 1. Activar el entorno virtual correcto
source .venv/bin/activate

# 2. Instalar dependencias desde pyproject.toml
pip install -e .

# 3. Verificar que se instaló
pip list | grep uvicorn
```

**Aprendizaje:** Los entornos virtuales (`.venv`) aíslan las dependencias. Cada proyecto tiene el suyo. Siempre hay que activarlo con `source .venv/bin/activate`.

---

### 🔴 Problema 3: bcrypt no tenía backend

**Síntoma:** `ValueError: No backends available - bcrypt`

**Causa:** La librería `libpass` necesita el paquete `bcrypt` instalado por separado

**Solución:**
```bash
pip install bcrypt  # El paquete Python nativo de bcrypt
```

**Aprendizaje:** A veces una librería tiene dependencias "opcionales" que no se instalan automáticamente. Siempre leer la documentación.

---

### 🔴 Problema 4: Router.ts contenía JSX

**Síntoma:** TypeScript daba error porque el archivo `router.ts` usaba `<a>` (JSX) pero tenía extensión `.ts`

**Causa:** Los archivos con JSX necesitan extensión `.tsx` (TypeScript + JSX)

**Solución:**
```bash
mv router.ts router.tsx  # Renombrar el archivo
```

**Aprendizaje:** `.ts` = solo TypeScript. `.tsx` = TypeScript + JSX. React siempre necesita `.tsx`.

---

### 🔴 Problema 5: TypeScript se quejaba de importar .tsx

**Síntoma:** `tsc --noEmit` daba error: "An import path cannot end with '.tsx'"

**Causa:** Teníamos `import { Link } from "./router.tsx"` y TypeScript estricto no permite la extensión

**Solución:**
```tsx
// ❌ Mal
import { Link } from "./router.tsx";

// ✅ Bien (sin extensión, Vite la resuelve automáticamente)
import { Link } from "./router";
```

**Aprendizaje:** En proyectos con Vite, las importaciones se hacen **sin extensión**. Vite encuentra el archivo automáticamente.

---

## 9. Tecnologías usadas

### 🌐 Frontend

| Tecnología | Versión | ¿Qué es? | ¿Por qué la usamos? |
|---|---|---|---|
| **React** | 19 | Biblioteca de UI | El estándar para interfaces modernas |
| **TypeScript** | 7 (5.9 en el backoffice) | JavaScript con tipos | Evita errores, mejor autocompletado |
| **Vite** | 8.3 | Bundler / dev server (website) | Más rápido que Webpack, recarga instantánea |
| **Next.js** | 16.3 | Framework de React (backoffice) | Rutas por carpetas, build optimizada; lo pedía AUTH‑02 |
| **Tailwind CSS** | 3.4 | Framework CSS | Escribimos CSS en el HTML, muy rápido |
| **Lucide React** | 1.47 | Iconos | Iconos bonitos y simples |
| ~~**React Router DOM**~~ | ~~7.18~~ | Enrutador del backoffice **hasta la migración a Next.js** | Sustituido por el App Router de Next.js |

### 🐍 Backend

| Tecnología | Versión | ¿Qué es? | ¿Por qué la usamos? |
|---|---|---|---|
| **Python** | 3.14 | Lenguaje de programación | Perfecto para APIs, fácil de aprender |
| **FastAPI** | 0.142 | Framework web | Moderno, rápido, validación automática |
| **Uvicorn** | 0.54 | Servidor | Corre la app de FastAPI |
| **TinyDB** | 4.9 | Base de datos | Archivo JSON, no necesita instalación |
| **python-jose** | 3.3 | JWT | Crear tokens de autenticación |
| **libpass[bcrypt]** | 1.9 | Hashing de contraseñas | Guardar contraseñas seguras |
| **pytest** | 8 | Tests | Verificar que todo funciona |

### 🔧 Herramientas

| Herramienta | ¿Para qué? |
|---|---|
| **npm** | Gestor de paquetes JavaScript |
| **pip** | Gestor de paquetes Python |
| **uv** | Gestor de Python alternativo, más rápido |
| **Playwright** | Tests e2e (emula navegador) |
| **GitHub Codespaces** | Entorno de desarrollo en la nube |

---

## 10. Comandos útiles

### 🚀 Para trabajar con el proyecto

```bash
# === FRONTENDS ===

# Iniciar website en modo desarrollo
cd uis/website && npm run dev

# Iniciar backoffice en modo desarrollo
cd uis/backoffice && npm run dev

# Build de producción (genera carpeta dist/)
cd uis/website && npm run build

# Verificar TypeScript sin errores
cd uis/website && npx tsc --noEmit

# === BACKEND ===

# Activar entorno virtual
cd services/api && source .venv/bin/activate

# Iniciar API
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Ejecutar tests
cd services/api && python -m pytest tests/ -v

# Crear usuario desde terminal
uv run create-user --email usuario@example.com

# === GENERAL ===

# Ver qué puertos están escuchando
lsof -i -P -n | grep LISTEN

# Ver logs de un puerto específico
lsof -i :8000
```

### 🔍 Probar la API con curl

```bash
# Health check
curl http://localhost:8000/health

# Login (obtener token)
curl -X POST http://localhost:8000/auth/login \
  -d 'username=admin@nexova.com&password=admin123'

# Obtener perfil con token (cambia TOKEN por el real)
curl http://localhost:8000/auth/me \
  -H "Authorization: Bearer TOKEN"

# Listar proveedores
curl http://localhost:8000/suppliers \
  -H "Authorization: Bearer TOKEN"
```

---

## 11. Glosario para estudiante

### 🧪 Términos técnicos

| Término | Significado simple |
|---|---|
| **API** | Un programa que recibe peticiones y devuelve respuestas. Como un camarero: tú pides (petición), él trae (respuesta) |
| **Endpoint** | Una URL específica de la API. Ej: `/auth/login`, `/health` |
| **JWT** | Un "token" (cadena de texto) que prueba quién eres. Como una pulsera de un concierto |
| **JSON** | Formato de datos. `{"nombre": "Juan", "edad": 30}` |
| **CORS** | Mecanismo de seguridad del navegador. Permite o bloquea peticiones a otros dominios |
| **DOM** | La representación de la web en el navegador. Lo que ves |
| **SPA** | Single Page Application. Web que no recarga al navegar |
| **Hash** | Transformar una contraseña en un código irreconocible. No se puede revertir |
| **Middleware** | Función que se ejecuta entre la petición y la respuesta. Como un filtro |
| **Fixture (test)** | Datos de prueba preparados antes de ejecutar un test |
| **Proxy** | Un intermediario. Vite hace de proxy entre frontend y backend |
| **Bundler** | Programa que empaqueta código JS/CSS para producción. Vite es uno |
| **Dependency Injection** | Pasar dependencias a una función en lugar de crearlas dentro |

### 🧱 Patrones de diseño

| Patrón | Explicación |
|---|---|
| **Arquitectura en capas** | Separar el código en capas: rutas → servicios → datos. Cada capa tiene una responsabilidad |
| **Monolito modular** | Un solo programa pero organizado en módulos independientes |
| **Provider Pattern** | Un componente que provee datos/estado a todos sus hijos (ej: AuthContext) |
| **Outlet/Layout pattern** | Una plantilla que envuelve el contenido (header, sidebar) |

---

## 12. Consejos finales

### 🎯 Para aprender de este proyecto

1. **Lee el CONTEXT.md primero** — Es el documento con los requisitos del "cliente". Todo el proyecto se construye para cumplir ese documento.

2. **Entiende el flujo completo** — Una petición empieza en el navegador del usuario, va al frontend (React/Vite), luego al backend (FastAPI), luego a la base de datos (TinyDB), y vuelve. Traza ese camino.

3. **Los tests son tu red de seguridad** — Si cambias algo y los tests pasan, estás bien. Si no hay tests para una funcionalidad, ten cuidado.

4. **Aprende a leer errores** — Los errores de TypeScript, Python, etc. dicen exactamente qué está mal. La línea y el mensaje son pistas.

5. **Un problema a la vez** — Cuando algo falla, cambia UNA sola cosa y prueba. No tres cosas a la vez.

### 💡 Lo que hace que este proyecto sea profesional

- ✅ **Separación de responsabilidades** — frontend ≠ backend ≠ base de datos
- ✅ **Validaciones en ambos lados** — frontend (UX rápida) + backend (seguridad)
- ✅ **Tests automatizados** — 155 tests que verifican que todo funciona
- ✅ **Accesibilidad** — aria-labels, focus-visible, prefers-reduced-motion
- ✅ **SEO** — Schema.org markup, HTML semántico
- ✅ **Código compartido** — incidents_analyzer lo usan CLI y API
- ✅ **Autenticación segura** — JWT + bcrypt + sin sesiones
- ✅ **Configuración por entorno** — Variables de entorno (SECRET_KEY, etc.)

### 📚 Próximos pasos para seguir aprendiendo

1. Añade tests para los componentes React (Cypress, Testing Library)
2. Implementa multi-idioma (i18n) como sugiere el CONTEXT.md
3. Conecta a una base de datos real (PostgreSQL) en lugar de TinyDB
4. Añade un dashboard con gráficos (Recharts, D3.js)
5. Despliega en producción (Vercel + Railway/Render)

---

> **Este documento es tuyo.** Léelo, modifícalo, hazte preguntas. Cada línea de código que ves aquí es el resultado de decisiones, pruebas, errores y correcciones. Eso es programar. ¡Sigue así! 🚀