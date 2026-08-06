"""
Ordering Physician Portal (spec section 15).

Separate auth flow using token-based access links per report.
Read-only access to the physician's own patients' finalised reports.
No internal workflow, knowledge database, or other case visibility.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.extensions import mongo_client
from src.services.portal import PortalService

router = APIRouter(prefix="/portal")
templates = Jinja2Templates(directory="src/templates/portal")

PORTAL_SESSION_KEY = "portal_token"


def _render(request: Request, template_name: str, **context):
    return templates.TemplateResponse(template_name, {"request": request, **context})


def _portal_report(request: Request):
    """Return the report for the current portal session, or None."""
    token = request.state.session.get(PORTAL_SESSION_KEY)
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


@router.get("/", response_class=HTMLResponse)
def portal_index(request: Request):
    return _render(request, "login.html")


@router.get("/access/{token}")
def portal_access(token: str, request: Request):
    """Direct access link sent to physician. Validates token and establishes portal session."""
    token_doc = PortalService.validate_token(token)
    if not token_doc:
        return _render(request, "login.html", error="This link is invalid or has expired.")

    request.state.session[PORTAL_SESSION_KEY] = token
    return RedirectResponse(url="/portal/report", status_code=303)


@router.get("/report", response_class=HTMLResponse)
def portal_report(request: Request):
    token_doc, report = _portal_report(request)
    if not report:
        return _render(request, "login.html", error="Session expired. Please use your access link.")

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

    return _render(
        request,
        "report.html",
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


@router.post("/logout")
def portal_logout(request: Request):
    request.state.session.pop(PORTAL_SESSION_KEY, None)
    return RedirectResponse(url="/portal/", status_code=303)
