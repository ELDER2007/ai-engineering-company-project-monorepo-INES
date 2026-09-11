# `backoffice` — Nexova internal admin app

Internal admin application for the Nexova team — authentication, candidate
management, vacancy management, internal communications, and other
back-office capabilities (see [`uis/README.md`](../README.md)). Today it's
just the dashboard shell described below; everything else is a disabled
placeholder in the sidebar.

## Stack

Same toolchain as [`uis/website`](../website) (Vite + React 18 + React
Router 6 + Tailwind CSS 4), kept self-contained with its own
`package.json`/`node_modules`. Dev server runs on port **3001** (website
uses 3000) so both apps can run side by side.

The Tailwind theme (`ink-*`/`accent-*` tokens in `src/index.css`) is
deliberately different from the website's (`brand-*`/`accent-*`, indigo +
amber) — a dark slate sidebar + emerald accent, so the internal tool reads
as its own app rather than a reskin of the public site.

## Layout

**Not shared with `uis/website`.** The public site uses a marketing
Header + Footer (`uis/website/src/pages/Layout.jsx`); the backoffice uses
its own sidebar + topbar admin shell:

```
src/pages/Layout.jsx   → <Sidebar/> + <Topbar/> + <Outlet/>
src/components/Sidebar.jsx
src/components/Topbar.jsx
```

## Structure

```
backoffice/
├── index.html           # noindex — internal tool, not public
├── package.json
├── vite.config.js        # port 3001
├── eslint.cjs
├── .env.example
└── src/
    ├── main.jsx
    ├── routes.jsx         # only "/" today
    ├── index.css          # Tailwind import + admin theme tokens
    ├── data/
    │   └── company.js      # literal facts transcribed from CONTEXT.md
    ├── lib/
    │   └── companyStats.js # derived logic over company.js (years in
    │                        # operation, currency formatting) — computed,
    │                        # not hardcoded
    ├── components/
    │   ├── Sidebar.jsx
    │   ├── Topbar.jsx
    │   └── CompanySnapshot.jsx  # renders company.js + companyStats.js
    └── pages/
        ├── Layout.jsx
        └── Dashboard.jsx   # "/" — welcome + CompanySnapshot
```

## Running it

```bash
npm install
npm run dev      # http://localhost:3001
npm run build
npm run lint
```

## Known limitations (v1)

- Sidebar is fixed-width and doesn't collapse on small screens — fine for
  an internal desktop tool for now, worth revisiting if mobile use shows up.
- No auth, no real data source — `Topbar`'s user chip and every disabled
  sidebar item ("Candidatos", "Vacantes", "Formación") are placeholders for
  future modules.

> _Estas instrucciones también están disponibles en [español](./README.es.md)._
