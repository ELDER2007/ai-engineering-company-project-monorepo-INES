# Project Brief — Nexova

> Fuente primaria: [`CONTEXT.md`](../CONTEXT.md) (briefing completo de la empresa) y [`company-choice.md`](../company-choice.md) (elección de departamentos del estudiante). Este archivo resume ambos para que cualquier agente tenga el "por qué" del proyecto sin tener que releerlos enteros.

## El negocio

**Nexova** es una consultora de recursos humanos y adquisición de talento fundada en 2011, con sede en Valencia (España) y una oficina de expansión en Miami (Florida). ~120 empleados, ~8M USD de facturación anual. Clientes: empresas medianas de tecnología, retail y servicios financieros.

Tres líneas de negocio:

1. **Headhunting ejecutivo y de mandos medios** — búsqueda y selección de perfiles, proceso personalizado con garantía de reemplazo.
2. **Outsourcing de atención al cliente** — equipos especializados para empresas tecnológicas, formación continua y supervisión dedicada.
3. **Formación corporativa** — programas de soft skills y liderazgo, presenciales y en línea.

## El equipo y el problema (Hito 1)

Trabajamos para el equipo de **Marketing y Comunicaciones**, liderado por **Carmen Ruiz** (Head of Marketing). El sitio web corporativo actual es de 2019, no ha tenido actualizaciones, es lento, no es accesible y no refleja el posicionamiento actual de la empresa.

Problema concreto: **no existe un sistema para capturar leads**. Las personas interesadas en oportunidades laborales envían un email genérico a `info@nexova.com`, sin ninguna estructura — "un caos" según la propia Carmen.

## Objetivo del Hito 1

Construir un sitio web corporativo moderno que:

- Presente profesionalmente quién es Nexova, qué hace y por qué las empresas la eligen (landing page con Header, Hero, Servicios, "Por qué Nexova", Contacto y Footer — contenido exacto en `CONTEXT.md`).
- Capture información de candidatos potenciales de forma **estructurada**, mediante un formulario de registro de talento (datos de contacto, experiencia, sector de interés, nivel de inglés, disponibilidad, LinkedIn opcional, comentarios, consentimiento de datos) con validaciones y mensajes de error específicos.
- Sea responsive, accesible y esté optimizado para SEO (incluye marcado Schema.org tipo `Organization`).
- Use Tailwind para el diseño (pedido explícito del stakeholder).
- Deje claro que el formulario es para **profesionales que buscan empleo**, no para empresas que buscan contratar servicios de Nexova (mensaje de redirección a `contacto@nexova.com` si aplica).

El soporte multiidioma es opcional pero recomendado (operación España + Miami); si se implementa, no debe restar calidad al idioma base.

## Foco adicional del estudiante (más allá del Hito 1)

Según `company-choice.md`, el estudiante eligió profundizar en dos departamentos a lo largo del curso:

- **Operaciones de Selección**: subida/filtrado/ranking automático de CVs, buscador de candidatos con filtros, portal de estado en tiempo real para candidatos, dashboard para consultores.
- **Atención al Cliente**: chatbot de soporte, sistema de tickets, dashboard de carga de trabajo en tiempo real, análisis de sentimiento básico para detectar clientes insatisfechos.

Idea de agente de IA a futuro: un **Agente Inteligente de Selección y Soporte** que combine scoring/ranking de candidatos + soporte conversacional de primera línea con base de conocimiento y detección de insatisfacción. Esto es la visión a mediano plazo del estudiante, no un requisito del Hito 1 — sirve para no diseñar el Hito 1 de forma que choque con esa dirección futura (p. ej., mantener los modelos de candidato/vacante reutilizables).

## Quién manda en caso de conflicto

Si algo aquí entra en conflicto con `CONTEXT.md`, **`CONTEXT.md` gana** — es la fuente única de verdad del dominio (campos, validaciones, copy, mensajes de error exactos).
