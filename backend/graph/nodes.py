import re
from datetime import datetime
from langsmith import traceable

from graph.state import AssistantState
from graph.memory import save_preference, get_preferences
from llm.client import invoke_structured_with_fallback
from models.schemas import (
    EmailDraftExtraction,
    CalendarEventExtraction,
    EmailReplyExtraction,
)


@traceable(run_type="chain", name="detect_intent")
def detect_intent(state: AssistantState) -> AssistantState:
    message = state.get("message", "").lower()

    if message.startswith("remember "):
        return {"intent": "remember_preference"}

    if re.search(r"reply to (email|message)\s+\d+", message):
        return {"intent": "reply_to_unread_email"}

    if "email" in message or "reply" in message:
        if any(
            word in message
            for word in ["draft", "write", "compose", "reply", "follow-up", "follow up"]
        ):
            return {"intent": "draft_email"}

    if any(word in message for word in ["create event", "schedule", "meeting", "calendar event"]):
        return {"intent": "draft_calendar_event"}

    if "unread email" in message or "emails" in message or "gmail" in message:
        return {"intent": "email_summary"}

    if "calendar" in message or "today" in message:
        return {"intent": "calendar_today"}

    return {"intent": "chat"}


@traceable(run_type="chain", name="handle_remember_preference")
def handle_remember_preference(state: AssistantState) -> AssistantState:
    user_id = state.get("user_id", "default_user")
    message = state.get("message", "")

    raw = message.replace("remember", "", 1).strip()
    save_preference(user_id, "user_preference", raw)

    return {
        "reply": f"Got it — I’ll remember: {raw}",
        "tool_used": "memory",
    }


@traceable(run_type="chain", name="respond_chat")
def respond_chat(state: AssistantState) -> AssistantState:
    user_id = state.get("user_id", "default_user")
    prefs = get_preferences(user_id)

    if prefs:
        pref_text = "; ".join([p["value"] for p in prefs[:3]])
        return {
            "reply": f"You said: {state.get('message', '')}. I also remember these preferences: {pref_text}",
            "tool_used": "none",
        }

    return {
        "reply": "I can summarize unread emails, show today's calendar, remember preferences, draft emails, reply to unread emails, or create calendar events.",
        "tool_used": "none",
    }


@traceable(run_type="chain", name="respond_email_summary")
def respond_email_summary(state: AssistantState) -> AssistantState:
    items = state.get("email_summary", [])
    if not items:
        return {
            "reply": "I could not find unread emails right now.",
            "tool_used": "gmail",
        }

    lines = ["Here are your unread emails:"]
    for item in items[:5]:
        lines.append(
            f"{item['index']}. {item['subject']} from {item['sender']}"
        )

    lines.append("You can say something like: reply to email 1 saying I can do next Tuesday afternoon")

    return {
        "reply": "\n".join(lines),
        "tool_used": "gmail",
    }


@traceable(run_type="chain", name="respond_calendar_today")
def respond_calendar_today(state: AssistantState) -> AssistantState:
    events = state.get("calendar_events", [])
    if not events:
        return {
            "reply": "You have no events on your calendar today.",
            "tool_used": "calendar",
        }

    lines = ["Here is your calendar for today:"]
    for event in events[:5]:
        lines.append(f"- {event['summary']} ({event['start']} to {event['end']})")

    return {
        "reply": "\n".join(lines),
        "tool_used": "calendar",
    }


@traceable(run_type="chain", name="prepare_email_draft")
def prepare_email_draft(state: AssistantState) -> AssistantState:
    user_id = state.get("user_id", "default_user")
    message = state.get("message", "")
    prefs = get_preferences(user_id)
    pref_text = "; ".join([p["value"] for p in prefs]) if prefs else "No stored preferences."

    prompt = f"""
You are helping prepare an email draft for an AI personal assistant.

User preferences:
{pref_text}

User request:
{message}

Instructions:
- Extract the recipient email address if provided.
- Generate a professional and useful subject.
- Generate a polished email body.
- Respect user preferences if relevant, such as concise tone.
- If no recipient email is explicitly provided, return an empty string for "to".
- Return only structured output.
"""

    result = invoke_structured_with_fallback(EmailDraftExtraction, prompt)

    draft = {
        "to": result.to,
        "subject": result.subject,
        "body": result.body,
    }

    return {
        "draft_email": draft,
        "approval_required": True,
        "approval_payload": {
            "action": "create_gmail_draft",
            "draft": draft,
        },
    }


