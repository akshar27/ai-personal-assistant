"""Vector store for email-history chunks.

`VectorStore` is the interface the rest of the app codes against.
`SqliteVectorStore` is the v1 implementation: embeddings live as float32 blobs
in SQLite and search is a NumPy cosine scan over one user's rows.

Why a linear scan: a single mailbox indexes to a few thousand chunks; scanning
them is sub-10 ms and needs no index or extra service. When the app goes
multi-tenant this interface gets a `PgVectorStore` (pgvector + HNSW) and nothing
else changes.
"""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np

from config import settings
from retrieval.embeddings import EMBEDDING_DIM


@dataclass
class Chunk:
    user_id: str
    message_id: str
    thread_id: str
    sender: str
    subject: str
    sent_at: str  # ISO string
    chunk_index: int
    text: str
    embedding: list[float] = field(repr=False, default_factory=list)


@dataclass
class SearchHit:
    message_id: str
    thread_id: str
    sender: str
    subject: str
    sent_at: str
    chunk_index: int
    text: str
    score: float


def _to_blob(vec: list[float]) -> bytes:
    return np.asarray(vec, dtype=np.float32).tobytes()


def _from_blob(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


class VectorStore(ABC):
    @abstractmethod
    def init(self) -> None: ...

    @abstractmethod
    def delete_message(self, user_id: str, message_id: str) -> int: ...

    @abstractmethod
    def add_chunks(self, chunks: list[Chunk]) -> int: ...

    @abstractmethod
    def search(self, user_id: str, query_vector: list[float], k: int = 6) -> list[SearchHit]: ...

    @abstractmethod
    def count(self, user_id: str) -> int: ...

    @abstractmethod
    def indexed_message_ids(self, user_id: str) -> set[str]: ...


class SqliteVectorStore(VectorStore):
    def __init__(self, db_file: str | None = None):
        # Resolve lazily per-call instead of caching so tests can point
        # settings at a temp file after construction.
        self._db_file = db_file

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_file or settings.history_index_db_file)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self) -> None:
        conn = self._conn()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS email_chunks (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      TEXT NOT NULL,
                message_id   TEXT NOT NULL,
                thread_id    TEXT,
                sender       TEXT,
                subject      TEXT,
                sent_at      TEXT,
                chunk_index  INTEGER NOT NULL,
                text         TEXT NOT NULL,
                embedding    BLOB NOT NULL,
                indexed_at   TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_email_chunks_user ON email_chunks(user_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_email_chunks_msg ON email_chunks(user_id, message_id)"
        )
        conn.commit()
        conn.close()

    def delete_message(self, user_id: str, message_id: str) -> int:
        conn = self._conn()
        cur = conn.execute(
            "DELETE FROM email_chunks WHERE user_id = ? AND message_id = ?",
            (user_id, message_id),
        )
        n = cur.rowcount
        conn.commit()
        conn.close()
        return n

    def add_chunks(self, chunks: list[Chunk]) -> int:
        if not chunks:
            return 0
        rows = []
        for c in chunks:
            if len(c.embedding) != EMBEDDING_DIM:
                raise ValueError(
                    f"embedding dim {len(c.embedding)} != expected {EMBEDDING_DIM}"
                )
            rows.append(
                (
                    c.user_id, c.message_id, c.thread_id, c.sender, c.subject,
                    c.sent_at, c.chunk_index, c.text, _to_blob(c.embedding),
                )
            )
        conn = self._conn()
        conn.executemany(
            """
            INSERT INTO email_chunks
                (user_id, message_id, thread_id, sender, subject, sent_at,
                 chunk_index, text, embedding)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
        conn.close()
        return len(rows)

    def search(self, user_id: str, query_vector: list[float], k: int = 6) -> list[SearchHit]:
        conn = self._conn()
        rows = conn.execute(
            """
            SELECT message_id, thread_id, sender, subject, sent_at,
                   chunk_index, text, embedding
            FROM email_chunks WHERE user_id = ?
            """,
            (user_id,),
        ).fetchall()
        conn.close()
        if not rows:
            return []

        mat = np.vstack([_from_blob(r["embedding"]) for r in rows])
        q = np.asarray(query_vector, dtype=np.float32)

        mat_norm = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9)
        q_norm = q / (np.linalg.norm(q) + 1e-9)
        scores = mat_norm @ q_norm

        top = np.argsort(scores)[::-1][:k]
        return [
            SearchHit(
                message_id=rows[i]["message_id"],
                thread_id=rows[i]["thread_id"],
                sender=rows[i]["sender"],
                subject=rows[i]["subject"],
                sent_at=rows[i]["sent_at"],
                chunk_index=rows[i]["chunk_index"],
                text=rows[i]["text"],
                score=float(scores[i]),
            )
            for i in top
        ]

    def count(self, user_id: str) -> int:
        conn = self._conn()
        n = conn.execute(
            "SELECT COUNT(*) FROM email_chunks WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        conn.close()
        return int(n)

    def indexed_message_ids(self, user_id: str) -> set[str]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT DISTINCT message_id FROM email_chunks WHERE user_id = ?", (user_id,)
        ).fetchall()
        conn.close()
        return {r[0] for r in rows}


class PgVectorStore(VectorStore):
    """Postgres + pgvector. Same interface as SqliteVectorStore; cosine search
    is an HNSW index scan (`embedding <=> query`) instead of a full NumPy pass."""

    def __init__(self, dsn: str | None = None):
        self._dsn = dsn

    def _dsn_str(self) -> str:
        return (self._dsn or settings.database_url).replace("postgresql+psycopg://", "postgresql://")

    def _connect(self):
        import psycopg
        from pgvector.psycopg import register_vector

        conn = psycopg.connect(self._dsn_str(), autocommit=True)
        register_vector(conn)  # needs the `vector` type to already exist (see init)
        return conn

    def init(self) -> None:
        import psycopg

        # First connection must NOT register_vector — the extension may not exist yet.
        with psycopg.connect(self._dsn_str(), autocommit=True) as conn:
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS email_chunks (
                    id           BIGSERIAL PRIMARY KEY,
                    user_id      TEXT NOT NULL,
                    message_id   TEXT NOT NULL,
                    thread_id    TEXT,
                    sender       TEXT,
                    subject      TEXT,
                    sent_at      TEXT,
                    chunk_index  INTEGER NOT NULL,
                    text         TEXT NOT NULL,
                    embedding    vector({EMBEDDING_DIM}) NOT NULL,
                    indexed_at   TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_email_chunks_user ON email_chunks(user_id)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_email_chunks_msg ON email_chunks(user_id, message_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_email_chunks_ann "
                "ON email_chunks USING hnsw (embedding vector_cosine_ops)"
            )

    def delete_message(self, user_id: str, message_id: str) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM email_chunks WHERE user_id = %s AND message_id = %s",
                (user_id, message_id),
            )
            return cur.rowcount

    def add_chunks(self, chunks: list[Chunk]) -> int:
        if not chunks:
            return 0
        import numpy as np

        rows = []
        for c in chunks:
            if len(c.embedding) != EMBEDDING_DIM:
                raise ValueError(f"embedding dim {len(c.embedding)} != expected {EMBEDDING_DIM}")
            rows.append(
                (c.user_id, c.message_id, c.thread_id, c.sender, c.subject, c.sent_at,
                 c.chunk_index, c.text, np.asarray(c.embedding, dtype=np.float32))
            )
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO email_chunks
                        (user_id, message_id, thread_id, sender, subject, sent_at,
                         chunk_index, text, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    rows,
                )
        return len(rows)

    def search(self, user_id: str, query_vector: list[float], k: int = 6) -> list[SearchHit]:
        import numpy as np

        q = np.asarray(query_vector, dtype=np.float32)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT message_id, thread_id, sender, subject, sent_at, chunk_index,
                       text, 1 - (embedding <=> %s) AS score
                FROM email_chunks
                WHERE user_id = %s
                ORDER BY embedding <=> %s
                LIMIT %s
                """,
                (q, user_id, q, k),
            ).fetchall()
        return [
            SearchHit(
                message_id=r[0], thread_id=r[1], sender=r[2], subject=r[3], sent_at=r[4],
                chunk_index=r[5], text=r[6], score=float(r[7]),
            )
            for r in rows
        ]

    def count(self, user_id: str) -> int:
        with self._connect() as conn:
            return int(
                conn.execute(
                    "SELECT COUNT(*) FROM email_chunks WHERE user_id = %s", (user_id,)
                ).fetchone()[0]
            )

    def indexed_message_ids(self, user_id: str) -> set[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT message_id FROM email_chunks WHERE user_id = %s", (user_id,)
            ).fetchall()
        return {r[0] for r in rows}


_default_store: VectorStore | None = None


def get_store() -> VectorStore:
    """Process-wide default store — PgVectorStore when DATABASE_URL is Postgres,
    otherwise a local SQLite store. Tests pass their own instance instead."""
    global _default_store
    if _default_store is None:
        _default_store = PgVectorStore() if settings.is_postgres else SqliteVectorStore()
        _default_store.init()
    return _default_store
