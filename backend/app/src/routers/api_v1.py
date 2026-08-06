from fastapi import APIRouter, Body, Depends, HTTPException, Request

from src.auth import current_user, require_login, require_role
from src.extensions import mongo_client
from src.services.assay_config import AssayConfigService
from src.services.biomarker import BiomarkerError, BiomarkerService
from src.services.federation import FederationError, FederationService
from src.services.gap_analysis import CohortService, GapAnalysisService
from src.services.ingestion import IngestionError, IngestionService
from src.services.knowledge import KnowledgeError, KnowledgeService
from src.services.portal import PortalError, PortalService
from src.services.preflight import PreflightService
from src.services.report import ReportError, ReportService
from src.services.samples import ReviewError, SampleService
from src.services.tat import TATService
from src.services.users import UserService


router = APIRouter(prefix="/api")


def _require_user(request: Request) -> dict:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorised")
    return user


# ----------------------------
# Health
# ----------------------------

@router.get("/health")
def health():
    return {"status": "ok", "service": "omixia"}


# ----------------------------
# Auth
# ----------------------------

@router.post("/auth/login")
def api_login(request: Request, payload: dict = Body(default={})):
    username = payload.get("username", "").strip()
    password = payload.get("password", "")
    if not username or not password:
        raise HTTPException(status_code=400, detail="username and password required")
    user = UserService.authenticate(username, password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    session_user = {
        "user_id": user["user_id"],
        "username": user["username"],
        "role": user["role"],
        "full_name": user.get("full_name", ""),
        "email": user.get("email", ""),
    }
    request.state.session["user"] = session_user
    return {"data": session_user}


@router.post("/auth/register", status_code=201, dependencies=[Depends(require_role("admin", "lab_director"))])
def api_register(payload: dict = Body(default={})):
    username = payload.get("username", "").strip()
    email = payload.get("email", "").strip()
    full_name = payload.get("full_name", "").strip()
    password = payload.get("password", "")
    role = payload.get("role", "reviewer").strip()

    valid_roles = {"reviewer", "senior_reviewer", "lab_director", "bioinformatician", "admin"}
    if role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(sorted(valid_roles))}")

    missing = [f for f, v in [("username", username), ("email", email), ("full_name", full_name), ("password", password)] if not v]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required fields: {', '.join(missing)}")

    if len(password) < 12:
        raise HTTPException(status_code=400, detail="Password must be at least 12 characters")

    try:
        user = UserService.create_user(username, email, role, full_name, password)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {"data": {
        "user_id": user["user_id"],
        "username": user["username"],
        "role": user["role"],
        "full_name": user.get("full_name", ""),
        "email": user.get("email", ""),
    }}


@router.post("/auth/logout")
def api_logout(request: Request):
    request.state.session.clear()
    return {"ok": True}


@router.get("/auth/me")
def api_me(request: Request):
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"data": user}


# ----------------------------
# Users
# ----------------------------

@router.get("/users", dependencies=[Depends(require_role("admin", "lab_director", "senior_reviewer"))])
def list_users():
    db = mongo_client.db
    users = list(db.users.find({}, {"_id": 0, "password_hash": 0}))
    return {"data": users}


@router.post("/users", status_code=201, dependencies=[Depends(require_role("admin", "lab_director"))])
def register_user(payload: dict = Body(default={})):
    username = payload.get("username", "").strip()
    email = payload.get("email", "").strip()
    role = payload.get("role", "").strip()
    full_name = payload.get("full_name", "").strip()
    password = payload.get("password", "")

    missing = [f for f, v in [("username", username), ("email", email), ("role", role), ("full_name", full_name), ("password", password)] if not v]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required fields: {', '.join(missing)}")

    if len(password) < 12:
        raise HTTPException(status_code=400, detail="Password must be at least 12 characters")

    try:
        user = UserService.create_user(username, email, role, full_name, password)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {"data": user}


# ----------------------------
# Samples
# ----------------------------

@router.get("/samples")
def list_samples():
    return {"data": SampleService.list_samples()}


@router.get("/samples/{sample_id}")
def get_sample(sample_id: str):
    sample = SampleService.get_sample(sample_id)
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")
    return {"data": sample}


# ----------------------------
# Assays
# ----------------------------

@router.get("/samples/{sample_id}/assays")
def get_sample_assays(sample_id: str):
    return {"data": SampleService.get_sample_assays(sample_id)}


