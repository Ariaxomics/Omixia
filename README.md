# Omixia

**Clinical Somatic Variant Interpretation & Reporting Platform**

Omixia supports SNV, CNV, SV, MSI, and TMB analysis with a multi-reviewer consensus workflow, structured evidence support, report generation, and federated knowledge sharing.

## Documentation

- **[Developer Guide](docs/DEVELOPER_GUIDE.md)** — full architecture, feature reference, API reference, CLI commands, configuration
- **[Product Specification](SPEC.md)** — requirements and design decisions

## Stack

| Layer | Technology |
|---|---|
| Backend | Flask 3.x, Python 3.12 |
| Database | MongoDB 7 |
| Cache / Sessions | Redis 7 |
| Server-rendered UI | Jinja2 + Tailwind CSS + HTMX |
| React SPA | React 18, TypeScript, Vite, TailwindCSS, TanStack Query |

## Quick Start

### Backend

```bash
cd backend

# Install dependencies
pip install -r app/requirements.txt

# Load demo data
flask load-demo

# Run the dev server (default: http://localhost:5000)
flask run
```

### React Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start the dev server (default: http://localhost:3000)
npm run dev
```

The Vite dev server proxies all `/api` requests to `http://localhost:5000`, so the Flask backend must be running first.

Demo credentials (password: `omixia_demo_1`):

| Username | Role |
|---|---|
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
