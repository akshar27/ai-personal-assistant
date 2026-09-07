"""SQLAlchemy engine, built lazily from `settings.database_url`.

Lazy + resettable so tests can point it at a throwaway SQLite file per test
(see tests/conftest.py) without any import-order gymnastics.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url

from config import settings

_engine: Engine | None = None


def _normalized_url(raw: str) -> str:
    """Force the psycopg (v3) driver for Postgres URLs; leave SQLite alone."""
    url = make_url(raw)
    if url.drivername in ("postgres", "postgresql"):
        url = url.set(drivername="postgresql+psycopg")
    return url.render_as_string(hide_password=False)


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        url = _normalized_url(settings.database_url)
        kwargs: dict = {"pool_pre_ping": True, "future": True}
        if url.startswith("sqlite"):
            # allow the connection to cross threads (uvicorn workers, tests)
            kwargs["connect_args"] = {"check_same_thread": False}
        _engine = create_engine(url, **kwargs)
    return _engine


def reset_engine() -> None:
    """Dispose and drop the cached engine (tests, or a config change)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None
