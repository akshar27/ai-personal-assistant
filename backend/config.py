import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
STORAGE_DIR.mkdir(exist_ok=True)

# Load backend/.env if present. Real environment variables still win.
load_dotenv(BASE_DIR / ".env")


class Settings(BaseModel):
    app_name: str = "AI Personal Assistant"
    app_env: str = os.getenv("APP_ENV", "development")

    # Signs the OAuth session cookie. MUST be set in any non-dev environment.
    session_secret: str = os.getenv("SESSION_SECRET", "dev-only-insecure-session-secret")

    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

    llm_provider: str = os.getenv("LLM_PROVIDER", "openai_first")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.1")
    ollama_embedding_model: str = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")

    # Escalate borderline prompt-injection checks to the LLM (off by default:
    # heuristics are deterministic and free).
    injection_llm_check: bool = os.getenv("INJECTION_LLM_CHECK", "").lower() in {"1", "true", "yes"}

    # Retrieval over email history.
    history_index_db_file: str = str(STORAGE_DIR / "history_index.db")
    history_ingest_max_messages: int = int(os.getenv("HISTORY_INGEST_MAX_MESSAGES", "200"))
    history_ingest_query: str = os.getenv("HISTORY_INGEST_QUERY", "newer_than:180d")

    langsmith_tracing: str | None = os.getenv("LANGSMITH_TRACING")
    langsmith_api_key: str | None = os.getenv("LANGSMITH_API_KEY")
    langsmith_project: str | None = os.getenv("LANGSMITH_PROJECT", "ai-personal-assistant")

    google_client_secrets_file: str = os.getenv(
        "GOOGLE_CLIENT_SECRETS_FILE",
        str(BASE_DIR / "client_secret.json"),
    )
    google_client_secret_json: str | None = os.getenv("GOOGLE_CLIENT_SECRET_JSON")

    google_redirect_uri: str = os.getenv(
        "GOOGLE_REDIRECT_URI",
        "http://localhost:8000/auth/google/callback",
    )

    frontend_origin: str = os.getenv(
        "FRONTEND_ORIGIN",
        "http://localhost:3000",
    )

    # Relational store (users, preferences, tasks, google tokens). SQLite for
    # local/dev/tests; a postgresql:// URL in production.
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{STORAGE_DIR / 'app.db'}")

    # Encrypts per-user Google tokens at rest. Generate:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    token_encryption_key: str | None = os.getenv("TOKEN_ENCRYPTION_KEY")

    tokens_file: str = str(STORAGE_DIR / "tokens.json")  # legacy single-user fallback
    memory_db_file: str = str(STORAGE_DIR / "memory.db")  # legacy; unused after DB migration

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith(("postgres://", "postgresql://", "postgresql+"))

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}


settings = Settings()

if settings.is_production and settings.session_secret == "dev-only-insecure-session-secret":
    raise RuntimeError("SESSION_SECRET must be set to a strong random value in production.")