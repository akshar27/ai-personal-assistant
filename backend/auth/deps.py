"""FastAPI dependencies for reading the session user."""

from fastapi import Depends, HTTPException, Request

from auth import session
from auth.users import User, get_user


def current_user_optional(request: Request) -> User | None:
    uid = session.read(request.cookies.get(session.COOKIE_NAME))
    if not uid:
        return None
    return get_user(uid)


def current_user(user: User | None = Depends(current_user_optional)) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="Not signed in.")
    return user
