"""Intent classification for the assistant graph.

Strategy — cheap and deterministic first, LLM only when unsure:

1. **Clarify continuation** — if the previous turn asked the user to clarify,
   the reply almost always continues that same action.
2. **Keyword heuristic** (`_keyword_intent`) — fast, deterministic, and the
   sole path exercised by most tests. If it lands on a concrete action we
   trust it.
3. **LLM second opinion** (`_llm_intent`) — only consulted when the heuristic
   falls through to ``chat``. Lets phrasings the keywords miss ("could you
   fire off a note to Sam") still reach the right tool. Any failure (no
   network, bad key, malformed output) degrades silently back to ``chat``.

`classify_intent` returns ``(intent, action_type)`` — the action type is a
pure function of the intent.
"""

import logging
import re

from graph.policy import ActionType
from llm.client import invoke_structured_with_fallback
from models.schemas import IntentClassification

logger = logging.getLogger("ai_assistant.intent")

EMAIL_PATTERN = r"[\w\.-]+@[\w\.-]+\.\w+"

# Every intent maps to exactly one action type (some are plain strings that
# predate the ActionType enum).
INTENT_TO_ACTION: dict[str, str] = {
    "chat": "chat",
    "email_summary": ActionType.EMAIL_SUMMARIZE.value,
    "calendar_today": "calendar_read",
    "draft_email": ActionType.EMAIL_DRAFT.value,
    "send_email": ActionType.EMAIL_SEND.value,
    "reply_to_unread_email": ActionType.EMAIL_REPLY_DRAFT.value,
    "draft_calendar_event": ActionType.CALENDAR_CREATE.value,
    "delete_calendar_event": ActionType.CALENDAR_DELETE.value,
    "remember_preference": ActionType.MEMORY_WRITE.value,
    "daily_briefing": "daily_briefing",
    "meeting_prep": "meeting_prep",
    "create_task": "create_task",
    "list_tasks": "list_tasks",
    "complete_task": "complete_task",
}

_LLM_PROMPT = """You classify a personal-assistant user message into one intent.

Intents:
- chat: greeting, small talk, question about the assistant, anything not below
- email_summary: summarize / read / check unread emails
- calendar_today: what's on the calendar / schedule today
- draft_email: compose or write an email DRAFT (not send)
- send_email: actually send an email now
- reply_to_unread_email: reply to a specific unread email
- draft_calendar_event: create / schedule a calendar event or meeting
- delete_calendar_event: cancel / delete / remove a calendar event
- remember_preference: store a personal preference for later
- daily_briefing: a full morning briefing of the day
- meeting_prep: prepare / brief for an upcoming meeting
- create_task: add a reminder / to-do
- list_tasks: show open tasks
- complete_task: mark a task done

Message: {message}

Respond with the single best intent. When in doubt, choose chat."""


def _continuation_intent(message: str, previous_action_type: str) -> str | None:
    """The prior turn asked for clarification — figure out which action it continues."""
    if previous_action_type == ActionType.EMAIL_DRAFT.value and re.search(EMAIL_PATTERN, message):
        return "draft_email"
    if previous_action_type == ActionType.EMAIL_SEND.value and re.search(EMAIL_PATTERN, message):
        return "send_email"
    if previous_action_type == ActionType.CALENDAR_CREATE.value:
        return "draft_calendar_event"
    if previous_action_type == ActionType.EMAIL_REPLY_DRAFT.value:
        return "reply_to_unread_email"
    return None


def _keyword_intent(message: str) -> str:
    """Deterministic keyword heuristic. `message` must already be lowercased/stripped."""
    if message.startswith("remember "):
        return "remember_preference"

    if any(
        phrase in message
        for phrase in [
            "daily briefing",
            "morning briefing",
            "daily summary",
            "brief me on my day",
            "what's on my plate today",
            "briefing",
        ]
    ):
        return "daily_briefing"

    if any(
        phrase in message
        for phrase in [
            "prep me for my next meeting",
            "prepare me for my next meeting",
            "meeting prep",
            "prepare for meeting",
            "next meeting prep",
        ]
    ):
        return "meeting_prep"

    if "task" in message and any(word in message for word in ["show", "list", "open", "my"]):
        return "list_tasks"

    if re.search(r"\b(mark|complete|finish)\s+task\s+\d+\s*(done|complete|completed)?", message):
        return "complete_task"

    if message.startswith("remind me") or "remind me to" in message:
        return "create_task"

    if re.search(r"reply to (email|message)\s+\d+", message):
        return "reply_to_unread_email"

    # "send an email to X" — compose + send (high-risk, gated by approval).
    # Checked before "draft" so it wins when both words appear. Missing details
    # (e.g. no recipient) are handled downstream by prepare_email_send → clarify.
    mentions_email = bool(re.search(r"\be-?mail\b|\bmessage\b", message))
    if "send" in message and mentions_email and "draft" not in message:
        return "send_email"

    # "cancel my 3pm meeting" / "delete the standup event"
    if re.search(r"\b(cancel|delete|remove)\b.*\b(meeting|event|call|appointment|invite)\b", message) or \
       re.search(r"\bcancel\b.*\b(my|the)\b.*\b(\d{1,2}\s*(am|pm)|standup|sync|1:1|one on one)\b", message):
        return "delete_calendar_event"

    if "email" in message or "reply" in message:
        if any(
            word in message
            for word in ["draft", "write", "compose", "reply", "follow-up", "follow up"]
        ):
            return "draft_email"

    if any(word in message for word in ["create event", "schedule", "meeting", "calendar event"]):
        return "draft_calendar_event"

    if "unread email" in message or "emails" in message or "gmail" in message:
        return "email_summary"

    calendar_today_phrases = (
        "calendar",
        "agenda",
        "my schedule",
        "schedule today",
        "today's schedule",
        "what's on today",
        "whats on today",
        "what do i have today",
        "my day today",
        "meetings today",
        "events today",
    )
    if any(phrase in message for phrase in calendar_today_phrases):
        return "calendar_today"

    return "chat"


def _llm_intent(message: str) -> str | None:
    """LLM fallback. Returns a valid intent string, or None on any failure."""
    try:
        result = invoke_structured_with_fallback(
            IntentClassification, _LLM_PROMPT.format(message=message)
        )
        intent = (getattr(result, "intent", "") or "").strip()
        return intent if intent in INTENT_TO_ACTION else None
    except Exception:
        logger.warning("LLM intent classification failed; falling back to keyword result", exc_info=True)
        return None


def classify_intent(
    message: str,
    previous_policy_decision: str = "",
    previous_action_type: str = "",
) -> tuple[str, str]:
    """Return ``(intent, action_type)`` for a user message."""
    normalized = (message or "").lower().strip()

    if previous_policy_decision == "clarify":
        cont = _continuation_intent(normalized, previous_action_type)
        if cont:
            return cont, INTENT_TO_ACTION[cont]

    keyword = _keyword_intent(normalized)
    if keyword != "chat":
        return keyword, INTENT_TO_ACTION[keyword]

    llm = _llm_intent(message)
    if llm and llm != "chat":
        return llm, INTENT_TO_ACTION[llm]

    return "chat", "chat"
