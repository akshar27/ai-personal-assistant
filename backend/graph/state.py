from typing import TypedDict, List, Dict, Any


class AssistantState(TypedDict, total=False):
    user_id: str
    message: str
    intent: str
    reply: str
    tool_used: str

    email_summary: List[dict]
    calendar_events: List[dict]
    preferences: List[dict]

    unread_emails: List[dict]
    selected_email: Dict[str, Any]

    draft_email: Dict[str, Any]
    draft_event: Dict[str, Any]

    approval_required: bool
    approval_payload: Dict[str, Any]
    approved: bool

    conflict_found: bool
    conflict_details: List[dict]
    suggested_event: Dict[str, Any]