from datetime import datetime, timedelta
from langsmith import traceable

from graph.state import AssistantState
from graph.memory import get_latest_preference_value
from retrieval.search import search_history
from integrations.gmail_client import (
    list_unread_emails,
    create_gmail_draft,
    create_gmail_reply_draft,
    send_gmail_message,
    get_email_by_id,
    gmail_link,
)
from integrations.calendar_client import (
    get_today_events,
    create_calendar_event,
    delete_calendar_event,
    get_events_in_range,
    get_upcoming_events,
)


@traceable(run_type="tool", name="fetch_email_summary")
def fetch_email_summary(state: AssistantState) -> AssistantState:
    items = list_unread_emails()
    return {
        "email_summary": items,
        "unread_emails": items,
    }


@traceable(run_type="tool", name="fetch_calendar_today")
def fetch_calendar_today(state: AssistantState) -> AssistantState:
    events = get_today_events()
    return {"calendar_events": events}


@traceable(run_type="tool", name="fetch_selected_email_tool")
def fetch_selected_email_tool(state: AssistantState) -> AssistantState:
    selected = state.get("selected_email", {})
    message_id = selected.get("id")
    if not message_id:
        raise RuntimeError("No selected email id found.")

    email = get_email_by_id(message_id)
    return {"selected_email": email}


@traceable(run_type="tool", name="create_email_draft_tool")
def create_email_draft_tool(state: AssistantState) -> AssistantState:
    draft = state.get("draft_email", {})

    if not draft:
        raise RuntimeError("No draft email found in state.")

    if not draft.get("to"):
        raise RuntimeError("Draft email is missing recipient.")
    if not draft.get("body"):
        raise RuntimeError("Draft email is missing body.")

    result = create_gmail_draft(
        to=draft["to"],
        subject=draft.get("subject", ""),
        body=draft["body"],
    )

    return {
        "reply": f"{result['message']} Draft ID: {result['id']}",
        "tool_used": "gmail_draft",
    }


@traceable(run_type="tool", name="create_email_reply_draft_tool")
def create_email_reply_draft_tool(state: AssistantState) -> AssistantState:
    draft = state.get("draft_email", {})
    selected_email = state.get("selected_email", {})

    if not draft:
        raise RuntimeError("No reply draft found in state.")
    if not selected_email:
        raise RuntimeError("No selected email found for reply draft.")
    if not selected_email.get("thread_id"):
        raise RuntimeError("Selected email is missing thread_id.")

    result = create_gmail_reply_draft(
        thread_id=selected_email["thread_id"],
        to=draft["to"],
        subject=draft["subject"],
        body=draft["body"],
    )

    return {
        "reply": f"{result['message']} Draft ID: {result['id']}",
        "tool_used": "gmail_reply_draft",
    }


@traceable(run_type="tool", name="send_email_tool")
def send_email_tool(state: AssistantState) -> AssistantState:
    email = state.get("send_email", {})
    if not email.get("to") or not email.get("body"):
        raise RuntimeError("No email to send (missing recipient or body).")

    result = send_gmail_message(
        to=email["to"], subject=email.get("subject", ""), body=email["body"]
    )
    return {
        "reply": f"Email sent to {email['to']}. (id: {result['id']})",
        "tool_used": "gmail_send",
    }


@traceable(run_type="tool", name="delete_event_tool")
def delete_event_tool(state: AssistantState) -> AssistantState:
    event = state.get("event_to_delete", {})
    if not event.get("id"):
        raise RuntimeError("No event selected to delete.")

    delete_calendar_event(event["id"])
    return {
        "reply": f"Cancelled: {event.get('summary', 'event')} ({event.get('start', '')}).",
        "tool_used": "calendar_delete",
    }


@traceable(run_type="tool", name="check_calendar_conflicts_tool")
def check_calendar_conflicts_tool(state: AssistantState) -> AssistantState:
    event = state.get("draft_event", {})

    if not event:
        raise RuntimeError("No draft event found in state.")

    user_id = state.get("user_id", "default_user")
    timezone_str = get_latest_preference_value(user_id, "timezone") or "America/Los_Angeles"

    start_iso = event["start"]
    end_iso = event["end"]

    conflicts = get_events_in_range(start_iso, end_iso, timezone_str)

    if not conflicts:
        return {
            "conflict_found": False,
            "conflict_details": [],
            "suggested_event": {},
        }

    start_dt = datetime.fromisoformat(start_iso)
    end_dt = datetime.fromisoformat(end_iso)
    duration = end_dt - start_dt

    suggested_start = end_dt + timedelta(minutes=30)
    suggested_end = suggested_start + duration

    suggested_event = {
        "summary": event["summary"],
        "start": suggested_start.isoformat(),
        "end": suggested_end.isoformat(),
        "conference_type": event.get("conference_type", "none"),
    }

    return {
        "conflict_found": True,
        "conflict_details": conflicts,
        "suggested_event": suggested_event,
    }


@traceable(run_type="tool", name="create_calendar_event_tool")
def create_calendar_event_tool(state: AssistantState) -> AssistantState:
    event = state.get("suggested_event") or state.get("draft_event", {})
    user_id = state.get("user_id", "default_user")
    timezone_str = get_latest_preference_value(user_id, "timezone") or "America/Los_Angeles"

    if not event:
        raise RuntimeError("No calendar event found in state.")
    if not event.get("summary"):
        raise RuntimeError("Calendar event is missing summary.")
    if not event.get("start") or not event.get("end"):
        raise RuntimeError("Calendar event is missing start or end time.")

    conference_type = event.get("conference_type", "none")

    result = create_calendar_event(
        summary=event["summary"],
        start_iso=event["start"],
        end_iso=event["end"],
        conference_type=conference_type,
        timezone_str=timezone_str,
    )

    reply = f"Calendar event created successfully. Event: {result['summary']}. Link: {result['htmlLink']}"

    if result.get("meetLink"):
        reply += f" Google Meet: {result['meetLink']}"

    return {
        "reply": reply,
        "tool_used": "calendar_event",
    }

@traceable(run_type="tool", name="retrieve_history_tool")
def retrieve_history_tool(state: AssistantState) -> AssistantState:
    """Semantic search over the user's indexed email history."""
    user_id = state.get("user_id", "default_user")
    query = state.get("message", "")

    hits = search_history(user_id, query)

    return {
        "history_query": query,
        "history_hits": [
            {
                "message_id": h.message_id,
                "thread_id": h.thread_id,
                "sender": h.sender,
                "subject": h.subject,
                "sent_at": h.sent_at,
                "text": h.text,
                "score": round(h.score, 4),
                "link": gmail_link(h.message_id),
            }
            for h in hits
        ],
        "tool_used": "history_search",
    }


@traceable(run_type="tool", name="fetch_upcoming_events_tool")
def fetch_upcoming_events_tool(state: AssistantState) -> AssistantState:
    user_id = state.get("user_id", "default_user")
    timezone_str = get_latest_preference_value(user_id, "timezone") or "America/Los_Angeles"

    events = get_upcoming_events(
        max_results=5,
        timezone_str=timezone_str,
    )

    return {
        "upcoming_events": events,
        "tool_used": "calendar_upcoming",
    }