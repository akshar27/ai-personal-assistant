from typing import TypedDict, List, Dict, Any, Optional


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

    # New fields for policy layer
    action_type: str
    action_payload: Dict[str, Any]

    policy_decision: str
    policy_reason: str
    risk_level: str
    pending_clarification_context: Dict[str, Any]

    daily_briefing: Dict[str, Any]
    briefing_ready: bool

    task: Dict[str, Any]
    tasks: List[dict]
    task_id: int

    upcoming_events: List[dict]
    next_meeting: Dict[str, Any]
    meeting_prep: Dict[str, Any]
    meeting_prep_ready: bool