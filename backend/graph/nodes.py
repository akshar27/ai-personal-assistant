import re
from datetime import datetime
from langsmith import traceable

from graph.state import AssistantState
from llm.client import invoke_structured_with_fallback
from graph.policy import evaluate_policy, ActionType, PolicyDecision
from models.schemas import (
    EmailDraftExtraction,
    CalendarEventExtraction,
    EmailReplyExtraction,
    DailyBriefingExtraction,
    TaskExtraction,
    MeetingPrepExtraction,
)
from graph.memory import (
    save_preference,
    get_preferences,
    get_latest_preference_value,
    create_task,
    get_open_tasks,
    mark_task_done,
)
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("America/Los_Angeles")


def normalize_local_iso(dt_str: str) -> str:
    dt_str = (dt_str or "").strip()
    if not dt_str:
        return dt_str

    # Convert trailing Z into +00:00 so fromisoformat can parse it
    if dt_str.endswith("Z"):
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.astimezone(LOCAL_TZ).replace(tzinfo=None).isoformat()

    dt = datetime.fromisoformat(dt_str)
    if dt.tzinfo is not None:
        return dt.astimezone(LOCAL_TZ).replace(tzinfo=None).isoformat()

    return dt.isoformat()

def extract_requested_hour(message: str) -> int | None:
    msg = message.lower()

    match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", msg)
    if not match:
        return None

    hour = int(match.group(1))
    meridiem = match.group(3)

    if meridiem == "pm" and hour != 12:
        hour += 12
    if meridiem == "am" and hour == 12:
        hour = 0

    return hour

@traceable(run_type="chain", name="detect_intent")
def detect_intent(state: AssistantState) -> AssistantState:
    message = state.get("message", "").lower().strip()

    base_reset = {
        "policy_decision": "",
        "policy_reason": "",
        "risk_level": "",
        "approval_required": False,
        "approval_payload": {},
        "approved": False,
        "action_payload": {},
        "draft_email": {},
        "draft_event": {},
        "conflict_found": False,
        "conflict_details": [],
        "suggested_event": {},
    }

    previous_policy_decision = state.get("policy_decision", "")
    previous_action_type = state.get("action_type", "")
    email_pattern = r"[\w\.-]+@[\w\.-]+\.\w+"

    if previous_policy_decision == "clarify":
        if previous_action_type == ActionType.EMAIL_DRAFT.value and re.search(email_pattern, message):
            return {
                **base_reset,
                "intent": "draft_email",
                "action_type": ActionType.EMAIL_DRAFT.value,
            }

        if previous_action_type == ActionType.CALENDAR_CREATE.value:
            return {
                **base_reset,
                "intent": "draft_calendar_event",
                "action_type": ActionType.CALENDAR_CREATE.value,
            }

        if previous_action_type == ActionType.EMAIL_REPLY_DRAFT.value:
            return {
                **base_reset,
                "intent": "reply_to_unread_email",
                "action_type": ActionType.EMAIL_REPLY_DRAFT.value,
            }

    if message.startswith("remember "):
        return {
            **base_reset,
            "intent": "remember_preference",
            "action_type": ActionType.MEMORY_WRITE.value,
        }

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
        return {
            **base_reset,
            "intent": "daily_briefing",
            "action_type": "daily_briefing",
        }

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
        return {
            **base_reset,
            "intent": "meeting_prep",
            "action_type": "meeting_prep",
        }

    if "task" in message and any(word in message for word in ["show", "list", "open", "my"]):
        return {
            **base_reset,
            "intent": "list_tasks",
            "action_type": "list_tasks",
        }

    if re.search(r"\b(mark|complete|finish)\s+task\s+\d+\s*(done|complete|completed)?", message):
        return {
            **base_reset,
            "intent": "complete_task",
            "action_type": "complete_task",
        }

    if message.startswith("remind me") or "remind me to" in message:
        return {
            **base_reset,
            "intent": "create_task",
            "action_type": "create_task",
        }

    if re.search(r"reply to (email|message)\s+\d+", message):
        return {
            **base_reset,
            "intent": "reply_to_unread_email",
            "action_type": ActionType.EMAIL_REPLY_DRAFT.value,
        }

    if "email" in message or "reply" in message:
        if any(
            word in message
            for word in ["draft", "write", "compose", "reply", "follow-up", "follow up"]
        ):
            return {
                **base_reset,
                "intent": "draft_email",
                "action_type": ActionType.EMAIL_DRAFT.value,
            }

    if any(word in message for word in ["create event", "schedule", "meeting", "calendar event"]):
        return {
            **base_reset,
            "intent": "draft_calendar_event",
            "action_type": ActionType.CALENDAR_CREATE.value,
        }

    if "unread email" in message or "emails" in message or "gmail" in message:
        return {
            **base_reset,
            "intent": "email_summary",
            "action_type": ActionType.EMAIL_SUMMARIZE.value,
        }

    if "calendar" in message or "today" in message:
        return {
            **base_reset,
            "intent": "calendar_today",
            "action_type": "calendar_read",
        }

    return {
        **base_reset,
        "intent": "chat",
        "action_type": "chat",
    }

