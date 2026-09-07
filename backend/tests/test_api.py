def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_chat_read_only(client):
    r = client.post("/chat", json={"user_id": "u1", "message": "summarize my unread emails"})
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "email_summary"
    assert body["requires_approval"] is False


def test_chat_draft_email_returns_approval_payload(client, fake_llm):
    from models.schemas import EmailDraftExtraction

    fake_llm.set(EmailDraftExtraction, EmailDraftExtraction(
        to="sam@example.com", subject="Hi", body="Hello Sam."
    ))
    r = client.post("/chat", json={
        "user_id": "approve-user",
        "message": "draft an email to sam@example.com saying hello",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["requires_approval"] is True
    assert body["approval_payload"] is not None


def test_chat_maps_integration_errors_to_a_friendly_reply(client, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("Google account not connected.")

    monkeypatch.setattr("app.graph.invoke", boom)
    r = client.post("/chat", json={"user_id": "u1", "message": "summarize my unread emails"})
    assert r.status_code == 200
    assert r.json()["reply"] == "Google account not connected."


def test_chat_hides_unexpected_errors(client, monkeypatch):
    def boom(*a, **k):
        raise ValueError("secret internal detail")

    monkeypatch.setattr("app.graph.invoke", boom)
    r = client.post("/chat", json={"user_id": "u1", "message": "hi"})
    assert r.status_code == 200
    assert "secret internal detail" not in r.json()["reply"]
