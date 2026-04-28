from langgraph.graph import StateGraph, END
from langgraph.types import interrupt
from langgraph.checkpoint.memory import InMemorySaver

from graph.state import AssistantState
from graph.nodes import (
    detect_intent,
    respond_chat,
    respond_email_summary,
    respond_calendar_today,
    handle_remember_preference,
    prepare_email_draft,
    prepare_calendar_event_draft,
    respond_conflict_suggestion,
    select_unread_email,
    prepare_reply_to_unread_email,
    policy_check,
    build_approval_payload,
    respond_policy_result,
    prepare_daily_briefing,
    respond_daily_briefing,
    prepare_task_from_message,
    create_task_node,
    list_tasks_node,
    complete_task_node,
    prepare_meeting_prep,
    respond_meeting_prep,
)
from graph.tools import (
    fetch_email_summary,
    fetch_calendar_today,
    create_email_draft_tool,
    create_email_reply_draft_tool,
    create_calendar_event_tool,
    check_calendar_conflicts_tool,
    fetch_selected_email_tool,
    fetch_upcoming_events_tool,
)


def approval_node(state: AssistantState) -> AssistantState:
    payload = state.get("approval_payload", {})
    decision = interrupt({
        "message": "Approve this action?",
        "payload": payload,
    })

    if not isinstance(decision, dict):
        return {
            "reply": "Approval response invalid.",
            "approved": False,
            "tool_used": "approval",
        }

    approved = bool(decision.get("approved", False))

    if not approved:
        return {
            "reply": "Action rejected. No action was taken.",
            "approved": False,
            "tool_used": "approval",
        }

    return {
        "approved": True,
        "tool_used": "approval",
    }


def route_intent(state: AssistantState) -> str:
    intent = state.get("intent", "chat")

    if intent == "remember_preference":
        return "remember_node"
    if intent == "draft_email":
        return "prepare_draft"
    if intent == "reply_to_unread_email":
        return "select_unread_email"
    if intent == "draft_calendar_event":
        return "prepare_calendar_draft"
    if intent == "email_summary":
        return "email_tool"
    if intent == "daily_briefing":
        return "email_tool"
    if intent == "calendar_today":
        return "calendar_tool"
    if intent == "create_task":
        return "prepare_task"
    if intent == "list_tasks":
        return "list_tasks"
    if intent == "complete_task":
        return "complete_task"
    if intent == "meeting_prep":
        return "upcoming_events_tool"

    return "chat_response"


def route_after_policy(state: AssistantState) -> str:
    decision = state.get("policy_decision", "")
    action_type = state.get("action_type", "")

    if decision == "allow":
        if action_type == "email_draft":
            return "create_draft"
        if action_type == "email_reply_draft":
            return "create_reply_draft"
        if action_type == "calendar_create":
            return "create_calendar_event"

        return "policy_response"

    if decision == "require_approval":
        return "build_approval"

    if decision in {"deny", "clarify"}:
        return "policy_response"

    return "policy_response"


def route_after_approval(state: AssistantState) -> str:
    if not state.get("approved"):
        return "end_rejected"

    action_type = state.get("action_type", "")

    if action_type == "email_draft":
        return "create_draft"

    if action_type == "email_reply_draft":
        return "create_reply_draft"

    if action_type == "calendar_create":
        return "create_calendar_event"

    return "end_rejected"


def route_after_conflict_check(state: AssistantState) -> str:
    return "policy_check"

def route_after_email_tool(state: AssistantState) -> str:
    if state.get("intent") == "daily_briefing":
        return "calendar_tool"
    return "email_response"

def route_after_calendar_tool(state: AssistantState) -> str:
    if state.get("intent") == "daily_briefing":
        return "prepare_daily_briefing"
    return "calendar_response"

