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

➡️ **Continuación:** [AUTH‑03 — recuperar y cambiar la contraseña](./aprendiendo%20con%20la%20ia%20-%20AUTH-03.md) (correo con Resend, tokens de un solo uso, seguridad y problemas resueltos).

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

La API cuenta con **206 tests automatizados** que verifican sus contratos y reglas principales:

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
- ✅ **Tests automatizados** — 206 tests de API que verifican contratos y reglas principales
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

---

---

# 📘 Añadido: AUTH‑03 — recuperar y cambiar la contraseña

> Esta parte se **añade al final** de tu cuaderno sin tocar lo anterior. Cuenta qué se construyó para recuperar y cambiar la contraseña (API, pantallas y correo), las decisiones que se tomaron y los problemas que aparecieron, con lo que se aprende de cada uno.
>
> **Resumen de lo que contiene:** conceptos (token, JWT, hash, enumeración de usuarios) · lo construido · 12 decisiones · 12 problemas resueltos · seguridad · archivos tocados · cómo probarlo · lo que falta · glosario · ejercicios.

### AUTH‑03 · 1. El encargo, en palabras sencillas

Ya se podía entrar (login), registrarse y ver el perfil. Faltaban dos cosas que toda web real tiene:

| Situación | Qué se pidió |
|---|---|
| **"Olvidé mi contraseña"** | Pedir un enlace por correo y elegir una contraseña nueva |
| **"Quiero cambiarla"** (ya estoy dentro) | Escribir la actual, la nueva y repetirla |

Y todo **de punta a punta**: la API, las pantallas y **el envío del correo**.

Las reglas que más importaron (las dio la tarea):

- El enlace del correo **caduca** y **solo sirve una vez**.
- **Nunca** se debe revelar si un email está registrado.
- Las **claves de API** (Resend, SendGrid…) solo en variables de entorno, nunca en el código.

---

### AUTH‑03 · 2. Conceptos que necesitas antes de empezar

#### ✉️ El enlace de recuperación es como una llave de un solo uso
Cuando dices "olvidé mi contraseña", la web no puede preguntarte "¿eres tú?" (precisamente no sabes la contraseña). Así que **demuestras que eres tú porque controlas tu correo**: te mandan un enlace con una llave (el *token*). Quien abre ese enlace puede poner una contraseña nueva. Por eso la llave tiene que ser:

- **Imposible de adivinar** (larga y aleatoria).
- **De caducidad corta** (30 minutos).
- **De un solo uso** (si no, un correo antiguo sería una puerta abierta para siempre).

#### 🔏 JWT firmado
Un JWT es un texto con datos dentro (quién eres, cuándo caduca) y una **firma** hecha con la clave secreta del servidor (`SECRET_KEY`). Si alguien cambia un solo carácter, la firma deja de cuadrar y el servidor lo rechaza. No se puede falsificar sin conocer la clave.

#### #️⃣ Hash
Un *hash* es una "huella" de un texto: de `hola` sale siempre la misma huella, pero **de la huella no se puede volver a `hola`**. Se usa para guardar contraseñas (bcrypt) y, aquí, para guardar los tokens de recuperación: la base de datos guarda solo la huella, así que quien la lea **no puede usar** los enlaces.

#### 🕵️ Enumeración de usuarios
Si la web responde "ese email no existe" a unos y "te hemos enviado un correo" a otros, un atacante puede **descubrir quién tiene cuenta** probando emails. Por eso la respuesta tiene que ser **idéntica** en los dos casos. Es lo que más cuidado exigió.

#### 🌱 Variables de entorno y `.env`
Son ajustes que viven **fuera del código**: claves, direcciones, modos. Se escriben en el archivo `services/api/.env`, que **git ignora** para que nadie suba por error una clave. En el repositorio solo está `.env.example`, una plantilla con los huecos vacíos.

