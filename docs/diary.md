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