@router.get("/sample-assays/{sample_id}")
def get_sample_assay(sample_id: str):
    assay = SampleService.get_sample_assays(sample_id)
    if not assay:
        raise HTTPException(status_code=404, detail="Assay not found")
    return {"data": assay}


# ----------------------------
# SNVs
# ----------------------------

@router.get("/sample-assays/{sample_assay_id}/snvs")
def get_snvs(sample_assay_id: str):
    return {"data": SampleService.get_snvs(sample_assay_id)}


@router.get("/sample-assays/{sample_assay_id}/snvs/{chrom}/{pos}/{ref}/{alt}")
def get_snv_detail(sample_assay_id: str, chrom: str, pos: str, ref: str, alt: str):
    """Get single SNV with review data"""
    snv = SampleService.get_snv(sample_assay_id, chrom, pos, ref, alt)
    if not snv:
        raise HTTPException(status_code=404, detail="SNV not found")
    return {"data": snv}


@router.post("/sample-assays/{sample_assay_id}/snvs/{chrom}/{pos}/{ref}/{alt}/review")
def submit_snv_review(
    sample_assay_id: str, chrom: str, pos: str, ref: str, alt: str,
    request: Request, payload: dict = Body(default={}),
):
    """Submit or update variant review"""
    tier = payload.get("tier") or None
    is_artifact = payload.get("is_artifact", False)
    interpretation = payload.get("interpretation", "")
    note = payload.get("note", "")
    bypass_justification = payload.get("bypass_justification", "")

    valid_tiers = ["tier_1", "tier_2", "tier_3", "tier_4", None]
    if tier not in valid_tiers:
        raise HTTPException(status_code=400, detail="Invalid tier value")

    user = _require_user(request)

    try:
        updated_snv = SampleService.update_snv_review(
            sample_assay_id, chrom, pos, ref, alt,
            tier,
            is_artifact,
            interpretation,
            actor_username=user["username"],
            actor_user_id=user["user_id"],
            actor_role=user["role"],
            note=note,
            bypass_justification=bypass_justification,
        )
    except ReviewError as e:
        raise HTTPException(status_code=409, detail=str(e))

    summary = SampleService.get_summary(sample_assay_id)
    return {"data": updated_snv, "summary": summary}


# ----------------------------
# Assay Configs
# ----------------------------

@router.get("/assay-configs")
def list_assay_configs():
    return {"data": AssayConfigService.list_configs()}


@router.get("/assay-configs/{assay_id}")
def get_assay_config(assay_id: str):
    config = AssayConfigService.get_active_config(assay_id)
    if not config:
        raise HTTPException(status_code=404, detail="Assay config not found")
    return {"data": config}


@router.post("/assay-configs", status_code=201, dependencies=[Depends(require_role("admin", "lab_director", "senior_reviewer"))])
def create_assay_config(payload: dict = Body(default=None)):
    if not payload:
        raise HTTPException(status_code=400, detail="Request body required")
    config = AssayConfigService.create_config(payload)
    return {"data": config}


# ----------------------------
# CNVs
# ----------------------------

@router.get("/sample-assays/{sample_assay_id}/cnvs", dependencies=[Depends(require_login)])
def get_cnvs(sample_assay_id: str):
    return {"data": SampleService.get_cnvs(sample_assay_id)}


@router.get("/sample-assays/{sample_assay_id}/cnvs/{gene}", dependencies=[Depends(require_login)])
def get_cnv(sample_assay_id: str, gene: str):
    cnv = SampleService.get_cnv(sample_assay_id, gene)
    if not cnv:
        raise HTTPException(status_code=404, detail="CNV not found")
    return {"data": cnv}


@router.post("/sample-assays/{sample_assay_id}/cnvs/{gene}/review")
def submit_cnv_review(sample_assay_id: str, gene: str, request: Request, payload: dict = Body(default={})):
    user = _require_user(request)
    try:
        updated = SampleService.update_cnv_review(
            sample_assay_id, gene,
            payload.get("tier") or None,
            payload.get("is_artifact", False),
            payload.get("interpretation", ""),
            actor_username=user["username"],
            actor_user_id=user["user_id"],
            actor_role=user["role"],
            note=payload.get("note", ""),
            bypass_justification=payload.get("bypass_justification", ""),
        )
    except ReviewError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"data": updated, "summary": SampleService.get_summary(sample_assay_id)}


# ----------------------------
# SVs / Fusions
# ----------------------------

