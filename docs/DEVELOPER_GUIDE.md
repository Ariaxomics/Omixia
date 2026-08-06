# Omixia — Developer Guide

**Version:** 2.1
**Last Updated:** 2026-08-05

How to set up, run, and change Omixia. For *how the system is built and why*, see [Architecture](ARCHITECTURE.md). For running it in production, see [Operations](OPERATIONS.md).

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Running the Application](#running-the-application)
3. [Authentication & Roles](#authentication--roles)
4. [Common Tasks](#common-tasks)
5. [React Frontend](#react-frontend)
6. [API Reference](#api-reference)
7. [CLI Commands](#cli-commands)
8. [Configuration](#configuration)

---

## Getting Started

### Prerequisites

- Docker + Docker Compose (this is how Mongo, Redis, the backend, and Nginx are run — there is no supported bare-metal setup)
- Node.js 18+ and npm, only if you're working on the React frontend locally
- (Optional, for the VCF ingestion pipeline only) `bcftools` and Ensembl VEP with a local cache — not required to run the app or click through the demo data

### Clone & Configure

```bash
git clone <repo-url> Omixia
cd Omixia/backend
cp .env.example .env
```

Edit `backend/.env` — at minimum set real values for `MONGO_INITDB_ROOT_PASSWORD`, `FLASK_SECRET_KEY`, and leave the rest as-is for local development. See [Configuration](#configuration) for the full variable reference.

---

## Running the Application

### Backend (Docker Compose)

```bash
cd backend
docker compose up -d --build
```

This starts four containers: `mongo_omixia`, `redis_omixia`, `app_omixia` (FastAPI, served by Gunicorn with Uvicorn workers on :8000 internally), and `nginx_omixia`.

Nginx exposes two ports:
| Port | Purpose |
|---|---|
| `80` | Proxies everything to the FastAPI app — landing page, `/api/*`, `/portal/*` |
| `8080` | Serves the built React SPA from `frontend/dist/` (local-only; production uses Cloudflare Pages instead) |

Check it's up:
```bash
curl http://localhost/api/health
# {"status":"ok","service":"omixia"}
```

### Load Demo Data

```bash
docker exec app_omixia python cli.py load-demo
```

This loads demo users, samples, assays, variants, and knowledge entries. All demo users share the password `omixia_demo_1`.

| Username | Role |
|---|---|
| `admin` | `admin` |
| `geneticist` | `reviewer` |
| `senior` | `senior_reviewer` |
| `director` | `lab_director` |
| `bioinf` | `bioinformatician` |

### Frontend (React SPA)

```bash
cd frontend
npm install
npm run dev          # http://localhost:3000, proxies /api → http://localhost:80 (nginx)
```

For a production-style local build served by nginx instead of the Vite dev server:
```bash
npm run build         # → frontend/dist/
docker compose -f ../backend/docker-compose.yml restart nginx
# then visit http://localhost:8080
```

### Applying Backend Code Changes

`backend/app` is bind-mounted into the `app` container, but the Gunicorn/Uvicorn workers only load Python once at boot, and pip packages live in the image layer, not the mount. So:

```bash
# Source-only change (no requirements.txt edit):
docker compose -f backend/docker-compose.yml up -d --force-recreate app

# requirements.txt changed:
docker compose -f backend/docker-compose.yml build app
docker compose -f backend/docker-compose.yml up -d --force-recreate app
```

### Stopping Everything

```bash
docker compose -f backend/docker-compose.yml down          # keep volumes (Mongo/Redis data, reports)
docker compose -f backend/docker-compose.yml down -v        # also wipe volumes
```

---

## Authentication & Roles

### Session Mechanism

Sessions are **cookie-based with server-side storage** — there is no JWT anywhere in the system.

1. On login, the server generates an opaque session id (`secrets.token_urlsafe(32)`).
2. The session dict is stored in Redis under `omixia:session:<id>`, TTL **7 days** (`SESSION_TTL_SECONDS` in `src/session.py`).
3. The id is signed with `itsdangerous` using `SECRET_KEY` and set as an httponly cookie named by `SESSION_COOKIE_NAME`.
4. Middleware in `main.py` loads the session onto `request.state.session` for every request and re-sets the cookie on the way out.

`request.state.session` behaves like a dict but **writes through to Redis on every mutation** — assigning `session["user"] = {...}` persists immediately; there is no explicit save step.

```
POST /login   { username, password }   → sets session["user"]  (Jinja2 form)
POST /logout  → clears session
```

**Role hierarchy:**

| Role | Key capabilities |
|---|---|
| `admin` | Full access — user management plus everything below. |
| `bioinformatician` | Import VCFs, manage callsets, view QC metrics. Cannot touch clinical interpretation. |
| `reviewer` | Review variants, set tier, write interpretation. Cannot finalise reports. |
| `senior_reviewer` | All reviewer capabilities + break tiebreaks + approve pre-finalisation + issue portal tokens. |
| `lab_director` | Read-only across everything + unlock finalised reports + lab-wide dashboards + manage assay configs + federation management. |
| `ordering_physician` | External portal only — read-only access to finalised reports via token link. |

The canonical list is `VALID_ROLES` in `src/services/users.py`.

### Enforcing Auth on an Endpoint

Auth is applied with **FastAPI dependencies**, not decorators:

```python
from fastapi import Depends
from src.auth import require_login, require_role

# any authenticated internal user
@router.get("/thing", dependencies=[Depends(require_login)])
def thing(): ...

# role whitelist
@router.post("/thing", dependencies=[Depends(require_role("lab_director", "senior_reviewer"))])
def create_thing(): ...
```

`require_login` raises `HTTPException(401)`; `require_role` raises 401 when unauthenticated and 403 on role mismatch. A global handler in `main.py` renders both as `{"error": "<message>"}`.

When the handler needs the user object itself, take `request: Request` and call `current_user(request)` (or the `_require_user(request)` helper in `api_v1.py`, which 401s on a missing session).

> ⚠️ **Known gap — several read endpoints are unauthenticated.** The endpoints marked `none` in the [API Reference](#api-reference) have no auth dependency and will serve clinical variant data to an unauthenticated caller. This is pre-existing behaviour inherited from the original Flask routes (they carried no `@require_login` either) and was preserved verbatim during the FastAPI migration — it is **not** a regression, but it is a real exposure that should be closed before any production deployment. Fix by adding `dependencies=[Depends(require_login)]` to each.

### React SPA Auth

The React frontend uses three dedicated JSON endpoints:

```
POST /api/auth/login   { username, password }  → sets session cookie, returns user object
POST /api/auth/logout                           → clears session
GET  /api/auth/me                              → returns current user or 401
```

`AuthContext` calls `GET /api/auth/me` on mount to rehydrate the session. All API calls set `withCredentials: true` so the browser forwards the session cookie.

In local development the Vite dev server proxies `/api` to `http://localhost:80` (nginx), so requests are same-origin and CORS never applies. In production the SPA is served from a different origin (Cloudflare Pages), so the cookie must be cross-origin capable — set `SESSION_COOKIE_SAMESITE=None`, `SESSION_COOKIE_SECURE=1`, and list the SPA origin in `ALLOWED_ORIGINS`.

### Physician Portal Auth

Completely separate from the internal session. Tokens stored in `report_access_tokens` collection.

```
GET /portal/access/<token>    → validates token, sets session["portal_token"], redirects to report
GET /portal/report            → read-only report view (finalised only)
POST /portal/logout
```

---

## React Frontend

A standalone React 18 + TypeScript SPA lives in `frontend/`. It is the sole interactive UI, consuming the `/api` REST endpoints and sharing the server's session-cookie auth mechanism.

### Tech Stack

| Concern | Library |
|---|---|
| Bundler | Vite 5 |
| UI framework | React 18 + TypeScript |
| Styling | Tailwind CSS 3 |
| Routing | React Router v6 |
| Data fetching / caching | TanStack Query v5 |
| HTTP | Axios (with `withCredentials: true`) |

### Directory Layout

```
frontend/
├── index.html
├── package.json
├── vite.config.ts           # dev server on :3000, /api proxied to :80 (nginx)
├── tsconfig.json
├── tailwind.config.js
├── postcss.config.js
└── src/
    ├── main.tsx             # ReactDOM root, QueryClientProvider
    ├── index.css            # Tailwind directives
    ├── App.tsx              # BrowserRouter, route tree, AuthProvider wrapper
    ├── api/
    │   ├── client.ts        # Axios instance — baseURL /api, withCredentials, 401 redirect
    │   ├── auth.ts          # login(), logout(), me()
    │   ├── samples.ts       # list(), get(), getAssays(), getSummary(), assign()
    │   ├── variants.ts      # SNV / CNV / SV list + review + preflight + biomarkers + callsets
    │   ├── reports.ts       # list(), create(), signOff(), finalise(), export()
    │   ├── knowledge.ts     # list(), search(), get(), create(), update()
    │   └── lab.ts           # dashboard(), gapAnalysis(), cohort()
    ├── contexts/
    │   └── AuthContext.tsx  # user state, login/logout actions, loading flag
    ├── components/
    │   ├── Layout.tsx        # Top navbar + <Outlet /> shell
    │   ├── ProtectedRoute.tsx # Redirects to /login when unauthenticated
    │   ├── Badge.tsx         # Tier (tier_1…4) and status colour badges
    │   └── LoadingSpinner.tsx
    └── pages/
        ├── LoginPage.tsx
        ├── DashboardPage.tsx
        ├── SamplesPage.tsx
        ├── SampleDetailPage.tsx
        ├── KnowledgePage.tsx
        ├── LabDashboardPage.tsx
        ├── GapAnalysisPage.tsx
        └── CohortPage.tsx
```

### Pages & Features

| Route | Page | Description |
|---|---|---|
| `/login` | `LoginPage` | Username/password form, POSTs to `/api/auth/login` |
| `/dashboard` | `DashboardPage` | Welcome banner, stat cards, recent samples table |
| `/samples` | `SamplesPage` | Searchable sample list; click to expand assays inline |
| `/samples/:sampleId/assays/:assayId` | `SampleDetailPage` | 7-tab workspace (see below) |
| `/knowledge` | `KnowledgePage` | Filterable knowledge list + side-panel detail + create/edit modal |
| `/lab-dashboard` | `LabDashboardPage` | TAT/SLA stats grid (senior_reviewer / lab_director only) |
| `/gap-analysis` | `GapAnalysisPage` | Gene + optional assay ID query → gap table (lab_director only) |
| `/cohort` | `CohortPage` | Gene / tier / type / assay filter → cohort query results |

### SampleDetailPage Tabs

| Tab | API calls | Key interactions |
|---|---|---|
| **SNVs** | `GET /sample-assays/<id>/snvs` | Click row → side panel with tier selector, interpretation, note fields; POST review |
| **CNVs** | `GET /sample-assays/<id>/cnvs` | Same review pattern, keyed by gene |
| **SVs** | `GET /sample-assays/<id>/svs` | Same review pattern, keyed by sv_id |
| **Biomarkers** | `GET /sample-assays/<id>/biomarkers` | Displays MSI/TMB classification; confirm form with discordance acknowledge |
| **Preflight** | `GET /sample-assays/<id>/preflight` | Pass/fail checklist; Re-run button |
| **Reports** | `GET /sample-assays/<id>/reports` | Create draft, sign off, finalise, export JSON link |
| **Callsets** | `GET /sample-assays/<id>/callsets` | Read-only table of imported callsets |

### Data Fetching Pattern

All server state is managed with TanStack Query. Each API module returns typed promises; query keys follow `[resource, id]` conventions so targeted invalidations work correctly:

```typescript
// After a review is submitted, invalidate the variant list and summary
qc.invalidateQueries({ queryKey: ['snvs', assayId] })
qc.invalidateQueries({ queryKey: ['summary', assayId] })
```

### Auth Flow

```
App mounts
  → AuthContext calls GET /api/auth/me
      ├─ 200: setUser(data) → renders protected routes
      └─ 401: setUser(null) → ProtectedRoute redirects to /login

User submits login form
  → POST /api/auth/login { username, password }
      ├─ 200: setUser(data), navigate('/dashboard')
      └─ 401: show error message

Axios interceptor: any 401 from other endpoints → window.location.href = '/login'
```

### Role-Based UI

Pages that require elevated roles check `user.role` from `AuthContext` and render an access-denied message rather than calling the API:

```typescript
const allowed = user?.role === 'lab_director' || user?.role === 'senior_reviewer'
if (!allowed) return <div>Access restricted…</div>
```

Editable actions in `KnowledgePage` (create / edit buttons) are also hidden for `reviewer` and `bioinformatician` roles.

### Running the Frontend

```bash
cd frontend
npm install
npm run dev          # http://localhost:3000 — proxies /api → http://localhost:80
npm run build        # production build → dist/  (runs tsc first)
npm run preview      # preview the production build locally
```

The backend stack must be up (`docker compose up -d` in `backend/`) for the Vite proxy to reach the API — the proxy target is nginx on port 80, not the app container directly.

Alternatively, skip the dev server entirely: `npm run build` writes to `frontend/dist/`, which nginx serves on **port 8080** via the bind mount in `docker-compose.yml`. Restart nginx after each build:

```bash
npm run build && docker compose -f ../backend/docker-compose.yml restart nginx
```

---
---

## Common Tasks

Recipes for the changes you'll make most often. Each one ends with the docs to update — see the Documentation Map in [CLAUDE.md](../CLAUDE.md).

### Add an API endpoint

1. **Business logic goes in a service**, never the router — `src/services/<domain>.py`:
   ```python
   class MyService:
       @staticmethod
       def get_data(thing_id: str) -> dict | None:
           db = mongo_client.db
           return db.things.find_one({"thing_id": thing_id}, {"_id": 0})
   ```
   No `fastapi` imports here. See [the layer rule](ARCHITECTURE.md#the-rule-that-matters).

2. **Add the route** in `src/routers/api_v1.py`:
   ```python
   @router.get("/things/{thing_id}", dependencies=[Depends(require_login)])
   def get_thing(thing_id: str):
       thing = MyService.get_data(thing_id)
       if not thing:
           raise HTTPException(status_code=404, detail="Thing not found")
       return {"data": thing}
   ```
   Return `{"data": ...}`; raise `HTTPException` for errors — the global handler renders `{"error": ...}`.

3. **Pick the auth dependency deliberately** — `require_login`, or `require_role("admin", …)`. Omitting it makes the endpoint public; see [Known Issues #1](ARCHITECTURE.md#1-nine-read-endpoints-have-no-authentication----security).

4. **Audit any mutation** (required):
   ```python
   AuditService.log(event_type="thing_updated", actor_user_id=user["user_id"],
                    actor_role=user["role"], target_collection="things",
                    target_id=thing_id, payload={"before": before, "after": after})
   ```

5. **Apply it**: `docker compose -f backend/docker-compose.yml up -d --force-recreate app`

6. **Verify** at <http://localhost/docs> — the endpoint appears automatically.

📄 Update: API Reference below · `CHANGELOG.md`

### Add a React page

1. Create `frontend/src/pages/MyPage.tsx`
2. Add an API module `frontend/src/api/myDomain.ts`:
   ```typescript
   import client from './client'
   export const myApi = {
     list: () => client.get('/my-resource').then((r) => r.data.data),
   }
   ```
3. Register the route in `App.tsx`: `<Route path="/my-page" element={<MyPage />} />`
4. Add to `navItems` in `components/Layout.tsx`, with a `roles` filter if role-gated
5. Build: `cd frontend && npm run build && docker compose -f ../backend/docker-compose.yml restart nginx`

📄 Update: [React Frontend](#react-frontend) · `CHANGELOG.md`

### Add or change a Mongo collection

1. Add index definitions to `src/db/indexes.py` — applied automatically at boot
2. Add a demo fixture in `backend/app/demo_data/<collection>.json`
3. Register it in `load_demo_data()` in `src/cli/load_demo.py`
4. Reload: `docker exec app_omixia python cli.py load-demo`

📄 Update: [Data Model](ARCHITECTURE.md#data-model) + [Database Indexes](ARCHITECTURE.md#database-indexes) · `CHANGELOG.md`

### Add a CLI command

1. Implement it in `src/cli/<name>.py` as a plain function with Typer-annotated parameters
2. Register in `cli.py`: `app.command("my-command")(_my_command)`
3. Mongo/Redis are already initialised by the `@app.callback()` — don't reconnect

📄 Update: [CLI Commands](#cli-commands) · `CHANGELOG.md`

### Add a configuration variable

1. Add the field to `Settings` in `src/config.py` (use `Field(validation_alias=...)` if the env name differs)
2. Add it to `backend/.env.example` with a safe placeholder — **never a real secret**
3. Recreate the container; env vars are read once at process start

📄 Update: [Configuration](#configuration) + [OPERATIONS.md](OPERATIONS.md) env table · `CHANGELOG.md`

---

## Conventions

| Area | Rule |
|---|---|
| Python formatting | **black**; type hints on all new functions |
| TypeScript formatting | **prettier** — 2-space indent, single quotes |
| Comments | Don't add docstrings/comments to code you didn't change |
| Error handling | No defensive handling for impossible scenarios |
| Handlers | Plain `def`, never `async def` — [why](ARCHITECTURE.md#why-handlers-are-def-not-async-def) |
| Services | No web-framework imports in `src/services/` |
| Mutations | Always `AuditService.log()` |
| Responses | `{"data": …}` / `{"error": …}` |

### Typecheck the frontend

```bash
cd frontend && npx tsc --noEmit
```

### Tests

There is no backend test suite yet — see [Known Issues #4](ARCHITECTURE.md#4-no-automated-test-suite). When adding one, run single tests rather than the full suite:

```bash
pytest tests/test_foo.py -k test_bar
```

---
## API Reference

All API routes are prefixed with `/api`. Authentication uses the internal session cookie (`withCredentials: true` from the React frontend, or a browser session from the Jinja2 login page).

The **Auth** column reflects what the code actually enforces, verified against `src/routers/api_v1.py`:

| Value | Meaning |
|---|---|
| `none` | No dependency — **served to unauthenticated callers**. See the [known gap](#enforcing-auth-on-an-endpoint). |
| `login` | `Depends(require_login)` — any authenticated user |
| `<role>, …` | `Depends(require_role(…))` — 401 unauthenticated, 403 wrong role |
| `login*` | No route-level dependency, but the handler calls `current_user()` / `_require_user()` and 401s itself — equivalent to `login` in effect |

Since FastAPI generates OpenAPI automatically, the live, always-current contract is served by the running backend at **`/docs`** (Swagger UI), **`/redoc`**, and **`/openapi.json`** — 56 paths at time of writing. Treat those as authoritative if this table ever drifts.

### Auth

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/login` | none | JSON login `{username, password}` → sets session, returns user object |
| POST | `/api/auth/register` | admin, lab_director | Create a user (201) |
| POST | `/api/auth/logout` | none | Clears session |
| GET | `/api/auth/me` | login\* | Returns current session user or 401 |

### Health

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/health` | none | Service health check |

### Samples & Assays

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/samples` | ⚠️ none | List all samples |
| GET | `/api/samples/<sample_id>` | ⚠️ none | Get sample detail |
| GET | `/api/samples/<sample_id>/assays` | ⚠️ none | List assays for a sample |
| GET | `/api/sample-assays/<id>` | ⚠️ none | Get sample assay detail |
| GET | `/api/sample-assays/<id>/summary` | ⚠️ none | Review-progress summary |
| POST | `/api/sample-assays/<id>/assign` | admin, senior_reviewer, lab_director | Assign reviewers |

### Variants

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/sample-assays/<id>/snvs` | ⚠️ none | List SNVs |
| GET | `/api/sample-assays/<id>/snvs/<chrom>/<pos>/<ref>/<alt>` | ⚠️ none | Get SNV detail |
| POST | `/api/sample-assays/<id>/snvs/<chrom>/<pos>/<ref>/<alt>/review` | login\* | Submit SNV review |
| GET | `/api/sample-assays/<id>/cnvs` | login | List CNVs |
| GET | `/api/sample-assays/<id>/cnvs/<gene>` | login | Get CNV detail |
| POST | `/api/sample-assays/<id>/cnvs/<gene>/review` | login\* | Submit CNV review |
| GET | `/api/sample-assays/<id>/svs` | login | List SVs |
| GET | `/api/sample-assays/<id>/svs/<sv_id>` | login | Get SV detail |
| POST | `/api/sample-assays/<id>/svs/<sv_id>/review` | login\* | Submit SV review |

### Biomarkers

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/sample-assays/<id>/biomarkers` | login | Get MSI/TMB biomarkers |
| POST | `/api/sample-assays/<id>/biomarkers/classify` | admin, bioinformatician, lab_director, senior_reviewer | Classify from callset |
| POST | `/api/sample-assays/<id>/biomarkers/confirm` | login\* | Reviewer confirmation |

### Preflight & Reports

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/sample-assays/<id>/preflight` | login | Run preflight checks |
| GET | `/api/sample-assays/<id>/reports` | login | List reports for case |
| POST | `/api/sample-assays/<id>/reports` | login\* | Create draft report (201) |
| GET | `/api/reports/<id>` | login | Get report detail |
| POST | `/api/reports/<id>/sign-off` | login\* | Add sign-off |
| POST | `/api/reports/<id>/finalise` | admin, senior_reviewer, lab_director | Finalise report |
| GET | `/api/reports/<id>/export` | login | Export JSON (schema v1) |
| POST | `/api/reports/<id>/addendum` | admin, senior_reviewer, lab_director | Create addendum (201) |
| POST | `/api/reports/<id>/portal-token` | admin, senior_reviewer, lab_director | Issue physician portal token (201) |

### Assay Configs

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/assay-configs` | ⚠️ none | List all assay configs |
| GET | `/api/assay-configs/<assay_id>` | ⚠️ none | Get active config |
| POST | `/api/assay-configs` | admin, senior_reviewer, lab_director | Create config (201) |

### Callsets / Ingestion

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/sample-assays/<id>/callsets` | login | List callsets for case |
| GET | `/api/callsets/<callset_id>` | login | Get callset detail |
| POST | `/api/sample-assays/<id>/callsets/import` | admin, bioinformatician, lab_director | Trigger import via API (201) |

### Users

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/users` | admin, lab_director, senior_reviewer | List users (no password hashes) |
| POST | `/api/users` | admin, lab_director | Create user (201) |

### Knowledge Database

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/knowledge` | login | List knowledge entries (filters: gene, variant_type, tier, disease_group, disease_subtype) |
| POST | `/api/knowledge` | admin, senior_reviewer, lab_director | Create entry (201) |
| GET | `/api/knowledge/<id>` | login | Get entry |
| PUT | `/api/knowledge/<id>` | admin, senior_reviewer, lab_director | Update entry (versioned) |
| GET | `/api/knowledge/search?q=...` | login | Full-text search (min 3 words) |
| GET | `/api/knowledge/lookup/snv?gene=&hgvsp=&disease_subtype=` | login | Disease-aware lookup |

### Advanced Features

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/lab/dashboard` | admin, lab_director, senior_reviewer | TAT/SLA dashboard stats |
| GET | `/api/gap-analysis?gene=&assay_id=` | admin, lab_director | Assay gene coverage query |
| GET | `/api/cohort?gene=&tier=&variant_type=&assay_id=&acknowledge=` | login | Cohort variant query |
| POST | `/api/federation/export` | admin, lab_director | Build and store knowledge export (201) |
| POST | `/api/federation/import` | admin, lab_director | Import from external registry |
| GET | `/api/federation/exports` | admin, lab_director | List export history |
| GET | `/api/federation/eligible` | admin, lab_director | Count of federation-eligible entries |

### Non-API Routes

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/` | none | Jinja2 landing page |
| GET | `/about` | none | Jinja2 about page |
| GET / POST | `/login` | none | Jinja2 login form (form-encoded, not JSON) |
| POST | `/logout` | none | Clears session, redirects to `/` |
| GET | `/portal/` | none | Physician portal landing |
| GET | `/portal/access/<token>` | token | Validates token, sets `session["portal_token"]`, redirects |
| GET | `/portal/report` | portal token | Read-only report view |
| POST | `/portal/logout` | none | Clears portal token |
| GET | `/docs`, `/redoc`, `/openapi.json` | none | Auto-generated API documentation |

---

## CLI Commands

The CLI is a [Typer](https://typer.tiangolo.com/) app at `backend/app/cli.py`. Every command opens its own Mongo/Redis connections, so it runs independently of the web workers.

Run it inside the app container (the usual case):

```bash
# Load seed / demo data
docker exec app_omixia python cli.py load-demo

# Create an internal user (prompts for password, min 12 chars)
docker exec -it app_omixia python cli.py create-user \
  --username jdoe --email jdoe@lab.example --full-name "J Doe" --role reviewer

# Import a single VCF (full pipeline)
docker exec app_omixia python cli.py import-vcf \
  --vcf <path> --qc <path> --sample-assay-id <id> \
  [--skip-normalise] [--skip-annotate]

# Run the directory watcher (long-running or cron mode)
docker exec app_omixia python cli.py run-watcher \
  [--watch-dir /data/vcf_inbox] [--interval 900] [--once]

# Discover options for any command
docker exec app_omixia python cli.py --help
docker exec app_omixia python cli.py import-vcf --help
```

Notes:
- `create-user` needs `-it` because it prompts for the password interactively.
- All paths are resolved **inside the container**.
- Running `python cli.py …` on the host works too, but only with the backend `.env` exported and Mongo/Redis reachable at the hostnames in `MONGO_URI` / `CACHE_REDIS_URL` (which are Docker service names, so container execution is strongly preferred).

---
## Configuration

Configuration is read from `backend/.env` into a `pydantic-settings` `Settings` object in `src/config.py`, exported as the module-level singleton `settings`. Start from `backend/.env.example`.

### Core

| Variable | Read as | Default | Description |
|---|---|---|---|
| `FLASK_SECRET_KEY` | `settings.SECRET_KEY` | `""` | Signing key for the session cookie. **Must be set** — an empty key makes sessions forgeable. Generate with `python -c "import secrets; print(secrets.token_hex(32))"`. |
| `SESSION_COOKIE_NAME` | same | `session` | Cookie name (this deployment uses `Omixia`). |
| `FLASK_DEBUG` | `settings.DEBUG` | `0` | `1` to enable debug mode. |
| `MONGO_URI` | same | `""` | MongoDB connection URI. |
| `OMIXIA_DB_NAME` | same | `""` | MongoDB database name. |
| `CACHE_REDIS_URL` | same | `""` | Redis URL — backs the session store. |
| `REPORTS_BASE_PATH` | same | `""` | Filesystem path for generated report files. |
| `DEVELOPMENT` / `TESTING` | same | `0` | Environment flags. |

> The `FLASK_`-prefixed names are retained deliberately: the migration mapped them via `Field(validation_alias=...)` rather than renaming, so existing `.env` files and the deployment runbook keep working. They no longer imply Flask is in use.

### Session & CORS (required for cross-origin production)

| Variable | Default | Description |
|---|---|---|
| `SESSION_COOKIE_SAMESITE` | `Lax` | Set to `None` when the SPA is served from a different origin. |
| `SESSION_COOKIE_SECURE` | `0` | Set to `1` in production; required whenever SameSite is `None`. |
| `ALLOWED_ORIGINS` | `""` | Comma-separated origins for `CORSMiddleware`. **Empty falls back to `*`**, which cannot be combined with credentialed requests — set it explicitly in production. |
| `SPA_BASE_URL` | `""` | SPA URL used by the Jinja2 landing page for cross-origin links. Falls back to `http://<host>:8080`. |

### Ingestion Pipeline

| Variable | Default | Description |
|---|---|---|
| `VCF_IMPORT_DIR` | `/data/vcf_inbox` | Watched inbox directory for `run-watcher`. |
| `BCFTOOLS_BIN` | `bcftools` | Path to the bcftools binary. |
| `VEP_BIN` | `vep` | Path to the Ensembl VEP binary. |
| `VEP_CACHE_DIR` | `""` | Path to the VEP local cache directory. |
| `REF_FASTA` | `""` | GRCh38 reference FASTA for `bcftools norm`. |
| `WATCHER_USER_ID` | `watcher` | User ID attributed to watcher-triggered imports. |
| `WATCHER_USERNAME` | `watcher` | Username attributed to watcher-triggered imports. |

These are consumed as Typer option defaults in `src/cli/{import_vcf,watcher}.py`, not through `Settings`.

### Docker Compose

| Variable | Description |
|---|---|
| `MONGO_INITDB_ROOT_USERNAME` | Mongo root user created on first container start. |
| `MONGO_INITDB_ROOT_PASSWORD` | Mongo root password — must match the credentials in `MONGO_URI`. |
| `PORT_NBR` | Informational; the app listens on 8000 inside the container. |
