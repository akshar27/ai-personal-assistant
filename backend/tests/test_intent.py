import pytest

from graph.nodes import detect_intent
from graph.policy import ActionType


def intent_of(message: str, **extra_state):
    return detect_intent({"message": message, "user_id": "u1", **extra_state})


@pytest.mark.parametrize(
    "message, expected_intent, expected_action",
    [
        ("remember I prefer concise emails", "remember_preference", ActionType.MEMORY_WRITE.value),
        ("summarize my unread emails", "email_summary", ActionType.EMAIL_SUMMARIZE.value),
        ("what's on my calendar today", "calendar_today", "calendar_read"),
        ("draft an email to sam@example.com about the demo", "draft_email", ActionType.EMAIL_DRAFT.value),
        ("write a follow up email", "draft_email", ActionType.EMAIL_DRAFT.value),
        ("reply to email 1 saying yes", "reply_to_unread_email", ActionType.EMAIL_REPLY_DRAFT.value),
        ("schedule a meeting tomorrow at 3pm", "draft_calendar_event", ActionType.CALENDAR_CREATE.value),
        ("give me my daily briefing", "daily_briefing", "daily_briefing"),
        ("prep me for my next meeting", "meeting_prep", "meeting_prep"),
        ("remind me to submit the report", "create_task", "create_task"),
        ("show my tasks", "list_tasks", "list_tasks"),
        ("mark task 3 done", "complete_task", "complete_task"),
        ("how are you today", "chat", "chat"),
    ],
)
def test_detect_intent_table(message, expected_intent, expected_action):
    result = intent_of(message)
    assert result["intent"] == expected_intent
    assert result["action_type"] == expected_action


def test_clarify_continuation_resumes_email_draft_when_recipient_supplied():
    # user was previously asked to clarify a missing recipient
    result = intent_of(
        "sam@example.com",
        policy_decision="clarify",
        action_type=ActionType.EMAIL_DRAFT.value,
    )
    assert result["intent"] == "draft_email"
    assert result["action_type"] == ActionType.EMAIL_DRAFT.value


def test_detect_intent_resets_prior_approval_state():
    result = intent_of("summarize my unread emails")
    assert result["approval_required"] is False
    assert result["approval_payload"] == {}
    assert result["draft_email"] == {}
