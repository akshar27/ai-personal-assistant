import json
import logging
from pathlib import Path

from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from config import settings

logger = logging.getLogger("ai_assistant.google_auth")

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
]


def _get_client_secret_source() -> str:
    if settings.google_client_secret_json:
        path = Path("/tmp/google_client_secret.json")
        path.write_text(settings.google_client_secret_json)
        return str(path)

    return settings.google_client_secrets_file


def create_flow(state: str | None = None) -> Flow:
    return Flow.from_client_secrets_file(
        _get_client_secret_source(),
        scopes=SCOPES,
        redirect_uri=settings.google_redirect_uri,
        state=state,
    )


def client_id() -> str:
    with open(_get_client_secret_source()) as f:
        cfg = json.load(f)
    return (cfg.get("web") or cfg.get("installed"))["client_id"]


def save_tokens(creds: Credentials) -> None:
    """Legacy single-user token file (used when there is no authenticated user)."""
    token_path = Path(settings.tokens_file)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json())


def _load_legacy_file_tokens() -> Credentials | None:
    token_path = Path(settings.tokens_file)
    if not token_path.exists():
        return None

    creds = Credentials.from_authorized_user_info(json.loads(token_path.read_text()), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(GoogleAuthRequest())
            save_tokens(creds)
            logger.info("refreshed legacy Google access token")
        except Exception:
            logger.exception("failed to refresh legacy Google access token")
            return None
    return creds


def load_tokens(user_id: str | None = None) -> Credentials | None:
    """Resolve Google credentials for the current user.

    Order: explicit `user_id` arg → the request-scoped user (ContextVar) → the
    legacy single-user token file. Guests (`guest:*`) have no Google access.
    """
    if user_id is None:
        from auth.context import get_current_user_id

        user_id = get_current_user_id()

    if user_id and not str(user_id).startswith("guest:"):
        from auth.tokens import load_user_creds

        return load_user_creds(user_id)

    return _load_legacy_file_tokens()
