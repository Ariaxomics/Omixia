from flask import Blueprint, jsonify, request, session

from src.auth import current_user, current_username, require_login, require_role
from src.services.assay_config import AssayConfigService
from src.services.ingestion import IngestionError, IngestionService
from src.services.biomarker import BiomarkerError, BiomarkerService
from src.services.federation import FederationError, FederationService
from src.services.gap_analysis import CohortService, GapAnalysisService
from src.services.knowledge import KnowledgeError, KnowledgeService
from src.services.portal import PortalError, PortalService
from src.services.preflight import PreflightService
from src.services.report import ReportError, ReportService
from src.services.samples import ReviewError, SampleService
from src.services.tat import TATService


api_bp = Blueprint("api", __name__)


# ----------------------------
# Health
# ----------------------------

@api_bp.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "omixia"})


# ----------------------------
# Auth
# ----------------------------

@api_bp.route("/auth/login", methods=["POST"])
def api_login():
    from src.services.users import UserService
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    if not username or not password:
        return jsonify({"error": "username and password required"}), 400
    user = UserService.authenticate(username, password)
    if not user:
        return jsonify({"error": "Invalid credentials"}), 401
    session["user"] = {
        "user_id": user["user_id"],
        "username": user["username"],
        "role": user["role"],
        "full_name": user.get("full_name", ""),
        "email": user.get("email", ""),
    }
    return jsonify({"data": session["user"]})