#### 📨 Servicio de correo transaccional
Enviar correos que lleguen a la bandeja (y no a spam) es difícil. Servicios como **Resend** o **SendGrid** lo hacen por ti: tú les envías el mensaje con una **API key** y ellos lo entregan.

---

### AUTH‑03 · 3. Cómo se trabajó

1. **Leer antes de escribir.** Se revisó cómo estaba hecho el login (JWT, TinyDB, tests) para seguir el mismo estilo y no inventar otro.
2. **Primero la API, luego las pantallas.** La parte de seguridad es la que no admite errores; las pantallas dependen de ella.
3. **Tests a la vez que el código.** Cada regla (caduca, un solo uso, siempre 200…) tiene su test. Al final: **206 tests** de la API.
4. **Probar en un navegador de verdad** con Playwright (el test `e2e:password`), no solo mirar el código.
5. **Revisar el resultado con capturas de pantalla** de cada pantalla.

> 💡 **Lección:** un test que nunca ha fallado no demuestra nada. Varias veces se comprobó que un test **fallaría** si la regla se rompiera.

---

### AUTH‑03 · 4. Lo que se construyó, pieza a pieza

#### 4.1 La API (`services/api`)

| Endpoint | ¿Hace falta sesión? | Qué hace |
|---|---|---|
| `POST /auth/forgot-password` | No | Recibe `{email}`. **Siempre responde 200** con el mismo mensaje. Si la cuenta existe y está activa, envía el correo. |
| `POST /auth/reset-password` | No | Recibe `{token, new_password}`. Cambia la contraseña y gasta el token. **400** si está caducado, falsificado o ya usado. |
| `POST /auth/change-password` | **Sí** | Recibe `{current_password, new_password}`. **400** si la actual es incorrecta. |

El camino completo de "olvidé mi contraseña":

```
1. forgot-password  → la API crea un token firmado y guarda SU HUELLA
2. correo           → llega un enlace  /reset-password?token=...
3. reset-password   → la API comprueba firma + caducidad + que no esté usado
4. nueva contraseña → se guarda con bcrypt, el token se borra
5. aviso            → llega un segundo correo: "tu contraseña ha cambiado"
```

#### 4.2 El token de recuperación

Está en `auth/security.py`. Es un JWT con cuatro datos:

```python
claims = {
    "user_id": str(user_uuid),   # de quién es
    "purpose": "password_reset", # para qué sirve (¡importante, ver problema 2!)
    "jti": secrets.token_urlsafe(16),  # identificador aleatorio único
    "exp": expires,              # cuándo caduca (30 min por defecto, entre 15 y 60)
}
```

Y se guarda **solo su huella** (`SHA-256`) en un archivo propio, `auth/db.json`, junto a la fecha de caducidad. "Un solo uso" funciona así: al usarlo, la huella se borra; si alguien lo intenta otra vez, la huella ya no está → **400**.

#### 4.3 El envío de correos (`core/mailer.py`)

Tiene tres "modos", elegidos con `EMAIL_BACKEND`:

| Modo | Para qué |
|---|---|
| `console` (por defecto) | **Desarrollo**: el correo no se envía, se **imprime en la terminal** de la API |
| `resend` | Envío real con la API de Resend (`RESEND_API_KEY`) |
| `smtp` | Cualquier proveedor por SMTP (sirve para SendGrid) |

Detalles que importan:

- Si eliges `resend` y falta la clave, **la API no arranca** (mejor fallar al empezar que el día que alguien olvida su contraseña).
- Los correos se envían **después de responder** al navegador (una *tarea en segundo plano*).
- Si el envío falla por algo pasajero (red, límite de Resend), **reintenta dos veces** (1 s y 3 s después).
- Si falla, el log dice **por qué** (por ejemplo `Resend answered 403: ...`) pero **nunca** imprime el enlace ni la clave.

#### 4.4 Las pantallas (`uis/backoffice`)

