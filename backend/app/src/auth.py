from functools import wraps

from flask import jsonify, redirect, request, session, url_for


def require_login(f):
    """Redirect to login (web) or return 401 (API) if no active session."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            if request.blueprint == "api":
                return jsonify({"error": "Unauthorised"}), 401
            return redirect(url_for("web.login"))
        return f(*args, **kwargs)
    return decorated


def require_role(*roles: str):
    """Enforce that the logged-in user has one of the given roles.
    Implies require_login — no need to stack both decorators.
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user = session.get("user")
            if not user:
                if request.blueprint == "api":
                    return jsonify({"error": "Unauthorised"}), 401
                return redirect(url_for("web.login"))
            if user.get("role") not in roles:
                if request.blueprint == "api":
                    return jsonify({"error": "Forbidden"}), 403
                return redirect(url_for("web.dashboard"))
            return f(*args, **kwargs)
        return decorated
    return decorator


def current_user() -> dict | None:
    """Return the current session user dict, or None."""
    return session.get("user")


def current_username() -> str:
    """Return username string for audit logging, falls back to 'unknown'."""
    user = session.get("user")
    return user["username"] if user else "unknown"
