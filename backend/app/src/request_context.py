from contextvars import ContextVar, Token

from starlette.requests import Request

_current_request: ContextVar[Request | None] = ContextVar("_current_request", default=None)


def get_current_request() -> Request | None:
    return _current_request.get()


def set_current_request(request: Request) -> Token:
    return _current_request.set(request)


def reset_current_request(token: Token) -> None:
    _current_request.reset(token)
