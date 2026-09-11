# `backoffice` — Aplicación interna de administración de Nexova

Aplicación interna de administración para el equipo de Nexova —
autenticación, gestión de candidatos, gestión de vacantes, comunicación
interna y otras capacidades de back-office (ver
[`uis/README.es.md`](../README.es.md)). Hoy es solo el shell del dashboard
descrito abajo; todo lo demás es un placeholder deshabilitado en el sidebar.

## Stack

El mismo toolchain que [`uis/website`](../website) (Vite + React 18 + React
Router 6 + Tailwind CSS 4), autocontenido con su propio
`package.json`/`node_modules`. El servidor de desarrollo corre en el puerto
**3001** (website usa el 3000) para que ambas apps puedan correr a la vez.

El tema de Tailwind (tokens `ink-*`/`accent-*` en `src/index.css`) es
deliberadamente distinto al del website (`brand-*`/`accent-*`, índigo +
ámbar) — sidebar gris oscuro + acento esmeralda, para que la herramienta
interna se lea como su propia app y no como un reskin del sitio público.

## Layout

**No se comparte con `uis/website`.** El sitio público usa un Header +
Footer de marketing (`uis/website/src/pages/Layout.jsx`); el backoffice usa
su propio shell de administración con sidebar + topbar:

```
src/pages/Layout.jsx   → <Sidebar/> + <Topbar/> + <Outlet/>
src/components/Sidebar.jsx
src/components/Topbar.jsx
```

## Estructura

```
backoffice/
├── index.html           # noindex — herramienta interna, no pública
├── package.json
├── vite.config.js        # puerto 3001
├── eslint.cjs
├── .env.example
└── src/
    ├── main.jsx
    ├── routes.jsx         # hoy solo existe "/"
    ├── index.css          # import de Tailwind + tokens del tema admin
    ├── data/
    │   └── company.js      # datos literales transcritos de CONTEXT.md
    ├── lib/
    │   └── companyStats.js # lógica derivada sobre company.js (años
    │                        # operando, formato de moneda) — calculado,
    │                        # no hardcodeado
    ├── components/
    │   ├── Sidebar.jsx
    │   ├── Topbar.jsx
    │   └── CompanySnapshot.jsx  # renderiza company.js + companyStats.js
    └── pages/
        ├── Layout.jsx
        └── Dashboard.jsx   # "/" — bienvenida + CompanySnapshot
```

## Cómo ejecutarlo

```bash
npm install
npm run dev      # http://localhost:3001
npm run build
npm run lint
```

## Limitaciones conocidas (v1)

- El sidebar es de ancho fijo y no colapsa en pantallas chicas — está bien
  para una herramienta interna de escritorio por ahora, vale la pena
  revisarlo si aparece uso desde mobile.
- Sin autenticación, sin fuente de datos real — el chip de usuario del
  `Topbar` y cada ítem deshabilitado del sidebar ("Candidatos", "Vacantes",
  "Formación") son placeholders para módulos futuros.

> _These instructions are also available in [English](./README.md)._