| Ruta | Qué hace |
|---|---|
| `/login` | Nuevo enlace **"¿Olvidaste tu contraseña?"** |
| `/forgot-password` | Pide el email. Muestra *"Si esa dirección está registrada, recibirás un enlace en breve."* y **desactiva el formulario** |
| `/reset-password?token=…` | Lee el token de la URL, pide la contraseña dos veces, y si va bien **redirige a `/login`** con un mensaje verde. Si falla, error claro + enlace a `/forgot-password` |
| `/account/change-password` | Contraseña actual + nueva + repetir. **Comprueba que coinciden antes de llamar a la API** |

Las reglas de la contraseña (mínimo 8 caracteres, máximo 72 bytes) están en un solo archivo, `src/lib/password.ts`, que usan el registro y las dos pantallas nuevas. Así no hay tres copias que puedan acabar diferentes.

---

### AUTH‑03 · 5. Las decisiones importantes (y por qué)

**1. Token firmado + huella guardada (las dos cosas).**
El JWT firmado permite rechazar falsificaciones **sin tocar la base de datos**. La huella guardada permite lo que un JWT por sí solo no puede: **gastarlo** (un JWT, una vez emitido, es válido hasta que caduca). Cada técnica cubre lo que le falta a la otra.

**2. Guardar la huella (hash), no el token.**
Si alguien lee `auth/db.json`, solo ve huellas. No puede construir enlaces válidos.

**3. Siempre `200` en `forgot-password`.**
Así no se revela quién tiene cuenta. Y también se unificó el **tiempo**: toda la búsqueda y el envío ocurren *después* de responder.

**4. El enlace sale de `FRONTEND_URL`, no de la petición.**
Si el enlace se construyera con la cabecera `Host` de quien lo pide, un atacante podría pedir un correo "para otra persona" cuyo enlace apunte a **su propia web**. Por eso la dirección viene de la configuración.

**5. Un correo de recuperación por cuenta y minuto.**
Para que nadie pueda llenar el buzón de otra persona con la ruta pública.

**6. Si la contraseña nueva no cumple las reglas, el token NO se gasta.**
Un error de formato no debería obligarte a pedir otro correo. (Decisión nuestra, no venía en la tarea.)

**7. Contraseña de cambio ≠ contraseña actual.**
`change-password` rechaza una nueva igual a la actual (422). Si no, "cambiar" no cambiaría nada.

**8. Contraseña actual incorrecta = `400`, no `401`.**
`401` significa "no tienes sesión válida", y el frontend responde cerrándote la sesión. Si te equivocas al teclear la contraseña actual **no debe expulsarte**. Por eso es `400`.

**9. El token solo vale mientras la contraseña no cambie.**
Cada token guarda una "huella de la contraseña vigente" al crearse. Si cambias la contraseña por otra vía, los enlaces pendientes **mueren solos**.

**10. Aviso por correo tras cada cambio.**
Si alguien entra en tu cuenta y cambia la clave, tú te enteras.

**11. Un archivo aparte para los tokens (`auth/db.json`).**
Un test del proyecto exige que los documentos de usuario tengan siempre los mismos campos. Mejor no tocar esa regla y guardar los tokens en otro sitio.

**12. `console` como modo por defecto.**
Así cualquiera puede desarrollar **sin cuenta de ningún servicio**: copia el enlace de la terminal. Y en producción hay que elegir otro modo a propósito.

---

### AUTH‑03 · 6. Problemas que aparecieron y cómo se resolvieron

#### Problema 1 — La especificación llegó por partes (y yo ya había decidido por mi cuenta)
**Qué pasó:** se pidió "implementa todo" sin la lista de requisitos. Se implementó con decisiones razonables (respuesta `202`, token aleatorio, 30 minutos). Cuando llegó la lista real, pedía **`200`**, token **firmado** y caducidad **entre 15 y 60 minutos**.
**Solución:** se ajustó: `202 → 200`, token aleatorio → JWT firmado, y la configuración rechaza valores fuera de 15–60.
**Lo que se aprende:** cuando falta información, avisar de lo que se ha supuesto. Y escribir el código para que cambiar una decisión sea barato (las constantes `MIN`/`MAX` están en `core/config.py`).

