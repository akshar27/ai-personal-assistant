"""Preferences + tasks, on the SQLAlchemy Core engine (`db.engine`).

Public API and return shapes are unchanged from the old raw-sqlite3 version, so
graph nodes and tests didn't have to move.
"""

import json
from datetime import datetime, timezone

from sqlalchemy import and_, insert, select, update

from db.engine import get_engine
from db.tables import preferences, tasks


def _now_utc_iso() -> str:
    """Current UTC time as a naive ISO string (no offset), matching how
    due_at / created_at have always been stored."""
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def init_memory() -> None:
    """Create tables if they don't exist (dev / tests). Production runs Alembic."""
    from db.tables import create_all

    create_all()


# =========================
# Preferences
# =========================

def save_preference(user_id: str, key: str, value: str) -> None:
    with get_engine().begin() as conn:
        conn.execute(insert(preferences).values(user_id=user_id, key=key, value=value))


def get_preferences(user_id: str):
    stmt = (
        select(preferences.c.key, preferences.c.value)
        .where(preferences.c.user_id == user_id)
        .order_by(preferences.c.id.desc())
    )
    with get_engine().connect() as conn:
        return [{"key": r.key, "value": r.value} for r in conn.execute(stmt)]


def get_latest_preference_value(user_id: str, key: str):
    stmt = (
        select(preferences.c.value)
        .where(and_(preferences.c.user_id == user_id, preferences.c.key == key))
        .order_by(preferences.c.id.desc())
        .limit(1)
    )
    with get_engine().connect() as conn:
        row = conn.execute(stmt).first()
    return row.value if row else None


# =========================
# Tasks
# =========================

def _task_row_to_dict(row) -> dict:
    d = dict(row._mapping)
    # keep the historical key name
    d["metadata"] = d.pop("task_metadata", None) or {}
    if isinstance(d["metadata"], str):
        try:
            d["metadata"] = json.loads(d["metadata"])
        except ValueError:
            d["metadata"] = {}
    return d


def create_task(
    user_id: str,
    title: str,
    due_at: str = None,
    source: str = "manual",
    metadata: dict = None,
) -> int:
    with get_engine().begin() as conn:
        result = conn.execute(
            insert(tasks).values(
                user_id=user_id,
                title=title,
                due_at=due_at,
                status="open",
                source=source,
                task_metadata=metadata or {},
                created_at=_now_utc_iso(),
            )
        )
    return int(result.inserted_primary_key[0])


def get_open_tasks(user_id: str):
    stmt = (
        select(tasks)
        .where(and_(tasks.c.user_id == user_id, tasks.c.status == "open"))
        .order_by(
            (tasks.c.due_at.is_(None)).asc(),  # nulls last
            tasks.c.due_at.asc(),
            tasks.c.id.desc(),
        )
    )
    with get_engine().connect() as conn:
        return [_task_row_to_dict(r) for r in conn.execute(stmt)]


def get_due_tasks(user_id: str):
    now = _now_utc_iso()
    stmt = (
        select(tasks)
        .where(
            and_(
                tasks.c.user_id == user_id,
                tasks.c.status == "open",
                tasks.c.due_at.is_not(None),
                tasks.c.due_at <= now,
            )
        )
        .order_by(tasks.c.due_at.asc())
    )
    with get_engine().connect() as conn:
        return [_task_row_to_dict(r) for r in conn.execute(stmt)]


def mark_task_done(user_id: str, task_id: int) -> bool:
    with get_engine().begin() as conn:
        result = conn.execute(
            update(tasks)
            .where(and_(tasks.c.user_id == user_id, tasks.c.id == task_id))
            .values(status="done")
        )
    return result.rowcount > 0


def get_task_by_id(user_id: str, task_id: int):
    stmt = select(tasks).where(and_(tasks.c.user_id == user_id, tasks.c.id == task_id))
    with get_engine().connect() as conn:
        row = conn.execute(stmt).first()
    return _task_row_to_dict(row) if row else None
