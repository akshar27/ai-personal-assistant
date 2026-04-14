import json
from pathlib import Path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from config import settings

SCOPES = [
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


def save_tokens(creds: Credentials) -> None:
    token_path = Path(settings.tokens_file)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json())


def load_tokens() -> Credentials | None:
    token_path = Path(settings.tokens_file)
    if not token_path.exists():
        return None

    data = token_path.read_text()
    return Credentials.from_authorized_user_info(json.loads(data), SCOPES)