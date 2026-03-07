from flask import Blueprint, render_template, redirect, url_for, request, session

from src.auth import current_user, current_username, require_login, require_role
from src.services.biomarker import BiomarkerError, BiomarkerService
from src.services.federation import FederationError, FederationService
from src.services.ingestion import IngestionService
from src.services.gap_analysis import CohortService, GapAnalysisService
from src.services.knowledge import KnowledgeError, KnowledgeService
from src.services.portal import PortalError, PortalService
from src.services.preflight import PreflightService
from src.services.report import ReportError, ReportService
from src.services.samples import ReviewError, SampleService
from src.services.tat import TATService
from src.services.users import UserService


web_bp = Blueprint(
    "web",
    __name__,
    template_folder="templates"
)


# ------------------------
# Home
# ------------------------
@web_bp.route("/")
def landing():
    return render_template("landing.html")


# ------------------------
# About
# ------------------------
@web_bp.route("/about")
def about():
    return render_template("about.html")


# ------------------------
# Login
# ------------------------
@web_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = UserService.authenticate(username, password)
        if user:
            session["user"] = user
            return redirect(url_for("web.dashboard"))

        return render_template("login.html", error="Invalid credentials")

    return render_template("login.html")


# ------------------------
# Logout
# ------------------------
@web_bp.route("/logout", methods=["POST"])
def logout():
    session.pop("user", None)
    return redirect(url_for("web.landing"))


# ------------------------
# Dashboard
# ------------------------
@web_bp.route("/dashboard")
@require_login
def dashboard():
    return render_template("dashboard.html", user=session["user"])


# ------------------------
# Samples
# ------------------------
@web_bp.route("/samples")
@require_login
def samples_page():
    return render_template("samples.html")


# ----------------------------
# HTMX PARTIALS
# ----------------------------

@web_bp.route("/partials/samples")
@require_login
def samples_partial():
    samples = SampleService.list_samples()
    return render_template("partials/samples_table.html", samples=samples)


@web_bp.route("/partials/samples/<sample_id>/assays")
@require_login
def assays_partial(sample_id):
    assays = SampleService.get_sample_assays(sample_id)
    return render_template("partials/assays_table.html", assays=assays)


@web_bp.route("/partials/sample-assays/<sample_assay_id>/snvs")
@require_login
def snvs_partial(sample_assay_id):
    snvs = SampleService.get_snvs(sample_assay_id)
    return render_template("partials/snv_table.html", snvs=snvs, sample_assay_id=sample_assay_id)


@web_bp.route("/partials/sample-assays/<sample_assay_id>/snvs/<chrom>/<pos>/<ref>/<alt>/detail")
@require_login
def snv_detail_partial(sample_assay_id, chrom, pos, ref, alt):
    snv = SampleService.get_snv(sample_assay_id, chrom, pos, ref, alt)
    if not snv:
        return "<td colspan='6'>Variant not found</td>", 404

    # Resolve disease subtype for knowledge lookup
    assays = SampleService.get_sample_assays(sample_assay_id)
    sample_id = assays[0]["sample_id"] if assays else None
    sample = SampleService.get_sample(sample_id) if sample_id else None
    disease_subtype = (sample or {}).get("disease_subtype")

    evidence = KnowledgeService.get_evidence_panel(snv, disease_subtype)
    return render_template("partials/snv_detail_form.html", snv=snv, **evidence)