@router.get("/sample-assays/{sample_assay_id}/svs", dependencies=[Depends(require_login)])
def get_svs(sample_assay_id: str):
    return {"data": SampleService.get_svs(sample_assay_id)}


@router.get("/sample-assays/{sample_assay_id}/svs/{sv_id}", dependencies=[Depends(require_login)])
def get_sv(sample_assay_id: str, sv_id: str):
    sv = SampleService.get_sv(sample_assay_id, sv_id)
    if not sv:
        raise HTTPException(status_code=404, detail="SV not found")
    return {"data": sv}


@router.post("/sample-assays/{sample_assay_id}/svs/{sv_id}/review")
def submit_sv_review(sample_assay_id: str, sv_id: str, request: Request, payload: dict = Body(default={})):
    user = _require_user(request)
    try:
        updated = SampleService.update_sv_review(
            sample_assay_id, sv_id,
            payload.get("tier") or None,
            payload.get("is_artifact", False),
            payload.get("interpretation", ""),
            actor_username=user["username"],
            actor_user_id=user["user_id"],
            actor_role=user["role"],
            note=payload.get("note", ""),
            bypass_justification=payload.get("bypass_justification", ""),
        )
    except ReviewError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"data": updated, "summary": SampleService.get_summary(sample_assay_id)}


# ----------------------------
# Case assignment (Task 5)
# ----------------------------

@router.post(
    "/sample-assays/{sample_assay_id}/assign",
    dependencies=[Depends(require_role("admin", "lab_director", "senior_reviewer"))],
)
def assign_case(sample_assay_id: str, payload: dict = Body(default={})):
    reviewers = payload.get("reviewers", [])
    bioinformatician = payload.get("bioinformatician")
    result = SampleService.assign_case(sample_assay_id, reviewers, bioinformatician)
    if not result:
        raise HTTPException(status_code=404, detail="Sample assay not found")
    return {"data": result}


# ----------------------------
# Preflight checklist (Task 5)
# ----------------------------

@router.get("/sample-assays/{sample_assay_id}/preflight", dependencies=[Depends(require_login)])
def run_preflight(sample_assay_id: str):
    checks = PreflightService.run_checks(sample_assay_id)
    return {
        "data": checks,
        "all_passed": PreflightService.all_passed(checks),
    }


# ----------------------------
# Biomarkers (Task 8)
# ----------------------------

@router.get("/sample-assays/{sample_assay_id}/biomarkers", dependencies=[Depends(require_login)])
def get_biomarkers(sample_assay_id: str):
    biomarker = BiomarkerService.get_biomarkers(sample_assay_id)
    if not biomarker:
        return {"data": None}
    return {"data": biomarker}


@router.post(
    "/sample-assays/{sample_assay_id}/biomarkers/classify",
    dependencies=[Depends(require_role("admin", "lab_director", "senior_reviewer", "bioinformatician"))],
)
def classify_biomarkers(sample_assay_id: str):
    try:
        doc = BiomarkerService.classify_from_callset(sample_assay_id)
    except BiomarkerError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"data": doc}


@router.post("/sample-assays/{sample_assay_id}/biomarkers/confirm")
def confirm_biomarkers(sample_assay_id: str, request: Request, payload: dict = Body(default={})):
    user = _require_user(request)
    try:
        updated = BiomarkerService.confirm(
            sample_assay_id,
            reviewer_note=payload.get("reviewer_note", ""),
            discordance_acknowledged=payload.get("discordance_acknowledged", False),
            actor_username=user["username"],
            actor_user_id=user["user_id"],
            actor_role=user["role"],
        )
    except BiomarkerError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"data": updated}


# ----------------------------
# Reports
# ----------------------------

@router.get("/sample-assays/{sample_assay_id}/reports", dependencies=[Depends(require_login)])
def list_reports(sample_assay_id: str):
    return {"data": ReportService.get_reports_for_assay(sample_assay_id)}


@router.post("/sample-assays/{sample_assay_id}/reports", status_code=201)
def create_report(sample_assay_id: str, request: Request):
    user = _require_user(request)
    try:
        report = ReportService.create_draft(
            sample_assay_id,
            created_by_user_id=user["user_id"],
            created_by_username=user["username"],
        )
    except ReportError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"data": report}


@router.get("/reports/{report_id}", dependencies=[Depends(require_login)])
def get_report(report_id: str):
    report = ReportService.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return {"data": report}