@api_bp.route("/auth/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"ok": True})


@api_bp.route("/auth/me", methods=["GET"])
def api_me():
    user = session.get("user")
    if not user:
        return jsonify({"error": "Not authenticated"}), 401
    return jsonify({"data": user})


# ----------------------------
# Users
# ----------------------------

@api_bp.route("/users", methods=["GET"])
@require_role("admin", "lab_director", "senior_reviewer")
def list_users():
    from src.extensions import mongo_client
    db = mongo_client.db
    users = list(db.users.find({}, {"_id": 0, "password_hash": 0}))
    return jsonify({"data": users})


@api_bp.route("/users", methods=["POST"])
@require_role("admin", "lab_director")
def register_user():
    from src.services.users import UserService
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    email = data.get("email", "").strip()
    role = data.get("role", "").strip()
    full_name = data.get("full_name", "").strip()
    password = data.get("password", "")

    missing = [f for f, v in [("username", username), ("email", email), ("role", role), ("full_name", full_name), ("password", password)] if not v]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    if len(password) < 12:
        return jsonify({"error": "Password must be at least 12 characters"}), 400

    try:
        user = UserService.create_user(username, email, role, full_name, password)
    except ValueError as e:
        return jsonify({"error": str(e)}), 409

    return jsonify({"data": user}), 201


# ----------------------------
# Samples
# ----------------------------

@api_bp.route("/samples", methods=["GET"])
def list_samples():
    return jsonify({
        "data": SampleService.list_samples()
    })


@api_bp.route("/samples/<sample_id>", methods=["GET"])
def get_sample(sample_id):
    sample = SampleService.get_sample(sample_id)
    if not sample:
        return jsonify({"error": "Sample not found"}), 404

    return jsonify({"data": sample})


# ----------------------------
# Assays
# ----------------------------

@api_bp.route("/samples/<sample_id>/assays", methods=["GET"])
def get_sample_assays(sample_id):
    return jsonify({
        "data": SampleService.get_sample_assays(sample_id)
    })


@api_bp.route("/sample-assays/<sample_id>", methods=["GET"])
def get_sample_assay(sample_id):
    assay = SampleService.get_sample_assays(sample_id)
    if not assay:
        return jsonify({"error": "Assay not found"}), 404

    return jsonify({"data": assay})


# ----------------------------
# SNVs
# ----------------------------

@api_bp.route("/sample-assays/<sample_assay_id>/snvs", methods=["GET"])
def get_snvs(sample_assay_id):
    return jsonify({
        "data": SampleService.get_snvs(sample_assay_id)
    })


@api_bp.route("/sample-assays/<sample_assay_id>/snvs/<chrom>/<pos>/<ref>/<alt>", methods=["GET"])
def get_snv_detail(sample_assay_id, chrom, pos, ref, alt):
    """Get single SNV with review data"""
    snv = SampleService.get_snv(sample_assay_id, chrom, pos, ref, alt)
    if not snv:
        return jsonify({"error": "SNV not found"}), 404
    return jsonify({"data": snv})


@api_bp.route("/sample-assays/<sample_assay_id>/snvs/<chrom>/<pos>/<ref>/<alt>/review", methods=["POST"])
def submit_snv_review(sample_assay_id, chrom, pos, ref, alt):
    """Submit or update variant review"""
    data = request.get_json()

    tier = data.get("tier") or None
    is_artifact = data.get("is_artifact", False)
    interpretation = data.get("interpretation", "")
    note = data.get("note", "")
    bypass_justification = data.get("bypass_justification", "")

    valid_tiers = ["tier_1", "tier_2", "tier_3", "tier_4", None]
    if tier not in valid_tiers:
        return jsonify({"error": "Invalid tier value"}), 400

    user = current_user()
    if not user:
        return jsonify({"error": "Unauthorised"}), 401

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
        return jsonify({"error": str(e)}), 409

    summary = SampleService.get_summary(sample_assay_id)
    return jsonify({"data": updated_snv, "summary": summary})


# ----------------------------
# Assay Configs
# ----------------------------

@api_bp.route("/assay-configs", methods=["GET"])
def list_assay_configs():
    return jsonify({"data": AssayConfigService.list_configs()})


@api_bp.route("/assay-configs/<assay_id>", methods=["GET"])
def get_assay_config(assay_id):
    config = AssayConfigService.get_active_config(assay_id)
    if not config:
        return jsonify({"error": "Assay config not found"}), 404
    return jsonify({"data": config})


@api_bp.route("/assay-configs", methods=["POST"])
@require_role("admin", "lab_director", "senior_reviewer")
def create_assay_config():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400
    config = AssayConfigService.create_config(data)
    return jsonify({"data": config}), 201


# ----------------------------
# CNVs
# ----------------------------

@api_bp.route("/sample-assays/<sample_assay_id>/cnvs", methods=["GET"])
@require_login
def get_cnvs(sample_assay_id):
    return jsonify({"data": SampleService.get_cnvs(sample_assay_id)})


@api_bp.route("/sample-assays/<sample_assay_id>/cnvs/<gene>", methods=["GET"])
@require_login
def get_cnv(sample_assay_id, gene):
    cnv = SampleService.get_cnv(sample_assay_id, gene)
    if not cnv:
        return jsonify({"error": "CNV not found"}), 404
    return jsonify({"data": cnv})


@api_bp.route("/sample-assays/<sample_assay_id>/cnvs/<gene>/review", methods=["POST"])
@require_login
def submit_cnv_review(sample_assay_id, gene):
    data = request.get_json() or {}
    user = current_user()
    if not user:
        return jsonify({"error": "Unauthorised"}), 401
    try:
        updated = SampleService.update_cnv_review(
            sample_assay_id, gene,
            data.get("tier") or None,
            data.get("is_artifact", False),
            data.get("interpretation", ""),
            actor_username=user["username"],
            actor_user_id=user["user_id"],
            actor_role=user["role"],
            note=data.get("note", ""),
            bypass_justification=data.get("bypass_justification", ""),
        )
    except ReviewError as e:
        return jsonify({"error": str(e)}), 409
    return jsonify({"data": updated, "summary": SampleService.get_summary(sample_assay_id)})


# ----------------------------
# SVs / Fusions
# ----------------------------

@api_bp.route("/sample-assays/<sample_assay_id>/svs", methods=["GET"])
@require_login
def get_svs(sample_assay_id):
    return jsonify({"data": SampleService.get_svs(sample_assay_id)})


@api_bp.route("/sample-assays/<sample_assay_id>/svs/<sv_id>", methods=["GET"])
@require_login
def get_sv(sample_assay_id, sv_id):
    sv = SampleService.get_sv(sample_assay_id, sv_id)
    if not sv:
        return jsonify({"error": "SV not found"}), 404
    return jsonify({"data": sv})


@api_bp.route("/sample-assays/<sample_assay_id>/svs/<sv_id>/review", methods=["POST"])
@require_login
def submit_sv_review(sample_assay_id, sv_id):
    data = request.get_json() or {}
    user = current_user()
    if not user:
        return jsonify({"error": "Unauthorised"}), 401
    try:
        updated = SampleService.update_sv_review(
            sample_assay_id, sv_id,
            data.get("tier") or None,
            data.get("is_artifact", False),
            data.get("interpretation", ""),
            actor_username=user["username"],
            actor_user_id=user["user_id"],
            actor_role=user["role"],
            note=data.get("note", ""),
            bypass_justification=data.get("bypass_justification", ""),
        )
    except ReviewError as e:
        return jsonify({"error": str(e)}), 409
    return jsonify({"data": updated, "summary": SampleService.get_summary(sample_assay_id)})


# ----------------------------
# Case assignment (Task 5)
# ----------------------------

@api_bp.route("/sample-assays/<sample_assay_id>/assign", methods=["POST"])
@require_role("admin", "lab_director", "senior_reviewer")
def assign_case(sample_assay_id):
    data = request.get_json() or {}
    reviewers = data.get("reviewers", [])
    bioinformatician = data.get("bioinformatician")
    result = SampleService.assign_case(sample_assay_id, reviewers, bioinformatician)
    if not result:
        return jsonify({"error": "Sample assay not found"}), 404
    return jsonify({"data": result})


# ----------------------------
# Preflight checklist (Task 5)
# ----------------------------

@api_bp.route("/sample-assays/<sample_assay_id>/preflight", methods=["GET"])
@require_login
def run_preflight(sample_assay_id):
    checks = PreflightService.run_checks(sample_assay_id)
    return jsonify({
        "data": checks,
        "all_passed": PreflightService.all_passed(checks),
    })


# ----------------------------
# Biomarkers (Task 8)
# ----------------------------

@api_bp.route("/sample-assays/<sample_assay_id>/biomarkers", methods=["GET"])
@require_login
def get_biomarkers(sample_assay_id):
    biomarker = BiomarkerService.get_biomarkers(sample_assay_id)
    if not biomarker:
        return jsonify({"data": None}), 200
    return jsonify({"data": biomarker})


@api_bp.route("/sample-assays/<sample_assay_id>/biomarkers/classify", methods=["POST"])
@require_role("admin", "lab_director", "senior_reviewer", "bioinformatician")
def classify_biomarkers(sample_assay_id):
    try:
        doc = BiomarkerService.classify_from_callset(sample_assay_id)
    except BiomarkerError as e:
        return jsonify({"error": str(e)}), 422
    return jsonify({"data": doc})


@api_bp.route("/sample-assays/<sample_assay_id>/biomarkers/confirm", methods=["POST"])
@require_login
def confirm_biomarkers(sample_assay_id):
    data = request.get_json() or {}
    user = current_user()
    if not user:
        return jsonify({"error": "Unauthorised"}), 401
    try:
        updated = BiomarkerService.confirm(
            sample_assay_id,
            reviewer_note=data.get("reviewer_note", ""),
            discordance_acknowledged=data.get("discordance_acknowledged", False),
            actor_username=user["username"],
            actor_user_id=user["user_id"],
            actor_role=user["role"],
        )
    except BiomarkerError as e:
        return jsonify({"error": str(e)}), 409
    return jsonify({"data": updated})


# ----------------------------
# Reports
# ----------------------------

@api_bp.route("/sample-assays/<sample_assay_id>/reports", methods=["GET"])
@require_login
def list_reports(sample_assay_id):
    return jsonify({"data": ReportService.get_reports_for_assay(sample_assay_id)})


@api_bp.route("/sample-assays/<sample_assay_id>/reports", methods=["POST"])
@require_login
def create_report(sample_assay_id):
    user = current_user()
    if not user:
        return jsonify({"error": "Unauthorised"}), 401
    try:
        report = ReportService.create_draft(
            sample_assay_id,
            created_by_user_id=user["user_id"],
            created_by_username=user["username"],
        )
    except ReportError as e:
        return jsonify({"error": str(e)}), 409
    return jsonify({"data": report}), 201


@api_bp.route("/reports/<report_id>", methods=["GET"])
@require_login
def get_report(report_id):
    report = ReportService.get_report(report_id)
    if not report:
        return jsonify({"error": "Report not found"}), 404
    return jsonify({"data": report})


@api_bp.route("/reports/<report_id>/sign-off", methods=["POST"])
@require_login
def sign_off_report(report_id):
    user = current_user()
    if not user:
        return jsonify({"error": "Unauthorised"}), 401
    try:
        updated = ReportService.add_signoff(
            report_id,
            actor_user_id=user["user_id"],
            actor_username=user["username"],
            actor_role=user["role"],
        )
    except ReportError as e:
        return jsonify({"error": str(e)}), 409
    return jsonify({"data": updated})


@api_bp.route("/reports/<report_id>/finalise", methods=["POST"])
@require_role("admin", "senior_reviewer", "lab_director")
def finalise_report(report_id):
    user = current_user()
    try:
        updated = ReportService.finalise(
            report_id,
            actor_user_id=user["user_id"],
            actor_username=user["username"],
            actor_role=user["role"],
        )
    except ReportError as e:
        return jsonify({"error": str(e)}), 409
    return jsonify({"data": updated})


@api_bp.route("/reports/<report_id>/export", methods=["GET"])
@require_login
def export_report_json(report_id):
    try:
        data = ReportService.export_json(report_id)
    except ReportError as e:
        return jsonify({"error": str(e)}), 404
    return jsonify(data)


@api_bp.route("/reports/<report_id>/addendum", methods=["POST"])
@require_role("admin", "senior_reviewer", "lab_director")
def create_addendum(report_id):
    user = current_user()
    try:
        doc = ReportService.create_addendum(
            report_id,
            created_by_user_id=user["user_id"],
            created_by_username=user["username"],
        )
    except ReportError as e:
        return jsonify({"error": str(e)}), 409
    return jsonify({"data": doc}), 201


# ----------------------------
# Knowledge Database
# ----------------------------

@api_bp.route("/knowledge", methods=["GET"])
@require_login
def list_knowledge():
    entries = KnowledgeService.list_entries(
        gene=request.args.get("gene", ""),
        variant_type=request.args.get("variant_type", ""),
        tier=request.args.get("tier", ""),
        disease_group=request.args.get("disease_group", ""),
        disease_subtype=request.args.get("disease_subtype", ""),
    )
    return jsonify({"data": entries})


@api_bp.route("/knowledge/search", methods=["GET"])
@require_login
def search_knowledge():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "Query parameter 'q' is required"}), 400
    try:
        results = KnowledgeService.search(
            q,
            filters={
                "gene": request.args.get("gene"),
                "tier": request.args.get("tier"),
                "disease_group": request.args.get("disease_group"),
            },
        )
    except KnowledgeError as e:
        return jsonify({"error": str(e)}), 422
    return jsonify({"data": results})


