# Omixia — Development Diary (Historical Archive)

> ## ⚠️ This file is frozen — do not add to it
>
> It is kept for the debugging narratives in entries 1–24, which are still worth grepping when a similar problem resurfaces.
>
> **New changes go in [CHANGELOG.md](../CHANGELOG.md)**, which is the maintained record of what changed and when. Milestones from this diary have been backfilled there; the day-to-day fixes were deliberately left here rather than duplicated.
>
> For how the system works today, see [ARCHITECTURE.md](ARCHITECTURE.md) — this diary describes states the codebase has since moved past (notably, everything before entry 24 predates the Flask → FastAPI migration).

**Covers:** 2026-03-08 → 2026-08-05
**Branch:** dev
**Author:** Development session log

---

## Overview

This session covers the creation of the React SPA frontend and a series of bugs found and fixed while bringing it up against the live Flask API and demo data.

---

## 1. React Frontend Created

A new SPA was built in `frontend/` using:
- React 18 + TypeScript + Vite
- TanStack Query v5 for server state
- Axios with `withCredentials: true` for session cookie auth
- React Router v6
- Tailwind CSS 3

Pages created: Login, Dashboard, Samples, Sample Detail (assay view), Knowledge, Lab Dashboard, Gap Analysis, Cohort.

---

## 2. Connectivity Issues (Port Not Accessible)

**Problem:** Vite dev server on port 3000 was not reachable from the home network; only port 80 was open.

**Fix:** Instead of running the Vite dev server, the build output (`frontend/dist/`) is served via a second Nginx server block on port 8080 (already exposed in Docker). The workflow is:
```bash
cd frontend && npm run build
```
Nginx on port 8080 serves the static files and proxies `/api/` to `app:8000`.

**Files changed:** `backend/nginx/default.conf`, `backend/docker-compose.yml`

---

## 3. 403 on Port 8080 After Build

**Problem:** `dist/` directory was owned by root (created by a Docker volume init), causing a permission denied error when rebuilding.

**Fix:** Delete and recreate `dist/`, then restart the nginx container so the bind mount inode is refreshed:
```bash
rm -rf frontend/dist && npm run build
docker compose restart nginx
```

---

## 4. Page Refresh Loop on Login

**Problem:** The Axios 401 interceptor in `client.ts` was redirecting to `/login` when `GET /api/auth/me` returned 401 on the initial unauthenticated load. This triggered another mount → another `GET /api/auth/me` → another 401 → infinite loop.

**Fix:** Skip the redirect when the failing URL is `/auth/me`:
```typescript
if (is401 && !url.includes('/auth/me')) {
  window.location.href = '/login'
}
```

**File:** `frontend/src/api/client.ts`

---

## 5. Login Failing for React Frontend (KeyError: `_id`)

**Problem:** `POST /api/auth/login` was crashing with `KeyError: '_id'`. The `api_login` route tried to access `user["_id"]`, but `UserService.authenticate()` returns a clean dict with `user_id` (no MongoDB `_id` field — it is excluded in all queries).

**Fix:**
```python
# Before
"user_id": str(user["_id"]),
# After
"user_id": user["user_id"],
```

**File:** `backend/app/src/blueprints/api_v1/routes.py:45`

---

## 6. Samples Page Showing Nothing

**Problem:** The `SamplesPage` used `sample._id` everywhere (for React keys, query keys, navigation URLs), but the backend excludes `_id` from all MongoDB queries. Also referenced `patient_name` which does not exist.

**Fixes:**
- `sample._id` → `sample.sample_id`
- `a._id` → `a.sample_assay_id`
- `patient_name` → `patient_pseudonym_id`
- Removed misleading `'unreviewed'` fallback badge on sample rows (status is per-assay, not per-sample)

**File:** `frontend/src/pages/SamplesPage.tsx`

---

## 7. Assay Detail Page — Multiple Field Name Mismatches

**Problem:** The `SampleDetailPage` had several wrong field names across all tabs.

### 7a. Variants — `review_status` and `tier` blank

`review_status` and `tier` are nested inside `review_current` in the DB document, not at the top level. The table accessed them as `row.review_status` directly.

**Fix:** Added `flattenVariant()` helper that hoists `review_current.status` → `review_status` and `review_current.tier` → `tier` before passing rows to `VariantTable`.

### 7b. CNV column name

`cnv_type` → `event_type` (actual field in `cnvs_raw`).

### 7c. SV column names and review ID

- Columns: `gene_a` / `gene_b` → `gene_5prime` / `gene_3prime`
- SV review URL used `variant._id` → `variant.sv_id`

### 7d. Summary showing `[object Object]`

