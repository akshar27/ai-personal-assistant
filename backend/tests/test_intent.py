import pytest

from graph.nodes import detect_intent
from graph.intent import _keyword_intent, classify_intent
from graph.policy import ActionType


@pytest.mark.parametrize(
    "message, expected_intent",
    [
        ("remember I prefer concise emails", "remember_preference"),
        ("summarize my unread emails", "email_summary"),
        ("what's on my calendar today", "calendar_today"),
        ("draft an email to sam@example.com about the demo", "draft_email"),
        ("write a follow up email", "draft_email"),
        ("send an email to sam@example.com saying hi", "send_email"),
        ("cancel my 3pm meeting", "delete_calendar_event"),
        ("delete the standup event", "delete_calendar_event"),
        ("reply to email 1 saying yes", "reply_to_unread_email"),
        ("schedule a meeting tomorrow at 3pm", "draft_calendar_event"),
        ("give me my daily briefing", "daily_briefing"),
        ("prep me for my next meeting", "meeting_prep"),
        ("remind me to submit the report", "create_task"),
        ("show my tasks", "list_tasks"),
        ("mark task 3 done", "complete_task"),
        ("how are you today", "chat"),
        ("hey there", "chat"),
        ("what did Sam say about the renewal date", "search_history"),
        ("did I already reply to the vendor", "search_history"),
        ("find the email from the recruiter about salary", "search_history"),
        ("search my inbox for the contract terms", "search_history"),
        ("when did we agree on the launch date in that thread", "search_history"),
    ],
)
def test_keyword_intent_table(message, expected_intent):
    assert _keyword_intent(message.lower().strip()) == expected_intent


def test_classify_intent_maps_action_type():
    intent, action_type = classify_intent("summarize my unread emails")
    assert intent == "email_summary"
    assert action_type == ActionType.EMAIL_SUMMARIZE.value


def test_clarify_continuation_resumes_email_draft_when_recipient_supplied():
    intent, action_type = classify_intent(
        "sam@example.com",
        previous_policy_decision="clarify",
        previous_action_type=ActionType.EMAIL_DRAFT.value,
    )
    assert intent == "draft_email"
    assert action_type == ActionType.EMAIL_DRAFT.value


def test_clarify_continuation_resumes_send_email():
    intent, _ = classify_intent(
        "actually send it to sam@example.com",
        previous_policy_decision="clarify",
        previous_action_type=ActionType.EMAIL_SEND.value,
    )
    assert intent == "send_email"


def test_detect_intent_node_resets_prior_approval_state():
    result = detect_intent({"message": "summarize my unread emails", "user_id": "u1"})
    assert result["intent"] == "email_summary"
    assert result["approval_required"] is False
    assert result["approval_payload"] == {}
    assert result["draft_email"] == {}
