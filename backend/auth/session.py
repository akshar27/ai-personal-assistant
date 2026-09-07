"""Signed session cookie carrying just the user id.

itsdangerous signs it with SESSION_SECRET; a tampered or stale cookie fails
verification and is treated as logged-out.
"""

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from config import settings

COOKIE_NAME = "assistant_session"
MAX_AGE_SECONDS = 60 * 60 * 24 * 30  # 30 days

_serializer = URLSafeTimedSerializer(settings.session_secret, salt="assistant-session")


def issue(user_id: str) -> str:
    return _serializer.dumps({"uid": user_id})


def read(token: str | None) -> str | None:
    if not token:
        return None
    try:
        data = _serializer.loads(token, max_age=MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    return data.get("uid")