The summary has nested objects (`raw_counts`, `review_counts`, `tier_counts`). The generic `Object.entries()` renderer called `String(v)` on them, producing `[object Object]`.

**Fix:** Replaced with explicit stat cards reading the nested fields directly.

### 7e. Reports tab using `_id`

All report operations used `r._id`; the backend uses `report_id`.

**Fix:** `r._id` → `r.report_id` for key, display, sign-off, finalise, and export URL.

### 7f. Callsets tab using `_id` and wrong fields

- `c._id` → `c.callset_id`
- `imported_by_username` and `variant_count` do not exist — replaced with `is_active` (badge) and `raw_counts.snv/cnv/sv`

**File:** `frontend/src/pages/SampleDetailPage.tsx`

---

## 8. Callset `raw_counts` Incorrect in Demo Data

**Problem:** The demo callset `CS_LUNG_001` stored `{snv: 3, cnv: 0, sv: 0}` but the actual loaded variants were `{snv: 2, cnv: 3, sv: 2}`. The counts were set during a simulated VCF import and never updated when CNV/SV demo data was added.

**Fix:** Updated `callsets.json` and the live MongoDB document:
```javascript
db.callsets.updateOne(
  { callset_id: "CS_LUNG_001" },
  { $set: { "raw_counts.snv": 2, "raw_counts.cnv": 3, "raw_counts.sv": 2 } }
)
```

---

## 9. Callset Missing `qc_status` → Preflight QC Check Failing

**Problem:** The demo callset had no `qc_status` field, causing the preflight "Callset QC within acceptable thresholds" check to always fail with status `unknown`.

**Fix:** Added `"qc_status": "passed"` to `callsets.json` and updated the live document:
```javascript
db.callsets.updateOne({ callset_id: "CS_LUNG_001" }, { $set: { qc_status: "passed" } })
```

---

## 10. Biomarkers Tab — All Fields Missing

**Problem:** The `BiomarkersTab` displayed fields that do not exist (`msi_status`, `tmb_score`, `tmb_class`, `status`). The confirm-button guard also checked `bm.status` instead of `bm.review_status`.

**Actual field names:**

| Wrong | Correct |
|---|---|
| `msi_status` | `msi_classification` |
| `tmb_score` | `tmb_mut_per_mb` |
| `tmb_class` | `tmb_classification` |
| `status` | `review_status` |

**Fix:** Updated all field references and added an amber discordance banner that shows `discordance_note` when `discordance_flag` is true.

**File:** `frontend/src/pages/SampleDetailPage.tsx`

---

## 11. Preflight Tab — All Checks Showing Red

**Problem:** The preflight API returns `{ status, description, detail }` per check, but the frontend read `{ passed, name, message }`.

**Fixes:**
- `check.passed` → `(check.status as string) === 'pass'`
- `check.name` → `check.description`
- `check.message` → `check.detail`

**File:** `frontend/src/pages/SampleDetailPage.tsx`

---

## 12. Knowledge Page — Wrong ID Field and Field Names

**Problem:** The `KnowledgePage` used `e._id` for row keys and update calls, and `clinical_significance` as a field name. The backend uses `knowledge_id` and `interpretation` respectively.

**Fixes:**
- `e._id` → `e.knowledge_id` (row key, selection highlight, update mutation)
- `clinical_significance` → `interpretation` (detail panel display, form state, input binding, `KnowledgePayload` interface)

**Files:** `frontend/src/pages/KnowledgePage.tsx`, `frontend/src/api/knowledge.ts`

---

## 13. Knowledge Page — Missing Demo Data + Silent Search Failure

**Problem:**
1. Only 1 of 5 knowledge entries was in MongoDB (demo data was partially loaded at some earlier point).
2. The full-text search silently returned empty results when fewer than 3 words were entered (MongoDB text search spec requirement: minimum 3 words). There was no user-facing explanation.

**Fixes:**
1. Reloaded all 5 demo knowledge entries directly into MongoDB.
2. Frontend now disables the search query when fewer than 3 words are typed and shows an inline hint: *"Full-text search requires at least 3 words. Use the Gene filter for single-gene lookup."* The `retry: false` option prevents TanStack Query from masking API errors with silent retries.

**File:** `frontend/src/pages/KnowledgePage.tsx`

---

---

## 14. User Registration API Route Added

**Date:** 2026-03-10

**Change:** Added `POST /api/users` and `GET /api/users` endpoints to the `api_v1` blueprint.

Previously, users could only be created via the `flask create-user` CLI command. These new routes expose user management over HTTP.

**`POST /api/users`** — Register a new user. Restricted to `admin` and `lab_director` roles.

