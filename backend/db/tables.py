"""Core table definitions (SQLAlchemy Core, no ORM).

Relational data only — email-history vectors live in the retrieval store, which
owns its own schema (SQLite blob table or a pgvector table).
"""

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    func,
)

metadata = MetaData()

users = Table(
    "users",
    metadata,
    # Google "sub" for real users, "guest:<uuid>" for anonymous sessions.
    Column("id", String(128), primary_key=True),
    Column("email", String(320)),
    Column("name", String(256)),
    Column("is_guest", Boolean, nullable=False, default=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
    Column("last_seen_at", DateTime(timezone=True), server_default=func.now()),
)

preferences = Table(
    "preferences",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String(128), nullable=False, index=True),
    Column("key", String(128), nullable=False),
    Column("value", Text, nullable=False),
)

tasks = Table(
    "tasks",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String(128), nullable=False, index=True),
    Column("title", Text, nullable=False),
    Column("due_at", String(32)),
    Column("status", String(16), nullable=False, default="open"),
    Column("source", String(32), default="manual"),
    Column("task_metadata", JSON, default=dict),
    Column("created_at", String(32), nullable=False),
)

google_tokens = Table(
    "google_tokens",
    metadata,
    Column("user_id", String(128), primary_key=True),
    Column("token_encrypted", Text, nullable=False),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
)


def create_all() -> None:
    from db.engine import get_engine

    metadata.create_all(get_engine())