@web_bp.route("/partials/sample-assays/<sample_assay_id>/snvs/<chrom>/<pos>/<ref>/<alt>/review", methods=["POST"])
@require_login
def snv_review_submit(sample_assay_id, chrom, pos, ref, alt):
    tier = request.form.get("tier") or None
    is_artifact = request.form.get("is_artifact") == "true"
    interpretation = request.form.get("interpretation", "")
    note = request.form.get("note", "")
    bypass_justification = request.form.get("bypass_justification", "")

    user = current_user()
    error = None

    try:
        SampleService.update_snv_review(
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
        error = str(e)

    snvs = SampleService.get_snvs(sample_assay_id)
    return render_template(
        "partials/snv_table.html",
        snvs=snvs,
        sample_assay_id=sample_assay_id,
        review_error=error,
    )


# ----------------------------
# CNV partials (Task 6)
# ----------------------------

@web_bp.route("/partials/sample-assays/<sample_assay_id>/cnvs")
@require_login
def cnvs_partial(sample_assay_id):
    cnvs = SampleService.get_cnvs(sample_assay_id)
    return render_template("partials/cnv_table.html", cnvs=cnvs, sample_assay_id=sample_assay_id)


@web_bp.route("/partials/sample-assays/<sample_assay_id>/cnvs/<gene>/detail")
@require_login
def cnv_detail_partial(sample_assay_id, gene):
    cnv = SampleService.get_cnv(sample_assay_id, gene)
    if not cnv:
        return "<td colspan='6'>CNV not found</td>", 404
    return render_template("partials/cnv_detail_form.html", cnv=cnv)


@web_bp.route("/partials/sample-assays/<sample_assay_id>/cnvs/<gene>/review", methods=["POST"])
@require_login
def cnv_review_submit(sample_assay_id, gene):
    tier = request.form.get("tier") or None
    is_artifact = request.form.get("is_artifact") == "true"
    interpretation = request.form.get("interpretation", "")
    note = request.form.get("note", "")
    bypass_justification = request.form.get("bypass_justification", "")

    user = current_user()
    error = None
    try:
        SampleService.update_cnv_review(
            sample_assay_id, gene, tier, is_artifact, interpretation,
            actor_username=user["username"],
            actor_user_id=user["user_id"],
            actor_role=user["role"],
            note=note,
            bypass_justification=bypass_justification,
        )
    except ReviewError as e:
        error = str(e)

    cnvs = SampleService.get_cnvs(sample_assay_id)
    return render_template(
        "partials/cnv_table.html", cnvs=cnvs,
        sample_assay_id=sample_assay_id, review_error=error,
    )


# ----------------------------
# SV partials (Task 7)
# ----------------------------

@web_bp.route("/partials/sample-assays/<sample_assay_id>/svs")
@require_login
def svs_partial(sample_assay_id):
    svs = SampleService.get_svs(sample_assay_id)
    return render_template("partials/sv_table.html", svs=svs, sample_assay_id=sample_assay_id)


@web_bp.route("/partials/sample-assays/<sample_assay_id>/svs/<sv_id>/detail")
@require_login
def sv_detail_partial(sample_assay_id, sv_id):
    sv = SampleService.get_sv(sample_assay_id, sv_id)
    if not sv:
        return "<td colspan='6'>SV not found</td>", 404
    return render_template("partials/sv_detail_form.html", sv=sv)


@web_bp.route("/partials/sample-assays/<sample_assay_id>/svs/<sv_id>/review", methods=["POST"])
@require_login
def sv_review_submit(sample_assay_id, sv_id):
    tier = request.form.get("tier") or None
    is_artifact = request.form.get("is_artifact") == "true"
    interpretation = request.form.get("interpretation", "")
    note = request.form.get("note", "")
    bypass_justification = request.form.get("bypass_justification", "")

    user = current_user()
    error = None
    try:
        SampleService.update_sv_review(
            sample_assay_id, sv_id, tier, is_artifact, interpretation,
            actor_username=user["username"],
            actor_user_id=user["user_id"],
            actor_role=user["role"],
            note=note,
            bypass_justification=bypass_justification,
        )
    except ReviewError as e:
        error = str(e)

    svs = SampleService.get_svs(sample_assay_id)
    return render_template(
        "partials/sv_table.html", svs=svs,
        sample_assay_id=sample_assay_id, review_error=error,
    )


# ----------------------------
# Biomarker partial (Task 8)
# ----------------------------

@web_bp.route("/partials/sample-assays/<sample_assay_id>/biomarkers")
@require_login
def biomarkers_partial(sample_assay_id):
    biomarker = BiomarkerService.get_biomarkers(sample_assay_id)
    return render_template(
        "partials/biomarker_card.html",
        biomarker=biomarker,
        sample_assay_id=sample_assay_id,
    )


@web_bp.route("/partials/sample-assays/<sample_assay_id>/biomarkers/confirm", methods=["POST"])
@require_login
def biomarker_confirm_submit(sample_assay_id):
    reviewer_note = request.form.get("reviewer_note", "")
    discordance_acknowledged = request.form.get("discordance_acknowledged") == "true"
    user = current_user()
    error = None

    try:
        BiomarkerService.confirm(
            sample_assay_id,
            reviewer_note=reviewer_note,
            discordance_acknowledged=discordance_acknowledged,
            actor_username=user["username"],
            actor_user_id=user["user_id"],
            actor_role=user["role"],
        )
    except BiomarkerError as e:
        error = str(e)

    biomarker = BiomarkerService.get_biomarkers(sample_assay_id)
    return render_template(
        "partials/biomarker_card.html",
        biomarker=biomarker,
        sample_assay_id=sample_assay_id,
        confirm_error=error,
    )


# ----------------------------
# Preflight partial (Task 5)
# ----------------------------

@web_bp.route("/partials/sample-assays/<sample_assay_id>/preflight")
@require_login
def preflight_partial(sample_assay_id):
    checks = PreflightService.run_checks(sample_assay_id)
    all_passed = PreflightService.all_passed(checks)
    return render_template(
        "partials/preflight_panel.html",
        checks=checks,
        all_passed=all_passed,
        sample_assay_id=sample_assay_id,
    )


# ----------------------------
# Report partials (Phase 6)
# ----------------------------

@web_bp.route("/partials/sample-assays/<sample_assay_id>/report")
@require_login
def report_partial(sample_assay_id):
    report = ReportService.get_active_report(sample_assay_id)
    user = current_user()
    return render_template(
        "partials/report_panel.html",
        report=report,
        sample_assay_id=sample_assay_id,
        user=user,
    )


@web_bp.route("/partials/sample-assays/<sample_assay_id>/reports/create", methods=["POST"])
@require_login
def report_create(sample_assay_id):
    user = current_user()
    error = None
    try:
        ReportService.create_draft(
            sample_assay_id,
            created_by_user_id=user["user_id"],
            created_by_username=user["username"],
        )
    except ReportError as e:
        error = str(e)

    report = ReportService.get_active_report(sample_assay_id)
    return render_template(
        "partials/report_panel.html",
        report=report,
        sample_assay_id=sample_assay_id,
        user=user,
        error=error,
    )


@web_bp.route("/partials/reports/<report_id>/sign-off", methods=["POST"])
@require_login
def report_signoff(report_id):
    user = current_user()
    error = None
    sample_assay_id = request.form.get("sample_assay_id", "")
    try:
        ReportService.add_signoff(
            report_id,
            actor_user_id=user["user_id"],
            actor_username=user["username"],
            actor_role=user["role"],
        )
    except ReportError as e:
        error = str(e)

    report = ReportService.get_active_report(sample_assay_id)
    return render_template(
        "partials/report_panel.html",
        report=report,
        sample_assay_id=sample_assay_id,
        user=user,
        error=error,
    )


@web_bp.route("/partials/reports/<report_id>/finalise", methods=["POST"])
@require_login
def report_finalise(report_id):
    user = current_user()
    error = None
    sample_assay_id = request.form.get("sample_assay_id", "")
    try:
        ReportService.finalise(
            report_id,
            actor_user_id=user["user_id"],
            actor_username=user["username"],
            actor_role=user["role"],
        )
    except ReportError as e:
        error = str(e)

    report = ReportService.get_active_report(sample_assay_id)
    return render_template(
        "partials/report_panel.html",
        report=report,
        sample_assay_id=sample_assay_id,
        user=user,
        error=error,
    )


# ----------------------------
# Knowledge Database (Phase 5)
# ----------------------------

@web_bp.route("/knowledge")
@require_login
def knowledge_page():
    return render_template("knowledge.html")


@web_bp.route("/partials/knowledge")
@require_login
def knowledge_list_partial():
    gene = request.args.get("gene", "").strip()
    variant_type = request.args.get("variant_type", "")
    tier = request.args.get("tier", "")
    disease_group = request.args.get("disease_group", "")
    q = request.args.get("q", "").strip()

    search_error = None
    if q:
        try:
            entries = KnowledgeService.search(
                q, filters={"gene": gene, "tier": tier, "disease_group": disease_group}
            )
        except KnowledgeError as e:
            entries = []
            search_error = str(e)
    else:
        entries = KnowledgeService.list_entries(
            gene=gene, variant_type=variant_type, tier=tier, disease_group=disease_group
        )

    return render_template(
        "partials/knowledge_list.html",
        entries=entries,
        search_error=search_error,
    )


@web_bp.route("/partials/knowledge/create", methods=["GET"])
@require_login
def knowledge_create_form():
    user = current_user()
    return render_template("partials/knowledge_form.html", entry=None, user=user)


@web_bp.route("/partials/knowledge/create", methods=["POST"])
@require_login
def knowledge_create_submit():
    user = current_user()
    error = None
    entry = None

    data = {
        "variant_type": request.form.get("variant_type"),
        "gene": request.form.get("gene", "").strip() or None,
        "hgvsp": request.form.get("hgvsp", "").strip() or None,
        "hgvsc": request.form.get("hgvsc", "").strip() or None,
        "consequence": request.form.get("consequence", "").strip() or None,
        "event_type": request.form.get("event_type", "").strip() or None,
        "gene_5prime": request.form.get("gene_5prime", "").strip() or None,
        "gene_3prime": request.form.get("gene_3prime", "").strip() or None,
        "disease_group": request.form.get("disease_group"),
        "disease_subtype": request.form.get("disease_subtype", "").strip() or None,
        "tier": request.form.get("tier"),
        "interpretation": request.form.get("interpretation", ""),
        "evidence_summary": request.form.get("evidence_summary", ""),
        "evidence_tags": [
            t.strip() for t in request.form.get("evidence_tags", "").split(",") if t.strip()
        ],
    }

    if user["role"] not in ("senior_reviewer", "lab_director"):
        error = "Only senior reviewers and lab directors can create knowledge entries."
    else:
        try:
            entry = KnowledgeService.create_entry(data, user["user_id"], user["username"])
        except KnowledgeError as e:
            error = str(e)

    if entry and not error:
        return render_template("partials/knowledge_entry.html", entry=entry, user=user)
    return render_template("partials/knowledge_form.html", entry=None, user=user, error=error, prefill=data)


@web_bp.route("/partials/knowledge/<knowledge_id>")
@require_login
def knowledge_entry_partial(knowledge_id):
    entry = KnowledgeService.get_entry(knowledge_id)
    if not entry:
        return "<p class='text-red-600'>Knowledge entry not found.</p>", 404
    user = current_user()
    return render_template("partials/knowledge_entry.html", entry=entry, user=user)


@web_bp.route("/partials/knowledge/<knowledge_id>/edit", methods=["GET"])
@require_login
def knowledge_edit_form(knowledge_id):
    entry = KnowledgeService.get_entry(knowledge_id)
    if not entry:
        return "<p class='text-red-600'>Knowledge entry not found.</p>", 404
    user = current_user()
    return render_template("partials/knowledge_form.html", entry=entry, user=user)


@web_bp.route("/partials/knowledge/<knowledge_id>/edit", methods=["POST"])
@require_login
def knowledge_edit_submit(knowledge_id):
    user = current_user()
    error = None

    data = {
        "tier": request.form.get("tier"),
        "interpretation": request.form.get("interpretation", ""),
        "evidence_summary": request.form.get("evidence_summary", ""),
        "evidence_tags": [
            t.strip() for t in request.form.get("evidence_tags", "").split(",") if t.strip()
        ],
        "disease_subtype": request.form.get("disease_subtype", "").strip() or None,
        "harmonisation_note": request.form.get("harmonisation_note", ""),
    }
    change_note = request.form.get("change_note", "").strip()

    if user["role"] not in ("senior_reviewer", "lab_director"):
        error = "Only senior reviewers and lab directors can edit knowledge entries."
        entry = KnowledgeService.get_entry(knowledge_id)
    else:
        try:
            entry = KnowledgeService.update_entry(
                knowledge_id, data, user["user_id"], user["username"], change_note=change_note
            )
        except KnowledgeError as e:
            error = str(e)
            entry = KnowledgeService.get_entry(knowledge_id)

    return render_template("partials/knowledge_entry.html", entry=entry, user=user, error=error)


# ----------------------------
# Lab Director Dashboard — TAT & SLA (Phase 7)
# ----------------------------

@web_bp.route("/lab-dashboard")
@require_role("lab_director", "senior_reviewer")
def lab_dashboard():
    return render_template("lab_dashboard.html")


@web_bp.route("/partials/lab-dashboard/stats")
@require_role("lab_director", "senior_reviewer")
def lab_dashboard_stats():
    stats = TATService.dashboard_stats()
    return render_template("partials/lab_stats.html", stats=stats)


# ----------------------------
# Assay Gap Analysis (Phase 7)
# ----------------------------

@web_bp.route("/gap-analysis")
@require_role("lab_director")
def gap_analysis_page():
    assay_versions = GapAnalysisService.list_assay_versions()
    return render_template("gap_analysis.html", assay_versions=assay_versions)


@web_bp.route("/partials/gap-analysis")
@require_role("lab_director")
def gap_analysis_partial():
    gene = request.args.get("gene", "").strip()
    assay_id = request.args.get("assay_id", "").strip()
    result = None
    if gene:
        result = GapAnalysisService.query_gene_coverage(gene, assay_id or None)
    return render_template("partials/gap_analysis_result.html", result=result, gene=gene)


# ----------------------------
# Cohort Query Interface (Phase 7)
# ----------------------------

@web_bp.route("/cohort")
@require_login
def cohort_page():
    assay_versions = GapAnalysisService.list_assay_versions()
    return render_template("cohort.html", assay_versions=assay_versions)


@web_bp.route("/partials/cohort/query")
@require_login
def cohort_query_partial():
    gene = request.args.get("gene", "").strip()
    tier = request.args.get("tier", "")
    variant_type = request.args.get("variant_type", "")
    assay_id = request.args.get("assay_id", "")
    acknowledge = request.args.get("acknowledge") == "1"

    result = None
    if gene or tier or variant_type:
        result = CohortService.query(
            gene=gene, tier=tier, variant_type=variant_type,
            assay_id=assay_id, acknowledge_multi_version=acknowledge,
        )
    return render_template("partials/cohort_result.html", result=result,
                           gene=gene, tier=tier, variant_type=variant_type,
                           assay_id=assay_id)


# ----------------------------
# Physician Portal Token Management (Phase 7)
# ----------------------------

@web_bp.route("/partials/reports/<report_id>/portal-tokens")
@require_role("lab_director", "senior_reviewer")
def portal_tokens_partial(report_id):
    tokens = PortalService.get_tokens_for_report(report_id)
    return render_template("partials/portal_tokens.html", report_id=report_id, tokens=tokens)


@web_bp.route("/partials/reports/<report_id>/portal-tokens/issue", methods=["POST"])
@require_role("lab_director", "senior_reviewer")
def portal_token_issue(report_id):
    user = current_user()
    error = None
    token_doc = None
    try:
        token_doc = PortalService.issue_token(report_id, user["user_id"], user["username"])
    except PortalError as e:
        error = str(e)
    tokens = PortalService.get_tokens_for_report(report_id)
    return render_template("partials/portal_tokens.html",
                           report_id=report_id, tokens=tokens,
                           new_token=token_doc, error=error)


# ----------------------------
# Federated Knowledge (Phase 7)
# ----------------------------

@web_bp.route("/federation")
@require_role("lab_director")
def federation_page():
    exports = FederationService.list_exports()
    eligible = FederationService.eligible_entries()
    return render_template("federation.html", exports=exports, eligible_count=len(eligible))


@web_bp.route("/partials/federation/export", methods=["POST"])
@require_role("lab_director")
def federation_export():
    user = current_user()
    lab_id = request.form.get("lab_id", "").strip()
    error = None
    export = None
    if not lab_id:
        error = "Lab ID is required."
    else:
        try:
            export = FederationService.build_export(lab_id, user["user_id"], user["username"])
        except FederationError as e:
            error = str(e)
    exports = FederationService.list_exports()
    eligible = FederationService.eligible_entries()
    return render_template("partials/federation_panel.html",
                           exports=exports, eligible_count=len(eligible),
                           export=export, error=error)


# ----------------------------
# Callsets (Phase 4)
# ----------------------------

@web_bp.route("/partials/sample-assays/<sample_assay_id>/callsets")
@require_login
def callsets_partial(sample_assay_id):
    callsets = IngestionService.get_callsets(sample_assay_id)
    return render_template(
        "partials/callsets_panel.html",
        callsets=callsets,
        sample_assay_id=sample_assay_id,
    )