@api_bp.route("/knowledge", methods=["POST"])
@require_role("admin", "senior_reviewer", "lab_director")
def create_knowledge():
    data = request.get_json() or {}
    user = current_user()
    try:
        entry = KnowledgeService.create_entry(data, user["user_id"], user["username"])
    except KnowledgeError as e:
        return jsonify({"error": str(e)}), 422
    return jsonify({"data": entry}), 201


@api_bp.route("/knowledge/<knowledge_id>", methods=["GET"])
@require_login
def get_knowledge(knowledge_id):
    entry = KnowledgeService.get_entry(knowledge_id)
    if not entry:
        return jsonify({"error": "Knowledge entry not found"}), 404
    return jsonify({"data": entry})


@api_bp.route("/knowledge/<knowledge_id>", methods=["PUT"])
@require_role("admin", "senior_reviewer", "lab_director")
def update_knowledge(knowledge_id):
    data = request.get_json() or {}
    user = current_user()
    try:
        updated = KnowledgeService.update_entry(
            knowledge_id, data, user["user_id"], user["username"],
            change_note=data.get("change_note", ""),
        )
    except KnowledgeError as e:
        return jsonify({"error": str(e)}), 422
    return jsonify({"data": updated})


@api_bp.route("/knowledge/lookup/snv", methods=["GET"])
@require_login
def lookup_snv_knowledge():
    gene = request.args.get("gene", "")
    hgvsp = request.args.get("hgvsp", "")
    disease_subtype = request.args.get("disease_subtype") or None
    if not gene or not hgvsp:
        return jsonify({"error": "gene and hgvsp are required"}), 400
    entry = KnowledgeService.lookup_for_snv(gene, hgvsp, disease_subtype)
    return jsonify({"data": entry})


