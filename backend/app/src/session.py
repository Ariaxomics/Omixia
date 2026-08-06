import json
import secrets

from itsdangerous import BadSignature, URLSafeSerializer
from starlette.requests import Request
from starlette.responses import Response

from src.config import settings
from src.extensions import redis_client

SESSION_TTL_SECONDS = 60 * 60 * 24 * 7
REDIS_KEY_PREFIX = "omixia:session:"

_serializer = URLSafeSerializer(settings.SECRET_KEY, salt="omixia-session")


class Session(dict):
    """Dict-backed session that writes through to Redis on every mutation."""

    def __init__(self, session_id: str, data: dict):
        super().__init__(data)
        self._session_id = session_id

    def _persist(self) -> None:
        redis_client.r.set(
            REDIS_KEY_PREFIX + self._session_id,
            json.dumps(dict(self)),
            ex=SESSION_TTL_SECONDS,
        )

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self._persist()

    def pop(self, key, *args):
        result = super().pop(key, *args)
        self._persist()
        return result

    def clear(self):
        super().clear()
        redis_client.r.delete(REDIS_KEY_PREFIX + self._session_id)


def _new_session_id() -> str:
    return secrets.token_urlsafe(32)


def load_session(request: Request) -> Session:
    """Read the session cookie, validate its signature, and load session data from Redis."""
    cookie = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if cookie:
        try:
            session_id = _serializer.loads(cookie)
        except BadSignature:
            session_id = None
        if session_id:
            raw = redis_client.r.get(REDIS_KEY_PREFIX + session_id)
            if raw is not None:
                return Session(session_id, json.loads(raw))

    return Session(_new_session_id(), {})


def set_session_cookie(response: Response, session: Session) -> None:
    """Sign the session id and attach it as a cookie on the response."""
    signed = _serializer.dumps(session._session_id)
    response.set_cookie(
        settings.SESSION_COOKIE_NAME,
        signed,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite=settings.SESSION_COOKIE_SAMESITE.lower(),
        secure=settings.SESSION_COOKIE_SECURE,
    )