Request body:
```json
{
  "username": "jsmith",
  "email": "j.smith@lab.org",
  "full_name": "Jane Smith",
  "role": "reviewer",
  "password": "secure_password_123"
}
```

Validation:
- All fields are required → `400`
- Password must be ≥ 12 characters → `400`
- Duplicate username or email → `409`
- Invalid role → `409`

Returns the created user (without `password_hash`) with status `201`.

**`GET /api/users`** — List all users (no password hashes). Restricted to `admin`, `lab_director`, and `senior_reviewer`.

**File:** `backend/app/src/blueprints/api_v1/routes.py`

---

## 15. `admin` Role Added

**Date:** 2026-03-10

**Change:** A new `admin` role was introduced that sits above `lab_director` and has access to every role-protected endpoint in the system.

`"admin"` was added to `VALID_ROLES` in `UserService` and prepended to every `@require_role(...)` decorator that previously included `lab_director`, covering:

| Endpoint | Decorator |
|---|---|
| `GET /api/users` | `admin`, `lab_director`, `senior_reviewer` |
| `POST /api/users` | `admin`, `lab_director` |
| `POST /api/assay-configs` | `admin`, `lab_director`, `senior_reviewer` |
| `POST /api/sample-assays/<id>/assign` | `admin`, `lab_director`, `senior_reviewer` |
| `POST /api/sample-assays/<id>/biomarkers/classify` | `admin`, `lab_director`, `senior_reviewer`, `bioinformatician` |
| `POST /api/reports/<id>/finalise` | `admin`, `senior_reviewer`, `lab_director` |
| `POST /api/reports/<id>/addendum` | `admin`, `senior_reviewer`, `lab_director` |
| `POST /api/knowledge` | `admin`, `senior_reviewer`, `lab_director` |
| `PUT /api/knowledge/<id>` | `admin`, `senior_reviewer`, `lab_director` |
| `GET /api/lab/dashboard` | `admin`, `lab_director`, `senior_reviewer` |
| `GET /api/gap-analysis` | `admin`, `lab_director` |
| `POST /api/reports/<id>/portal-token` | `admin`, `lab_director`, `senior_reviewer` |
| `POST /api/federation/export` | `admin`, `lab_director` |
| `POST /api/federation/import` | `admin`, `lab_director` |
| `GET /api/federation/exports` | `admin`, `lab_director` |
| `POST /api/sample-assays/<id>/callsets/import` | `admin`, `bioinformatician`, `lab_director` |

**Files:** `backend/app/src/services/users.py`, `backend/app/src/blueprints/api_v1/routes.py`

---

## 16. `admin` Demo User Missing from Database

**Date:** 2026-03-10

**Problem:** The `admin` user defined in `backend/app/demo_data/users.json` was not present in the database. Only 4 users existed (geneticist, senior, director, bioinf).

**Root cause:** The `admin` entry was added to `users.json` after `flask load-demo` was last run. The original file (committed in `04c274d`) contained only 4 users. The `admin` entry was added locally but `load-demo` was never re-executed, so the database was never updated.

**Fix:** Re-run the demo loader inside the running container:
```bash
docker exec app_omixia flask load-demo
```
This wipes and re-imports all users from the current `users.json`, including `admin`.

**Note:** `load_demo.py` also omitted `admin` from its credentials print-out (lines 57–61), which should be updated to include the admin user for completeness.

**File:** `backend/app/demo_data/users.json`, `backend/app/src/cli/load_demo.py`

---

## 17. `admin` Role Added to Lab Dashboard and Gap Analysis Web Routes

**Date:** 2026-03-10

**Problem:** The `admin` role had access to the API endpoints (`/api/lab/dashboard`, `/api/gap-analysis`) but was missing from the corresponding web routes, so an admin user would be redirected to the dashboard instead of seeing those pages.

**Fix:** Added `"admin"` to four `@require_role` decorators in the web blueprint:

| Route | Before | After |
|---|---|---|
| `GET /lab-dashboard` | `lab_director`, `senior_reviewer` | `admin`, `lab_director`, `senior_reviewer` |
| `GET /partials/lab-dashboard/stats` | `lab_director`, `senior_reviewer` | `admin`, `lab_director`, `senior_reviewer` |
| `GET /gap-analysis` | `lab_director` | `admin`, `lab_director` |
| `GET /partials/gap-analysis` | `lab_director` | `admin`, `lab_director` |

**File:** `backend/app/src/blueprints/web/routes.py`

---

---

## 18. User Registration Frontend (UsersPage)

**Date:** 2026-03-11

**Change:** Added a `UsersPage` at `/users` visible to `admin`, `lab_director`, and `senior_reviewer`.

