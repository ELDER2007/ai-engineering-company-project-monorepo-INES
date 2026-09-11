# `website` — Sitio público de Nexova

Sitio web corporativo público de Nexova (Hito 1). El contenido y las reglas
de validación deben seguir exactamente [`CONTEXT.md`](../../CONTEXT.md) —
ver [`memory-bank/progress.md`](../../memory-bank/progress.md) para lo que
ya está construido y lo que falta.

## Stack

Estructurado a partir de la plantilla [`react-hello-webapp`](https://github.com/4GeeksAcademy/react-hello-webapp)
de 4Geeks Academy (Vite + React + React Router + patrón de estado global
con reducer), reemplazando Bootstrap por Tailwind CSS — Tailwind es un
requisito explícito del stakeholder en `CONTEXT.md`.

- **Vite 5** — servidor de desarrollo / bundler (se sube desde el Vite 4 de la
  plantilla porque `@tailwindcss/vite` requiere Vite ^5).
- **React 18** + **React Router 6** — el enrutado vive en `src/routes.jsx`.
- **Tailwind CSS 4** (`@tailwindcss/vite`) — tokens de marca (`brand-*`/`accent-*`)
  definidos vía `@theme` en `src/index.css`; reemplázalos por colores de
  marca reales cuando estén disponibles.
- Estado global vía `src/hooks/useGlobalReducer.jsx` + `src/store.js` (React
  Context + `useReducer`), el mismo patrón que la plantilla — hoy solo lo
  usan las páginas de referencia `Demo`/`Single`, no la landing real.

## Estructura

```
website/
├── index.html          # aquí vive el JSON-LD Organization de Schema.org
├── package.json
├── vite.config.js
├── eslint.cjs
├── vercel.json
├── .env.example
└── src/
    ├── main.jsx            # punto de entrada: StoreProvider + RouterProvider
    ├── routes.jsx          # tabla de rutas
    ├── store.js            # reducer + estado inicial (solo Demo/Single)
    ├── index.css           # import de Tailwind + tokens de marca
    ├── hooks/
    │   └── useGlobalReducer.jsx
    ├── components/
    │   ├── Header.jsx      # Header real: logo + nav Inicio/Servicios/Talento/Contacto
    │   ├── Footer.jsx      # Footer real: copyright + LinkedIn/Instagram
    │   ├── Hero.jsx
    │   ├── Services.jsx    # + ServiceCard.jsx (reutilizable)
    │   ├── WhyNexova.jsx   # + StatCard.jsx (reutilizable)
    │   ├── Contact.jsx
    │   └── ScrollToTop.jsx
    ├── pages/
    │   ├── Layout.jsx      # Header + <Outlet/> + Footer
    │   ├── Home.jsx        # "/" — la landing real (Hero, Services, WhyNexova, Contact)
    │   ├── Talent.jsx      # "/talento" — STUB, el formulario real está pendiente (ver abajo)
    │   ├── Demo.jsx        # demo de la plantilla del store global (referencia)
    │   └── Single.jsx      # demo de detalle de la plantilla (referencia)
    └── assets/img/
```

`Demo.jsx`/`Single.jsx` se conservan de la plantilla como ejemplo funcional
del patrón de estado global; bórralos cuando dejen de servir como
referencia. A propósito no están enlazados desde el nav real.

## Cómo ejecutarlo

```bash
npm install
npm run dev      # http://localhost:3000
npm run build
npm run lint
```

Esta app es autocontenida (su propio `package.json`/`node_modules`) — todavía
no está enganchada a un workspace de npm en la raíz del repo (ver los huecos
de tooling documentados en `memory-bank/techContext.md`).

## Pendiente (Hito 1)

Ver [`memory-bank/progress.md`](../../memory-bank/progress.md) para la lista
completa y actualizada. En resumen: el formulario de registro de talento en
`/talento` (hoy es un stub) con sus 11 campos/validaciones/mensajes de error
exactos de `CONTEXT.md`, los mensajes de éxito/redirección, y una revisión
dedicada de accesibilidad/SEO.

> _These instructions are also available in [English](./README.md)._
