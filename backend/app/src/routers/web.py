from urllib.parse import urlparse

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.config import settings
from src.services.users import UserService

router = APIRouter()
templates = Jinja2Templates(directory="src/templates/web")


def _get_spa_base_url(request: Request) -> str:
    if settings.SPA_BASE_URL:
        parsed = urlparse(settings.SPA_BASE_URL)
        return f"{parsed.scheme}://{parsed.netloc}"
    host = request.url.hostname or ""
    return f"http://{host}:8080"


def _render(request: Request, template_name: str, **context):
    return templates.TemplateResponse(
        template_name,
        {
            "request": request,
            "session": request.state.session,
            "spa_base_url": _get_spa_base_url(request),
            **context,
        },
    )


# ------------------------
# Home
# ------------------------
@router.get("/", response_class=HTMLResponse)
def landing(request: Request):
    return _render(request, "landing.html")


# ------------------------
# About
# ------------------------
@router.get("/about", response_class=HTMLResponse)
def about(request: Request):
    return _render(request, "about.html")


# ------------------------
# Login
# ------------------------
@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return _render(request, "login.html")


@router.post("/login")
def login_submit(request: Request, username: str = Form(""), password: str = Form("")):
    username = username.strip()
    user = UserService.authenticate(username, password)
    if user:
        request.state.session["user"] = user
        return RedirectResponse(url="/", status_code=303)

    return _render(request, "login.html", error="Invalid credentials")


# ------------------------
# Logout
# ------------------------
@router.post("/logout")
def logout(request: Request):
    request.state.session.pop("user", None)
    return RedirectResponse(url="/", status_code=303)
