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
)
from graph.tools import (
    fetch_email_summary,
    fetch_calendar_today,
    create_email_draft_tool,
    create_email_reply_draft_tool,
    create_calendar_event_tool,
    check_calendar_conflicts_tool,
    fetch_selected_email_tool,
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
    if intent == "calendar_today":
        return "calendar_tool"
    return "chat_response"


def route_after_approval(state: AssistantState) -> str:
    payload = state.get("approval_payload", {})
    action = payload.get("action")

    if not state.get("approved"):
        return "end_rejected"

    if action == "create_gmail_draft":
        return "create_draft"

    if action == "create_gmail_reply_draft":
        return "create_reply_draft"

    if action == "create_calendar_event":
        return "create_calendar_event"

    return "end_rejected"


def route_after_conflict_check(state: AssistantState) -> str:
    return "approval_node"


def build_graph():
    graph = StateGraph(AssistantState)

    graph.add_node("detect_intent", detect_intent)
    graph.add_node("remember_node", handle_remember_preference)
    graph.add_node("prepare_draft", prepare_email_draft)

    graph.add_node("select_unread_email", select_unread_email)
    graph.add_node("fetch_selected_email", fetch_selected_email_tool)
    graph.add_node("prepare_reply_to_unread_email", prepare_reply_to_unread_email)

    graph.add_node("prepare_calendar_draft", prepare_calendar_event_draft)

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
        },
    )

    graph.add_edge("remember_node", END)

    graph.add_edge("prepare_draft", "approval_node")

    graph.add_edge("select_unread_email", "fetch_selected_email")
    graph.add_edge("fetch_selected_email", "prepare_reply_to_unread_email")
    graph.add_edge("prepare_reply_to_unread_email", "approval_node")

    graph.add_edge("prepare_calendar_draft", "check_calendar_conflicts")
    graph.add_conditional_edges(
        "check_calendar_conflicts",
        route_after_conflict_check,
        {
            "approval_node": "approval_node",
        },
    )

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

    graph.add_edge("create_draft", END)
    graph.add_edge("create_reply_draft", END)
    graph.add_edge("create_calendar_event", END)

    graph.add_edge("email_tool", "email_response")
    graph.add_edge("calendar_tool", "calendar_response")
    graph.add_edge("chat_response", END)
    graph.add_edge("email_response", END)
    graph.add_edge("calendar_response", END)
    graph.add_edge("conflict_response", END)

    checkpointer = InMemorySaver()
    return graph.compile(checkpointer=checkpointer)