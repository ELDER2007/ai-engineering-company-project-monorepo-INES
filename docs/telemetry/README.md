# Nexova: proyecto de diseno de telemetria

## Que se entrega

Respuesta al RFI de gestion: diseno de telemetria de inventario, autenticacion, navegacion, abandono de flujos, proveedores, incidencias, website, salud tecnica y procesos internos. El catalogo contiene 40 tipos con hipotesis, decision, responsable, prioridad y modo batch/stream; cinco se clasifican como Obligatorio y 35 como Oportunidad identificada. Esta fase es documental: no requiere arrancar el website, el backoffice, la API ni un servidor nuevo.

| Documento | Contenido |
| --- | --- |
| [telemetry-plan.md](telemetry-plan.md) | RFI, clasificacion de 40 tipos, mapa con 12 puntos, diccionario de 50 claves, allowlist/PII/entrega por evento, frecuencia, riesgos, exclusiones y pruebas de aceptacion. |
| [event-schemas.json](event-schemas.json) | JSON Schema Draft 2020-12 version 2.0.0, envelope del enunciado con sesion/correlacion, validacion de 40 variantes y ocho ejemplos sinteticos. |
| [Cuaderno de aprendizaje](../../aprendiendo%20con%20la%20ia.md#telemetria-plan-de-diseno) | Trabajo realizado, decisiones, problemas encontrados, soluciones, validacion y limites. |

Fuente de requisitos: [briefing completo de Nexova](../../nexova-BRIEFING.es.md). Orientacion del monorepo: [README general](../../README.md).

## Revision de Fase 1

- Metricas obligatorias: los cinco nombres coinciden literalmente con el briefing; entidades, identificadores, categorias, oficinas y monedas se mantienen sin sustituir el dominio de Nexova.
- Flujo completo: acceso autenticado -> carga de inventario -> formulario -> validacion local -> API -> reglas de negocio -> orden confirmada -> confirmacion visible. La seccion 6 del plan incluye diagrama y 12 puntos, con ramas de rechazo y abandono.
- Exploracion adicional: autenticacion, carga de secciones, latencia de API, errores frontend, navegacion y otros dominios; no se limita a cumplir un minimo numerico.
- Regla de oro: todas las filas del catalogo incluyen hipotesis y decision concreta.
- Origen: clasificacion individual de cinco Obligatorio y 35 Oportunidad identificada, independiente de P0/P1/P2.

El envelope exige `eventId`, `timestamp`, `sessionId`, `userId`, `event_type`, `schemaVersion`, `requestId` y `properties`, mas entorno y fuente. Sustituye la primera propuesta local 1.0.0 sin sesion; es un cambio incompatible de contrato, no una migracion desplegada. Hay ejemplos de los cinco eventos de inventario, login fallido, navegacion anonima y proceso sin sesion. No sustituyen las pruebas de integracion.

## Revision de Fases 2 y 3

- Envelope: diez claves obligatorias con descripciones en el JSON; ocho exigidas por el enunciado mas entorno y fuente. Valor null no significa campo opcional.
- Esquemas: cinco metricas obligatorias y 35 eventos adicionales en diez categorias. La taxonomia entidad_accion conserva los nombres literales del briefing.
- Propiedades: seccion 15 del plan con diccionario de 50 claves (nombre, tipo, presencia y descripcion), allowlist individual para 40 eventos y perfil de sensibilidad/sanitizacion previo por evento. Todos los payloads actuales tienen sus claves declaradas como obligatorias y rechazan extras.
- Formato: Draft 2020-12, con format habilitado. No validarlo como draft-07 porque ignoraria unevaluatedProperties en los payloads compuestos.
- Entrega: 16 eventos stream y 24 batch, con justificacion individual por urgencia de la decision, no por preferencia de tecnologia.
- Frecuencia: seccion 16 con debounce de busqueda, deduplicacion de navegacion/flujo, agrupacion de alertas sin eliminar hechos, buffer cliente limitado y backpressure/reintentos del publicador.
- Riesgos y exclusiones: PII indirecta, confidencialidad comercial, volumen, duplicados, reloj, perdida y contratos; ocho grupos de candidatos descartados, con motivo y alternativa. No se considera HMAC como anonimizacion irreversible.

Comprobacion ejecutada para esta revision: las 40 allowlists y sus claves obligatorias coinciden entre schema y matriz; las 50 claves tienen entrada en el diccionario; las 40 filas tienen perfil PII y motivo de entrega; ocho ejemplos siguen siendo validos. La anotacion del envelope tambien se comprobo con 16 casos de campos extra rechazados sobre los ocho ejemplos. No se ha instrumentado ninguna de estas politicas.

## Revision Contra la Rubrica

La seccion 14 del [plan](telemetry-plan.md) contiene la matriz E01-E10 con evidencia para los diez criterios: obligatorios, amplitud, hipotesis/decision, envelope, allowlists, schema, entrega, privacidad, riesgos y precision de implementacion. Es autoevaluacion de diseno, no aprobacion docente ni nota garantizada.

Se ha corregido una incoherencia encontrada durante la revision: el schema de product_created admitia cambios classification/threshold aunque su descripcion exige catalogue. Ahora rechaza ambos en altas y los mantiene permitidos en product_updated. Los nombres, el numero de eventos y las allowlists no cambian; se alinea una restriccion del contrato de diseno 2.0.0 aun no instrumentado.

Resultado de esta revision: diez criterios con evidencia localizada, cinco obligatorios coincidentes con briefing, 40 variantes y allowlists verificadas, 50 claves documentadas, reparto 16 stream/24 batch y ocho ejemplos validos. La bateria actual rechaza 639 casos invalidos: 637 de claves obligatorias/extra y dos de tipo de cambio incorrecto en alta. No incluye pruebas funcionales del backend ni implica aprobacion docente.

## Que Te Corresponde y Que Queda Preparado

### Trabajo Tecnico Preparado Con Copilot

- Plan de las fases 1, 2 y 3, basado en el briefing de Nexova.
- Catalogo de 40 eventos, cinco obligatorios y 35 oportunidades, con hipotesis y decisiones.
- Mapa de inventario con 12 puntos, envelope, schema, allowlists, privacidad y estrategia de entrega.
- README generales en espanol e ingles orientados a portfolio, y registro de decisiones en el cuaderno.
- Comprobaciones locales del schema, ejemplos y coherencia documental. No tienes que instalar servicios ni repetir comandos para esta entrega de diseno.

Validacion final ejecutada sobre el catalogo actual: 40 fixtures de evento validos, ocho ejemplos validos, 637 casos invalidos rechazados (claves obligatorias ausentes y campos extra), clasificacion coincidente y 20 enlaces locales de la entrega resueltos. Esta bateria tiene un alcance distinto al historial de 807 casos sobre 38 variantes: no se suman ni se comparan como una cobertura equivalente. No acredita instrumentacion en produccion.

### Tus Pasos Antes de Entregar

1. Lee el resumen de este README y recorre el plan. Prepara la explicacion de cinco conceptos: por que el stock solo cambia mediante ordenes, diferencia evento/metrica, funcion del envelope/requestId, allowlist y privacidad, y cuando elegir stream o batch.
2. Confirma con tu docente el mecanismo de entrega (enlace de repositorio o PR) y la fecha concreta. El enunciado dice viernes, pero no identifica por si solo una convocatoria. Si exige draft-07 especificamente, avisalo: el contrato actual usa Draft 2020-12 y no debe cambiarse solo el identificador del draft.
3. La publicacion de estos seis documentos ya esta autorizada: rama de entrega, commit, push a origin y PR contra main con titulo `docs: telemetry design plan`. Consulta el enlace de PR registrado al completar la publicacion; la autorizacion no incluye hacer merge ni instrumentar la aplicacion.
4. Una vez publicada, envia el enlace por el canal del curso, responde al feedback del docente y solicita revision. El merge corresponde solo despues de aprobacion y checks; no se da por autorizado por tener documentos locales.

### Decisiones Que Requieren Revision, No Trabajo Manual Tuyo

El baseline de cinco entradas y umbral del 10%, las ventanas de agregacion/abandono, la retencion, los minimos y las alertas son propuestas documentadas. En este proyecto formativo puedes presentarlas al docente como decisiones justificadas; en un caso real deben aprobarlas negocio, tecnologia y privacidad. No necesitas contactar con personas ficticias de Nexova ni configurar Supabase, un colector o un dashboard para esta entrega.

No incluyas contrasenas, JWT, claves de Supabase ni datos personales en la entrega. La implementacion de captura, outbox y almacenamiento es otra fase; no esta pendiente como tarea manual tuya de hoy.

## Como usar la entrega

1. Leer el plan y resolver con negocio las decisiones propuestas (baseline, retencion, calendario y catalogo).
2. Consultar los ejemplos incluidos en la clave `examples` del JSON; no son datos de produccion ni ordenes insertadas.
3. Validar los eventos con un validador Draft 2020-12 con `format` habilitado. Validar tambien las reglas aritmeticas y transaccionales del plan en el servicio.
4. Implementar en una fase posterior los campos faltantes, outbox, captura, almacenamiento y pruebas de integracion. No considerar instrumentados estos eventos por existir la documentacion.

## Validacion local sin servidor

Desde la raiz, comprobar sintaxis con la biblioteca estandar:

```bash
python -m json.tool docs/telemetry/event-schemas.json > /dev/null
```

Si el entorno dispone de `jsonschema`, comprobar el contrato y sus ocho ejemplos:

```bash
python - <<'PY'
import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker

schema = json.loads(Path("docs/telemetry/event-schemas.json").read_text())
Draft202012Validator.check_schema(schema)
validator = Draft202012Validator(schema, format_checker=FormatChecker())
for example in schema["examples"]:
    validator.validate(example)
print(f"Contrato valido; {len(schema['examples'])} ejemplos aceptados")
PY
```

`jsonschema` es una herramienta de comprobacion, no una dependencia nueva de la aplicacion. Si no esta disponible, la comprobacion de sintaxis no sustituye la validacion del contrato.

Historial de comprobaciones: la ampliacion anterior valido ocho ejemplos, 38 variantes y rechazo 807 casos invalidos. La revision de Fase 1 conserva los ocho ejemplos validos y comprueba especificamente dos variantes nuevas (carga de seccion y validacion local), con 17 casos invalidos rechazados. Ademas se verifica la correspondencia de los 40 tipos entre schema/catalogo/clasificacion, los cinco obligatorios contra el briefing y los 12 puntos unicos del flujo. No se afirma haber repetido la bateria de 807 casos sobre las 40 variantes. El comando anterior reproduce schema y ocho ejemplos, no esas baterias locales ni pruebas funcionales de la aplicacion.

## Fuera de alcance

No se han cambiado modelos, endpoints, interfaces, bases de datos ni dependencias. El dataset sugerido (ocho productos, tres programas, 15 entradas y 15 salidas) y las pruebas de integracion estan especificados, no ejecutados. Tampoco se pueden medir matriculas/finalizaciones con estos eventos de inventario. La publicacion documental en una PR no equivale a despliegue: el merge requiere aprobacion y no esta autorizado en esta tarea.