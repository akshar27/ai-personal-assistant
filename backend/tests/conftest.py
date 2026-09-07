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
    """Point the memory store at a fresh SQLite file for each test."""
    from config import settings
    from graph import memory

    db_file = tmp_path / "memory.db"
    monkeypatch.setattr(settings, "memory_db_file", str(db_file))
    memory.init_memory()
    yield db_file


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
            raise AssertionError(f"FakeLLM got an unexpected schema: {schema.__name__}")
        data = self.responses[schema.__name__]
        return data if not isinstance(data, dict) else schema(**data)


@pytest.fixture
def fake_llm(monkeypatch):
    fake = FakeLLM()
    # Patch every module that imported the symbol directly.
    monkeypatch.setattr("graph.nodes.invoke_structured_with_fallback", fake)
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
        "events": [],
        "today_events": [],
        "upcoming": [],
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

    for name, fn in {
        "list_unread_emails": list_unread_emails,
        "get_email_by_id": get_email_by_id,
        "create_gmail_draft": create_gmail_draft,
        "create_gmail_reply_draft": create_gmail_reply_draft,
        "get_today_events": get_today_events,
        "get_events_in_range": get_events_in_range,
        "create_calendar_event": create_calendar_event,
        "get_upcoming_events": get_upcoming_events,
    }.items():
        monkeypatch.setattr(f"graph.tools.{name}", fn)

    return state