**Features:**
- Lists all registered users in a table (username, email, role badge, active status, created date)
- Register form visible only to `admin` and `lab_director`
- Role-based assignable roles: `admin` can assign any role; `lab_director` cannot assign `admin`
- Client-side validation: all fields required, password ≥ 12 chars
- Uses TanStack Query `useQuery` + `useMutation`; refetches list on successful registration

**New files:**
- `frontend/src/api/users.ts` — `usersApi.list()` and `usersApi.create()`
- `frontend/src/pages/UsersPage.tsx`

**Modified files:**
- `frontend/src/App.tsx` — added `/users` route
- `frontend/src/components/Layout.tsx` — added "Users" nav link with role filter

---

## 19. Lab Dashboard Demo Data and UI Overhaul

**Date:** 2026-03-11

**Problem:** The lab dashboard showed no data. `TATService.dashboard_stats()` returned empty/null aggregates because only one `sample_assay` existed (no terminal cases, no SLA variation). The frontend page also rendered nested objects as `[object Object]` using a raw `Object.entries()` dump.

**Fix — Demo data expanded:**
- `backend/app/demo_data/samples.json`: 2 → 9 samples (LUNG, BREAST, BRAIN, COLON, SKIN, KIDNEY, LIVER, OVARY, PROSTATE)
- `backend/app/demo_data/sample_assays.json`: 1 → 9 assays covering all states and SLA outcomes:

| Assay | State | SLA status |
|---|---|---|
| SA_LUNG_001 | `review_in_progress` | on_track (stalled) |
| SA_BREAST_001 | `pending_qc` | on_track |
| SA_BRAIN_001 | `review_in_progress` | amber (urgent) |
| SA_COLON_001 | `analysis_ready` | breached |
| SA_SKIN_001 | `review_complete` | amber |
| SA_KIDNEY_001 | `preflight_failed` | breached |
| SA_LIVER_001 | `report_delivered` | terminal (within SLA) |
| SA_OVARY_001 | `report_delivered` | terminal (within SLA) |
| SA_PROSTATE_001 | `finalised` | terminal |

**Fix — Frontend rewritten:**
- Typed TypeScript interfaces: `ActiveCase`, `AssayBreakdown`, `DashboardStats`
- Summary stat cards: Active Cases, Finalised, SLA Breached (red), Due Within 48h (amber), Stalled Cases, Within SLA %, Median TAT
- Active cases table with colour-coded SLA badges (breached=red, amber=yellow, on_track=green), priority badge, stalled badge, TAT hours
- TAT by Assay breakdown table

**File:** `frontend/src/pages/LabDashboardPage.tsx`

---

## 20. SPEC.md and CLAUDE.md Restructured for Phases 8 and 9

**Date:** 2026-03-11

**Change:** Both documentation files were overhauled to give clear, actionable task lists for the remaining work.

**SPEC.md — Phase 16 section rewritten:**
- Phases 1–7 converted to `- [x]` checkbox format with every completed item documented
- Phase 8 (Architecture Harmonisation) broken into 5 tasks with atomic `- [ ]` sub-items and exact API endpoint references
- Phase 9 (Production Deployment) broken into 10 tasks with exact shell commands, `config.yml` snippets, environment variable names, and a 10-item smoke-test checklist

**CLAUDE.md — Expanded from 6 lines to full project guide:**
- Project structure tree
- Three-blueprint architecture explanation
- Auth mechanism summary
- Phase progress table
- Phase 8 next-task ordered list
- Phase 9 deployment quick reference
- Key patterns (endpoint, API module, page, audit logging, demo data)

---

## 21. Phase 8 — Architecture Harmonisation Complete

**Date:** 2026-03-11

**Change:** Completed the full Phase 8 task list: React SPA is now the sole clinical interface, the web blueprint is slimmed to landing/about/login/logout only, and CORS + cross-origin session cookies are fully configured.

### 8.1 — Feature parity (already done)

All clinical tabs (Variants, CNV, SV, Biomarkers, Reports, Callsets, Preflight) were already present in `SampleDetailPage.tsx` from earlier sessions.

### 8.2 — Physician portal token UI

Added an "Issue physician link" button to the Reports tab, visible only to `lab_director`, `senior_reviewer`, and `admin` on finalised reports. Clicking it calls `POST /api/reports/<id>/portal-token` and displays the returned URL inline.

Added `issuePortalToken()` to `frontend/src/api/reports.ts`.

Fixed the Export JSON `<a href>` to use `client.defaults.baseURL` (reads `VITE_API_BASE_URL`) instead of the hardcoded `/api` prefix.