def build_graph():
    graph = StateGraph(AssistantState)

    graph.add_node("detect_intent", detect_intent)
    graph.add_node("remember_node", handle_remember_preference)
    graph.add_node("prepare_draft", prepare_email_draft)

    graph.add_node("select_unread_email", select_unread_email)
    graph.add_node("fetch_selected_email", fetch_selected_email_tool)
    graph.add_node("prepare_reply_to_unread_email", prepare_reply_to_unread_email)

    graph.add_node("prepare_calendar_draft", prepare_calendar_event_draft)

    graph.add_node("policy_check", policy_check)
    graph.add_node("build_approval", build_approval_payload)
    graph.add_node("policy_response", respond_policy_result)

    graph.add_node("approval_node", approval_node)
    graph.add_node("create_draft", create_email_draft_tool)
    graph.add_node("create_reply_draft", create_email_reply_draft_tool)
    graph.add_node("create_calendar_event", create_calendar_event_tool)

    graph.add_node("email_tool", fetch_email_summary)
    graph.add_node("calendar_tool", fetch_calendar_today)
    graph.add_node("check_calendar_conflicts", check_calendar_conflicts_tool)

    graph.add_node("chat_response", respond_chat)
    graph.add_node("email_response", respond_email_summary)
    graph.add_node("calendar_response", respond_calendar_today)
    graph.add_node("conflict_response", respond_conflict_suggestion)

    graph.add_node("prepare_daily_briefing", prepare_daily_briefing)
    graph.add_node("daily_briefing_response", respond_daily_briefing)

    graph.add_node("prepare_task", prepare_task_from_message)
    graph.add_node("create_task", create_task_node)
    graph.add_node("list_tasks", list_tasks_node)
    graph.add_node("complete_task", complete_task_node)

    graph.add_node("upcoming_events_tool", fetch_upcoming_events_tool)
    graph.add_node("prepare_meeting_prep", prepare_meeting_prep)
    graph.add_node("meeting_prep_response", respond_meeting_prep)

    graph.set_entry_point("detect_intent")

    graph.add_conditional_edges(
        "detect_intent",
        route_intent,
        {
            "remember_node": "remember_node",
            "prepare_draft": "prepare_draft",
            "select_unread_email": "select_unread_email",
            "prepare_calendar_draft": "prepare_calendar_draft",
            "email_tool": "email_tool",
            "calendar_tool": "calendar_tool",
            "chat_response": "chat_response",
            "prepare_task": "prepare_task",
            "list_tasks": "list_tasks",
            "complete_task": "complete_task",
            "upcoming_events_tool": "upcoming_events_tool",
        },
    )

    graph.add_edge("remember_node", END)

    # Email draft flow
    graph.add_edge("prepare_draft", "policy_check")

    # Reply-to-email flow
    graph.add_edge("select_unread_email", "fetch_selected_email")
    graph.add_edge("fetch_selected_email", "prepare_reply_to_unread_email")
    graph.add_edge("prepare_reply_to_unread_email", "policy_check")

    graph.add_edge("upcoming_events_tool", "prepare_meeting_prep")
    graph.add_edge("prepare_meeting_prep", "meeting_prep_response")

    # Calendar flow
    graph.add_edge("prepare_calendar_draft", "check_calendar_conflicts")
    graph.add_conditional_edges(
        "check_calendar_conflicts",
        route_after_conflict_check,
        {
            "policy_check": "policy_check",
        },
    )

    # Policy routing
    graph.add_conditional_edges(
        "policy_check",
        route_after_policy,
        {
            "create_draft": "create_draft",
            "create_reply_draft": "create_reply_draft",
            "create_calendar_event": "create_calendar_event",
            "build_approval": "build_approval",
            "policy_response": "policy_response",
        },
    )

    # Approval payload builder
    graph.add_edge("build_approval", "approval_node")

    # Approval routing
    graph.add_conditional_edges(
        "approval_node",
        route_after_approval,
        {
            "create_draft": "create_draft",
            "create_reply_draft": "create_reply_draft",
            "create_calendar_event": "create_calendar_event",
            "end_rejected": END,
        },
    )

    # Final execution paths
    graph.add_edge("create_draft", END)
    graph.add_edge("create_reply_draft", END)
    graph.add_edge("create_calendar_event", END)

    # Read-only tool flows
    graph.add_conditional_edges(
        "email_tool",
        route_after_email_tool,
        {
            "calendar_tool": "calendar_tool",
            "email_response": "email_response",
        },
    )

    graph.add_conditional_edges(
        "calendar_tool",
        route_after_calendar_tool,
        {
            "prepare_daily_briefing": "prepare_daily_briefing",
            "calendar_response": "calendar_response",
        },
    )

    # End states
    graph.add_edge("chat_response", END)
    graph.add_edge("email_response", END)
    graph.add_edge("calendar_response", END)
    graph.add_edge("conflict_response", END)
    graph.add_edge("policy_response", END)
    graph.add_edge("prepare_daily_briefing", "daily_briefing_response")
    graph.add_edge("daily_briefing_response", END)
    graph.add_edge("prepare_task", "create_task")
    graph.add_edge("create_task", END)
    graph.add_edge("list_tasks", END)
    graph.add_edge("complete_task", END)
    graph.add_edge("meeting_prep_response", END)

    checkpointer = InMemorySaver()
    return graph.compile(checkpointer=checkpointer)