@router.post("/reports/{report_id}/sign-off")
def sign_off_report(report_id: str, request: Request):
    user = _require_user(request)
    try:
        updated = ReportService.add_signoff(
            report_id,
            actor_user_id=user["user_id"],
            actor_username=user["username"],
            actor_role=user["role"],
        )
    except ReportError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"data": updated}


@router.post(
    "/reports/{report_id}/finalise",
    dependencies=[Depends(require_role("admin", "senior_reviewer", "lab_director"))],
)
def finalise_report(report_id: str, request: Request):
    user = current_user(request)
    try:
        updated = ReportService.finalise(
            report_id,
            actor_user_id=user["user_id"],
            actor_username=user["username"],
            actor_role=user["role"],
        )
    except ReportError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"data": updated}


@router.get("/reports/{report_id}/export", dependencies=[Depends(require_login)])
def export_report_json(report_id: str):
    try:
        data = ReportService.export_json(report_id)
    except ReportError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return data


@router.post(
    "/reports/{report_id}/addendum",
    status_code=201,
    dependencies=[Depends(require_role("admin", "senior_reviewer", "lab_director"))],
)
def create_addendum(report_id: str, request: Request):
    user = current_user(request)
    try:
        doc = ReportService.create_addendum(
            report_id,
            created_by_user_id=user["user_id"],
            created_by_username=user["username"],
        )
    except ReportError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"data": doc}


# ----------------------------
# Knowledge Database
# ----------------------------

@router.get("/knowledge", dependencies=[Depends(require_login)])
def list_knowledge(gene: str = "", variant_type: str = "", tier: str = "", disease_group: str = "", disease_subtype: str = ""):
    entries = KnowledgeService.list_entries(
        gene=gene,
        variant_type=variant_type,
        tier=tier,
        disease_group=disease_group,
        disease_subtype=disease_subtype,
    )
    return {"data": entries}


@router.get("/knowledge/search", dependencies=[Depends(require_login)])
def search_knowledge(q: str = "", gene: str | None = None, tier: str | None = None, disease_group: str | None = None):
    q = q.strip()
    if not q:
        raise HTTPException(status_code=400, detail="Query parameter 'q' is required")
    try:
        results = KnowledgeService.search(
            q,
            filters={
                "gene": gene,
                "tier": tier,
                "disease_group": disease_group,
            },
        )
    except KnowledgeError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"data": results}


@router.post("/knowledge", status_code=201, dependencies=[Depends(require_role("admin", "senior_reviewer", "lab_director"))])
def create_knowledge(request: Request, payload: dict = Body(default={})):
    user = current_user(request)
    try:
        entry = KnowledgeService.create_entry(payload, user["user_id"], user["username"])
    except KnowledgeError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"data": entry}


@router.get("/knowledge/{knowledge_id}", dependencies=[Depends(require_login)])
def get_knowledge(knowledge_id: str):
    entry = KnowledgeService.get_entry(knowledge_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Knowledge entry not found")
    return {"data": entry}


@router.put("/knowledge/{knowledge_id}", dependencies=[Depends(require_role("admin", "senior_reviewer", "lab_director"))])
def update_knowledge(knowledge_id: str, request: Request, payload: dict = Body(default={})):
    user = current_user(request)
    try:
        updated = KnowledgeService.update_entry(
            knowledge_id, payload, user["user_id"], user["username"],
            change_note=payload.get("change_note", ""),
        )
    except KnowledgeError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"data": updated}


@router.get("/knowledge/lookup/snv", dependencies=[Depends(require_login)])
def lookup_snv_knowledge(gene: str = "", hgvsp: str = "", disease_subtype: str | None = None):
    if not gene or not hgvsp:
        raise HTTPException(status_code=400, detail="gene and hgvsp are required")
    entry = KnowledgeService.lookup_for_snv(gene, hgvsp, disease_subtype)
    return {"data": entry}


# ----------------------------
# Summary
# ----------------------------

