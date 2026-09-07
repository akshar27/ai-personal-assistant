"""Session cookies, guest users, and per-user Google token storage."""

import pytest

from auth import session
from auth.users import create_guest_user, get_user, upsert_google_user


def test_session_roundtrip():
    tok = session.issue("guest:abc")
    assert session.read(tok) == "guest:abc"


def test_tampered_session_is_rejected():
    assert session.read("not-a-real-token") is None
    assert session.read(None) is None


def test_guest_user_is_created_and_flagged():
    u = create_guest_user()
    assert u.id.startswith("guest:")
    assert u.is_guest is True
    assert u.can_use_google is False
    assert get_user(u.id).is_guest is True


def test_google_user_upsert_is_idempotent():
    a = upsert_google_user("sub-1", "a@x.com", "A")
    b = upsert_google_user("sub-1", "a@x.com", "A Renamed")
    assert a.id == b.id == "sub-1"
    assert get_user("sub-1").name == "A Renamed"
    assert get_user("sub-1").is_guest is False


def test_token_encryption_roundtrip(monkeypatch):
    from cryptography.fernet import Fernet
    from config import settings

    monkeypatch.setattr(settings, "token_encryption_key", Fernet.generate_key().decode())

    from auth.tokens import save_user_tokens, load_user_creds, delete_user_tokens

    class FakeCreds:
        def to_json(self):
            # far-future expiry → load_user_creds treats it as fresh, no refresh call
            return (
                '{"token": "abc", "refresh_token": "r", "client_id": "c", '
                '"client_secret": "s", "scopes": [], "expiry": "2999-01-01T00:00:00Z"}'
            )

    upsert_google_user("sub-2", "b@x.com", "B")
    save_user_tokens("sub-2", FakeCreds())

    creds = load_user_creds("sub-2")
    assert creds is not None
    assert creds.token == "abc"

    delete_user_tokens("sub-2")
    assert load_user_creds("sub-2") is None


def test_missing_encryption_key_is_a_clear_error(monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "token_encryption_key", None)
    from auth.tokens import _fernet

    with pytest.raises(RuntimeError, match="TOKEN_ENCRYPTION_KEY"):
        _fernet()


# --- endpoint-level -------------------------------------------------

def test_guest_endpoint_sets_a_cookie_and_me_reflects_it(fake_llm, fake_google):
    from fastapi.testclient import TestClient
    import app as app_module

    with TestClient(app_module.app) as c:
        r = c.post("/auth/guest")
        assert r.status_code == 200 and r.json()["is_guest"] is True
        assert session.COOKIE_NAME in r.cookies or "set-cookie" in {k.lower() for k in r.headers}

        me = c.get("/auth/me")
        assert me.json()["user"]["is_guest"] is True


def test_chat_requires_a_session(fake_llm, fake_google):
    from fastapi.testclient import TestClient
    import app as app_module

    with TestClient(app_module.app) as c:
        r = c.post("/chat", json={"user_id": "conv1", "message": "hi"})
        assert r.status_code == 401


def test_guest_cannot_index_email(client, test_user, monkeypatch):
    monkeypatch.setattr(test_user, "is_guest", True)
    r = client.post("/history/index", json={})
    assert r.status_code == 403
