# Omixia

**Clinical Somatic Variant Interpretation & Reporting Platform**

Omixia supports SNV, CNV, SV, MSI, and TMB analysis with a multi-reviewer consensus workflow, structured evidence support, report generation, and federated knowledge sharing.

## Documentation

Start with whichever matches what you're trying to do:

| I want to… | Read |
|---|---|
| Understand how the system is built and why | **[Architecture](docs/ARCHITECTURE.md)** — layers, request lifecycle, data model, subsystems, known issues |
| Set it up, run it, or change it | **[Developer Guide](docs/DEVELOPER_GUIDE.md)** — quick start, common tasks, API reference, CLI, configuration |
| Deploy, back up, or troubleshoot it | **[Operations](docs/OPERATIONS.md)** — secrets, backups, container management |
| See what changed recently | **[Changelog](CHANGELOG.md)** |
| Know what it's *supposed* to do | **[Product Specification](SPEC.md)** — requirements + phase checklist |
| Read historical engineering narrative | [Development Diary](docs/diary.md) — frozen; superseded by the changelog |

Contributing? [CLAUDE.md](CLAUDE.md) carries the Definition of Done and the Documentation Map — which docs to update for each kind of change.

The live API contract is always at **`/docs`** on a running backend (auto-generated OpenAPI).

## Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI 0.115.x, Python 3.12 (Gunicorn + Uvicorn workers) |
| Database | MongoDB 7 (PyMongo, synchronous) |
| Cache / Sessions | Redis 7 |
| React SPA | React 18, TypeScript, Vite, TailwindCSS, TanStack Query |
| Server-rendered pages | Jinja2 — landing, login, physician portal only |
| CLI | Typer |

## Quick Start

Requires Docker and Docker Compose.

### Backend

```bash
cd backend
cp .env.example .env          # then set MONGO_INITDB_ROOT_PASSWORD + FLASK_SECRET_KEY

docker compose up -d --build

# Load demo data
docker exec app_omixia python cli.py load-demo

# Verify
curl http://localhost/api/health     # {"status":"ok","service":"omixia"}
```

Interactive API docs are generated automatically at <http://localhost/docs>.

### React Frontend

```bash
cd frontend
npm install
npm run dev          # http://localhost:3000
```

The Vite dev server proxies `/api` to `http://localhost:80` (nginx), so the backend stack must be up first.

Alternatively `npm run build` writes to `frontend/dist/`, which nginx serves on <http://localhost:8080>.

Demo credentials (password: `omixia_demo_1`):

| Username | Role |
|---|---|
| `admin` | admin |
| `geneticist` | reviewer |
| `senior` | senior_reviewer |
| `director` | lab_director |
| `bioinf` | bioinformatician |

## Implemented Phases

| Phase | Feature Area | Status |
|---|---|---|
| 1 | Foundation — users, roles, assay config, audit log | Done |
| 2 | Core Review Workflow — two-reviewer consensus, bypass, case assignment | Done |
| 3 | Variant Types — CNV, SV/fusion, MSI/TMB biomarkers | Done |
| 4 | Data Ingestion — VCF import, bcftools norm, VEP, QC gate, callset versioning | Done |
| 5 | Knowledge Database — variant knowledge CRUD, evidence panel, full-text search | Done |
| 6 | Report Generation — snapshot, preflight checklist, sign-offs, JSON export | Done |
| 7 | Advanced Features — TAT/SLA dashboard, physician portal, gap analysis, cohort query, federated knowledge | Done |
| 8 | Architecture Harmonisation — React sole UI, slim server-rendered surface, CORS | Done |
| 9 | Production Deployment — Cloudflare Tunnel + Pages, backups, monitoring | Pending |

The backend was migrated from Flask to FastAPI on 2026-08-05; see `docs/diary.md` §24 for the rationale and gotchas.
