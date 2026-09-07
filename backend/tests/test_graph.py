"""End-to-end tests of the LangGraph assistant with a fake LLM and fake Google
clients. Covers the read-only paths, the policy layer, and the full
human-in-the-loop approval resume."""

import pytest
from langgraph.types import Command

from graph.assistant_graph import build_graph
from models.schemas import CalendarEventExtraction, EmailDraftExtraction, TaskExtraction


@pytest.fixture
def graph():
    return build_graph()


def invoke(graph, message, user_id="u1", thread=None):
    thread = thread or f"t-{message[:20]}"
    return graph.invoke(
        {"user_id": user_id, "message": message},
        config={"configurable": {"thread_id": thread}},
    )


def test_email_summary_is_read_only(graph, fake_llm, fake_google):
    result = invoke(graph, "summarize my unread emails")
    assert result["intent"] == "email_summary"
    assert "Lunch?" in result["reply"]
    assert not result.get("approval_required")


def test_remember_preference_persists(graph, fake_llm, fake_google):
    from graph import memory

    result = invoke(graph, "remember I prefer concise emails")
    assert result["intent"] == "remember_preference"
    assert "concise emails" in memory.get_latest_preference_value("u1", "user_preference")


def test_draft_email_requires_approval_then_creates_on_yes(graph, fake_llm, fake_google):
    fake_llm.set(EmailDraftExtraction, EmailDraftExtraction(
        to="sam@example.com", subject="Demo follow-up", body="Thanks for the demo today."
    ))
    thread = "draft-flow"

    first = invoke(graph, "draft an email to sam@example.com about the demo", thread=thread)
    assert first["policy_decision"] == "require_approval"
    assert "__interrupt__" in first

    resume = graph.invoke(
        Command(resume={"approved": True}),
        config={"configurable": {"thread_id": thread}},
    )
    assert resume["approved"] is True
    assert fake_google["drafts"] == [
        {"to": "sam@example.com", "subject": "Demo follow-up", "body": "Thanks for the demo today."}
    ]


def test_draft_email_rejected_creates_nothing(graph, fake_llm, fake_google):
    fake_llm.set(EmailDraftExtraction, EmailDraftExtraction(
        to="sam@example.com", subject="s", body="b"
    ))
    thread = "reject-flow"
    invoke(graph, "draft an email to sam@example.com saying hi", thread=thread)

    resume = graph.invoke(Command(resume={"approved": False}),
                          config={"configurable": {"thread_id": thread}})
    assert resume["approved"] is False
    assert fake_google["drafts"] == []


def test_draft_email_missing_recipient_asks_to_clarify(graph, fake_llm, fake_google):
    fake_llm.set(EmailDraftExtraction, EmailDraftExtraction(to="", subject="s", body="b"))
    result = invoke(graph, "draft an email saying thanks")
    assert result["policy_decision"] == "clarify"
    assert result.get("approval_required") is False


def test_calendar_event_with_google_meet_requires_approval(graph, fake_llm, fake_google):
    fake_llm.set(CalendarEventExtraction, CalendarEventExtraction(
        summary="Sync with Sam",
        start="2026-07-01T15:00:00",
        end="2026-07-01T15:30:00",
        conference_type="google_meet",
    ))
    result = invoke(graph, "schedule meeting tomorrow at 3pm with google meet")
    assert result["intent"] == "draft_calendar_event"
    assert result["policy_decision"] == "require_approval"
    assert result["draft_event"]["conference_type"] == "google_meet"


def test_explicit_hour_overrides_a_bad_llm_time(graph, fake_llm, fake_google):
    # user said 3pm; the LLM returned 8am — the node should snap to 15:00, not clarify
    fake_llm.set(CalendarEventExtraction, CalendarEventExtraction(
        summary="Standup", start="2026-07-01T08:00:00", end="2026-07-01T08:30:00",
        conference_type="none",
    ))
    result = invoke(graph, "schedule standup tomorrow at 3pm")
    assert result["policy_decision"] == "require_approval"
    assert result["draft_event"]["start"].endswith("T15:00:00")


def test_create_and_list_tasks(graph, fake_llm, fake_google):
    fake_llm.set(TaskExtraction, TaskExtraction(title="apply to Lyft", due_at="", source="job_search"))
    created = invoke(graph, "remind me to apply to Lyft", thread="task-a")
    assert created["intent"] == "create_task"

    listed = invoke(graph, "show my tasks", thread="task-a")
    assert "apply to Lyft" in listed["reply"]


def test_unknown_chat_uses_the_llm(graph, fake_llm, fake_google):
    fake_llm.text = "I'm doing well — how can I help?"
    result = invoke(graph, "hey how's it going")
    assert result["intent"] == "chat"
    assert result["reply"] == "I'm doing well — how can I help?"