**File:** `frontend/src/pages/SampleDetailPage.tsx`, `frontend/src/api/reports.ts`

### 8.3 — Federation page

Created `frontend/src/api/federation.ts` with `listExports`, `eligibleCount`, and `export` methods.

Created `frontend/src/pages/FederationPage.tsx` — shows eligible entry count, export history table, and an export form with `lab_id` input. Restricted to `lab_director`.

Added `GET /api/federation/eligible` endpoint to `api_v1` routes (was missing; only `eligible_entries()` existed in the service layer).

Added `/federation` route to `App.tsx` and "Federation" nav link to `Layout.tsx`.

**New files:** `frontend/src/api/federation.ts`, `frontend/src/pages/FederationPage.tsx`

**Modified files:** `backend/app/src/blueprints/api_v1/routes.py`, `frontend/src/App.tsx`, `frontend/src/components/Layout.tsx`

### 8.4 — Web blueprint slimmed

`backend/app/src/blueprints/web/routes.py` rewritten to keep only 4 routes: `GET /` (landing), `GET /about`, `GET+POST /login`, `POST /logout`. All HTMX partials, dashboard, samples, knowledge, cohort, lab-dashboard, gap-analysis, federation, and callsets routes removed.

Login success now redirects to `web.landing` (the React SPA link covers the actual post-login destination).

All app-section Jinja2 templates and partials moved to `backend/app/src/blueprints/web/templates/archive/`.

### 8.5 — CORS and cross-origin session cookies

Added `Flask-Cors==4.0.1` to `requirements.txt` and rebuilt the Docker image.

`__init__.py`: added CORS initialisation covering `r"/api/*"` with `supports_credentials=True`, using `ALLOWED_ORIGINS` list when set or falling back to `"*"` in development.

`config.py`: added three new config values:
- `SESSION_COOKIE_SAMESITE` (default `"Lax"`)
- `SESSION_COOKIE_SECURE` (default `False`)
- `ALLOWED_ORIGINS` (parsed from comma-separated env var)

`nginx/default.conf`: added `proxy_hide_header Access-Control-Allow-Origin` to the `/api/` location block on port 80 to prevent Flask-CORS and nginx from adding duplicate CORS headers.

Rebuilt Docker image to pick up the new dependency: `docker compose build app && docker compose up -d app`.

**Modified files:** `backend/app/requirements.txt`, `backend/app/src/__init__.py`, `backend/app/src/config.py`, `backend/nginx/default.conf`, `frontend/tsconfig.json` (added `"types": ["vite/client"]` to fix pre-existing `import.meta.env` TS error)

---

## 22. Landing Page — Cross-Origin Links to React SPA

**Date:** 2026-03-11

**Problem:** The web blueprint's landing page had two links pointing to Flask routes that were removed in Phase 8:
- "View Samples" → `/samples` (dead route)
- "Login to Dashboard" → `/login` (Flask session login, not the React SPA)

When a user clicked either button, the request hit Flask on port 80, which no longer handled those paths.

**Fix:** Added `SPA_BASE_URL` config variable (env var, default `http://localhost:8080`) and passed it to the landing template. The two buttons now link to `{{ spa_base_url }}/samples` and `{{ spa_base_url }}/login`, pointing directly into the React SPA.

**Local dev flow:**
1. User visits `http://localhost` (Flask landing)
2. Clicks "View Samples" → `http://localhost:8080/samples` (React SPA)
3. React's `ProtectedRoute` redirects unauthenticated users to `/login` within the SPA
4. User logs in via `POST /api/v1/auth/login`, lands on `/samples`

**Production:** set `SPA_BASE_URL=https://app.yourdomain.com` in `backend/.env`.

**Modified files:**
- `backend/app/src/config.py` — added `SPA_BASE_URL`
- `backend/app/src/blueprints/web/routes.py` — pass `spa_base_url` to template
- `backend/app/src/blueprints/web/templates/landing.html` — updated `href` attributes
- `backend/.env.example` — documented `SPA_BASE_URL`

---

---

## 23. Phase 9 — Production Deployment (Cloudflare Free Tier)

**Date:** 2026-03-22

**Goal:** Deploy Omixia as a publicly accessible demo at zero cost using Cloudflare Quick Tunnel (backend) and Cloudflare Pages (frontend SPA).

---

### 23.1 — Ops Documentation (`docs/ops.md`)

Created `docs/ops.md` as the operational runbook for the deployment. Contains:
- Secret rotation procedures for `FLASK_SECRET_KEY`, MongoDB password, and Redis
- Full environment variable reference table (what each var does and where it is read)
- Backup and restore instructions using `scripts/backup_mongo.sh`
- Docker container management commands (restart, rebuild, logs)

