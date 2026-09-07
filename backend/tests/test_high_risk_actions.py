"""Send-email and delete-event go through the same policy → approval gate as
drafts, but they are HIGH risk and actually execute an irreversible action."""

import pytest
from langgraph.types import Command

from graph.assistant_graph import build_graph
from graph.nodes import detect_intent
from graph.policy import ActionType
from models.schemas import EmailSendExtraction, EventMatchExtraction


@pytest.fixture
def graph():
    return build_graph()


def invoke(graph, message, thread, user_id="u1"):
    return graph.invoke(
        {"user_id": user_id, "message": message},
        config={"configurable": {"thread_id": thread}},
    )


# --- intent detection -------------------------------------------------

@pytest.mark.parametrize(
    "message, expected",
    [
        ("send an email to sam@example.com saying I'll be late", "send_email"),
        ("send this email", "send_email"),
        ("email sam@example.com and send it", "send_email"),
        ("draft an email to sam@example.com", "draft_email"),   # 'draft' still wins
        ("cancel my 3pm meeting", "delete_calendar_event"),
        ("delete the standup event", "delete_calendar_event"),
        ("remove my dentist appointment", "delete_calendar_event"),
    ],
)
def test_intent_routes_high_risk_actions(message, expected):
    assert detect_intent({"message": message, "user_id": "u1"})["intent"] == expected


# --- send email -----------------------------------------------------

def test_send_email_requires_high_risk_approval_then_sends(graph, fake_llm, fake_google):
    fake_llm.set(EmailSendExtraction, EmailSendExtraction(
        to="sam@example.com", subject="Running late", body="I'll be 10 minutes late."
    ))
    thread = "send-flow"

    first = invoke(graph, "send an email to sam@example.com saying I'll be late", thread)
    assert first["action_type"] == ActionType.EMAIL_SEND.value
    assert first["policy_decision"] == "require_approval"
    assert first["risk_level"] == "high"
    assert "__interrupt__" in first
    assert fake_google["sent"] == []  # nothing sent yet

    resume = graph.invoke(Command(resume={"approved": True}),
                          config={"configurable": {"thread_id": thread}})
    assert resume["approved"] is True
    assert fake_google["sent"] == [
        {"to": "sam@example.com", "subject": "Running late", "body": "I'll be 10 minutes late."}
    ]


def test_send_email_rejected_sends_nothing(graph, fake_llm, fake_google):
    fake_llm.set(EmailSendExtraction, EmailSendExtraction(to="sam@example.com", subject="x", body="y"))
    thread = "send-reject"
    invoke(graph, "send an email to sam@example.com saying hi", thread)
    graph.invoke(Command(resume={"approved": False}),
                 config={"configurable": {"thread_id": thread}})
    assert fake_google["sent"] == []


def test_send_email_without_recipient_clarifies(graph, fake_llm, fake_google):
    fake_llm.set(EmailSendExtraction, EmailSendExtraction(to="", subject="x", body="y"))
    result = invoke(graph, "send an email saying I'll be late", "send-clarify")
    assert result["policy_decision"] == "clarify"
    assert fake_google["sent"] == []


# --- delete event --------------------------------------------------

def test_delete_event_requires_approval_then_deletes(graph, fake_llm, fake_google):
    fake_google["upcoming"] = [
        {"id": "ev-standup", "summary": "Standup", "start": "2026-07-01T09:00:00"},
        {"id": "ev-sync", "summary": "Project Sync", "start": "2026-07-01T15:00:00"},
    ]
    fake_llm.set(EventMatchExtraction, EventMatchExtraction(match_index=2))
    thread = "del-flow"

    first = invoke(graph, "cancel my project sync meeting", thread)
    assert first["action_type"] == ActionType.CALENDAR_DELETE.value
    assert first["policy_decision"] == "require_approval"
    assert "__interrupt__" in first
    assert fake_google["deleted"] == []

    resume = graph.invoke(Command(resume={"approved": True}),
                          config={"configurable": {"thread_id": thread}})
    assert resume["approved"] is True
    assert fake_google["deleted"] == ["ev-sync"]


def test_delete_event_no_match_clarifies(graph, fake_llm, fake_google):
    fake_google["upcoming"] = [{"id": "ev1", "summary": "Standup", "start": "2026-07-01T09:00:00"}]
    fake_llm.set(EventMatchExtraction, EventMatchExtraction(match_index=0))
    result = invoke(graph, "cancel the budget review meeting", "del-clarify")
    assert result["policy_decision"] == "clarify"
    assert fake_google["deleted"] == []
