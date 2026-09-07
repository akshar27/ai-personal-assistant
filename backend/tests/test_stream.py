import json


def sse_events(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        if line.startswith("data: "):
            out.append(json.loads(line[len("data: "):]))
    return out


def test_stream_returns_a_final_event_for_chat(client, fake_llm):
    fake_llm.text = "Hello! I can help with email and calendar."
    r = client.post("/chat/stream", json={"user_id": "s1", "message": "hi there"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")

    events = sse_events(r.text)
    final = [e for e in events if e["type"] == "final"]
    assert len(final) == 1
    assert final[0]["reply"] == "Hello! I can help with email and calendar."
    assert final[0]["requires_approval"] is False


def test_stream_final_event_carries_the_approval_payload(client, fake_llm):
    from models.schemas import EmailDraftExtraction

    fake_llm.set(EmailDraftExtraction, EmailDraftExtraction(
        to="sam@example.com", subject="Hi", body="Hello."
    ))
    r = client.post("/chat/stream", json={
        "user_id": "s2", "message": "draft an email to sam@example.com saying hi",
    })
    events = sse_events(r.text)
    final = next(e for e in events if e["type"] == "final")
    assert final["requires_approval"] is True
    assert final["approval_payload"]["payload"]["draft"]["to"] == "sam@example.com"


def test_stream_maps_integration_errors(client, monkeypatch):
    monkeypatch.setattr(
        "app.graph.stream",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("Google account not connected.")),
    )
    r = client.post("/chat/stream", json={"user_id": "s3", "message": "summarize my emails"})
    final = next(e for e in sse_events(r.text) if e["type"] == "final")
    assert final["reply"] == "Google account not connected."
    assert final["intent"] == "error"
