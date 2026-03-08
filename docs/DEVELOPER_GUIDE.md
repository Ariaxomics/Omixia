# Omixia — Developer Guide

**Version:** 1.1
**Last Updated:** 2026-03-08
**Branch:** dev

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Project Structure](#project-structure)
3. [Getting Started](#getting-started)
4. [Authentication & Roles](#authentication--roles)
5. [React Frontend](#react-frontend)
6. [Data Models](#data-models)
7. [Feature Reference](#feature-reference)
   - [Phase 1 — Foundation](#phase-1--foundation)
   - [Phase 2 — Core Review Workflow](#phase-2--core-review-workflow)
   - [Phase 3 — Variant Types](#phase-3--variant-types)
   - [Phase 4 — Data Ingestion](#phase-4--data-ingestion)
   - [Phase 5 — Knowledge Database](#phase-5--knowledge-database)
   - [Phase 6 — Report Generation](#phase-6--report-generation)
   - [Phase 7 — Advanced Features](#phase-7--advanced-features)
8. [API Reference](#api-reference)
9. [CLI Commands](#cli-commands)
10. [Database Indexes](#database-indexes)
11. [Configuration](#configuration)

---

## Architecture Overview

Omixia is a clinical-grade somatic variant interpretation and reporting platform built with:

| Layer | Technology |
|---|---|
| Backend | Flask 3.x, Python 3.12 |
| Database | MongoDB 7 (document store) |
| Cache / Sessions | Redis 7 |
| Server-rendered UI | Jinja2 + Tailwind CSS + HTMX |
| React SPA | React 18, TypeScript, Vite, TailwindCSS, TanStack Query, Axios |
| Server | Gunicorn + Nginx |
| VCF normalisation | bcftools norm (subprocess) |
| Variant annotation | Ensembl VEP (subprocess) |

**Design principles:**
- Two frontend options share the same REST API: (1) Jinja2 + HTMX server-rendered UI, (2) standalone React SPA
- Services layer encapsulates all business logic; blueprints are thin routing only
- Append-only audit log — no updates or deletes on `audit_log`
- Optimistic locking on variant reviews using MongoDB `$expr` array length checks
- All clinical identifiers are pseudonymised; real patient identity lives in an external system

---

## Project Structure

```
frontend/                      # React SPA (see React Frontend section)
  src/
    api/                       # Axios API modules per domain
    components/                # Shared UI components
    contexts/                  # React contexts (auth)
    pages/                     # One file per route/page

backend/
  app/
    src/
      __init__.py              # Flask app factory, blueprint + CLI registration
      auth.py                  # @require_login, @require_role decorators, session helpers
      config.py                # Config class reading from environment variables
      extensions.py            # mongo_client, redis_client singletons
      blueprints/
        api_v1/
          routes.py            # All REST API endpoints (prefix: /api)
        web/
          routes.py            # All HTMX/HTML web routes
          templates/
            base.html          # Nav + layout shell
            samples.html       # Main review workspace (tabbed)
            dashboard.html
            knowledge.html
            lab_dashboard.html
            gap_analysis.html
            cohort.html
            federation.html
            partials/          # HTMX swap targets
              snv_table.html / snv_detail_form.html
              cnv_table.html / cnv_detail_form.html
              sv_table.html / sv_detail_form.html
              biomarker_card.html
              preflight_panel.html
              report_panel.html
              callsets_panel.html
              knowledge_list.html / knowledge_entry.html / knowledge_form.html
              lab_stats.html
              gap_analysis_result.html
              cohort_result.html
              portal_tokens.html
              federation_panel.html
        portal/
          routes.py            # Physician portal (prefix: /portal)
          templates/portal/
            login.html
            report.html
      services/
        assay_config.py        # Assay configuration CRUD
        audit.py               # Append-only audit log
        biomarker.py           # MSI/TMB classification and review
        federation.py          # Federated knowledge export/import
        gap_analysis.py        # Assay gap analysis + cohort queries
        ingestion.py           # VCF import pipeline (Phase 4)
        knowledge.py           # Variant knowledge database
        portal.py              # Physician portal token management
        preflight.py           # Pre-finalisation checklist
        report.py              # Report lifecycle management
        samples.py             # Variant review state machine
        tat.py                 # TAT/SLA tracking
        users.py               # User management + authentication
      db/
        indexes.py             # MongoDB index definitions
      cli/
        create_user.py         # flask create-user command
        import_vcf.py          # flask import-vcf command
        load_demo.py           # flask load-demo command
        watcher.py             # flask run-watcher command
    demo_data/                 # Seed data loaded by flask load-demo
      assay_configs.json
      biomarkers.json
      callsets.json
      cnvs_raw.json
      sample_assays.json
      samples.json
      snvs_raw.json
      svs_raw.json
      users.json
      variant_knowledge.json
```

---

## Getting Started

### Environment Variables

```bash
SECRET_KEY=<random-32-byte-hex>
SESSION_COOKIE_NAME=omixia_session
FLASK_DEBUG=0

MONGO_URI=mongodb://mongo:27017/
OMIXIA_DB_NAME=omixia

CACHE_REDIS_URL=redis://redis:6379/0
REPORTS_BASE_PATH=/data/reports

# Ingestion pipeline
VCF_IMPORT_DIR=/data/vcf_inbox
BCFTOOLS_BIN=bcftools
VEP_BIN=vep
VEP_CACHE_DIR=/data/vep_cache
REF_FASTA=/data/reference/GRCh38.fa
```

### Load Demo Data

```bash
flask load-demo
```

This loads demo users, samples, assays, variants, and knowledge entries. All demo users share the password `omixia_demo_1`.

| Username | Role |
|---|---|
| `geneticist` | `reviewer` |
| `senior` | `senior_reviewer` |
| `director` | `lab_director` |
| `bioinf` | `bioinformatician` |

---

## Authentication & Roles

### Internal Users

Session-based auth backed by Redis. Sessions expire after 8 hours of inactivity.

```
POST /login   { username, password }   → sets session["user"]
POST /logout  → clears session
```

**Role hierarchy:**

| Role | Key capabilities |
|---|---|
| `bioinformatician` | Import VCFs, manage callsets, view QC metrics. Cannot touch clinical interpretation. |
| `reviewer` | Review variants, set tier, write interpretation. Cannot finalise reports. |
| `senior_reviewer` | All reviewer capabilities + break tiebreaks + approve pre-finalisation + issue portal tokens. |
| `lab_director` | Read-only across everything + unlock finalised reports + lab-wide dashboards + manage assay configs + federation management. |
| `ordering_physician` | External portal only — read-only access to finalised reports via token link. |

### Decorator Usage

```python
@require_login          # any authenticated internal user
@require_role("lab_director", "senior_reviewer")   # role whitelist
```

### React SPA Auth

The React frontend uses three dedicated JSON endpoints on the API blueprint:

```
POST /api/auth/login   { username, password }  → sets session cookie, returns user object
POST /api/auth/logout                           → clears session
GET  /api/auth/me                              → returns current user or 401
```

`AuthContext` calls `GET /api/auth/me` on mount to rehydrate the session. All subsequent API calls include `withCredentials: true` so the browser forwards the session cookie. The Vite dev server proxies `/api` to `http://localhost:5000` to avoid CORS.

### Physician Portal Auth

Completely separate from the internal session. Tokens stored in `report_access_tokens` collection.

```
GET /portal/access/<token>    → validates token, sets session["portal_token"], redirects to report
GET /portal/report            → read-only report view (finalised only)
POST /portal/logout
```

---

## React Frontend

A standalone React 18 + TypeScript SPA lives in `frontend/`. It consumes the same `/api` REST endpoints as any external client and shares the Flask session-cookie auth mechanism.

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
├── vite.config.ts           # dev server on :3000, /api proxied to :5000
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
npm run dev          # http://localhost:3000
npm run build        # production build → dist/
npm run preview      # preview the production build locally
```

The Flask backend must be running at `http://localhost:5000` for the Vite proxy to forward API calls correctly.

---

## Data Models

### users
```
user_id         string (uuid)
username        string (unique index)
email           string (unique index)
role            enum
full_name       string
password_hash   string (bcrypt)
created_at      datetime
is_active       boolean
```

### samples
```
sample_id              string
patient_pseudonym_id   string  ← hash only, real identity is external
disease_group          "solid" | "haematological"
disease_subtype        string
created_at             datetime
```

### sample_assays
```
sample_assay_id         string
sample_id               string
assay_id / assay_version string
active_callset_id       string
status                  "pending_qc" | "qc_failed" | "analysis_ready" |
                        "review_in_progress" | "review_complete" |
                        "preflight_failed" | "finalised" |
                        "report_delivered" | "superseded"
priority                "routine" | "urgent"
assigned_reviewers      [user_id]
assigned_bioinformatician  user_id
sla_due_at              datetime
created_at              datetime
state_history           [{status, timestamp, actor_user_id, note}]
```

### callsets
```
callset_id              string (unique index)
sample_assay_id         string
vcf_path / vcf_checksum string
normalised_vcf_path     string
qc_metrics              {mean_depth, pct_bases_100x, contamination_estimate,
                         tumor_purity, tumor_purity_source, msi_score, tmb_mut_per_mb}
qc_status               "pending" | "passed" | "failed" | "borderline"
qc_failures             [string]
annotation_vep_version  string
import_status           "pending" | "normalising" | "annotating" | "imported" |
                        "superseded" | "failed"
import_error            string
raw_counts              {snv, cnv, sv}
created_at              datetime
imported_by             user_id
```

### snvs_raw / cnvs_raw / svs_raw
All variant collections share a `review_current` embedded document and a `review_history` append-only array. See [Phase 2](#phase-2--core-review-workflow) for the state machine.

### variant_knowledge
```
knowledge_id        string (uuid, unique index)
variant_type        "snv" | "cnv" | "sv"
gene / hgvsp / hgvsc / consequence   (SNV key)
event_type                           (CNV key)
gene_5prime / gene_3prime            (SV key)
disease_group / disease_subtype      string (null = pan-disease)
tier                "tier_1" | "tier_2" | "tier_3" | "tier_4"
interpretation      string
evidence_summary    string
evidence_tags       [string]
observation_count   int
version             int
version_history     [{version, tier, interpretation, edited_by, edited_at, change_note}]
is_contested        boolean
federation_eligible boolean
```

### reports
```
report_id               string (uuid, unique index)
sample_assay_id         string
status                  "draft" | "pending_sign_off" | "finalised" | "delivered" |
                        "amended" | "superseded"
report_type             "primary" | "addendum" | "corrected"
snapshot                { sample, assay, callset_qc, snvs, cnvs, svs, biomarkers,
                          knowledge_versions_used, threshold_versions_used }
preflight_checks        [{check_id, description, status, detail}]
sign_offs               [{user_id, role, signed_at, signature_type}]
created_at              datetime
```

### report_access_tokens
```
token           string (unique index, secrets.token_urlsafe(32))
report_id       string
issued_by_*     user metadata
issued_at       datetime
expires_at      datetime  (30-day TTL)
revoked         boolean
last_accessed_at datetime
```

---

## Feature Reference

---

### Phase 1 — Foundation

**Files:** `services/users.py`, `services/assay_config.py`, `services/audit.py`, `auth.py`

#### User Management
- `UserService.authenticate(username, password)` — bcrypt verify, returns user dict or None
- `UserService.create_user(data)` — hashes password, assigns uuid, stores to `users`

#### Assay Configuration
- `AssayConfigService.get_active_config(assay_id)` — returns currently active assay config
- `AssayConfigService.get_config(assay_id, version)` — exact version lookup
- `AssayConfigService.create_config(data)` — create new assay config (lab_director / senior_reviewer only)

Each assay config stores:
- `gene_panel` — list of `{gene, chrom, start, end, min_depth}` entries
- `cnv_thresholds` — amplification/deletion/LOH boundaries
- `msi_thresholds` / `tmb_thresholds` — biomarker classification cutoffs
- `qc_thresholds` — `{min_mean_depth, min_pct_bases_100x, max_contamination, min_tumor_purity}`
- `sla_days` — `{routine: 14, urgent: 5}`

#### Audit Log
`AuditService.log(event_type, actor_user_id, actor_role, target_collection, target_id, payload)`

Never raises on failure. Append-only — no updates or deletes ever written to `audit_log`.

---

### Phase 2 — Core Review Workflow

**Files:** `services/samples.py`

#### Two-Reviewer Consensus State Machine

```
unreviewed
  → pending_second_review   (first reviewer submits tier + interpretation)
  → concordant              (second reviewer agrees on same tier)
  → discordant              (second reviewer assigns different tier)
  → escalated               → resolved (senior_reviewer makes final call)
```

A variant is **reportable** only when `consensus_status = "concordant"` or `"resolved"`.

#### Key functions

| Function | Description |
|---|---|
| `SampleService.update_snv_review(...)` | Submit/update SNV review. Enforces state machine. |
| `SampleService.update_cnv_review(...)` | Same for CNVs. |
| `SampleService.update_sv_review(...)` | Same for SVs. |

All review updates are **optimistic-locked** using:
```python
{"$expr": {"$eq": [{"$size": "$review_history"}, history_len]}}
```
If the history has grown since the page was loaded, the update is rejected and the user sees a conflict error.

#### Bypass Mechanism

When a `senior_reviewer` sets `bypass_justification` (non-empty), the single-reviewer result is accepted and marked `resolved`. Recorded in audit trail and surfaced in report.

#### Case Assignment

`SampleService.assign_case(sample_assay_id, reviewer_ids, bioinformatician_id)` — lab_director / senior_reviewer only.

---

### Phase 3 — Variant Types

**Files:** `services/samples.py`, `services/biomarker.py`

#### CNV Review

- Keyed by `(sample_assay_id, gene)`.
- `is_borderline = True` when copy number is within 10% of a threshold boundary.
- Borderline CNVs require explicit geneticist selection with justification.

#### SV / Fusion Review

- Keyed by `sv_id`.
- `is_novel_breakpoint = True` flags novel breakpoints for extended review even when the gene pair is known.
- `sv_type` values: `fusion`, `inversion`, `deletion`, `duplication`, `translocation`.

#### MSI / TMB Biomarkers

`BiomarkerService.classify_from_callset(sample_assay_id)` — reads `msi_score` and `tmb_mut_per_mb` from the active callset's QC metrics and classifies against the active assay config thresholds.

`BiomarkerService.confirm(sample_assay_id, reviewer_note, discordance_acknowledged, ...)` — lightweight confirmation step required before preflight can pass.

Discordance flag (`discordance_flag = True`) is set when MSI and TMB classifications contradict each other (e.g. MSI-H + TMB-Low). Reviewer must explicitly acknowledge before proceeding.

---

### Phase 4 — Data Ingestion

**Files:** `services/ingestion.py`, `cli/import_vcf.py`, `cli/watcher.py`

#### VCF Import Pipeline

```
1. SHA256 checksum → idempotency check (skip if already imported)
2. Validate sample_assay_id exists
3. Supersede any existing imported callset for this case
4. Create callset record (import_status = "pending")
5. bcftools norm: left-align, split multiallelics, trim padding
6. VEP annotation: --everything --canonical --offline
7. Parse annotated VCF → insert snvs_raw documents
8. Parse QC JSON → populate qc_metrics
9. QC gate evaluation → qc_status: passed / borderline / failed
10. Update sample_assay status: analysis_ready / pending_qc / qc_failed
11. Append to state_history, write audit log entry
```

#### QC Gate Thresholds (from assay config `qc_thresholds`)

| Metric | Default |
|---|---|
| `min_mean_depth` | 100× |
| `min_pct_bases_100x` | 80.0% |
| `max_contamination` | 0.05 |
| `min_tumor_purity` | 0.20 (when set) |

`borderline` status is returned when only soft metrics fail (purity / contamination near threshold). Hard failures (depth, coverage) → `failed`.

#### Callset Versioning

If a new VCF is imported for a case that already has an `imported` callset:
- All previous callsets for that `sample_assay_id` are marked `import_status = "superseded", is_active = False`
- A `callset_superseded` audit event is written
- The new callset becomes active

#### CLI: `flask import-vcf`

```bash
flask import-vcf \
  --vcf /path/to/sample.vcf.gz \
  --qc /path/to/sample.qc.json \
  --sample-assay-id SA_LUNG_001 \
  --user-id user123 \
  --username bioinf \
  --bcftools /usr/bin/bcftools \
  --vep /usr/bin/vep \
  --vep-cache /data/vep_cache \
  --ref-fasta /data/GRCh38.fa
```

Flags `--skip-normalise` and `--skip-annotate` bypass the external tool calls (dev/testing use only).

#### CLI: `flask run-watcher`

Polls `VCF_IMPORT_DIR` every 15 minutes (configurable via `--interval`).

Expected file layout in the inbox directory:
```
<watch_dir>/
  sample.vcf.gz           ← VCF file
  sample.qc.json          ← QC metrics (optional)
  sample.meta.json        ← Required: {"sample_assay_id": "SA_..."}
  processed/              ← successfully imported files moved here
  failed/                 ← failed imports moved here
```

Use `--once` for cron-based invocation instead of long-running process.

---

### Phase 5 — Knowledge Database

**Files:** `services/knowledge.py`, `blueprints/web/templates/knowledge.html`

#### Variant Knowledge Entries

Curated clinical interpretations stored per variant + disease context. Three primary keys:

| Variant Type | Key |
|---|---|
| SNV | `gene + hgvsp + disease_subtype` |
| CNV | `gene + event_type + disease_group` |
| SV/Fusion | `gene_5prime + gene_3prime + disease_group` |

`disease_subtype = null` means the entry applies pan-disease within the `disease_group`.

#### Lookup Strategy

`KnowledgeService.lookup_for_snv(variant, disease_subtype)` applies a two-tier fallback:
1. Exact match: `gene + hgvsp + disease_subtype`
2. Pan-disease fallback: same gene + hgvsp with `disease_subtype = null`

#### Evidence Panel

When a reviewer opens a novel variant (no knowledge match), `KnowledgeService.get_evidence_panel(variant)` bundles:
- Exact knowledge entry (if matched)
- Same-codon entries (regex prefix extraction on hgvsp)
- Same-gene entries

This powers the pre-fill UI in `snv_detail_form.html`.

#### Full-Text Search

```python
KnowledgeService.search(query, filters={})
```
Uses MongoDB `$text` index on `(interpretation, evidence_summary)`. Requires minimum 3 words in the query to prevent misleading partial matches.

#### Versioning

Every edit to a knowledge entry appends to `version_history` and increments `version`. `change_note` is required for edits. `senior_reviewer` and `lab_director` can edit; all internal users can read.

#### Observation Tracking

`KnowledgeService.increment_observation(knowledge_id)` — called when a knowledge entry is applied to a review. Increments `observation_count` and sets `federation_eligible = True` when count reaches 5.

---

### Phase 6 — Report Generation

**Files:** `services/report.py`, `services/preflight.py`

#### Report Lifecycle

```
draft
  → pending_sign_off   (after first sign-off)
  → finalised          (requires ≥2 sign-offs, all preflight checks pass,
                        senior_reviewer or lab_director only)
  → delivered / amended / superseded
```

#### Pre-Finalisation Preflight Checklist

`PreflightService.run_checks(sample_assay_id)` evaluates:

| Check | Condition |
|---|---|
| All variants reviewed | No `unreviewed` variants remain |
| Consensus met | All variants are `concordant` or `resolved` |
| Tier 1/2 interpretations complete | No blank interpretation on Tier 1 or 2 variants |
| Biomarkers confirmed | MSI/TMB `review_status = "confirmed"` |
| QC within thresholds | Callset `qc_status = "passed"` |
| Two sign-offs obtained | ≥2 entries in `report.sign_offs` |

Any failed check blocks finalisation with a specific reason. The result is also stored in `report.preflight_checks` at finalisation time.

#### Report Snapshot

`ReportService.finalise()` creates an **immutable snapshot** of all case data at the time of sign-off:
```
snapshot.sample         ← sample metadata
snapshot.assay          ← assay config at time of review
snapshot.callset_qc     ← QC metrics
snapshot.snvs/cnvs/svs  ← reportable variants only (concordant or resolved, non-artifact)
snapshot.biomarkers
snapshot.knowledge_versions_used   ← knowledge_id → version number
snapshot.threshold_versions_used
```

#### Report Export

`ReportService.export_json(report_id)` — returns JSON following internal schema v1. Suitable for EHR ingestion. Does not expose raw MongoDB document structure.

#### Amendment Policy

| Scenario | Action |
|---|---|
| Typo, report not yet delivered | Internal amendment — `status = "amended"`, audit logged |
| Substantive change, report delivered | New `corrected_report`, supersedes original |
| New info after delivery | `addendum` report appended, original unchanged |

---

### Phase 7 — Advanced Features

---

#### TAT Tracking & SLA Alerting

**File:** `services/tat.py`

`TATService.sla_status(assay)` returns one of:

| Status | Condition |
|---|---|
| `complete` | Case in terminal state (finalised / delivered) |
| `on_track` | Active, >48h before SLA deadline |
| `amber` | Active, ≤48h before SLA deadline |
| `breached` | Active, SLA deadline passed |
| `unknown` | No `sla_due_at` field |

`TATService.is_stalled(assay)` — `True` when the case is active and no state change has occurred in >24 hours.

`TATService.dashboard_stats()` returns:
```json
{
  "active_cases": [...],       // annotated with _sla_status, _tat_hours, _stalled
  "summary": {
    "total_active": int,
    "breached": int,
    "stalled": int,
    "pct_within_sla": float
  },
  "assay_breakdown": [
    { "assay_id": str, "count": int, "avg_tat": float, "median_tat": float }
  ]
}
```

Accessible at `/lab-dashboard` (lab_director / senior_reviewer only).

---

#### Ordering Physician Portal

**File:** `services/portal.py`, `blueprints/portal/routes.py`

`PortalService.issue_token(report_id, ...)` — generates a `secrets.token_urlsafe(32)` token with 30-day TTL. Automatically revokes any previous active tokens for the same report.

The access URL for the physician: `https://<host>/portal/access/<token>`

The portal is read-only. Physicians see:
- Case information (pseudonymised patient ID, diagnosis, assay)
- Tumour biomarkers (MSI/TMB)
- Reportable variants: SNVs, CNVs, SVs/Fusions (with tier and interpretation)
- Sign-offs list

Physician portal uses a **separate session key** (`portal_token`) from the internal user session (`user`) to prevent cross-contamination.

Token management (issue / view history) is accessible to `senior_reviewer` and `lab_director` from the Report tab of the variant review workspace.

---

#### Assay Gap Analysis

**File:** `services/gap_analysis.py`

`GapAnalysisService.query_gene_coverage(gene, assay_id=None)` queries the `gene_panel` arrays across all assay versions to determine:
- `covered_by` — assay versions whose panel includes the gene
- `not_covered_by` — assay versions whose panel does NOT include the gene
- `uncovered_cases` — active cases run on panels that don't cover the gene

Accessible at `/gap-analysis` (lab_director only). **Read-only — does not modify any records.**

---

#### Cohort Query Interface

**File:** `services/gap_analysis.py` (`CohortService`)

`CohortService.query(gene, tier, variant_type, assay_id, acknowledge_multi_version)` queries `snvs_raw`, `cnvs_raw`, `svs_raw` simultaneously and annotates each result with `_assay_id`, `_assay_version`, `_variant_type`.

When results span multiple assay panel versions, `multi_version_warning = True` is returned and the UI requires explicit acknowledgment before showing the data (`?acknowledge=1`).

Accessible at `/cohort` (all internal users).

---

#### Federated Knowledge Sharing

**File:** `services/federation.py`

**Export eligibility criteria:**
- `observation_count ≥ 5`
- `federation_eligible = True`

`FederationService.build_export(lab_id, ...)` — packages all eligible entries into a `federation_exports` document including schema version, entry count, and a snapshot of each entry.

`FederationService.import_from_registry(payload, ...)` — processes an incoming export from another lab:
- Finds matching local entries by variant key
- If no local entry: creates a shadow entry (`_federated = True`) — read-only, not modifiable
- If local entry exists and tier differs by ≥1: sets `is_contested = True` on the local entry, surfacing the discordance to reviewers

Export schema version is `1.0`. Accessible at `/federation` (lab_director only).

---

## API Reference

All API routes are prefixed with `/api`. Authentication uses the internal session cookie (`withCredentials: true` from the React frontend, or a browser session from the Jinja2 UI).

### Auth

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/login` | None | JSON login `{username, password}` → sets session, returns user object |
| POST | `/api/auth/logout` | None | Clears session |
| GET | `/api/auth/me` | None | Returns current session user or 401 |

### Health

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/health` | None | Service health check |

### Samples & Assays

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/samples` | login | List all samples |
| GET | `/api/samples/<sample_id>` | login | Get sample detail |
| GET | `/api/samples/<sample_id>/assays` | login | List assays for a sample |
| GET | `/api/sample-assays/<id>` | login | Get sample assay detail |
| POST | `/api/sample-assays/<id>/assign` | senior_reviewer, lab_director | Assign reviewers |

### Variants

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/sample-assays/<id>/snvs` | login | List SNVs |
| GET | `/api/sample-assays/<id>/snvs/<chrom>/<pos>/<ref>/<alt>` | login | Get SNV detail |
| POST | `/api/sample-assays/<id>/snvs/<chrom>/<pos>/<ref>/<alt>/review` | login | Submit SNV review |
| GET | `/api/sample-assays/<id>/cnvs` | login | List CNVs |
| GET | `/api/sample-assays/<id>/cnvs/<gene>` | login | Get CNV detail |
| POST | `/api/sample-assays/<id>/cnvs/<gene>/review` | login | Submit CNV review |
| GET | `/api/sample-assays/<id>/svs` | login | List SVs |
| GET | `/api/sample-assays/<id>/svs/<sv_id>` | login | Get SV detail |
| POST | `/api/sample-assays/<id>/svs/<sv_id>/review` | login | Submit SV review |

### Biomarkers

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/sample-assays/<id>/biomarkers` | login | Get MSI/TMB biomarkers |
| POST | `/api/sample-assays/<id>/biomarkers/classify` | bioinformatician, lab_director, senior_reviewer | Classify from callset |
| POST | `/api/sample-assays/<id>/biomarkers/confirm` | login | Reviewer confirmation |

### Preflight & Reports

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/sample-assays/<id>/preflight` | login | Run preflight checks |
| GET | `/api/sample-assays/<id>/reports` | login | List reports for case |
| POST | `/api/sample-assays/<id>/reports` | login | Create draft report |
| GET | `/api/reports/<id>` | login | Get report detail |
| POST | `/api/reports/<id>/sign-off` | login | Add sign-off |
| POST | `/api/reports/<id>/finalise` | senior_reviewer, lab_director | Finalise report |
| GET | `/api/reports/<id>/export` | login | Export JSON (schema v1) |
| POST | `/api/reports/<id>/addendum` | login | Create addendum |
| POST | `/api/reports/<id>/portal-token` | senior_reviewer, lab_director | Issue physician portal token |

### Assay Configs

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/assay-configs` | login | List all assay configs |
| GET | `/api/assay-configs/<assay_id>` | login | Get active config |
| POST | `/api/assay-configs` | senior_reviewer, lab_director | Create config |

### Callsets / Ingestion

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/sample-assays/<id>/callsets` | login | List callsets for case |
| GET | `/api/callsets/<callset_id>` | login | Get callset detail |
| POST | `/api/sample-assays/<id>/callsets/import` | bioinformatician, lab_director | Trigger import via API |

### Knowledge Database

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/knowledge` | login | List knowledge entries (filters: gene, variant_type, tier, disease_group) |
| POST | `/api/knowledge` | senior_reviewer, lab_director | Create entry |
| GET | `/api/knowledge/<id>` | login | Get entry |
| PUT | `/api/knowledge/<id>` | senior_reviewer, lab_director | Update entry (versioned) |
| GET | `/api/knowledge/search?q=...` | login | Full-text search (min 3 words) |
| GET | `/api/knowledge/lookup/snv?gene=&hgvsp=&disease_subtype=` | login | Disease-aware lookup |

### Advanced Features

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/lab/dashboard` | lab_director, senior_reviewer | TAT/SLA dashboard stats |
| GET | `/api/gap-analysis?gene=&assay_id=` | lab_director | Assay gene coverage query |
| GET | `/api/cohort?gene=&tier=&variant_type=&assay_id=` | login | Cohort variant query |
| POST | `/api/federation/export` | lab_director | Build and store knowledge export |
| POST | `/api/federation/import` | lab_director | Import from external registry |
| GET | `/api/federation/exports` | lab_director | List export history |

---

## CLI Commands

```bash
# Load seed / demo data
flask load-demo

# Create an internal user
flask create-user

# Import a single VCF (full pipeline)
flask import-vcf --vcf <path> --qc <path> --sample-assay-id <id> \
                 [--skip-normalise] [--skip-annotate]

# Run the directory watcher (long-running or cron mode)
flask run-watcher [--watch-dir /data/vcf_inbox] [--interval 900] [--once]
```

---

## Database Indexes

All indexes are ensured at startup by `db/indexes.py → ensure_indexes()`.

| Collection | Index | Notes |
|---|---|---|
| `users` | `email` (unique), `username` (unique) | |
| `assay_configs` | `(assay_id, version)` (unique), `is_active` | |
| `audit_log` | `timestamp`, `actor_user_id`, `target_id` | |
| `callsets` | `callset_id` (unique), `sample_assay_id`, `vcf_checksum`, `(sample_assay_id, import_status)` | |
| `cnvs_raw` | `(sample_assay_id, gene)` (unique) | |
| `svs_raw` | `sample_assay_id`, `(sample_assay_id, sv_id)` (unique) | |
| `sample_assays` | `sample_id`, `status` | |
| `biomarkers` | `sample_assay_id` (unique) | |
| `reports` | `report_id` (unique), `sample_assay_id`, `(sample_assay_id, status)` | |
| `variant_knowledge` | `knowledge_id` (unique), `(variant_type, gene)`, `(variant_type, gene, hgvsp, disease_subtype)`, `(variant_type, gene_5prime, gene_3prime)`, text index `(interpretation, evidence_summary)` named `knowledge_text_search` | |
| `report_access_tokens` | `token` (unique), `report_id`, `(report_id, revoked)` | |
| `federation_exports` | `export_id` (unique), `target_lab_id`, `exported_at` | |

---

## Configuration

All configuration is read from environment variables via `src/config.py`.

| Variable | Description |
|---|---|
| `SECRET_KEY` | Flask session signing key |
| `SESSION_COOKIE_NAME` | Cookie name (default: `omixia_session`) |
| `FLASK_DEBUG` | `1` to enable debug mode |
| `MONGO_URI` | MongoDB connection URI |
| `OMIXIA_DB_NAME` | MongoDB database name |
| `CACHE_REDIS_URL` | Redis connection URL for sessions |
| `REPORTS_BASE_PATH` | Filesystem path for generated PDF/JSON report files |
| `VCF_IMPORT_DIR` | Watched inbox directory for the watcher CLI |
| `BCFTOOLS_BIN` | Path to bcftools binary (default: `bcftools`) |
| `VEP_BIN` | Path to Ensembl VEP binary (default: `vep`) |
| `VEP_CACHE_DIR` | Path to VEP local cache directory |
| `REF_FASTA` | Path to GRCh38 reference FASTA for bcftools norm |
| `WATCHER_USER_ID` | User ID attributed to watcher-triggered imports |
| `WATCHER_USERNAME` | Username attributed to watcher-triggered imports |
