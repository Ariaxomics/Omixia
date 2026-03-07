"""
Ordering Physician Portal (spec section 15).

Separate auth flow using token-based access links per report.
Read-only access to the physician's own patients' finalised reports.
No internal workflow, knowledge database, or other case visibility.
"""

from flask import Blueprint, render_template, redirect, url_for, request, session, abort

from src.extensions import mongo_client
from src.services.portal import PortalService

portal_bp = Blueprint(
    "portal",
    __name__,
    template_folder="templates",
    url_prefix="/portal",
)

PORTAL_SESSION_KEY = "portal_token"


def _portal_report():
    """Return the report for the current portal session, or None."""
    token = session.get(PORTAL_SESSION_KEY)
    if not token:
        return None, None
    token_doc = PortalService.validate_token(token)
    if not token_doc:
        return None, None

    db = mongo_client.db
    report = db.reports.find_one(
        {"report_id": token_doc["report_id"]}, {"_id": 0}
    )
    return token_doc, report


@portal_bp.route("/")
def portal_index():
    return render_template("portal/login.html")


@portal_bp.route("/access/<token>")
def portal_access(token):
    """Direct access link sent to physician. Validates token and establishes portal session."""
    token_doc = PortalService.validate_token(token)
    if not token_doc:
        return render_template("portal/login.html", error="This link is invalid or has expired.")

    session[PORTAL_SESSION_KEY] = token
    return redirect(url_for("portal.portal_report"))


@portal_bp.route("/report")
def portal_report():
    token_doc, report = _portal_report()
    if not report:
        return render_template("portal/login.html", error="Session expired. Please use your access link.")

    db = mongo_client.db
    snapshot = report.get("snapshot", {})
    sample = snapshot.get("sample", {})
    assay = snapshot.get("assay", {})
    callset_qc = snapshot.get("callset_qc", {})
    biomarkers = snapshot.get("biomarkers", {})

    # Only include reportable (concordant/resolved, non-artifact) variants
    def reportable(variants):
        return [
            v for v in variants
            if not (v.get("review_current") or {}).get("is_artifact")
            and (v.get("review_current") or {}).get("consensus_status") in ("concordant", "resolved")
        ]

    snvs = reportable(snapshot.get("snvs", []))
    cnvs = reportable(snapshot.get("cnvs", []))
    svs = reportable(snapshot.get("svs", []))

    return render_template(
        "portal/report.html",
        report=report,
        sample=sample,
        assay=assay,
        callset_qc=callset_qc,
        biomarkers=biomarkers,
        snvs=snvs,
        cnvs=cnvs,
        svs=svs,
        sign_offs=report.get("sign_offs", []),
    )


@portal_bp.route("/logout", methods=["POST"])
def portal_logout():
    session.pop(PORTAL_SESSION_KEY, None)
    return redirect(url_for("portal.portal_index"))
