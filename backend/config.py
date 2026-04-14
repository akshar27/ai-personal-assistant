import os
from pathlib import Path
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
STORAGE_DIR.mkdir(exist_ok=True)


class Settings(BaseModel):
    app_name: str = "AI Personal Assistant"
    app_env: str = os.getenv("APP_ENV", "development")

    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    llm_provider: str = os.getenv("LLM_PROVIDER", "openai_first")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.1")

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

    tokens_file: str = str(STORAGE_DIR / "tokens.json")
    memory_db_file: str = str(STORAGE_DIR / "memory.db")


settings = Settings()