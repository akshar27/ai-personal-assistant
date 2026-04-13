import sqlite3
from config import settings


def get_connection():
    conn = sqlite3.connect(settings.memory_db_file)
    conn.row_factory = sqlite3.Row
    return conn


def init_memory():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


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
        "SELECT key, value FROM preferences WHERE user_id = ?",
        (user_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [{"key": row["key"], "value": row["value"]} for row in rows]