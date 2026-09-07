"""User rows — Google `sub` for real accounts, `guest:<uuid>` for anonymous."""

import uuid
from dataclasses import dataclass

from sqlalchemy import insert, select, update
from sqlalchemy.sql import func

from db.engine import get_engine
from db.tables import users


@dataclass
class User:
    id: str
    email: str | None
    name: str | None
    is_guest: bool

    @property
    def can_use_google(self) -> bool:
        return not self.is_guest


def _row_to_user(row) -> User:
    return User(id=row.id, email=row.email, name=row.name, is_guest=bool(row.is_guest))


def get_user(user_id: str) -> User | None:
    with get_engine().connect() as conn:
        row = conn.execute(select(users).where(users.c.id == user_id)).first()
    return _row_to_user(row) if row else None


def upsert_google_user(sub: str, email: str | None, name: str | None) -> User:
    with get_engine().begin() as conn:
        exists = conn.execute(select(users.c.id).where(users.c.id == sub)).first()
        if exists:
            conn.execute(
                update(users)
                .where(users.c.id == sub)
                .values(email=email, name=name, last_seen_at=func.now())
            )
        else:
            conn.execute(
                insert(users).values(
                    id=sub, email=email, name=name, is_guest=False
                )
            )
    return User(id=sub, email=email, name=name, is_guest=False)


def create_guest_user() -> User:
    guest_id = f"guest:{uuid.uuid4().hex}"
    with get_engine().begin() as conn:
        conn.execute(insert(users).values(id=guest_id, is_guest=True))
    return User(id=guest_id, email=None, name=None, is_guest=True)


def touch_user(user_id: str) -> None:
    with get_engine().begin() as conn:
        conn.execute(
            update(users).where(users.c.id == user_id).values(last_seen_at=func.now())
        )
