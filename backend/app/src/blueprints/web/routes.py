from flask import Blueprint, render_template, redirect, url_for, request, session

from src.auth import current_user, current_username, require_login
from src.services.biomarker import BiomarkerError, BiomarkerService
from src.services.preflight import PreflightService
from src.services.report import ReportError, ReportService
from src.services.samples import ReviewError, SampleService
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
    return render_template("partials/snv_detail_form.html", snv=snv)


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
