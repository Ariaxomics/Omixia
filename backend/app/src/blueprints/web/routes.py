from flask import Blueprint, render_template, redirect, url_for, request, session

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
        username = request.form.get("username")
        password = request.form.get("password")

        # VERY BASIC DEMO LOGIN
        if username == "geneticist" and password == "omixia":
            session["user"] = username
            return redirect(url_for("web.dashboard"))

        return render_template("login.html", error="Invalid credentials")

    return render_template("login.html")


# ------------------------
# Dashboard
# ------------------------
@web_bp.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("web.login"))

    return render_template("dashboard.html", user=session["user"])