# `website` — Nexova public site

Public-facing corporate website for Nexova (Hito 1). Content and validation
rules must follow [`CONTEXT.md`](../../CONTEXT.md) exactly — see
[`memory-bank/progress.md`](../../memory-bank/progress.md) for what's built
and what's next.

## Stack

Scaffolded from 4Geeks Academy's [`react-hello-webapp`](https://github.com/4GeeksAcademy/react-hello-webapp)
template structure (Vite + React + React Router + a global-state reducer
pattern), with Tailwind CSS added in place of Bootstrap — Tailwind is an
explicit stakeholder requirement in `CONTEXT.md`.

- **Vite 5** — dev server / bundler (bumped from the template's Vite 4 because
  `@tailwindcss/vite` requires Vite ^5).
- **React 18** + **React Router 6** — routing lives in `src/routes.jsx`.
- **Tailwind CSS 4** (`@tailwindcss/vite`) — brand tokens (`brand-*`/`accent-*`)
  defined via `@theme` in `src/index.css`; swap them for real brand colors
  when available.
- Global state via `src/hooks/useGlobalReducer.jsx` + `src/store.js` (React
  Context + `useReducer`), same pattern as the template — currently only
  used by the `Demo`/`Single` reference pages, not by the real landing.

## Structure

```
website/
├── index.html          # Schema.org Organization JSON-LD lives here
├── package.json
├── vite.config.js
├── eslint.cjs
├── vercel.json
├── .env.example
└── src/
    ├── main.jsx            # entry point: StoreProvider + RouterProvider
    ├── routes.jsx          # route table
    ├── store.js            # reducer + initial state (Demo/Single only)
    ├── index.css           # Tailwind import + brand theme tokens
    ├── hooks/
    │   └── useGlobalReducer.jsx
    ├── components/
    │   ├── Header.jsx      # real Header: logo + Inicio/Servicios/Talento/Contacto nav
    │   ├── Footer.jsx      # real Footer: copyright + LinkedIn/Instagram
    │   ├── Hero.jsx
    │   ├── Services.jsx    # + ServiceCard.jsx (reusable)
    │   ├── WhyNexova.jsx   # + StatCard.jsx (reusable)
    │   ├── Contact.jsx
    │   └── ScrollToTop.jsx
    ├── pages/
    │   ├── Layout.jsx      # Header + <Outlet/> + Footer
    │   ├── Home.jsx        # "/" — the real landing (Hero, Services, WhyNexova, Contact)
    │   ├── Talent.jsx      # "/talento" — STUB, real form is pending (see below)
    │   ├── Demo.jsx        # template demo of the global store (reference)
    │   └── Single.jsx      # template demo detail page (reference)
    └── assets/img/
```

`Demo.jsx`/`Single.jsx` are kept from the template as a working example of
the global-state pattern; delete them once they're no longer useful as a
reference. They're intentionally not linked from the real nav.

## Running it

```bash
npm install
npm run dev      # http://localhost:3000
npm run build
npm run lint
```

This app is self-contained (its own `package.json`/`node_modules`) — it is
not wired into an npm workspace at the repo root yet (see the tooling gaps
noted in `memory-bank/techContext.md`).

## Pending (Hito 1)

See [`memory-bank/progress.md`](../../memory-bank/progress.md) for the full,
up-to-date list. In short: the talent registration form at `/talento`
(currently a stub) with its exact 11 fields/validations/error messages from
`CONTEXT.md`, the success/redirect messages, and a dedicated
accessibility/SEO pass.

> _Estas instrucciones también están disponibles en [español](./README.es.md)._
