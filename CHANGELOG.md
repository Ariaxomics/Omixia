# Changelog

All notable changes to Omixia are recorded here. Newest first.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Categories: **Added**, **Changed**, **Fixed**, **Removed**, **Security**, **Deprecated**.

> **Every behaviour change gets an entry here, in the same commit as the change.** See the Documentation Map in [CLAUDE.md](CLAUDE.md) for which other docs to update alongside it.
>
> Detailed debugging narratives from before this file existed live in [docs/diary.md](docs/diary.md). Milestones below were backfilled from it; the day-to-day fixes were not.

---

## [Unreleased]

### Added
- `CHANGELOG.md` — this file.
- `docs/ARCHITECTURE.md` — how the system is built: seven-layer model, boot sequence, request lifecycle, consensus state machine, optimistic locking, session and audit mechanisms, plus a standing **Known Issues & Tech Debt** register.
- `docs/DEVELOPER_GUIDE.md` gained a **Common Tasks** section — recipes for adding an endpoint, a React page, a collection, a CLI command, or a config variable, each naming the docs to update.
- **Documentation Map** in `CLAUDE.md` — a table binding each kind of code change to the docs it must update, plus a Definition of Done.

### Changed
- Documentation restructured from six organically-grown files into five active docs split along a real seam — *understanding the system* (`ARCHITECTURE.md`) vs *working on it* (`DEVELOPER_GUIDE.md`). The guide went from 1,185 lines to ~670.
- `docs/ops.md` renamed to `docs/OPERATIONS.md` for consistency with its siblings.
- `docs/diary.md` marked as a frozen historical log, superseded by this changelog.

### Fixed
- API Reference auth column now reflects what the code actually enforces, verified by parsing `Depends(...)` out of `src/routers/api_v1.py`. It previously claimed protection on endpoints that have none.

### Security
- **Documented (not yet fixed):** nine `GET` endpoints serve clinical data without authentication — `/api/samples`, `/api/sample-assays/{id}/snvs`, `/api/sample-assays/{id}/summary`, `/api/assay-configs` and related. Confirmed returning HTTP 200 to cookie-less requests. Pre-existing since the Flask implementation; tracked as [Known Issues #1](docs/ARCHITECTURE.md#known-issues--tech-debt).
- **Documented (not yet fixed):** `/docs`, `/redoc`, and `/openapi.json` expose the full 56-path API surface publicly.

---

## [2026-08-05] — Backend migration: Flask → FastAPI

Full rewrite of the backend web layer. React, MongoDB, Redis, nginx, and all business logic unchanged.

### Added
- `backend/app/main.py` — FastAPI application: CORS, session middleware, global exception handler, lifespan startup.
- `backend/app/cli.py` — Typer CLI replacing the four Flask CLI commands.
- `backend/app/src/session.py` — Redis-backed signed-cookie sessions replacing Flask-Session.
- `backend/app/src/request_context.py` — `ContextVar` carrying the in-flight request, so `AuditService` can capture IP and session id without a framework dependency.
- Auto-generated OpenAPI documentation at `/docs`, `/redoc`, `/openapi.json` (56 paths).

### Changed
- `@require_login` / `@require_role` decorators → FastAPI dependencies (`Depends(...)`) in `src/auth.py`.
- `src/blueprints/` → `src/routers/`; Flask blueprints became `APIRouter`s at identical URL prefixes, so nginx and the frontend needed **zero** changes.
- Jinja2 templates moved to `src/templates/{web,portal}/` under `Jinja2Templates`.
- `src/config.py` now uses `pydantic-settings`. Existing `FLASK_SECRET_KEY` / `FLASK_DEBUG` env names retained via `Field(validation_alias=...)` so deployed `.env` files keep working.
- Dockerfile entrypoint: `gunicorn wsgi:app` → `gunicorn -k uvicorn.workers.UvicornWorker main:app`. Same port, same worker model.
- CLI invocation: `flask <command>` → `python cli.py <command>`.

### Fixed
- Pinned `click==8.1.7`; `typer` 0.12.5 is incompatible with click ≥ 8.2 and crashed every CLI command with `TypeError: Secondary flag is not valid for non-boolean flag`.
- Added explicit `Jinja2` dependency — FastAPI does not pull it in, so `Jinja2Templates` failed at import.

### Removed
- `src/blueprints/`, `wsgi.py`, and the pre-Phase-8 archived HTMX templates.
- Dependencies: `Flask`, `Flask-Session`, `Flask-Cors`.

### Notes
- Route handlers are deliberately synchronous `def`, not `async def` — PyMongo blocks, so FastAPI's threadpool is the correct execution context. See [Known Issues #3](docs/ARCHITECTURE.md#known-issues--tech-debt).
- The service layer's framework independence meant ~3,100 lines of clinical logic moved across frameworks with a single line changed (the audit request-context lookup).
- Full migration narrative: [docs/diary.md §24](docs/diary.md).

---

## [2026-03-22] — Phase 9: Production deployment (Cloudflare)

### Added
- `docs/ops.md` operational runbook — secret rotation, environment reference, backup and restore.
- `scripts/backup_mongo.sh` — timestamped `mongodump` snapshots with 30-day retention.
- Cloudflare Quick Tunnel (backend) + Cloudflare Pages (SPA) deployment path.

### Fixed
- `config.py` read `SECRET_KEY` while `.env` defined `FLASK_SECRET_KEY`, leaving the signing key `None`. Login appeared to succeed but every subsequent request was unauthenticated.
- `.gitignore` used `frontend/node_modules/*`, which ignored contents but not the directory, leaving 2,416 tracked files including broken `.bin` symlinks that crashed the Cloudflare Pages build.

---

## [2026-03-11] — Phase 8: Architecture harmonisation

### Changed
- React SPA became the sole interactive UI. The `web` blueprint was slimmed to the landing page and login form; the HTMX partials it previously served were archived.
- CORS restricted to the `api_v1` blueprint, with cross-origin session cookies (`SESSION_COOKIE_SAMESITE=None`, `SESSION_COOKIE_SECURE=1`) for the Pages-hosted SPA.

### Added
- `admin` role, and the `admin` demo user.
- `UsersPage` and user-registration API endpoints.

---

## [2026-03-08] — React SPA

### Added
- React 18 + TypeScript + Vite SPA in `frontend/`, with TanStack Query, React Router v6, Tailwind, and Axios (`withCredentials: true`) against the existing REST API.
- nginx server block on port 8080 serving `frontend/dist/`.

### Fixed
- Axios 401 interceptor caused a refresh loop by redirecting on the initial `/auth/me` session check; that endpoint is now exempt.
- Numerous field-name mismatches between the API and the new SPA (`_id` → `sample_id` / `knowledge_id`, `clinical_significance` → `interpretation`). See [docs/diary.md](docs/diary.md) §5–13.

---

## Earlier

Phases 1–7 — foundation and auth, two-reviewer consensus review workflow, CNV/SV/biomarker support, VCF ingestion pipeline, knowledge database, report generation, and advanced features (TAT/SLA, physician portal, gap analysis, cohort query, federation) — predate this changelog. See [SPEC.md](SPEC.md) §16 for the phase checklist and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#subsystems) for how each subsystem works.