**New file:** `docs/ops.md`

---

### 23.2 — MongoDB Backup Script (`scripts/backup_mongo.sh`)

Created a shell script that produces timestamped `mongodump` snapshots:
- Runs `mongodump` inside the `mongo_omixia` container via `docker exec`
- Copies the dump to a local `backups/` directory
- Auto-reads `MONGO_PASSWORD` from `backend/.env` if not set in the environment
- Cleans up the temp dump inside the container after copying
- Deletes local backups older than 30 days automatically

Usage:
```bash
bash scripts/backup_mongo.sh
```

**New file:** `scripts/backup_mongo.sh`

---

### 23.3 — `.gitignore` Fix: Committed `node_modules` Symlinks

**Problem:** The Cloudflare Pages CI build failed with:
```
Cannot find module '../lib/tsc.js'
```
Root cause: `.gitignore` contained `frontend/node_modules/*`, which ignores the *contents* of `node_modules/` but not the directory itself. Git had tracked the `frontend/node_modules/.bin/` symlinks (including the `tsc` symlink). The symlink pointed to `../typescript/bin/tsc`, which in turn called `../lib/tsc.js` — a file that was gitignored. On Cloudflare Pages (a fresh clone), the symlink existed but the target did not, causing the build to crash.

**Fix:**
1. Changed `frontend/node_modules/*` → `frontend/node_modules/` in `.gitignore` (ignores the directory entirely)
2. Added `backups/` entry to `.gitignore`
3. Removed all 2416 tracked files under `frontend/node_modules/`:
```bash
git rm -r --cached frontend/node_modules/
git commit -m "remove accidentally tracked node_modules"
```

**File:** `.gitignore`

---

### 23.4 — `config.py` Bug Fix: Sessions Always Broken

**Problem:** Login appeared to succeed (201 response from the API) but every subsequent request was unauthenticated. Every protected route returned 401 immediately after login.

**Root cause:** `config.py` read `os.getenv("SECRET_KEY")` but `backend/.env` defined `FLASK_SECRET_KEY`. Because `SECRET_KEY` was never set in the environment, `app.config["SECRET_KEY"]` was `None`. Flask could not sign session cookies, so every session was discarded on the next request.

**Fix:**
```python
# config.py line 5 — before
SECRET_KEY = os.getenv("SECRET_KEY")
# after
SECRET_KEY = os.getenv("FLASK_SECRET_KEY")
```

Also renamed the variable in `backend/.env` to make the name unambiguous:
```
# before
SECRET_KEY=saile
# after
FLASK_SECRET_KEY=saile
```

**Files:** `backend/app/src/config.py`, `backend/.env`

---

### 23.5 — Production CORS / Session Cookie Configuration

Set the following values in `backend/.env` to enable cross-origin session cookies between Cloudflare Pages (frontend) and the backend tunnel:

| Variable | Value | Why |
|---|---|---|
| `SESSION_COOKIE_SAMESITE` | `None` | Required for cross-origin cookie sending |
| `SESSION_COOKIE_SECURE` | `True` | Required when `SameSite=None` (HTTPS only) |
| `ALLOWED_ORIGINS` | `https://omixia.pages.dev` | Restricts Flask-CORS to the Pages origin |
| `SPA_BASE_URL` | `https://omixia.pages.dev` | Used by Flask landing page links |

These values were already scaffolded in `config.py` (Phase 8); this step activated them for the live deployment.

---

### 23.6 — Cloudflare Quick Tunnel (Backend)

Used Cloudflare's free Quick Tunnel to expose the Docker nginx container (port 80) to the public internet without a Cloudflare account or domain:

```bash
cloudflared tunnel --url http://localhost:80
```

This generates a random `*.trycloudflare.com` URL that proxies all traffic to `localhost:80`. The tunnel URL is ephemeral — it changes every time the tunnel process is restarted.

**Tunnel URL history:**
- Session 1: `https://innovative-captured-urls-flooring.trycloudflare.com`
- Session 2: `https://kingdom-manager-properly-concept.trycloudflare.com`

**Limitation:** Each tunnel restart requires rebuilding the React frontend with the new `VITE_API_BASE_URL` and redeploying to Cloudflare Pages. A named tunnel (requires Cloudflare account + custom domain) would give a stable URL.

---

### 23.7 — Cloudflare Pages (Frontend)

Deployed the React SPA to Cloudflare Pages at `https://omixia.pages.dev`:

**Pages project settings:**
- Repository: GitHub `dev` branch
- Build command: `cd frontend && npm run build`
- Build output: `frontend/dist`
- Environment variable: `VITE_API_BASE_URL=https://<tunnel-url>/api`

