"""The current user id for this request / graph run.

The graph and the Gmail/Calendar integrations run synchronously inside a request,
so a ContextVar lets `google_auth.load_tokens()` find the right user's
credentials without threading `user_id` through every tool call.
"""

from contextlib import contextmanager
from contextvars import ContextVar

_current_user_id: ContextVar[str | None] = ContextVar("current_user_id", default=None)


def get_current_user_id() -> str | None:
    return _current_user_id.get()


def set_current_user_id(user_id: str | None) -> None:
    _current_user_id.set(user_id)


@contextmanager
def user_scope(user_id: str | None):
    token = _current_user_id.set(user_id)
    try:
        yield
    finally:
        _current_user_id.reset(token)
