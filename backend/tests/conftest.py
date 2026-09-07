"""Shared fixtures. Every test runs against a throwaway SQLite file and a fake
LLM / fake Google clients — no network, no API keys."""

import os
import sys
from pathlib import Path

import pytest

# Make `backend/` importable when pytest is run from the repo root.
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

# Set before anything imports config / load_dotenv. These win over backend/.env.
os.environ["OPENAI_API_KEY"] = "test-key-not-used"
os.environ["LLM_PROVIDER"] = "openai"
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGSMITH_API_KEY"] = ""  # present-but-empty so load_dotenv won't fill it


@pytest.fixture(autouse=True)
def temp_memory_db(tmp_path, monkeypatch):
    """Point the memory + history stores at fresh SQLite files for each test."""
    from config import settings
    from graph import memory

    db_file = tmp_path / "memory.db"
    monkeypatch.setattr(settings, "memory_db_file", str(db_file))
    monkeypatch.setattr(settings, "history_index_db_file", str(tmp_path / "history.db"))

    import retrieval.store as store_mod
    monkeypatch.setattr(store_mod, "_default_store", None)

    memory.init_memory()
    yield db_file


# A deterministic stand-in for real embeddings: hashes tokens into a fixed-width
# bag-of-words vector, so semantically-overlapping text lands near each other
# without any network call.
def _fake_vector(text: str):
    import numpy as np
    from retrieval.embeddings import EMBEDDING_DIM

    vec = np.zeros(EMBEDDING_DIM, dtype=np.float32)
    for tok in text.lower().split():
        vec[hash(tok) % EMBEDDING_DIM] += 1.0
    norm = np.linalg.norm(vec)
    if norm:
        vec /= norm
    return vec.tolist()


@pytest.fixture
def fake_embeddings(monkeypatch):
    # ingest.py / search.py reference `embeddings.embed_*` via the module, so
    # patching the source module is enough.
    monkeypatch.setattr("retrieval.embeddings.embed_texts",
                        lambda texts: [_fake_vector(t) for t in texts])
    monkeypatch.setattr("retrieval.embeddings.embed_query", lambda t: _fake_vector(t))
    return _fake_vector


class FakeLLM:
    """Records prompts and returns canned structured responses keyed by schema name."""

    def __init__(self):
        self.responses: dict[str, object] = {}
        self.calls: list[tuple[str, str]] = []

    def set(self, schema_cls, value):
        self.responses[schema_cls.__name__] = value

    def __call__(self, schema, prompt):
        self.calls.append((schema.__name__, prompt))
        if schema.__name__ not in self.responses:
            # The LLM intent "second opinion" is only reached when the keyword
            # heuristic is unsure — default it to plain chat so tests that don't
            # care about it don't have to wire it up.
            if schema.__name__ == "IntentClassification":
                return schema(intent="chat")
            raise AssertionError(f"FakeLLM got an unexpected schema: {schema.__name__}")
        data = self.responses[schema.__name__]
        return data if not isinstance(data, dict) else schema(**data)


@pytest.fixture
def fake_llm(monkeypatch):
    fake = FakeLLM()
    # Patch every module that imported the symbol directly.
    monkeypatch.setattr("graph.nodes.invoke_structured_with_fallback", fake)
    monkeypatch.setattr("graph.intent.invoke_structured_with_fallback", fake)
    # Plain-text calls (chat replies): return whatever `fake.text` is set to.
    fake.text = "OK."
    monkeypatch.setattr("graph.nodes.invoke_text_with_fallback", lambda prompt: fake.text)
    return fake


@pytest.fixture
def fake_google(monkeypatch):
    """Replace the Gmail / Calendar tool calls with in-memory fakes."""
    state = {
        "unread": [
            {"index": 1, "id": "m1", "thread_id": "t1", "subject": "Lunch?",
             "sender": "Sam <sam@example.com>", "snippet": "Free Friday?"},
        ],
        "drafts": [],
        "sent": [],
        "events": [],
        "today_events": [],
        "upcoming": [],
        "deleted": [],
        # Full-body messages for retrieval ingestion: list of dicts shaped like
        # integrations.gmail_client.get_message_full's return value.
        "messages": [],
    }

    def list_message_ids(query="newer_than:180d", max_results=200):
        return [{"id": m["id"], "thread_id": m.get("thread_id", "t" + m["id"])}
                for m in state["messages"][:max_results]]

    def get_message_full(message_id):
        m = next(x for x in state["messages"] if x["id"] == message_id)
        return {
            "id": m["id"],
            "thread_id": m.get("thread_id", "t" + m["id"]),
            "subject": m.get("subject", "(No Subject)"),
            "sender": m.get("sender", "someone@example.com"),
            "sent_at": m.get("sent_at", "2026-08-01T00:00:00"),
            "body": m.get("body", ""),
        }

    def list_unread_emails(max_results=5):
        return state["unread"]

    def get_email_by_id(message_id):
        return next(e for e in state["unread"] if e["id"] == message_id)

    def create_gmail_draft(to, subject, body):
        state["drafts"].append({"to": to, "subject": subject, "body": body})
        return {"id": "draft-1", "message": "Draft created successfully."}

    def create_gmail_reply_draft(thread_id, to, subject, body):
        state["drafts"].append({"thread_id": thread_id, "to": to, "subject": subject, "body": body})
        return {"id": "reply-1", "message": "Reply draft created successfully."}

    def send_gmail_message(to, subject, body):
        state["sent"].append({"to": to, "subject": subject, "body": body})
        return {"id": "sent-1", "message": "Email sent."}

    def delete_calendar_event(event_id):
        state["deleted"].append(event_id)
        return {"id": event_id, "message": "Event deleted."}

    def get_today_events(max_results=10):
        return state["today_events"]

    def get_events_in_range(start_iso, end_iso, timezone_str="America/Los_Angeles"):
        return []  # no conflicts by default

    def create_calendar_event(summary, start_iso, end_iso, conference_type="none", timezone_str=None):
        ev = {"summary": summary, "start": start_iso, "end": end_iso,
              "htmlLink": "https://calendar.example/e1"}
        if conference_type == "google_meet":
            ev["meetLink"] = "https://meet.example/abc-defg-hij"
        state["events"].append(ev)
        return ev

    def get_upcoming_events(max_results=5, timezone_str=None):
        return state["upcoming"]

    monkeypatch.setattr("retrieval.ingest.list_message_ids", list_message_ids)
    monkeypatch.setattr("retrieval.ingest.get_message_full", get_message_full)

    for name, fn in {
        "list_unread_emails": list_unread_emails,
        "get_email_by_id": get_email_by_id,
        "create_gmail_draft": create_gmail_draft,
        "create_gmail_reply_draft": create_gmail_reply_draft,
        "send_gmail_message": send_gmail_message,
        "get_today_events": get_today_events,
        "get_events_in_range": get_events_in_range,
        "create_calendar_event": create_calendar_event,
        "delete_calendar_event": delete_calendar_event,
        "get_upcoming_events": get_upcoming_events,
    }.items():
        monkeypatch.setattr(f"graph.tools.{name}", fn)

    return state