# ----------------------------
# Summary
# ----------------------------

@api_bp.route("/sample-assays/<sample_assay_id>/summary", methods=["GET"])
def get_summary(sample_assay_id):
    summary = SampleService.get_summary(sample_assay_id)
    if not summary:
        return jsonify({"error": "Summary not found"}), 404

    return jsonify({"data": summary})

# ----------------------------
# TAT / Lab Dashboard (Phase 7)
# ----------------------------

@api_bp.route("/lab/dashboard", methods=["GET"])
@require_role("admin", "lab_director", "senior_reviewer")
def lab_dashboard_api():
    return jsonify({"data": TATService.dashboard_stats()})


# ----------------------------
# Gap Analysis (Phase 7)
# ----------------------------

@api_bp.route("/gap-analysis", methods=["GET"])
@require_role("admin", "lab_director")
def gap_analysis_api():
    gene = request.args.get("gene", "").strip()
    assay_id = request.args.get("assay_id", "").strip() or None
    if not gene:
        return jsonify({"error": "gene parameter required"}), 400
    return jsonify({"data": GapAnalysisService.query_gene_coverage(gene, assay_id)})


# ----------------------------
# Cohort Query (Phase 7)
# ----------------------------

@api_bp.route("/cohort", methods=["GET"])
@require_login
def cohort_query_api():
    result = CohortService.query(
        gene=request.args.get("gene", ""),
        tier=request.args.get("tier", ""),
        variant_type=request.args.get("variant_type", ""),
        assay_id=request.args.get("assay_id", ""),
        acknowledge_multi_version=request.args.get("acknowledge") == "1",
    )
    return jsonify({"data": result})