#### Problema 2 — ¡El enlace del correo abría una sesión! (el más grave)
**Qué pasó:** al pasar el token a JWT, se comprobó `GET /auth/me` con el token del correo… y devolvió **200**. Los tokens de sesión solo exigían `user_id` y `exp`, y el de recuperación también los tenía. Resultado: **quien tuviera el enlace podía entrar sin contraseña**.
**Solución:** el token de recuperación lleva `purpose: "password_reset"`, y la comprobación de sesión **rechaza cualquier token que tenga `purpose`**. Y al revés: el de recuperación solo se acepta si trae ese propósito. Hay tests en las dos direcciones.
**Lo que se aprende:** cuando reutilizas un mecanismo (JWT) para algo nuevo, pregúntate **"¿puede esto confundirse con lo antiguo?"**. Esto se encontró **porque se probó a propósito**, no por casualidad.

#### Problema 3 — Se podía adivinar qué emails existían por el tiempo de respuesta
**Qué pasó:** aunque la respuesta era idéntica, con un email **existente** la API tardaba ~1,5 ms más (crear el token, escribir en el archivo). Medido, no supuesto.
**Solución:** todo lo que depende de si la cuenta existe se hace **después** de responder, en segundo plano.
**Matiz honesto:** después de moverlo, el cronómetro del test ya no sirve (el cliente de pruebas espera a la tarea). La mejora está razonada y el test comprueba el contenido idéntico, pero **no se volvió a medir el tiempo real**.
**Lo que se aprende:** la seguridad no es solo lo que dice la respuesta, también **cuánto tarda**.

#### Problema 4 — Un script de edición falló a medias y rompió 19 tests
**Qué pasó:** un script cambiaba varios archivos. Una de las sustituciones no encontró su texto, el script **se paró**… pero antes ya había guardado otros archivos. Quedó el código a medias y fallaron 19 tests.
**Solución:** se leyó el error, se vio qué faltaba y se aplicó lo pendiente. Los 196 tests volvieron a pasar.
**Lo que se aprende:** los errores de un test **leen como una lista de tareas pendientes**. Y los cambios automáticos deben comprobar que encuentran lo que buscan (`assert`) en lugar de continuar en silencio.

#### Problema 5 — Un test fallaba por culpa del propio test
**Qué pasó:** se comprobaba que la contraseña `"short"` no aparecía en la respuesta de error. Pero el mensaje de FastAPI contiene `string_too_short`… que incluye la palabra *short*. El test se asustaba de su propio texto.
**Solución:** usar una contraseña de prueba que no coincida con palabras del mensaje (`"abc-12"`).
**Lo que se aprende:** cuando un test falla, **dos opciones**: el código está mal o el test está mal. Hay que mirar cuál.

#### Problema 6 — El navegador de pruebas no arrancaba
**Qué pasó:** Playwright descargó Chromium, pero al lanzarlo dio `libatk-1.0.so.0: cannot open shared object file`. Faltaban librerías del sistema en el Codespace.
**Solución:** `npx playwright install-deps chromium`.
**Lo que se aprende:** "se instaló" y "funciona" no son lo mismo; el mensaje de error nombra exactamente la pieza que falta.

#### Problema 7 — Los tests del navegador fallaban, pero la app estaba bien
**Qué pasó:** dos fallos del e2e eran del **test**: (a) el enlace del correo lleva la URL pública del Codespace y el test esperaba `localhost`; (b) tras renombrar una ruta, quedaba **una línea con la ruta antigua**.
**Solución:** el test ahora usa la ruta y el token del enlace, y se buscó la ruta antigua en todo el proyecto con `grep`.
**Lo que se aprende:** al renombrar algo, **busca todas las apariciones**. Y no toques la app para "arreglar" un fallo que es del test.

