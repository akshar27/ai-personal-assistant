import sqlite3
import json
from datetime import datetime
from config import settings


def get_connection():
    conn = sqlite3.connect(settings.memory_db_file)
    conn.row_factory = sqlite3.Row
    return conn


def init_memory():
    conn = get_connection()
    cur = conn.cursor()

    # Preferences table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL
        )
    """)

    # Tasks table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            due_at TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            source TEXT DEFAULT 'manual',
            metadata TEXT,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


# =========================
# Preferences
# =========================

def save_preference(user_id: str, key: str, value: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO preferences (user_id, key, value) VALUES (?, ?, ?)",
        (user_id, key, value),
    )

    conn.commit()
    conn.close()


def get_preferences(user_id: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT key, value
        FROM preferences
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (user_id,),
    )

    rows = cur.fetchall()
    conn.close()

    return [{"key": row["key"], "value": row["value"]} for row in rows]


def get_latest_preference_value(user_id: str, key: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT value
        FROM preferences
        WHERE user_id = ? AND key = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (user_id, key),
    )

    row = cur.fetchone()
    conn.close()

    return row["value"] if row else None


# =========================
# Tasks
# =========================

def create_task(
    user_id: str,
    title: str,
    due_at: str = None,
    source: str = "manual",
    metadata: dict = None,
):
    conn = get_connection()
    cur = conn.cursor()

    created_at = datetime.utcnow().isoformat()
    metadata_json = json.dumps(metadata or {})

    cur.execute(
        """
        INSERT INTO tasks (
            user_id,
            title,
            due_at,
            status,
            source,
            metadata,
            created_at
        )
        VALUES (?, ?, ?, 'open', ?, ?, ?)
        """,
        (
            user_id,
            title,
            due_at,
            source,
            metadata_json,
            created_at,
        ),
    )

    task_id = cur.lastrowid

    conn.commit()
    conn.close()

    return task_id


def get_open_tasks(user_id: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT *
        FROM tasks
        WHERE user_id = ?
          AND status = 'open'
        ORDER BY
          CASE WHEN due_at IS NULL THEN 1 ELSE 0 END,
          due_at ASC,
          id DESC
        """,
        (user_id,),
    )

    rows = cur.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_due_tasks(user_id: str):
    conn = get_connection()
    cur = conn.cursor()

    now = datetime.utcnow().isoformat()

    cur.execute(
        """
        SELECT *
        FROM tasks
        WHERE user_id = ?
          AND status = 'open'
          AND due_at IS NOT NULL
          AND due_at <= ?
        ORDER BY due_at ASC
        """,
        (user_id, now),
    )

    rows = cur.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def mark_task_done(user_id: str, task_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE tasks
        SET status = 'done'
        WHERE user_id = ?
          AND id = ?
        """,
        (user_id, task_id),
    )

    updated = cur.rowcount

    conn.commit()
    conn.close()

    return updated > 0


def get_task_by_id(user_id: str, task_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT *
        FROM tasks
        WHERE user_id = ?
          AND id = ?
        """,
        (user_id, task_id),
    )

    row = cur.fetchone()
    conn.close()

    return dict(row) if row else None