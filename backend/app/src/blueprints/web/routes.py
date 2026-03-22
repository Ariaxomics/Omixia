from urllib.parse import urlparse

from flask import Blueprint, render_template, redirect, url_for, request, session, current_app

from src.services.users import UserService


web_bp = Blueprint(
    "web",
    __name__,
    template_folder="templates"
)


def _get_spa_base_url() -> str:
    spa_base_url = current_app.config.get("SPA_BASE_URL") or ""
    if spa_base_url:
        parsed = urlparse(spa_base_url)
        return f"{parsed.scheme}://{parsed.netloc}"
    host = request.host.split(":")[0]
    return f"http://{host}:8080"


@web_bp.context_processor
def inject_spa_base_url():
    return {"spa_base_url": _get_spa_base_url()}


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
            return redirect(url_for("web.landing"))

        return render_template("login.html", error="Invalid credentials")

    return render_template("login.html")


# ------------------------
# Logout
# ------------------------
@web_bp.route("/logout", methods=["POST"])
def logout():
    session.pop("user", None)
    return redirect(url_for("web.landing"))
