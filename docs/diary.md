# Omixia React Frontend — Development Diary

**Date:** 2026-03-08
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