The `VITE_API_BASE_URL` is baked into the JS bundle at build time by Vite. If the tunnel URL changes, the env var must be updated in the Pages dashboard and a new deployment triggered.

**Issue encountered:** The first successful Pages build was deploying an old commit (`d436a26`) because the node_modules fix commits had not been pushed yet. Fix: `git push origin dev`.

---

### 23.8 — Nginx `proxy_hide_header` Removed (CORS Fix)

**Problem:** After the Pages deployment went live, login returned a network error in the browser with "CORS missing allow header" visible in the Network tab.

**Root cause:** `backend/nginx/default.conf` contained:
```nginx
proxy_hide_header Access-Control-Allow-Origin;
```
in both `/api/` location blocks. This directive tells nginx to **strip** that response header from the upstream before forwarding to the browser. Flask-CORS was correctly setting the `Access-Control-Allow-Origin` header, but nginx was removing it. The browser never received the CORS header and blocked the response.

The directive was added in Phase 8 with the comment "prevent nginx from adding duplicates", but `proxy_hide_header` removes upstream headers — the opposite of the intended effect. Nginx was not adding its own CORS headers; there were no duplicates to prevent.

**Fix:** Removed both `proxy_hide_header Access-Control-Allow-Origin;` lines from `nginx/default.conf` and restarted the nginx container:
```bash
docker compose -f backend/docker-compose.yml restart nginx
```

After this fix, login worked and the dashboard at `https://omixia.pages.dev/dashboard` was accessible.

**File:** `backend/nginx/default.conf`

---

### 23.9 — Deployment Architecture (Current State)

```
Browser
  │
  ├─ https://omixia.pages.dev        (Cloudflare Pages — React SPA)
  │    └─ VITE_API_BASE_URL → https://<tunnel>.trycloudflare.com/api
  │
  └─ https://<tunnel>.trycloudflare.com
       └─ Cloudflare Quick Tunnel → localhost:80
            └─ nginx (Docker)
                 ├─ /api/* → Flask app:8000
                 └─ /      → Flask app:8000 (landing, login, portal)
```

Demo credentials: `admin` / `omixia_demo_1`

---

## Summary of Affected Files

| File | Changes |
|---|---|
| `frontend/src/api/client.ts` | Fix 401 refresh loop |
| `frontend/src/api/knowledge.ts` | Rename `clinical_significance` → `interpretation` |
| `frontend/src/pages/LoginPage.tsx` | (no changes needed — backend fix resolved login) |
| `frontend/src/pages/SamplesPage.tsx` | Fix `_id` → `sample_id`, patient field, status |
| `frontend/src/pages/SampleDetailPage.tsx` | Fix variants, summary, reports, callsets, biomarkers, preflight |
| `frontend/src/pages/KnowledgePage.tsx` | Fix `_id` → `knowledge_id`, field names, search UX |
| `frontend/vite.config.ts` | `host: true`, correct proxy target |
| `backend/nginx/default.conf` | Add port 8080 React SPA server block |
| `backend/docker-compose.yml` | Expose port 8080, mount `frontend/dist` |
| `backend/app/src/blueprints/api_v1/routes.py` | Fix `user["_id"]` → `user["user_id"]` in `api_login` |
| `backend/app/demo_data/callsets.json` | Fix `raw_counts`, add `qc_status` |

---

## 24. Backend Migration: Flask → FastAPI

**Date:** 2026-08-05

**Goal:** Full rewrite of the backend from Flask to FastAPI, keeping React and MongoDB unchanged, ahead of the still-pending Phase 9 production deployment.

### 24.1 — Approach

The `src/services/*.py` layer (~3,100 lines: samples, report, knowledge, biomarker, preflight, tat, gap_analysis, federation, ingestion, portal, users) was already framework-agnostic — pure PyMongo, no Flask imports except one lazy import in `audit.py`. That made the migration mostly a rewrite of the thin routing layer:

