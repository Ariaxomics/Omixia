# Omixia — Architecture

**Version:** 1.0
**Last Updated:** 2026-08-05

How Omixia is built and why. Read this to **understand** the system; see the [Developer Guide](DEVELOPER_GUIDE.md) to **work on** it, and [Operations](OPERATIONS.md) to **run** it.

---

## Table of Contents

1. [What It Is](#what-it-is)
2. [The Layer Model](#the-layer-model)
3. [Boot Sequence](#boot-sequence)
4. [Request Lifecycle](#request-lifecycle)
5. [Core Mechanisms](#core-mechanisms)
6. [Project Structure](#project-structure)
7. [Data Model](#data-model)
8. [Database Indexes](#database-indexes)
9. [Subsystems](#subsystems)
10. [Known Issues & Tech Debt](#known-issues--tech-debt)

---

## What It Is

Omixia is a clinical-grade somatic variant interpretation and reporting platform. A tumour sample is sequenced, variants are called into a VCF, and Omixia is where humans decide what those variants *mean* and sign a report a physician can act on.

That clinical context — not the technology — explains most of the design. This is a **records office**, not a shop:

| Requirement | Consequence in the code |
|---|---|
| Two people must agree before a finding is reportable | Two-reviewer [consensus state machine](#the-consensus-state-machine) |
| Nothing may be silently altered | Append-only `audit_log`; `review_history` only ever grows |
| A signed report must never change retroactively | Reports store an immutable [snapshot](#report-generation) |
| Concurrent reviewers must not clobber each other | [Optimistic locking](#optimistic-locking) on every review write |
| Patient identity must not live here | Only `patient_pseudonym_id` is stored |

### Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI 0.115.x (ASGI), Python 3.12 |
| Database | MongoDB 7, PyMongo (**synchronous** driver) |
| Cache / Sessions | Redis 7 |
| Frontend | React 18, TypeScript, Vite, TailwindCSS, TanStack Query, Axios |
| Server-rendered pages | Jinja2 — landing, login, physician portal only |
| Server | Gunicorn (process manager) + `uvicorn.workers.UvicornWorker` + Nginx |
| CLI | Typer |
| VCF normalisation | bcftools (subprocess) |
| Variant annotation | Ensembl VEP (subprocess) |

---

## The Layer Model

The system is best understood bottom-up. Each layer knows only about the layer below it.

```
        ┌──────────────────────────────────────────────┐
  7     │  CLI (Typer)          cli.py                 │──┐  side door,
        └──────────────────────────────────────────────┘  │  skips 3-6
        ┌──────────────────────────────────────────────┐  │
  6     │  React SPA            frontend/src/          │  │
        └──────────────────────────────────────────────┘  │
        ┌──────────────────────────────────────────────┐  │
  5     │  nginx + Docker       :80 / :8080            │  │
        └──────────────────────────────────────────────┘  │
        ┌──────────────────────────────────────────────┐  │
  4     │  App shell            main.py                │  │
        │  CORS · session mw · error handler · lifespan │  │
        └──────────────────────────────────────────────┘  │
        ┌──────────────────────────────────────────────┐  │
  3     │  Routers              src/routers/           │  │
        │  HTTP verbs · auth deps · no business logic   │  │
        └──────────────────────────────────────────────┘  │
        ┌──────────────────────────────────────────────┐  │
  2     │  Services             src/services/          │◄─┘
        │  ALL business logic · framework-agnostic      │
        └──────────────────────────────────────────────┘
        ┌──────────────────────────────────────────────┐
  1     │  MongoDB collections + indexes                │
        └──────────────────────────────────────────────┘
```

### The rule that matters

**Layer 2 must never import a web framework.** Services are plain Python classes with static methods that talk to PyMongo. No request objects, no decorators, no `fastapi` imports.

This is not stylistic. It is load-bearing:

- The **CLI enters at layer 2**, so `import-vcf` runs the identical `IngestionService.import_vcf()` that the API endpoint calls. One implementation, two entry points.
- The **Flask → FastAPI migration** (2026-08-05) rewrote ~900 lines of layers 3–4 and changed **one line** of layer 2 — the audit log's request-context lookup. 3,100 lines of clinical logic moved across frameworks untouched.

If you find yourself importing `Request` into `src/services/`, stop: the thing you need belongs in the router, or should be passed in as a parameter.

### Layer 3 handlers are thin by construction

Every router handler does exactly three things — check the badge, call the department, wrap the answer:

```python
@router.post("/sample-assays/{sample_assay_id}/snvs/{chrom}/{pos}/{ref}/{alt}/review")
def submit_snv_review(sample_assay_id, chrom, pos, ref, alt,
                      request: Request, payload: dict = Body(default={})):
    user = _require_user(request)                    # 1. auth
    try:
        updated = SampleService.update_snv_review(   # 2. delegate
            sample_assay_id, chrom, pos, ref, alt, ...)
    except ReviewError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"data": updated, "summary": ...}          # 3. envelope
```

Business rules live in `SampleService`. The router only translates a `ReviewError` into HTTP 409.

---

## Boot Sequence

`main.py` runs this once per worker process, before serving any request:

```
gunicorn spawns worker
   │
   ▼
UvicornWorker imports main:app
   │
   ▼
lifespan() startup
   ├─ mongo_client.init_app()     MongoClient(settings.MONGO_URI)
   ├─ redis_client.init_app()     redis.from_url(settings.CACHE_REDIS_URL)
   └─ ensure_indexes()            idempotent createIndex calls
   │                              wrapped in try/except — a cold Mongo
   │                              logs a warning instead of killing the worker
   ▼
middleware + routers registered
   ▼
"Application startup complete."
```

Two workers means this runs twice; `ensure_indexes()` is idempotent so that's harmless.

**Configuration** is read once at import time into a `pydantic-settings` singleton, `settings`, in `src/config.py`. Environment variables are read at process start, so a `.env` change requires a container recreate — not just a restart. See [Configuration](DEVELOPER_GUIDE.md#configuration).

---

## Request Lifecycle

An end-to-end trace of a geneticist tiering a BRAF variant — the path most other requests also follow:

```
 1  Browser    POST /api/sample-assays/SA_LUNG_001/snvs/7/140453136/A/T/review
               Cookie: Omixia=<signed>          body: {"tier": "tier_1", ...}
                  │
 2  nginx     ──►│ location /api/ → proxy_pass http://app:8000
                  │
 3  middleware──►│ set_current_request(request)      ← ContextVar, for audit
                  │ load_session()  cookie → unsign → Redis → dict
                  │ request.state.session = Session(...)
                  │
 4  router    ──►│ _require_user(request) → user dict, or 401
                  │ validate tier ∈ {tier_1..4, None}, else 400
                  │
 5  service   ──►│ SampleService.update_snv_review(...)
                  │   ├─ find_one()                    read current state
                  │   ├─ _resolve_state_transition()   unreviewed → pending_second
                  │   │     (raises ReviewError on any policy violation)
                  │   ├─ find_one_and_update()         optimistic-locked write
                  │   ├─ AuditService.log()            reads ContextVar for IP
                  │   └─ recalculate_summary()
                  │
 6  router    ──►│ return {"data": snv, "summary": {...}}
                  │      ReviewError → HTTPException(409) → {"error": "..."}
                  │
 7  middleware──►│ set_session_cookie(response)   refresh 7-day TTL
                  │
 8  React     ◄──│ invalidateQueries(['snvs', id]) → table + summary refetch
```

### Why handlers are `def`, not `async def`

FastAPI inspects each path operation. An `async def` handler runs **on the event loop**; a plain `def` handler runs **in a threadpool**.

PyMongo is synchronous and blocking. Running it on the event loop would stall every concurrent request in that worker. Declaring handlers as plain `def` lets FastAPI move them to the threadpool, where blocking is safe.

> ⚠️ **Do not add `async` to a handler that calls a service.** It will block the whole worker. Changing this properly means migrating all of `src/services/` to Motor — a deliberate non-goal.

---

## Core Mechanisms

### The Consensus State Machine

The clinical heart of the system, in `_resolve_state_transition()` at [samples.py:27](../backend/app/src/services/samples.py#L27):

```
   unreviewed
       │  first reviewer submits tier
       ▼
 pending_second_review
       │
       ├── second reviewer, SAME tier ──────────► concordant  ✅ reportable
       │
       ├── second reviewer, DIFFERENT tier ─────► discordant
       │                                              │
       │                                              │ senior_reviewer
       │                                              │ or lab_director
       │                                              ▼
       │                                           resolved   ✅ reportable
       │
       └── senior_reviewer + bypass_justification ─► resolved  ✅ (audited)
```

Enforced rules, each a guard clause in that function:

| Rule | Where |
|---|---|
| You cannot supply both reviews yourself | compares `actor_user_id` to `history[0]["actor_user_id"]` |
| Only `senior_reviewer` / `lab_director` may break a tie | `RESOLVER_ROLES` |
| Only those roles may amend an already-resolved variant | first guard clause |
| Reportable ⇔ `concordant` or `resolved` | `REPORTABLE_STATUSES` |

**The bypass is the interesting case.** A senior reviewer can single-handedly resolve a variant, but only with a non-empty `bypass_justification`, which is written into both `review_history` and the audit log. The system doesn't forbid the shortcut — it makes the shortcut permanently visible.

### Optimistic Locking

Two reviewers open the same variant; both save. Without protection the second silently overwrites the first, defeating consensus entirely.

The fix at [samples.py:243](../backend/app/src/services/samples.py#L243) uses **the length of the history array as a version number**:

```python
history_len = len(history)          # e.g. 1 at read time
updated = db.snvs_raw.find_one_and_update(
    {**variant_filter,
     "$expr": {"$eq": [{"$size": {"$ifNull": ["$review_history", []]}}, history_len]}},
    {"$set":  {"review_current": new_current},
     "$push": {"review_history": new_entry}},
    return_document=ReturnDocument.AFTER,
)
if updated is None:
    raise ReviewError("Review was modified by another user...")
```

The write lands only if the array is still the length it was at read time. If the other reviewer got there first the array grew, the filter matches nothing, Mongo returns `None`, and the loser is told to refresh. One atomic operation — no locks, no transactions.

The same pattern guards CNV and SV reviews.

### Sessions

Cookie-based with **server-side storage**. No JWT anywhere.

```
Login
  ├─ id      = secrets.token_urlsafe(32)          opaque, meaningless alone
  ├─ Redis   omixia:session:<id> = {"user": {…}}  TTL 7 days
  └─ Cookie  itsdangerous-signed <id>, httponly
```

The cookie carries only a signed pointer; user data never leaves the server, so it cannot be tampered with, and logout genuinely destroys it.

`Session` subclasses `dict` and overrides `__setitem__` to **write through to Redis on mutation** — `session["user"] = {...}` persists immediately. There is no save step, so forgetting one is impossible. Implementation in `src/session.py`.

### Audit Logging

`AuditService.log()` takes no request parameter, yet records the caller's IP and session id. It reads them from a `ContextVar` that the session middleware populates per request — `src/request_context.py`.

This keeps layer 2 framework-free while still capturing request metadata. Under Flask this was `flask.has_request_context()`; the ContextVar is the framework-neutral equivalent, and replacing it was the single line of business logic the FastAPI migration touched.

Audit writes are wrapped in a bare `except` that logs to stderr — **an audit failure must never break a clinical workflow**. The log is append-only: no code path updates or deletes from `audit_log`.

### The Response Envelope

Success is `{"data": …}`; errors are `{"error": "<message>"}`. FastAPI's default error shape is `{"detail": …}`, so `main.py` installs a global handler:

```python
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
```

Those four lines are why the entire React frontend needed zero changes during the framework migration.

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
    main.py                    # FastAPI() instance: CORS, session middleware,
                                # global exception handler, router includes,
                                # lifespan (Mongo/Redis init, ensure_indexes)
    cli.py                     # Typer CLI entrypoint — load-demo, create-user,
                                # import-vcf, run-watcher
    src/
      auth.py                  # require_login / require_role FastAPI dependencies,
                                # current_user() / current_username()
      session.py               # Redis-backed signed-cookie session (Session class,
                                # load_session / set_session_cookie)
      request_context.py       # ContextVar carrying the in-flight Request, so
                                # services/audit.py can read IP/session id without
                                # a framework dependency
      config.py                # pydantic-settings Settings, reads .env
      extensions.py            # mongo_client, redis_client singletons
      routers/
        api_v1.py               # All REST API endpoints (prefix: /api)
        web.py                   # Landing page + login/logout (prefix: /)
        portal.py                # Physician portal (prefix: /portal)
      templates/
        web/
          base.html              # Nav + layout shell
          landing.html
          login.html
          about.html
        portal/
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
        create_user.py         # `python cli.py create-user` implementation
        import_vcf.py          # `python cli.py import-vcf` implementation
        load_demo.py           # `python cli.py load-demo` implementation
        watcher.py             # `python cli.py run-watcher` implementation
    demo_data/                 # Seed data loaded by `python cli.py load-demo`
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
  docker-compose.yml
  nginx/default.conf           # Port 80 → FastAPI app; port 8080 → React dist (local)
  .env                         # Secrets — gitignored
  .env.example                 # Template — committed, no secrets
```

> The React SPA is the only place app functionality lives. `routers/web.py` and `routers/portal.py` render Jinja2 templates only for the public landing page, the internal login form, and the physician read-only portal — do not add app features there.

---


## Data Model

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
All variant collections share a `review_current` embedded document and a `review_history` append-only array. See [Review Workflow](#review-workflow--two-reviewer-consensus) for the state machine.

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


## Subsystems

One section per functional area. These correspond to the implementation phases tracked in [SPEC.md](../SPEC.md) §16 — named here by what they *do* rather than when they were built.

---

### Foundation — Users, Roles, Assay Config, Audit

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

### Review Workflow — Two-Reviewer Consensus

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

### Variant Types — CNV, SV, Biomarkers

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

### Data Ingestion — The VCF Pipeline

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

#### CLI: `python cli.py import-vcf`

```bash
docker exec app_omixia python cli.py import-vcf \
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

Flags `--skip-normalise` and `--skip-annotate` bypass the external tool calls (dev/testing use only). Paths are resolved **inside the container**, so mount any input directory into the `app` service first.

#### CLI: `python cli.py run-watcher`

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

### Knowledge Database

**Files:** `services/knowledge.py`, `routers/api_v1.py`, `frontend/src/pages/KnowledgePage.tsx`

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

This powers the pre-fill UI in the SNV review side panel of `SampleDetailPage.tsx`.

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

### Report Generation

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

### Advanced Features — TAT, Portal, Gap Analysis, Federation

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

**File:** `services/portal.py`, `routers/portal.py`

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


---

## Known Issues & Tech Debt

Live list of things a newcomer would otherwise have to rediscover. Each entry states the risk and the fix. Close one → delete the entry and note it in [CHANGELOG.md](../CHANGELOG.md).

### 1. Nine read endpoints have no authentication — ⚠️ security

These serve real clinical data to an unauthenticated caller. Verified with a cookie-less request returning HTTP 200:

```
GET /api/samples
GET /api/samples/{sample_id}
GET /api/samples/{sample_id}/assays
GET /api/sample-assays/{id}
GET /api/sample-assays/{id}/summary
GET /api/sample-assays/{id}/snvs
GET /api/sample-assays/{id}/snvs/{chrom}/{pos}/{ref}/{alt}
GET /api/assay-configs
GET /api/assay-configs/{assay_id}
```

Pre-existing — the original Flask routes carried no `@require_login` either, and the FastAPI port preserved behaviour verbatim. **Not** a migration regression, but a real exposure.

**Fix:** add `dependencies=[Depends(require_login)]` to each in `src/routers/api_v1.py`. One line apiece. Should be closed before any public deployment.

### 2. Auto-generated API docs are public

`/docs`, `/redoc`, and `/openapi.json` expose the full 56-path API surface without authentication. Harmless locally; a free reconnaissance map in production.

**Fix:** `FastAPI(docs_url=None, redoc_url=None, openapi_url=None)` in `main.py` when `not settings.DEVELOPMENT`, or gate behind an auth dependency.

### 3. Route handlers must stay synchronous

Adding `async def` to any handler that calls a service will block the event loop on PyMongo I/O and collapse that worker's throughput. Constrains an otherwise-idiomatic FastAPI style.

**Fix (large):** migrate `src/services/` to Motor. Deliberately deferred — ~3,100 lines for no functional gain at current scale.

### 4. No automated test suite

There are no backend tests. Every change is verified by manual smoke testing, which does not scale and leaves the consensus state machine — the most safety-critical code — uncovered.

**Fix:** pytest against a throwaway Mongo. Highest-value first targets: `_resolve_state_transition()` (pure function, trivial to test), the optimistic-locking conflict path, and `PreflightService.run_checks()`.

### 5. `SECRET_KEY` defaults to empty string

`src/config.py` defaults `SECRET_KEY` to `""`. An unset `FLASK_SECRET_KEY` yields a predictable signing key rather than a startup failure, making session cookies forgeable.

**Fix:** fail fast at startup when `SECRET_KEY` is empty and `DEVELOPMENT` is false.

### 6. Environment variables still carry `FLASK_` prefixes

`FLASK_SECRET_KEY` and `FLASK_DEBUG` are read into `settings.SECRET_KEY` / `settings.DEBUG` via `Field(validation_alias=...)`. Kept deliberately so existing `.env` files and the deployment runbook keep working, but they now misname the framework.

**Fix (cosmetic, breaking):** rename to `OMIXIA_SECRET_KEY` / `OMIXIA_DEBUG`, updating `.env`, `.env.example`, and [OPERATIONS.md](OPERATIONS.md) together.
