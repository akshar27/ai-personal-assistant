from datetime import datetime, timedelta
from langsmith import traceable

from graph.state import AssistantState
from integrations.gmail_client import (
    list_unread_emails,
    create_gmail_draft,
    create_gmail_reply_draft,
    get_email_by_id,
)
from integrations.calendar_client import (
    get_today_events,
    create_calendar_event,
    get_events_in_range,
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
    result = create_gmail_draft(
        to=draft["to"],
        subject=draft["subject"],
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


@traceable(run_type="tool", name="check_calendar_conflicts_tool")
def check_calendar_conflicts_tool(state: AssistantState) -> AssistantState:
    event = state.get("draft_event", {})
    start_iso = event["start"]
    end_iso = event["end"]

    conflicts = get_events_in_range(start_iso, end_iso)

    if not conflicts:
        return {
            "conflict_found": False,
            "conflict_details": [],
            "approval_required": True,
            "approval_payload": {
                "action": "create_calendar_event",
                "event": event,
                "note": "No calendar conflicts found.",
                "conflicts": [],
            },
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
    }

    return {
        "conflict_found": True,
        "conflict_details": conflicts,
        "suggested_event": suggested_event,
        "approval_required": True,
        "approval_payload": {
            "action": "create_calendar_event",
            "event": suggested_event,
            "note": "Requested slot was busy. Suggested next available slot instead.",
            "conflicts": conflicts,
        },
    }


@traceable(run_type="tool", name="create_calendar_event_tool")
def create_calendar_event_tool(state: AssistantState) -> AssistantState:
    event = state.get("suggested_event") or state.get("draft_event", {})
    result = create_calendar_event(
        summary=event["summary"],
        start_iso=event["start"],
        end_iso=event["end"],
    )
    return {
        "reply": f"Calendar event created successfully. Event: {result['summary']}. Link: {result['htmlLink']}",
        "tool_used": "calendar_event",
    }