@router.get("/sample-assays/{sample_assay_id}/summary")
def get_summary(sample_assay_id: str):
    summary = SampleService.get_summary(sample_assay_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found")
    return {"data": summary}


# ----------------------------
# TAT / Lab Dashboard (Phase 7)
# ----------------------------

@router.get("/lab/dashboard", dependencies=[Depends(require_role("admin", "lab_director", "senior_reviewer"))])
def lab_dashboard_api():
    return {"data": TATService.dashboard_stats()}


# ----------------------------
# Gap Analysis (Phase 7)
# ----------------------------

@router.get("/gap-analysis", dependencies=[Depends(require_role("admin", "lab_director"))])
def gap_analysis_api(gene: str = "", assay_id: str | None = None):
    gene = gene.strip()
    assay_id = (assay_id or "").strip() or None
    if not gene:
        raise HTTPException(status_code=400, detail="gene parameter required")
    return {"data": GapAnalysisService.query_gene_coverage(gene, assay_id)}


# ----------------------------
# Cohort Query (Phase 7)
# ----------------------------

@router.get("/cohort", dependencies=[Depends(require_login)])
def cohort_query_api(gene: str = "", tier: str = "", variant_type: str = "", assay_id: str = "", acknowledge: str = ""):
    result = CohortService.query(
        gene=gene,
        tier=tier,
        variant_type=variant_type,
        assay_id=assay_id,
        acknowledge_multi_version=acknowledge == "1",
    )
    return {"data": result}


# ----------------------------
# Portal Token Management (Phase 7)
# ----------------------------

@router.post(
    "/reports/{report_id}/portal-token",
    status_code=201,
    dependencies=[Depends(require_role("admin", "lab_director", "senior_reviewer"))],
)
def issue_portal_token(report_id: str, request: Request):
    user = current_user(request)
    try:
        token_doc = PortalService.issue_token(report_id, user["user_id"], user["username"])
    except PortalError as e:
        raise HTTPException(status_code=409, detail=str(e))
    portal_url = f"/portal/access/{token_doc['token']}"
    return {"data": {"portal_url": portal_url, "expires_at": token_doc["expires_at"]}}


# ----------------------------
# Federation (Phase 7)
# ----------------------------

@router.post("/federation/export", status_code=201, dependencies=[Depends(require_role("admin", "lab_director"))])
def federation_export_api(request: Request, payload: dict = Body(default={})):
    user = current_user(request)
    lab_id = payload.get("lab_id", "").strip()
    if not lab_id:
        raise HTTPException(status_code=400, detail="lab_id is required")
    try:
        export = FederationService.build_export(lab_id, user["user_id"], user["username"])
    except FederationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"data": {k: v for k, v in export.items() if k != "entries"}}


@router.post("/federation/import", dependencies=[Depends(require_role("admin", "lab_director"))])
def federation_import_api(request: Request, payload: dict = Body(default={})):
    user = current_user(request)
    try:
        result = FederationService.import_from_registry(payload, user["username"])
    except FederationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"data": result}


@router.get("/federation/exports", dependencies=[Depends(require_role("admin", "lab_director"))])
def list_federation_exports():
    return {"data": FederationService.list_exports()}


@router.get("/federation/eligible", dependencies=[Depends(require_role("admin", "lab_director"))])
def federation_eligible():
    entries = FederationService.eligible_entries()
    return {"data": {"count": len(entries)}}


# ----------------------------
# Callsets / Ingestion (Phase 4)
# ----------------------------

@router.get("/sample-assays/{sample_assay_id}/callsets", dependencies=[Depends(require_login)])
def list_callsets(sample_assay_id: str):
    return {"data": IngestionService.get_callsets(sample_assay_id)}


@router.get("/callsets/{callset_id}", dependencies=[Depends(require_login)])
def get_callset(callset_id: str):
    callset = IngestionService.get_callset(callset_id)
    if not callset:
        raise HTTPException(status_code=404, detail="Callset not found")
    return {"data": callset}


@router.post(
    "/sample-assays/{sample_assay_id}/callsets/import",
    status_code=201,
    dependencies=[Depends(require_role("admin", "bioinformatician", "lab_director"))],
)
def import_callset(sample_assay_id: str, request: Request, payload: dict = Body(default={})):
    """
    Trigger a VCF import via API (dev / testing only — skips normalisation and annotation).
    Body: { "vcf_path": "...", "qc_json_path": "...", "skip_normalise": true, "skip_annotate": true }
    """
    user = current_user(request)
    vcf_path = payload.get("vcf_path", "")
    if not vcf_path:
        raise HTTPException(status_code=400, detail="vcf_path is required")
    try:
        callset = IngestionService.import_vcf(
            vcf_path=vcf_path,
            qc_json_path=payload.get("qc_json_path"),
            sample_assay_id=sample_assay_id,
            imported_by_user_id=user["user_id"],
            imported_by_username=user["username"],
            skip_normalise=payload.get("skip_normalise", False),
            skip_annotate=payload.get("skip_annotate", False),
        )
    except IngestionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"data": callset}