@traceable(run_type="chain", name="select_unread_email")
def select_unread_email(state: AssistantState) -> AssistantState:
    message = state.get("message", "").lower()
    unread_emails = state.get("unread_emails", [])

    match = re.search(r"reply to (email|message)\s+(\d+)", message)
    if not match:
        return {
            "reply": "I couldn't figure out which unread email you want to reply to.",
            "tool_used": "gmail",
        }

    selected_index = int(match.group(2))

    for item in unread_emails:
        if item.get("index") == selected_index:
            return {"selected_email": item}

    return {
        "reply": f"I couldn't find unread email number {selected_index}. Please summarize unread emails first.",
        "tool_used": "gmail",
    }


@traceable(run_type="chain", name="prepare_reply_to_unread_email")
def prepare_reply_to_unread_email(state: AssistantState) -> AssistantState:
    user_id = state.get("user_id", "default_user")
    message = state.get("message", "")
    prefs = get_preferences(user_id)
    pref_text = "; ".join([p["value"] for p in prefs]) if prefs else "No stored preferences."
    selected_email = state.get("selected_email", {})

    prompt = f"""
You are helping prepare a reply email for an AI personal assistant.

User preferences:
{pref_text}

Original email sender:
{selected_email.get("sender", "")}

Original email subject:
{selected_email.get("subject", "")}

Original email snippet:
{selected_email.get("snippet", "")}

User reply instruction:
{message}

Instructions:
- Write only the reply body.
- Make it context-aware to the original email.
- Respect user preferences if relevant, such as concise tone.
- Do not include a subject line.
- Do not include placeholder text.
- Return only structured output.
"""

    result = invoke_structured_with_fallback(EmailReplyExtraction, prompt)

    draft = {
        "to": selected_email.get("sender", ""),
        "subject": selected_email.get("subject", ""),
        "body": result.body,
    }

    return {
        "draft_email": draft,
        "approval_required": True,
        "approval_payload": {
            "action": "create_gmail_reply_draft",
            "draft": draft,
            "email_context": {
                "sender": selected_email.get("sender", ""),
                "subject": selected_email.get("subject", ""),
                "snippet": selected_email.get("snippet", ""),
            },
        },
    }


@traceable(run_type="chain", name="prepare_calendar_event_draft")
def prepare_calendar_event_draft(state: AssistantState) -> AssistantState:
    user_id = state.get("user_id", "default_user")
    message = state.get("message", "")
    prefs = get_preferences(user_id)
    pref_values = [p["value"].lower() for p in prefs]
    pref_text = "; ".join([p["value"] for p in prefs]) if prefs else "No stored preferences."
    now = datetime.now()

    default_duration = 30
    if any("45 minute" in p or "45-min" in p for p in pref_values):
        default_duration = 45
    elif any("60 minute" in p or "1 hour" in p for p in pref_values):
        default_duration = 60

    preferred_time_note = ""
    if any("morning" in p for p in pref_values):
        preferred_time_note = "Prefer morning meetings when the user request is flexible."
    elif any("afternoon" in p for p in pref_values):
        preferred_time_note = "Prefer afternoon meetings when the user request is flexible."

    prompt = f"""
You are helping prepare a calendar event draft for an AI personal assistant.

Current datetime:
{now.isoformat()}

User preferences:
{pref_text}

User request:
{message}

Instructions:
- Extract an event title.
- Infer the correct start and end datetime.
- Return start and end as ISO datetime strings.
- Default duration to {default_duration} minutes unless user specifies otherwise.
- {preferred_time_note}
- If user says "tomorrow afternoon", choose a sensible afternoon time like 2:00 PM.
- Return only structured output.
"""

    result = invoke_structured_with_fallback(CalendarEventExtraction, prompt)

    event_payload = {
        "summary": result.summary,
        "start": result.start,
        "end": result.end,
    }

    return {
        "draft_event": event_payload,
    }


@traceable(run_type="chain", name="respond_conflict_suggestion")
def respond_conflict_suggestion(state: AssistantState) -> AssistantState:
    conflicts = state.get("conflict_details", [])
    suggested = state.get("suggested_event", {})

    if not conflicts:
        return {
            "reply": "No calendar conflicts found.",
            "tool_used": "calendar",
        }

    lines = [
        "That time conflicts with existing events.",
        "I suggested the next available slot for approval:",
        f"- {suggested.get('summary')} ({suggested.get('start')} to {suggested.get('end')})",
        "Conflicting events:",
    ]

    for item in conflicts[:5]:
        lines.append(f"- {item['summary']} ({item['start']} to {item['end']})")

    return {
        "reply": "\n".join(lines),
        "tool_used": "calendar_conflict",
    }