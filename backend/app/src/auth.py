from fastapi import HTTPException, Request

from src.session import Session


def get_session(request: Request) -> Session:
    return request.state.session


def current_user(request: Request) -> dict | None:
    """Return the current session user dict, or None."""
    return request.state.session.get("user")


def current_username(request: Request) -> str:
    """Return username string for audit logging, falls back to 'unknown'."""
    user = current_user(request)
    return user["username"] if user else "unknown"


def require_login(request: Request) -> dict:
    """FastAPI dependency: 401 if no active session."""
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorised")
    return user


def require_role(*roles: str):
    """FastAPI dependency factory: 401 if no session, 403 if role not in roles."""

    def dependency(request: Request) -> dict:
        user = current_user(request)
        if not user:
            raise HTTPException(status_code=401, detail="Unauthorised")
        if user.get("role") not in roles:
            raise HTTPException(status_code=403, detail="Forbidden")
        return user

    return dependency