@traceable(run_type="chain", name="handle_remember_preference")
def handle_remember_preference(state: AssistantState) -> AssistantState:
    user_id = state.get("user_id", "default_user")
    message = state.get("message", "")

    raw = message.replace("remember", "", 1).strip()
    if not raw:
        return {
            "reply": "Please tell me what you want me to remember.",
            "tool_used": "memory",
        }

    lowered = raw.lower()

    if "timezone" in lowered:
        timezone_value = raw.split("timezone", 1)[-1].replace("is", "", 1).strip()
        try:
            ZoneInfo(timezone_value)
        except Exception:
            return {
                "reply": "That timezone looks invalid. Please use a format like Asia/Kolkata or America/Los_Angeles.",
                "tool_used": "memory",
            }

        save_preference(user_id, "timezone", timezone_value)
        return {
            "reply": f"Got it — I’ll use {timezone_value} as your timezone.",
            "tool_used": "memory",
        }

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
        lines.append(f"{item['index']}. {item['subject']} from {item['sender']}")

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
    pending_context = state.get("pending_clarification_context", {})
    original_message = pending_context.get("original_message", "")

    email_pattern = r"[\w\.-]+@[\w\.-]+\.\w+"
    if original_message and re.search(email_pattern, message):
        message = f"{original_message} Recipient email address is {message}"
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
        "to": (result.to or "").strip(),
        "subject": (result.subject or "").strip(),
        "body": (result.body or "").strip(),
    }

    if not draft["to"]:
        return {
            "draft_email": draft,
            "policy_decision": "clarify",
            "policy_reason": "I need the recipient email address before I can prepare this draft.",
            "approval_required": False,
            "approval_payload": {},
            "pending_clarification_context": {
                "original_intent": "draft_email",
                "original_message": message,
            },
            "tool_used": "gmail_prepare_draft",
        }

    if not draft["body"]:
        return {
            "draft_email": draft,
            "policy_decision": "clarify",
            "policy_reason": "I could not generate the email body. Please rephrase your request.",
            "approval_required": False,
            "approval_payload": {},
            "tool_used": "gmail_prepare_draft",
        }

    return {
        "draft_email": draft,
        "action_payload": {
            "action": "create_gmail_draft",
            "draft": draft,
        },
        "tool_used": "gmail_prepare_draft",
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

    if not selected_email:
        return {
            "policy_decision": "clarify",
            "policy_reason": "I could not find the email you want to reply to. Please summarize unread emails first.",
            "approval_required": False,
            "approval_payload": {},
            "tool_used": "gmail_prepare_reply_draft",
        }

    sender = (selected_email.get("sender") or "").strip()
    subject = (selected_email.get("subject") or "").strip()

    if not sender:
        return {
            "policy_decision": "clarify",
            "policy_reason": "The selected email is missing sender information, so I cannot prepare a reply yet.",
            "approval_required": False,
            "approval_payload": {},
            "tool_used": "gmail_prepare_reply_draft",
        }

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

    body = (result.body or "").strip()
    if not body:
        return {
            "policy_decision": "clarify",
            "policy_reason": "I could not generate the reply body. Please rephrase your reply request.",
            "approval_required": False,
            "approval_payload": {},
            "tool_used": "gmail_prepare_reply_draft",
        }

    draft = {
        "to": sender,
        "subject": subject,
        "body": body,
    }

    return {
        "draft_email": draft,
        "action_payload": {
            "action": "create_gmail_reply_draft",
            "draft": draft,
            "email_context": {
                "sender": sender,
                "subject": subject,
                "snippet": (selected_email.get("snippet", "") or "")[:300],
            },
        },
        "tool_used": "gmail_prepare_reply_draft",
    }


@traceable(run_type="chain", name="prepare_calendar_event_draft")
def prepare_calendar_event_draft(state: AssistantState) -> AssistantState:
    user_id = state.get("user_id", "default_user")
    message = state.get("message", "")
    prefs = get_preferences(user_id)
    pref_values = [p["value"].lower() for p in prefs]
    pref_text = "; ".join([p["value"] for p in prefs]) if prefs else "No stored preferences."
    from zoneinfo import ZoneInfo

    user_timezone = get_latest_preference_value(user_id, "timezone") or "America/Los_Angeles"

    try:
        tz = ZoneInfo(user_timezone)
    except Exception:
        user_timezone = "America/Los_Angeles"
        tz = ZoneInfo(user_timezone)

    now = datetime.now(tz)

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

User timezone:
{user_timezone}

User preferences:
{pref_text}

User request:
{message}

Instructions:
- Extract a clean event title.
- The event title must describe the meeting itself, not the conferencing platform.
- Do not include words like "Google Meet", "Meet link", "video call", or "meeting link" in the title unless the user explicitly wants that phrase as part of the title.
- Infer the correct start and end datetime.
- Interpret all dates and times in {user_timezone} unless the user explicitly specifies another timezone.
- Return start and end as ISO datetime strings in local {user_timezone} time.
- Do not return UTC values.
- Do not return a trailing "Z".
- Return naive local ISO strings like 2026-04-16T15:00:00.
- Default duration to {default_duration} minutes unless user specifies otherwise.
- {preferred_time_note}
- If user says "tomorrow afternoon", choose a sensible afternoon time like 2:00 PM.
- Detect whether the user wants no conference link or a Google Meet link.
- Return conference_type as either "none" or "google_meet".
- If the user mentions Google Meet, Meet link, video call, or meeting link, use "google_meet".
- Return only structured output.
"""

    result = invoke_structured_with_fallback(CalendarEventExtraction, prompt)

    event_payload = {
        "summary": (result.summary or "").strip(),
        "start": normalize_local_iso(result.start or ""),
        "end": normalize_local_iso(result.end or ""),
        "conference_type": (getattr(result, "conference_type", "none") or "none").strip().lower(),
    }

    summary = event_payload["summary"]
    summary = re.sub(r"\bgoogle meet\b", "", summary, flags=re.IGNORECASE).strip()
    summary = re.sub(r"\bmeet link\b", "", summary, flags=re.IGNORECASE).strip()
    summary = re.sub(r"\bvideo call\b", "", summary, flags=re.IGNORECASE).strip()
    summary = re.sub(r"\s{2,}", " ", summary).strip(" -:")

    event_payload["summary"] = summary or "Meeting"

    allowed_conference_types = {"none", "google_meet"}
    if event_payload["conference_type"] not in allowed_conference_types:
        event_payload["conference_type"] = "none"

    if not event_payload["summary"]:
        return {
            "draft_event": event_payload,
            "policy_decision": "clarify",
            "policy_reason": "I need an event title or purpose before I can prepare the calendar event.",
            "approval_required": False,
            "approval_payload": {},
            "tool_used": "calendar_prepare_event",
        }

    if not event_payload["start"] or not event_payload["end"]:
        return {
            "draft_event": event_payload,
            "policy_decision": "clarify",
            "policy_reason": "I could not determine the event time. Please provide a clearer date or time.",
            "approval_required": False,
            "approval_payload": {},
            "tool_used": "calendar_prepare_event",
        }

    try:
        start_dt = datetime.fromisoformat(event_payload["start"])
        end_dt = datetime.fromisoformat(event_payload["end"])
    except ValueError:
        return {
            "draft_event": event_payload,
            "policy_decision": "clarify",
            "policy_reason": "The event time format looks invalid. Please try again with a clearer time.",
            "approval_required": False,
            "approval_payload": {},
            "tool_used": "calendar_prepare_event",
        }

    requested_hour = extract_requested_hour(message)
    if requested_hour is not None and start_dt.hour != requested_hour:
        return {
            "draft_event": event_payload,
            "policy_decision": "clarify",
            "policy_reason": f"I interpreted the meeting as {start_dt.strftime('%-I:%M %p')}, but you mentioned {requested_hour % 12 or 12}:00 {'PM' if requested_hour >= 12 else 'AM'}. Please confirm the intended time.",
            "approval_required": False,
            "approval_payload": {},
            "tool_used": "calendar_prepare_event",
        }

    if end_dt <= start_dt:
        return {
            "draft_event": event_payload,
            "policy_decision": "clarify",
            "policy_reason": "The event end time must be after the start time.",
            "approval_required": False,
            "approval_payload": {},
            "tool_used": "calendar_prepare_event",
        }

    print("RAW CALENDAR EXTRACTION:", result)
    print("EVENT PAYLOAD:", event_payload)

    return {
        "draft_event": event_payload,
        "action_payload": {
            "action": "create_calendar_event",
            "event": event_payload,
        },
        "tool_used": "calendar_prepare_event",
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


@traceable(run_type="chain", name="policy_check")
def policy_check(state: AssistantState) -> AssistantState:
    existing_decision = state.get("policy_decision")
    if existing_decision in {"clarify", "deny"}:
        return {
            "policy_decision": existing_decision,
            "policy_reason": state.get("policy_reason", "More information is required."),
            "risk_level": state.get("risk_level", ""),
            "approval_required": False,
            "approval_payload": {},
        }

    action_type_value = state.get("action_type", "")
    action_payload = state.get("action_payload", {})

    if not action_type_value:
        return {
            "policy_decision": PolicyDecision.CLARIFY.value,
            "policy_reason": "No action type detected.",
            "risk_level": "",
            "approval_required": False,
            "approval_payload": {},
        }

    try:
        action_type = ActionType(action_type_value)
    except ValueError:
        return {
            "policy_decision": PolicyDecision.CLARIFY.value,
            "policy_reason": f"Unsupported action type: {action_type_value}",
            "risk_level": "",
            "approval_required": False,
            "approval_payload": {},
        }

    result = evaluate_policy(
        action_type,
        {
            "message": state.get("message", ""),
            "action_payload": action_payload,
        },
    )

    decision = result["decision"]
    risk = result["risk"]

    return {
        "policy_decision": decision.value if hasattr(decision, "value") else str(decision),
        "policy_reason": result["reason"],
        "risk_level": risk.value if hasattr(risk, "value") else str(risk),
        "approval_required": (
            decision == PolicyDecision.REQUIRE_APPROVAL
            or getattr(decision, "value", "") == PolicyDecision.REQUIRE_APPROVAL.value
        ),
    }


@traceable(run_type="chain", name="build_approval_payload")
def build_approval_payload(state: AssistantState) -> AssistantState:
    user_id = state.get("user_id", "default_user")
    timezone_str = get_latest_preference_value(user_id, "timezone") or "America/Los_Angeles"
    payload = {
        "action_type": state.get("action_type", ""),
        "risk_level": state.get("risk_level", ""),
        "reason": state.get("policy_reason", ""),
        "payload": state.get("action_payload", {}),
        "timezone": timezone_str,
    }

    if state.get("conflict_found"):
        payload["conflict_found"] = True
        payload["conflict_details"] = state.get("conflict_details", [])
        payload["suggested_event"] = state.get("suggested_event", {})

    return {
        "reply": "Please review and approve this action.",
        "approval_required": True,
        "approval_payload": payload,
    }


@traceable(run_type="chain", name="respond_policy_result")
def respond_policy_result(state: AssistantState) -> AssistantState:
    decision = state.get("policy_decision", "")
    reason = state.get("policy_reason", "No reason provided.")

    if decision == PolicyDecision.DENY.value:
        return {
            "reply": f"I can’t perform that action. {reason}",
            "tool_used": "policy",
        }

    if decision == PolicyDecision.CLARIFY.value:
        return {
            "reply": f"I need a bit more information before I do that. {reason}",
            "tool_used": "policy",
        }

    return state


@traceable(run_type="chain", name="prepare_daily_briefing")
def prepare_daily_briefing(state: AssistantState) -> AssistantState:
    user_id = state.get("user_id", "default_user")
    email_items = state.get("email_summary", [])
    calendar_events = state.get("calendar_events", [])
    prefs = get_preferences(user_id)
    open_tasks = get_open_tasks(user_id)

    pref_text = "; ".join([p["value"] for p in prefs[:5]]) if prefs else "No stored preferences."

    email_lines = [
        f"{item.get('subject', '(No Subject)')} from {item.get('sender', 'Unknown')}"
        for item in email_items[:5]
    ]

    calendar_lines = [
        f"{event.get('summary', '(No Title)')} from {event.get('start', '')} to {event.get('end', '')}"
        for event in calendar_events[:5]
    ]

    follow_up_lines = []
    task_lines = []

    for task in open_tasks[:10]:
        due = task.get("due_at") or "No due date"
        line = f"{task.get('title', '(Untitled Task)')} — due {due}"

        if task.get("source") == "follow_up":
            follow_up_lines.append(line)
        else:
            task_lines.append(line)

    email_context = "\n".join(email_lines) if email_lines else "No unread emails."
    calendar_context = "\n".join(calendar_lines) if calendar_lines else "No events scheduled today."
    follow_up_context = "\n".join(follow_up_lines) if follow_up_lines else "No open follow-ups."
    task_context = "\n".join(task_lines) if task_lines else "No open tasks."

    prompt = f"""
You are preparing a concise daily briefing for a personal AI assistant user.

User preferences:
{pref_text}

Unread emails:
{email_context}

Today's calendar:
{calendar_context}

Open follow-ups:
{follow_up_context}

Open tasks:
{task_context}

Instructions:
- Summarize only the most relevant unread emails.
- Summarize today's meetings clearly.
- Mention follow-ups separately from regular tasks.
- Include open tasks that are due soon or important.
- Suggest 2-3 practical priorities for the day.
- If there are no meetings, suggest focus time for the highest priority task.
- Keep it concise, useful, and assistant-like.
- Return only structured output.
"""

    result = invoke_structured_with_fallback(DailyBriefingExtraction, prompt)

    return {
        "daily_briefing": {
            "email_summary": result.email_summary,
            "calendar_summary": result.calendar_summary,
            "follow_ups": follow_up_lines,
            "tasks": task_lines,
            "priorities": result.priorities,
            "overall_brief": result.overall_brief,
        },
        "briefing_ready": True,
        "tool_used": "daily_briefing",
    }


@traceable(run_type="chain", name="respond_daily_briefing")
def respond_daily_briefing(state: AssistantState) -> AssistantState:
    briefing = state.get("daily_briefing", {})

    if not briefing:
        return {
            "reply": "I couldn't prepare your daily briefing right now.",
            "tool_used": "daily_briefing",
        }

    priorities = briefing.get("priorities", [])
    follow_ups = briefing.get("follow_ups", [])
    tasks = briefing.get("tasks", [])

    priority_text = "\n".join([f"- {p}" for p in priorities]) if isinstance(priorities, list) else str(priorities)
    follow_up_text = "\n".join([f"- {f}" for f in follow_ups]) if follow_ups else "No open follow-ups."
    task_text = "\n".join([f"- {t}" for t in tasks]) if tasks else "No open tasks."

    reply = (
        f"Here’s your daily briefing:\n\n"
        f"📩 Emails:\n{briefing.get('email_summary', '-')}\n\n"
        f"📅 Calendar:\n{briefing.get('calendar_summary', '-')}\n\n"
        f"📌 Follow-ups:\n{follow_up_text}\n\n"
        f"✅ Tasks:\n{task_text}\n\n"
        f"🎯 Top priorities:\n{priority_text}\n\n"
        f"🧠 Overview:\n{briefing.get('overall_brief', '-')}"
    )

    return {
        "reply": reply,
        "tool_used": "daily_briefing",
    }

@traceable(run_type="chain", name="prepare_task_from_message")
def prepare_task_from_message(state: AssistantState) -> AssistantState:
    user_id = state.get("user_id", "default_user")
    message = state.get("message", "")
    timezone_str = get_latest_preference_value(user_id, "timezone") or "America/Los_Angeles"

    try:
        tz = ZoneInfo(timezone_str)
    except Exception:
        timezone_str = "America/Los_Angeles"
        tz = ZoneInfo(timezone_str)

    now = datetime.now(tz)

    prompt = f"""
You are extracting a task/reminder for a personal AI assistant.

Current datetime:
{now.isoformat()}

User timezone:
{timezone_str}

User request:
{message}

Instructions:
- Extract a short task title.
- Extract due_at as ISO datetime if a due time/date is mentioned.
- Interpret relative dates like tonight, tomorrow, in 3 days using the current datetime and user timezone.
- If user says tonight, choose 8:00 PM.
- If no due time is provided, return an empty string for due_at.
- source should be one of: manual, follow_up, job_search, email, calendar.
- If it is about following up with someone, use source "follow_up".
- Return only structured output.
"""

    result = invoke_structured_with_fallback(TaskExtraction, prompt)

    task = {
        "title": (result.title or "").strip(),
        "due_at": (result.due_at or "").strip(),
        "source": (result.source or "manual").strip(),
    }

    if not task["title"]:
        return {
            "policy_decision": "clarify",
            "policy_reason": "I need a task title before I can create a reminder.",
            "approval_required": False,
            "approval_payload": {},
            "tool_used": "task_prepare",
        }

    return {
        "task": task,
        "tool_used": "task_prepare",
    }


@traceable(run_type="chain", name="create_task_node")
def create_task_node(state: AssistantState) -> AssistantState:
    user_id = state.get("user_id", "default_user")
    task = state.get("task", {})

    if not task or not task.get("title"):
        return {
            "reply": "I couldn't create the task because the title is missing.",
            "tool_used": "task",
        }

    task_id = create_task(
        user_id=user_id,
        title=task["title"],
        due_at=task.get("due_at") or None,
        source=task.get("source", "manual"),
        metadata={"created_from": state.get("message", "")},
    )

    due_text = f" Due: {task['due_at']}" if task.get("due_at") else ""

    return {
        "task_id": task_id,
        "reply": f"Done — I created task #{task_id}: {task['title']}.{due_text}",
        "tool_used": "task",
    }


@traceable(run_type="chain", name="list_tasks_node")
def list_tasks_node(state: AssistantState) -> AssistantState:
    user_id = state.get("user_id", "default_user")
    tasks = get_open_tasks(user_id)

    if not tasks:
        return {
            "tasks": [],
            "reply": "You have no open tasks right now.",
            "tool_used": "task",
        }

    lines = ["Here are your open tasks:"]
    for task in tasks[:10]:
        due = task.get("due_at") or "No due date"
        lines.append(f"{task['id']}. {task['title']} — {due}")

    return {
        "tasks": tasks,
        "reply": "\n".join(lines),
        "tool_used": "task",
    }


@traceable(run_type="chain", name="complete_task_node")
def complete_task_node(state: AssistantState) -> AssistantState:
    user_id = state.get("user_id", "default_user")
    message = state.get("message", "").lower()

    match = re.search(r"\btask\s+(\d+)", message)
    if not match:
        return {
            "reply": "Which task should I mark done? Say something like: mark task 1 done.",
            "tool_used": "task",
        }

    task_id = int(match.group(1))
    success = mark_task_done(user_id, task_id)

    if not success:
        return {
            "reply": f"I couldn't find open task #{task_id}.",
            "tool_used": "task",
        }

    return {
        "task_id": task_id,
        "reply": f"Done — task #{task_id} is marked complete.",
        "tool_used": "task",
    }

@traceable(run_type="chain", name="prepare_meeting_prep")
def prepare_meeting_prep(state: AssistantState) -> AssistantState:
    user_id = state.get("user_id", "default_user")
    events = state.get("upcoming_events", [])
    prefs = get_preferences(user_id)
    open_tasks = get_open_tasks(user_id)

    if not events or len(events) == 0:
        return {
            "reply": "I couldn't find any upcoming meetings to prepare for.",
            "tool_used": "meeting_prep",
        }

    next_meeting = events[0]

    pref_text = "; ".join([p["value"] for p in prefs[:5]]) if prefs else "No stored preferences."

    task_lines = []
    for task in open_tasks[:5]:
        due = task.get("due_at") or "No due date"
        task_lines.append(f"{task.get('title')} — due {due}")

    task_context = "\n".join(task_lines) if task_lines else "No open tasks."

    prompt = f"""
You are preparing the user for their next meeting.

User preferences:
{pref_text}

Next meeting:
Title: {next_meeting.get("summary")}
Start: {next_meeting.get("start")}
End: {next_meeting.get("end")}
Location: {next_meeting.get("location")}
Description: {next_meeting.get("description")}
Attendees: {", ".join(next_meeting.get("attendees", []))}
Meet link: {next_meeting.get("meetLink")}

Open tasks:
{task_context}

Instructions:
- Summarize what this meeting is likely about.
- Mention meeting time and link if available.
- Suggest 3 useful talking points.
- Suggest 2-3 actions the user should take before the meeting.
- Keep it concise and practical.
- Return only structured output.
- Do not suggest checking or reviewing the meeting link.
- Make suggested actions specific and useful.
- Suggested actions should relate to tasks, preparation, blockers, updates, or follow-ups.
- Avoid generic advice like "come prepared" unless it includes a concrete action.
"""

    result = invoke_structured_with_fallback(MeetingPrepExtraction, prompt)

    return {
        "next_meeting": next_meeting,
        "meeting_prep": {
            "meeting_summary": result.meeting_summary,
            "context": result.context,
            "talking_points": result.talking_points,
            "suggested_actions": result.suggested_actions,
        },
        "meeting_prep_ready": True,
        "tool_used": "meeting_prep",
    }


@traceable(run_type="chain", name="respond_meeting_prep")
def respond_meeting_prep(state: AssistantState) -> AssistantState:
    meeting = state.get("next_meeting", {})
    prep = state.get("meeting_prep", {})

    if not meeting or not prep:
        return {
            "reply": "I couldn't prepare for your next meeting right now.",
            "tool_used": "meeting_prep",
        }

    talking_points = prep.get("talking_points", [])
    actions = prep.get("suggested_actions", [])

    talking_text = (
        "\n".join([f"- {p}" for p in talking_points])
        if isinstance(talking_points, list)
        else str(talking_points)
    )

    # Remove weak / redundant actions
    filtered_actions = []
    for action in actions if isinstance(actions, list) else [str(actions)]:
        lowered = action.lower()
        if "meeting link" in lowered or "review the link" in lowered or "ensure you can join" in lowered:
            continue
        filtered_actions.append(action)

    action_text = (
        "\n".join([f"- {a}" for a in filtered_actions])
        if filtered_actions
        else "- Prepare a quick update on your current work\n- Bring 1–2 blockers or questions\n- Review any related tasks before the meeting"
    )

    link_text = meeting.get("meetLink") or meeting.get("htmlLink") or "No meeting link found."
    time_text = format_event_time(meeting.get("start", ""), meeting.get("end", ""))

    reply = (
        f"Here’s your prep for the next meeting:\n\n"
        f"📅 Meeting:\n{meeting.get('summary')} — {time_text}\n\n"
        f"🔗 Link:\n{link_text}\n\n"
        f"🧠 Context:\n{prep.get('context', '-')}\n\n"
        f"💬 Talking points:\n{talking_text}\n\n"
        f"✅ Suggested actions:\n{action_text}"
    )

    return {
        "reply": reply,
        "tool_used": "meeting_prep",
    }

def format_event_time(start: str, end: str) -> str:
    try:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)

        start_text = start_dt.strftime("%b %-d, %-I:%M %p")
        end_text = end_dt.strftime("%-I:%M %p")

        return f"{start_text} – {end_text}"
    except Exception:
        return f"{start} to {end}"