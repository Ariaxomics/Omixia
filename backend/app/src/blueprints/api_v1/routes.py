from flask import Blueprint, jsonify, request, session

from src.auth import current_user, current_username, require_login, require_role
from src.services.assay_config import AssayConfigService
from src.services.biomarker import BiomarkerError, BiomarkerService
from src.services.preflight import PreflightService
from src.services.report import ReportError, ReportService
from src.services.samples import ReviewError, SampleService


api_bp = Blueprint("api", __name__)


# ----------------------------
# Health
# ----------------------------

@api_bp.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "omixia"})


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
@require_role("lab_director", "senior_reviewer")
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
@require_role("lab_director", "senior_reviewer")
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
@require_role("lab_director", "senior_reviewer", "bioinformatician")
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
@require_role("senior_reviewer", "lab_director")
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
@require_role("senior_reviewer", "lab_director")
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
# Summary
# ----------------------------

@api_bp.route("/sample-assays/<sample_assay_id>/summary", methods=["GET"])
def get_summary(sample_assay_id):
    summary = SampleService.get_summary(sample_assay_id)
    if not summary:
        return jsonify({"error": "Summary not found"}), 404

    return jsonify({"data": summary})