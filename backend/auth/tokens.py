"""Per-user Google credentials, encrypted at rest (Fernet) in `google_tokens`."""

import json
import logging

from cryptography.fernet import Fernet
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from sqlalchemy import insert, select, update

from config import settings
from db.engine import get_engine
from db.tables import google_tokens
from integrations.google_auth import SCOPES

logger = logging.getLogger("ai_assistant.auth.tokens")


def _fernet() -> Fernet:
    key = settings.token_encryption_key
    if not key:
        raise RuntimeError(
            "TOKEN_ENCRYPTION_KEY is not set. Generate one with "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def save_user_tokens(user_id: str, creds: Credentials) -> None:
    blob = _fernet().encrypt(creds.to_json().encode()).decode()
    with get_engine().begin() as conn:
        exists = conn.execute(
            select(google_tokens.c.user_id).where(google_tokens.c.user_id == user_id)
        ).first()
        if exists:
            conn.execute(
                update(google_tokens)
                .where(google_tokens.c.user_id == user_id)
                .values(token_encrypted=blob)
            )
        else:
            conn.execute(insert(google_tokens).values(user_id=user_id, token_encrypted=blob))


def load_user_creds(user_id: str) -> Credentials | None:
    with get_engine().connect() as conn:
        row = conn.execute(
            select(google_tokens.c.token_encrypted).where(google_tokens.c.user_id == user_id)
        ).first()
    if not row:
        return None

    try:
        data = json.loads(_fernet().decrypt(row.token_encrypted.encode()).decode())
    except Exception:
        logger.exception("could not decrypt stored Google tokens for user=%s", user_id)
        return None

    creds = Credentials.from_authorized_user_info(data, SCOPES)
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(GoogleAuthRequest())
            save_user_tokens(user_id, creds)
            logger.info("refreshed Google access token for user=%s", user_id)
        except Exception:
            logger.exception("failed to refresh Google token for user=%s", user_id)
            return None
    return creds


def delete_user_tokens(user_id: str) -> None:
    from sqlalchemy import delete

    with get_engine().begin() as conn:
        conn.execute(delete(google_tokens).where(google_tokens.c.user_id == user_id))