#### Problema 8 — Renombrar una ruta (`/account/password` → `/account/change-password`)
**Qué pasó:** la lista de requisitos nombraba `/account/change-password` y yo había creado `/account/password`.
**Solución:** se renombró la carpeta y se actualizaron el menú, los README y el test.
**Lo que se aprende:** una pequeña diferencia de nombre entre lo pedido y lo entregado es un fallo en una evaluación.

#### Problema 9 — Pegar valores en el `.env`
**Qué pasó:** se pegaron las líneas `SECRET_KEY=…` al principio o al final del archivo, y la API seguía sin ver los valores.
**Solución y explicación:** las variables **ya existían, vacías**; había que **escribir el valor después del `=` en esa misma línea** y guardar (Ctrl+S). Una línea que empieza por `#` es un comentario y se ignora, por eso para activar `EMAIL_FROM` y `RESEND_API_KEY` hay que **quitar el `# `**.
**Detalles que confunden a todo el mundo:**
- La API solo lee el `.env` **al arrancar**: tras cambiarlo, reiníciala (Ctrl+C y a lanzarla de nuevo).
- El comando `.venv/bin/uvicorn …` solo funciona **desde `services/api`**, porque `.venv` está ahí. Desde la raíz da `No such file or directory`.

#### Problema 10 — El PR no se podía crear
**Qué pasó:** `gh pr create` falló con "No commits between main and feature/password-reset", aunque la rama sí tenía commits.
**Causa:** tu repositorio es un **fork** de otro (`4GeeksAcademy/...`), y la herramienta apuntaba por defecto al original.
**Solución:** indicar el repositorio con `--repo ELDER2007/...`. Al diagnosticar se creó un PR con el texto "test"; **se sustituyó enseguida** por la descripción real.
**Lo que se aprende:** cuando un error no tiene sentido, **comprueba lo que supones** (¿a qué repositorio está apuntando?) antes de reintentar lo mismo.

#### Problema 11 — "Could not send the email" sin decir por qué
**Qué pasó:** en tu terminal salió `Could not send the email` después de cambiar la contraseña. Probablemente falló el correo de aviso. Pero el mensaje **no decía el motivo**, y yo no podía ver tu terminal.
**Qué se hizo:**
1. Se **reprodujo** el envío con tu configuración: funcionó. Así que no era un fallo fijo, sino puntual (red o límite de Resend). **No se pudo confirmar la causa.**
2. Se mejoró el código para que, la próxima vez, el log diga **el motivo exacto** de Resend.
3. Se añadieron los **reintentos** para los fallos pasajeros.
**Lo que se aprende:** un mensaje de error sin causa es un problema por sí mismo. **Mejorar los mensajes** es arreglar.

#### Problema 12 — El PR #13 aparecía cerrado
Se detectó al revisar el proyecto: estaba cerrado sin fusionar. Al intentar crear uno nuevo, GitHub dijo que ya había uno abierto: se había reabierto. Lo importante: **comprobar el estado real antes de actuar**, no suponerlo.

---

### AUTH‑03 · 7. Seguridad: lo que hay que tener claro

| Regla | Cómo se cumple |
|---|---|
| El token caduca | `exp` dentro del JWT (15–60 min) **y** fecha guardada. Hay un test que aísla cada una |
| No se reutiliza | Se guarda la huella y se borra al usar |
| Nunca revelar si un email existe | Misma respuesta, mismo cuerpo, y el trabajo va después de responder |
| La clave de API solo en el entorno | Se lee con `os.environ`; `.env` está en `.gitignore`; se buscaron claves en el repositorio y no hay |
| El token no sirve como sesión | Claim `purpose` rechazado por la comprobación de sesión |
| Contraseñas nunca en claro | bcrypt, como el resto del proyecto |
| El 422 no devuelve tu contraseña | El manejador de errores quita el campo `input` en rutas `/auth` |