- **Kept PyMongo synchronous, route handlers `def` not `async def`** — FastAPI runs sync handlers in a threadpool automatically, so the entire services layer moved over unchanged. Rewriting to Motor/async was ruled out as disproportionate effort for no functional payoff.
- **Flask-Session (Redis) → hand-rolled signed-cookie sessions** (`src/session.py`): opaque session id signed with `itsdangerous`, session dict stored as JSON in Redis, `request.state.session` is a dict-like `Session` object that writes through to Redis on every mutation. Preserves the same cookie name/SameSite/Secure behavior the React SPA already depended on — no frontend changes needed.
- **`@require_login`/`@require_role` decorators → FastAPI dependencies** (`Depends(...)`) raising `HTTPException(401/403)` (`src/auth.py`).
- **Same URL prefixes verbatim** (`/api/*`, `/portal/*`, `/`) — blueprints became `APIRouter`s with identical routes/methods, so nginx and the frontend needed zero changes.
- **`{"data": ...}` / `{"error": "<msg>"}` envelope preserved** via a global `HTTPException` handler in `main.py` that renders `{"error": exc.detail}` instead of FastAPI's default `{"detail": ...}`.
- **`audit.py`'s `flask.has_request_context()` reach-in** replaced with `src/request_context.py` — a `contextvars.ContextVar[Request]` set by a small middleware in `main.py`, read back by `audit.py` for IP/session id capture. No changes needed to any of the ~40 call sites that already pass `actor_user_id`/`actor_role` explicitly.
- **Flask CLI commands → Typer app** (`cli.py` at the app root: `load-demo`, `create-user`, `import-vcf`, `run-watcher`), replacing `flask <command>` with `python cli.py <command>`.
- **Jinja2 templates** for the `web`/`portal` routers moved to `starlette.templating.Jinja2Templates` under `src/templates/{web,portal}/`. Only the live templates (`landing.html`, `login.html`, `base.html`, `about.html`, `portal/login.html`, `portal/report.html`) were carried over — `src/blueprints/web/templates/archive/*` was dead code (pre-Phase-8 HTMX partials, unreferenced by any route) and was dropped rather than migrated.
- **Dockerfile**: `gunicorn -w 2 -b 0.0.0.0:8000 wsgi:app` → `gunicorn -k uvicorn.workers.UvicornWorker -w 2 -b 0.0.0.0:8000 main:app`. Same multi-worker process model, same port — `docker-compose.yml` and `nginx/default.conf` needed no changes.

### 24.2 — Gotchas hit during the port

- **`config.py`**: `.env` still uses `FLASK_SECRET_KEY`/`FLASK_DEBUG` (left as-is, not renamed). The new pydantic-settings `Settings` class maps them via `Field(validation_alias="FLASK_SECRET_KEY")` etc.
- **`Jinja2Templates` needs the `jinja2` package explicitly** — FastAPI/Starlette don't pull it in as a hard dependency; had to add it to `requirements.txt`.
- **`typer==0.12.5` is incompatible with `click>=8.2`** (pip resolved `click==8.4.2` by default) — the CLI failed at startup with `TypeError: Secondary flag is not valid for non-boolean flag.` while building the boolean-flag options in `import_vcf`/`watcher`. Fixed by pinning `click==8.1.7` in `requirements.txt`.
- **`src/__init__.py`** still had the old Flask `create_app()` factory; since `src` is imported as a plain package now, this broke every import with `ModuleNotFoundError: No module named 'flask'` until emptied out.
- **Sandbox note**: the running `app_omixia` container could not be stopped/recreated from within this session (`docker stop`/`kill`/`rm` all returned "permission denied" at the daemon level) — verification was done via a throwaway parallel container (`docker run ... backend-app`) on the same network instead. The actual `app_omixia` cutover (`docker compose up -d --force-recreate app`) needs to be run by a human/session with permission to manage that container.

### 24.3 — Verification performed

Via the parallel verification container: `/api/health`, `python cli.py load-demo`, login/logout/`/api/auth/me` session round-trip for multiple demo users, role gating (401 unauthenticated, 403 wrong role) with the `{"error": ...}` envelope intact, SNV review submission (confirmed the resulting `audit_log` entry correctly captured `ip_address`/`session_id` via the new `request_context` mechanism), preflight checks, knowledge search, lab dashboard stats, and the `web`/`portal` Jinja2 pages (landing, login, portal index) all returning 200.

Not exercised: the full finalise → portal-token → portal-access chain (the demo dataset has no report that passes preflight to finalise) and the CNV/SV/federation endpoints specifically — these are mechanical 1:1 ports of the same pattern already verified elsewhere, but haven't been individually clicked through in the browser.

**Files changed:** `backend/app/main.py` (new), `backend/app/cli.py` (new), `backend/app/src/{config,extensions,auth,session,request_context}.py`, `backend/app/src/routers/{api_v1,web,portal}.py` (new, replacing `src/blueprints/`), `backend/app/src/templates/{web,portal}/` (new, replacing `src/blueprints/*/templates/`), `backend/app/src/cli/*.py`, `backend/app/src/db/indexes.py`, `backend/app/src/services/audit.py`, `backend/app/requirements.txt`, `backend/app/Dockerfile`, `CLAUDE.md`.