# ----------------------------
# Portal Token Management (Phase 7)
# ----------------------------

@api_bp.route("/reports/<report_id>/portal-token", methods=["POST"])
@require_role("admin", "lab_director", "senior_reviewer")
def issue_portal_token(report_id):
    user = current_user()
    try:
        token_doc = PortalService.issue_token(report_id, user["user_id"], user["username"])
    except PortalError as e:
        return jsonify({"error": str(e)}), 409
    portal_url = f"/portal/access/{token_doc['token']}"
    return jsonify({"data": {"portal_url": portal_url, "expires_at": token_doc["expires_at"]}}), 201


# ----------------------------
# Federation (Phase 7)
# ----------------------------

@api_bp.route("/federation/export", methods=["POST"])
@require_role("admin", "lab_director")
def federation_export_api():
    user = current_user()
    data = request.get_json() or {}
    lab_id = data.get("lab_id", "").strip()
    if not lab_id:
        return jsonify({"error": "lab_id is required"}), 400
    try:
        export = FederationService.build_export(lab_id, user["user_id"], user["username"])
    except FederationError as e:
        return jsonify({"error": str(e)}), 422
    return jsonify({"data": {k: v for k, v in export.items() if k != "entries"}}), 201


@api_bp.route("/federation/import", methods=["POST"])
@require_role("admin", "lab_director")
def federation_import_api():
    user = current_user()
    payload = request.get_json() or {}
    try:
        result = FederationService.import_from_registry(payload, user["username"])
    except FederationError as e:
        return jsonify({"error": str(e)}), 422
    return jsonify({"data": result})


@api_bp.route("/federation/exports", methods=["GET"])
@require_role("admin", "lab_director")
def list_federation_exports():
    return jsonify({"data": FederationService.list_exports()})


@api_bp.route("/federation/eligible", methods=["GET"])
@require_role("admin", "lab_director")
def federation_eligible():
    entries = FederationService.eligible_entries()
    return jsonify({"data": {"count": len(entries)}})


# ----------------------------
# Callsets / Ingestion (Phase 4)
# ----------------------------

@api_bp.route("/sample-assays/<sample_assay_id>/callsets", methods=["GET"])
@require_login
def list_callsets(sample_assay_id):
    return jsonify({"data": IngestionService.get_callsets(sample_assay_id)})


@api_bp.route("/callsets/<callset_id>", methods=["GET"])
@require_login
def get_callset(callset_id):
    callset = IngestionService.get_callset(callset_id)
    if not callset:
        return jsonify({"error": "Callset not found"}), 404
    return jsonify({"data": callset})


@api_bp.route("/sample-assays/<sample_assay_id>/callsets/import", methods=["POST"])
@require_role("admin", "bioinformatician", "lab_director")
def import_callset(sample_assay_id):
    """
    Trigger a VCF import via API (dev / testing only — skips normalisation and annotation).
    Body: { "vcf_path": "...", "qc_json_path": "...", "skip_normalise": true, "skip_annotate": true }
    """
    user = current_user()
    data = request.get_json() or {}
    vcf_path = data.get("vcf_path", "")
    if not vcf_path:
        return jsonify({"error": "vcf_path is required"}), 400
    try:
        callset = IngestionService.import_vcf(
            vcf_path=vcf_path,
            qc_json_path=data.get("qc_json_path"),
            sample_assay_id=sample_assay_id,
            imported_by_user_id=user["user_id"],
            imported_by_username=user["username"],
            skip_normalise=data.get("skip_normalise", False),
            skip_annotate=data.get("skip_annotate", False),
        )
    except IngestionError as exc:
        return jsonify({"error": str(exc)}), 422
    return jsonify({"data": callset}), 201