**⚠️ Una clave de API es como una contraseña:** no la pegues en un chat, en el código ni en un commit. Si se te escapa, bórrala en el panel del servicio y crea otra.

---

### AUTH‑03 · 8. Archivos que se tocaron

**API (`services/api`)**
- `auth/router.py` — los tres endpoints nuevos
- `auth/service.py` — la lógica (crear/validar tokens, cambiar contraseña)
- `auth/security.py` — creación y verificación del token firmado
- `auth/schemas.py` — formatos de entrada
- `auth/emails.py` — el texto de los correos (texto plano + HTML, con el nombre escapado)
- `core/mailer.py` — **nuevo**: envío por `console` / `resend` / `smtp`, con reintentos
- `core/config.py` — caducidad (15–60), `FRONTEND_URL`, ruta de `auth/db.json`
- `users/service.py` — `set_password` (cambiar contraseña sin pedir la actual, solo para el reset)
- `main.py` — comprobaciones al arrancar
- `tests/test_password.py` — **nuevo**: los tests de todo esto
- `.env.example`, `.gitignore`, `README.md`

**Backoffice (`uis/backoffice`)**
- `src/views/ForgotPasswordPage.tsx`, `ResetPasswordPage.tsx`, `ChangePasswordPage.tsx` — **nuevos**
- `src/app/(public)/forgot-password`, `reset-password` y `src/app/(app)/account/change-password` — las rutas
- `src/components/AuthShell.tsx` — la tarjeta común de las páginas públicas
- `src/lib/password.ts` — reglas de contraseña compartidas
- `src/lib/api.ts`, `LoginPage.tsx`, `Layout.tsx`, `RegisterPage.tsx`
- `e2e/password.e2e.mjs` — **nuevo**: prueba en un navegador real

**Commits en la rama `feature/password-reset`:** `474fc8d` (API), `49ccbd6` (pantallas), `6da0ac5` (reintentos y motivo del fallo), `a471646` (validación del analizador, web pública y documentación).

---

### AUTH‑03 · 9. Cómo verlo funcionando

**Terminal 1 — la API** (desde `services/api`):
```bash
cd services/api
.venv/bin/uvicorn main:app --reload --port 8000
```

**Terminal 2 — la web** (desde la raíz):
```bash
npm run dev:backoffice
```

**Probar la recuperación:**
1. En `/login`, pulsa **"¿Olvidaste tu contraseña?"**.
2. Escribe tu email y pulsa **Enviar enlace**.
3. Con `EMAIL_BACKEND=console`, el correo **aparece en la terminal de la API**; con `resend`, llega a tu bandeja (mira también en spam).
4. Abre el enlace, escribe la contraseña nueva dos veces y guarda.
5. Te lleva a `/login` con un mensaje verde. Entra con la nueva.

**Correr los tests:**
```bash
cd services/api && .venv/bin/python -m pytest -q      # 206 tests de la API
cd uis/backoffice && npm run e2e:password             # en un navegador real (API y web arrancadas)
```

**Para usar Resend de verdad**, en `services/api/.env`:
```
EMAIL_BACKEND=resend
RESEND_API_KEY=re_…tu clave…
EMAIL_FROM=onboarding@resend.dev
```
(Con ese remitente de pruebas, Resend solo te deja enviar **al email de tu propia cuenta**.)

---

### AUTH‑03 · 10. Lo que NO está hecho

Saber qué falta es tan importante como saber qué hay:

