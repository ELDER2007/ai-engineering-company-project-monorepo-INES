# Nexova API (`services/api`)

Centralized FastAPI backend for Nexova, per [docs/ARCHITECTURE_PROPOSAL.md](../../docs/ARCHITECTURE_PROPOSAL.md): one app, one router per domain.

## Domains implemented

- **`incidents/`** — Support ticket CSV analysis ("Analizador de Incidencias"). Validates and computes metrics on Nexova support-incident exports, per the rules in [scripts/CONTEXT-nexova.md](../../scripts/CONTEXT-nexova.md). Reuses the same [`incidents_analyzer`](../../packages/incidents_analyzer) package as the CLI script in `scripts/analyze.py`, so both run identical validation/metrics logic.
- **`users/`** — Internal accounts (email + password, bcrypt-hashed through `libpass`) with full CRUD, stored in TinyDB.
- **`profiles/`** — One `Profile` per user (strictly one-to-one through `user_id`, the `User.id`): the **name and the contact data** (`contact_email`, `phone`, `address`) live here, not in `User`. Stored in TinyDB (`profiles/db.json`, gitignored).
- **`auth/`** — Login (OAuth2 password flow + JWT carrying the user `id`), the `get_current_user` dependency used to protect every other domain, and the password flows: reset by email when it was forgotten, and change while logged in.
- **`suppliers/`** — Supplier directory ("Directorio de Proveedores", Patricia Solís / Nexova). Replaces the HR spreadsheet with a [TinyDB](https://tinydb.readthedocs.io/)-backed store, seeded on startup with the 15 suppliers from [`suppliers/seed_data.py`](./suppliers/seed_data.py) (spec: [CONTEXT-suppliers.md](./suppliers/CONTEXT-suppliers.md)). Pydantic (`suppliers/schemas.py`) rejects with `422` any missing `country`, a `status` outside `active`/`suspended`, empty `categories`, or a `currency` that doesn't match the country (Spain→EUR, USA→USD). Suspending (not deleting) is the preferred way to retire a supplier.

## Authentication

Every route except `POST /auth/login`, `POST /users` (sign-up), `POST /auth/forgot-password`, `POST /auth/reset-password`, `GET /health` and the docs (`/docs`, `/openapi.json`) needs a valid session: `Authorization: Bearer <JWT>`. Without one the API answers `401` (with `WWW-Authenticate: Bearer`).

- **Users are credentials plus account state**, stored in their own TinyDB file, `users/db.json` (gitignored). Each document is a `User` (`users/schemas.py`): `id` (uuid), `email`, `hashed_password`, `is_active`, `role` (`admin` | `manager` | `user`; nothing else is accepted) and `created_at` (UTC). No display name or contact data: those are in the Profile. The password is hashed with bcrypt before it is stored (max 72 bytes) and is never returned, logged or echoed back, not even in `422` responses. `is_active=false` blocks login and invalidates its tokens (`401`, the same answer as a wrong password). Every new account is active, including those created through the public sign-up, which can log in straight away; an admin can switch any account off (`is_active=false`). `role` is granted only by an admin (`PUT /users/{id}`), by the `AUTH_INITIAL_*` bootstrap user (admin) or by `create-user --role admin`; `POST /users` (public sign-up) always creates a `user`. Documents written before this model (`user_uuid`/`password_hash`) are migrated on startup. Emails are case-insensitive (stored lower-cased) and unique.
- **Password rule: never plain text, always bcrypt through `libpass`.** Install `libpass[bcrypt]`, not the unmaintained `passlib`; the import is the same (`from passlib.hash import bcrypt`). All hashing lives in `auth/security.py` (`hash_password` / `verify_password`).
- **Auth rule: stateless JWT only.** No server-side sessions and no cookies (no `SessionMiddleware`, no `Set-Cookie`, no session store, no token blacklist). The client keeps the token and sends it in `Authorization: Bearer`; CORS runs with `allow_credentials=False`. The only per-request lookup is reading the user from TinyDB to check that it still exists and is active.
- **Storage rule: users and profiles live only in TinyDB**, now and after Supabase/PostgreSQL is added. No users or profiles tables in Supabase, and no SQLModel models for them. SQL tables of other modules (inventory, …) store just a `user_uuid` column with the TinyDB `User.id`, as a plain reference (no foreign key: there is no users table). Deleting a user therefore does not cascade into those tables by itself.
- **Login** — `POST /auth/login`, OAuth2 password flow: `application/x-www-form-urlencoded` with `username` = the **email** and `password`. The credentials are checked against the bcrypt hash in TinyDB; an unknown email, a wrong password and a malformed email all give the same `401 {"detail": "Incorrect email or password"}` (and take about the same time). On success:

  ```json
  {"access_token": "<jwt>", "token_type": "bearer", "expires_in": 1800}
  ```

- **Token** — JWT signed with HS256 by `python-jose` using `SECRET_KEY`. Claims are the minimum: `user_id` (the `id` of the user document in TinyDB) and `exp`. Nothing else: no email, no password. The user is re-read on every request, so deleting an account kills its tokens at once, and changing the email keeps the session. Lifetime: `ACCESS_TOKEN_EXPIRE_MINUTES` (default 30, must be a positive integer); `expires_in` is that value in seconds.
- **Who may touch what** (`403 Forbidden` = valid token, not yours; `401` = no valid token). Roles are `admin` | `manager` | `user` (new users are `user`); only `admin` has extra powers today (`manager` is stored and assignable but grants nothing yet). Any valid session can use the suppliers and incidents APIs. For accounts and profiles: **reading** someone's user or profile is for its owner or an admin, **listing** every user or profile is for admins, **changing or deleting** a user is for the owner or an admin, and **writing a profile** is for the owner only. Only an admin can change a `role` or `is_active`, and only the owner can change their own password. The last active admin can be neither demoted, deactivated nor deleted (`409`). The `403` comes before any lookup, so an unknown id answers `403` too: nobody can probe which accounts exist.

Protection is applied on the routers themselves (`dependencies=[Depends(get_current_user)]`), so a route added to `suppliers/`, `incidents/`, `users/` or `profiles/` is private by default, and `tests/test_auth.py` fails if any documented operation is left open.

### Forgotten and changed passwords

- **Forgotten password** — `POST /auth/forgot-password` with `{"email"}` always answers `200` with the same message, whether the account exists, is deactivated or was never there. For an active account it emails a link, `FRONTEND_URL/reset-password?token=…`. `POST /auth/reset-password` with `{"token", "new_password"}` then sets the new password (`204`). It does not log the user in.
- **The token** is a signed JWT (HS256, same `SECRET_KEY`) with `user_id`, `purpose: "password_reset"`, a random `jti` and a short `exp`; it only travels in the email. Session tokens refuse any token with a `purpose`, so the link can never open a session. The API also keeps its SHA-256 in `auth/db.json` (TinyDB, gitignored), one document per pending token: `{token_hash, user_id, password_fingerprint, created_at, expires_at}`. The user documents are not touched. A token works **once**, expires after `PASSWORD_RESET_EXPIRE_MINUTES` (default 30, allowed 15-60), is replaced when a newer link is requested, and dies if the password changes by any other route or the account is deleted or deactivated. Unknown, used and expired tokens all give the same `400`.
- **No inbox flooding** — one reset email per account per minute; further requests in that minute still answer `200` and send nothing.
- **The link never comes from the request.** It is built from `FRONTEND_URL`, not from the `Host` header, so nobody can make the email point at another site.
- **Changing it while logged in** — `POST /auth/change-password` with `{"current_password", "new_password"}` (`204`). A wrong current password is a `400` (not a `401`, which would mean "no session"); a new password equal to the current one is a `422`. `PUT /users/{id}` with `password` + `current_password` still works too.
- **A notice is emailed** to the owner after every reset or change, without the password.
- **Emails** are sent in a background task, after the response, through `core/mailer.py`. `EMAIL_BACKEND` picks how: `console` (default) prints them to the API's output instead of sending them, which is what you want in development: copy the link from the terminal. `smtp` works with any provider's SMTP relay, and `resend` uses Resend's HTTP API. A transient failure (network, `429`, `5xx`) is retried twice, 1 s and 3 s later; a definitive one (bad key, unverified sender) is not. If it still fails it is logged, with the provider's reason and without the link, and the answer does not change.

### Profiles (one-to-one with users)

`User` is only credentials; everything a person sees or that is used to reach them is in the `Profile`: `id` (its own uuid), `user_id` (the owner, unique), `name` (required, 1-80 chars), `contact_email` (optional, may differ from the login email), `phone` (optional) and `address` (optional, up to 200 chars).

- **The relation is enforced by construction**: creating a user creates its profile (default `name` = the local part of the email, so `ana@x.com` → `ana`, unless `POST /users` gives a `name`) and deleting a user deletes it. There is no `POST`/`DELETE` on `/profiles`, and the profile is looked up by `user_id`, so a second one cannot exist. If the profile insert fails, the user creation is rolled back.
- **Existing databases are migrated on startup**: `migrate_legacy_profiles()` turns `{user_uuid, display_name, …}` documents into `{id, user_id, name, …}`, then `sync_profiles()` gives a profile to every user that lacks one and drops profiles whose user is gone. A missing profile is also recreated when its owner reads or edits `/profiles/me`.
- Reading a profile by id is for its owner or an admin and the full list is for admins (`403` otherwise). Writing is for the owner only: `PUT /profiles/me`, or `PUT /profiles/{user_id}` with your own id (`403` with anyone else's, admins included). Editing a profile never touches the login credentials.

### Configuration

| Env var | Purpose |
|---|---|
| `SECRET_KEY` | JWT signing key, at least 32 characters (`openssl rand -hex 32`). **Required in production.** If unset, a random per-process key is used (sessions die on restart, and it breaks with several workers). |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token lifetime in minutes (default `30`). An invalid value (`0`, negative, not an integer) stops the API at startup. |
| `AUTH_INITIAL_EMAIL` / `AUTH_INITIAL_PASSWORD` | Creates the first user on startup, only if the user store is empty. |
| `PASSWORD_RESET_EXPIRE_MINUTES` | Lifetime of a password-reset link in minutes (default `30`, allowed 15-60). An invalid value stops the API at startup. |
| `FRONTEND_URL` | Base URL of the backoffice, used for the link in the reset email. Defaults to the Codespace's forwarded URL for port 5174, or `http://localhost:5174`. **Set it in production.** |
| `EMAIL_BACKEND` | `console` (default: emails are printed, not sent), `smtp` or `resend`. **Never `console` in production**: the reset links would be in the logs. |
| `EMAIL_FROM` | Sender, e.g. `Nexova <no-reply@nexova.com>`. Required for `smtp` and `resend`; the provider must have verified it. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_SECURITY` | For `EMAIL_BACKEND=smtp`. Port defaults to `587`; security is `starttls` (default), `ssl` (port 465) or `none`. |
| `RESEND_API_KEY` | For `EMAIL_BACKEND=resend`. |

A mailer that is missing a setting stops the API at startup, instead of failing the first time somebody forgets a password.

Without them the API starts with no users; create one with `uv run create-user --email <email>` (prompts for the password).

## Endpoints

Routes are served under one prefix per domain: `/auth`, `/users`, `/profiles`, `/suppliers`. Supplier routes are also mounted at `/api/suppliers` (hidden from `/docs`): that is the path the backoffice uses through the Vite proxy, which only forwards `/api`. Incident routes live at `/api/incidents`, fixed by the project brief.

All endpoints below need a session (see above) except `POST /auth/login`, `POST /auth/forgot-password`, `POST /auth/reset-password`, `POST /users` and `/health`.

| Method | Path | Description |
|---|---|---|
| `POST` | `/auth/login` | Public. Exchange the email (form field `username`) and password for a bearer token (`access_token`, `token_type`, `expires_in`). `401` on bad credentials. |
| `GET` | `/auth/me` | The user of the current session (`id`, `email`, `is_active`, `role`, `created_at`) plus its linked `profile` (`name`, `contact_email`, `phone`, `address`, …). Never the hash. |
| `POST` | `/auth/forgot-password` | Public. `{"email"}`. Emails a single-use reset link if the account exists and is active. Always `200` with the same message; `422` only for a malformed email. |
| `POST` | `/auth/reset-password` | Public. `{"token", "new_password"}` (password 8-72 bytes). Sets the new password and spends the token (`204`). `400` if the token is unknown, used or expired; `422` on an invalid password (the token is not spent). |
| `POST` | `/auth/change-password` | `{"current_password", "new_password"}` for the session's own account (`204`). `400` if the current password is wrong, `422` if the new one is the same or invalid. |
| `GET` | `/users` | **Admins only** (`403`). List users (`id`, `email`, `is_active`, `role`, `created_at`; never the hash). |
| `GET` | `/users/directory` | Any session. Who is who: `[{user_id, name}]` of the **active** users, sorted by name. Nothing else (no email, role or contact data), so it is the way to show names without listing accounts. |
| `POST` | `/users` | Register a user: `{"email", "password"}` (password 8-72 bytes) plus optional initial profile `name`, `phone`, `address`. The password is hashed before storing and the linked Profile is created in the same operation (`201`). The new user is always a `user`. **Public** (no session needed): it is the sign-up. The account is **active** straight away (`is_active=true`): it can sign in at once with `POST /auth/login`. The `201` answer carries a `message` saying so. `409` if the email exists, `422` on invalid data (nothing is created). |
| `GET` | `/users/{user_id}` | One user: the owner or an admin (`403` otherwise). `404` if missing (admins only ever see that). |
| `PUT` | `/users/{user_id}` | Partial update (omitted fields are kept) of `email`, `password` and, for admins only, `role` and `is_active` (this is how an account is switched off, or back on). Allowed to the owner or an admin (`403` otherwise). The owner needs `current_password` to change their email or password (`422` if missing, `400` if wrong); an admin editing someone else does not, but cannot change their password (`403`). `409` if the email is taken or it would demote, deactivate or remove the last active admin. |
| `DELETE` | `/users/{user_id}` | Delete a user and its linked profile (`204`). Allowed to the owner or an admin (`403` otherwise); `404` if missing; `409` if it is the last user or the last active admin. |
| `GET` | `/profiles` | **Admins only** (`403`). List all profiles (`id`, `user_id`, `name`, `contact_email`, `phone`, `address`). |
| `GET` | `/profiles/me` | Your own profile. |
| `GET` | `/profiles/{user_id}` | One user's profile: the owner or an admin (`403` otherwise). `404` if missing. |
| `PUT` | `/profiles/me` | Partial update of your own `name`, `phone`, `address` (and `contact_email`); omitted fields are kept and an explicit `null` clears `phone`, `address` or `contact_email` (not `name`). `id` and `user_id` can't be sent (`422`). `422` on invalid data. |
| `PUT` | `/profiles/{user_id}` | Same as `/profiles/me` but by id; only for your own id, `403` for anyone else (admins included). |
| `POST` | `/api/incidents/analyze` | Upload a CSV (`multipart/form-data`, field name `file`), get back the analysis as JSON. `400` if the file isn't `.csv`, `422` if required columns are missing or the file has no data rows. |
| `GET` | `/api/incidents/results/export` | Download the most recent analysis as `results.csv` (one metric per row). `404` if no analysis has run yet in this process. |
| `GET` | `/suppliers` | List all suppliers. |
| `GET` | `/suppliers/search/by-country?country=Spain\|USA` | Filter by country. |
| `GET` | `/suppliers/search/by-category?category=...` | Filter by category (one of `job_boards`, `ats_software`, `assessment_tools`, `training_platforms`, `payroll_and_hr_software`, `video_interview`, `background_check`, `office_and_facilities`, `it_and_software_licenses`). |
| `GET` | `/suppliers/{id}` | Get one supplier. `404` if missing. |
| `POST` | `/suppliers` | Create a supplier. `422` on invalid data. |
| `PATCH` | `/suppliers/{id}` | Partial update. Changing `monthly_rate` stamps `updated_at` (audit). The merged record is re-validated, so changing `country` alone (currency mismatch) is a `422`. |
| `PATCH` | `/suppliers/{id}/rate` | Update the monthly rate (`{"monthly_rate": 350}`). Always stamps `updated_at` with the time of the change. `422` if the rate is `<= 0`; `404` if the supplier doesn't exist. |
| `PATCH` | `/suppliers/{id}/status` | Activate/suspend (`{"status": "active" \| "suspended"}`). |
| `DELETE` | `/suppliers/{id}` | Remove a supplier (`204`). `404` if it doesn't exist. The CONTEXT prefers suspending to keep the relationship history; use this for entries made by mistake. |
| `GET` | `/health` | Public liveness check. |

Interactive docs (Swagger UI) are available at `/docs` when the server is running; use *Authorize* there with your email (in the *username* box) and password to try the protected routes.

## Running locally

```bash
cd services/api
pip install -r requirements.txt
cp .env.example .env    # then set SECRET_KEY (openssl rand -hex 32) and, on the first run only,
                        # AUTH_INITIAL_EMAIL / AUTH_INITIAL_PASSWORD. `.env` is gitignored and loaded on startup;
                        # real environment variables take precedence over it.
uvicorn main:app --reload --port 8000
```

To (re)load the initial suppliers into TinyDB by hand (the API also seeds an empty database on startup):

```bash
uv run seed              # seed only if empty
uv run seed --reset      # wipe and reload the 15 initial suppliers
```

`uv run seed` uses the `seed` script declared in `pyproject.toml` (uv installs the dependencies on first run). Run it from `services/api`; from the repo root use `uv run --project services/api seed`, since the root has no Python project. `python seed.py` works too if the dependencies are already installed.

`ALLOWED_ORIGINS` (comma-separated) controls CORS; defaults to the local Vite dev ports (`5173`, `5174`) used by `uis/website` and `uis/backoffice` when unset. Set it explicitly in production — see `docs/ARCHITECTURE_PROPOSAL.md` section 4.4.

## Known limitations

- The "last analysis" used by the export endpoint is kept in an in-memory, module-level variable — it is lost on restart and is not shared across multiple worker processes. Acceptable for this feature's current scope; documented rather than hidden.
- The suppliers directory is stored at `suppliers/db.json`, a TinyDB flat file that's regenerated (and reseeded) whenever it's missing — it's gitignored, not source. A second worker process would not see writes made by another one; fine for the current single-process scope, and the reason the project brief already earmarks a move to Postgres once the ORM is ready.
- Login and `POST /auth/change-password` have no rate limiting or lockout yet (`POST /auth/forgot-password` only limits emails per account, not requests), and a token stays valid until it expires or its account is deleted: changing or resetting a password does **not** revoke the tokens already issued (they carry no `iat`), and there is no refresh or logout endpoint, so keep `ACCESS_TOKEN_EXPIRE_MINUTES` short. Put the API behind a reverse proxy with rate limits until that is added.
- `uis/backoffice` does not send a token yet, so its calls to `/api/suppliers` and `/api/incidents` now get `401` until a login screen is added.