- **Correo real con SendGrid:** no existe un modo propio (se puede usar `smtp` con `smtp.sendgrid.net`, pero no se ha probado). Resend sí se probó contra un servidor real, y el envío al correo de tu cuenta funcionó.
- **Cambiar la contraseña no cierra las sesiones ya abiertas.** El JWT de sesión es "sin estado": vale hasta que caduca (30 min). Cerrarlas exigiría un cambio de diseño.
- **No hay límite de intentos** en el login ni en `change-password`. En `forgot-password` solo se limita el número de **correos por cuenta**, no el de peticiones.
- **El registro (`POST /users`) sigue diciendo `409` si el email ya existe**, lo que sí revela que la cuenta existe. Arreglarlo cambia cómo funciona el alta.
- **El remitente `onboarding@resend.dev`** hace que los correos caigan fácilmente en spam. Para producción hay que **verificar un dominio propio**.

---

### AUTH‑03 · 11. Glosario

| Palabra | Significa |
|---|---|
| **Token** | Texto que actúa de "llave" o "pulsera" |
| **JWT** | Token con datos dentro y una firma que impide falsificarlo |
| **Hash / huella** | Resumen irreversible de un texto |
| **bcrypt** | Forma lenta y segura de hacer el hash de contraseñas |
| **Enumeración de usuarios** | Descubrir quién tiene cuenta por cómo responde la web |
| **Un solo uso** | Un token que deja de valer en cuanto se usa |
| **Tarea en segundo plano** | Algo que se hace *después* de responder al navegador |
| **Variable de entorno** | Ajuste que vive fuera del código (en `.env`) |
| **API key** | Contraseña de tu programa para usar un servicio externo |
| **Backend de correo** | La forma elegida de enviar emails (`console`, `resend`, `smtp`) |
| **SMTP** | Protocolo estándar para enviar correo |
| **Fork** | Copia de un repositorio ajeno en tu cuenta |
| **PR (Pull Request)** | Petición para fusionar tu rama en `main` |
| **e2e** | Prueba "de punta a punta", con un navegador real |
| **401 / 400 / 422 / 200 / 204** | Sin sesión / petición mala / datos inválidos / OK con cuerpo / OK sin cuerpo |

---

### AUTH‑03 · 12. Ejercicios para practicar

1. **Cambia la caducidad.** Pon `PASSWORD_RESET_EXPIRE_MINUTES=15` en el `.env`, pide un enlace y comprueba que el correo dice "15 minutos". Prueba con `10`: ¿qué pasa al arrancar la API y por qué?
2. **Rómpelo a propósito.** Pide un enlace, úsalo, y vuelve a abrirlo. ¿Qué ves? Cambia una letra del token y ábrelo: ¿qué ves y por qué es el mismo mensaje?
3. **Mira la huella.** Pide un enlace y abre `services/api/auth/db.json`. ¿Puedes reconstruir el enlace con lo que hay ahí? ¿Por qué es bueno que no se pueda?
4. **Compara respuestas.** Con `curl`, llama a `forgot-password` con tu email y con uno inventado. ¿En qué se parecen las respuestas?
5. **Lee un test.** Abre `tests/test_password.py` y busca `test_a_session_token_is_not_a_reset_token_and_the_other_way_round`. Con tus palabras: ¿qué fallo grave evita?
6. **Reto de diseño.** El registro dice `409` si el email existe, lo que revela cuentas. ¿Cómo lo cambiarías sin que el usuario pierda la información de que "ese email ya está usado"? (Pista: piensa en qué podría decirse **por correo** en vez de en pantalla.)
7. **Pregúntate siempre:** *"¿Y si alguien quisiera abusar de esto?"* Aplícalo al `change-password`: ¿qué pasaría si no pidiera la contraseña actual?

---

> 🌟 **Lo más importante de toda la tarea:** el mayor fallo (el enlace que abría una sesión) **no lo encontró un test que ya existía**: se encontró porque alguien se preguntó *"¿y si usara este token donde no debe?"* y lo **probó**. Aprende a desconfiar de tu propio código con cariño.
