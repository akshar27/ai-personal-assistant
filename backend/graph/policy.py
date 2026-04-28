from enum import Enum
from typing import Any, Dict, Optional


class ActionType(str, Enum):
    EMAIL_SUMMARIZE = "email_summarize"
    EMAIL_DRAFT = "email_draft"
    EMAIL_REPLY_DRAFT = "email_reply_draft"
    EMAIL_SEND = "email_send"
    CALENDAR_CREATE = "calendar_create"
    CALENDAR_UPDATE = "calendar_update"
    CALENDAR_DELETE = "calendar_delete"
    MEMORY_WRITE = "memory_write"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PolicyDecision(str, Enum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"
    CLARIFY = "clarify"


ACTION_RISK_MAP = {
    ActionType.EMAIL_SUMMARIZE: RiskLevel.LOW,
    ActionType.EMAIL_DRAFT: RiskLevel.MEDIUM,
    ActionType.EMAIL_REPLY_DRAFT: RiskLevel.MEDIUM,
    ActionType.EMAIL_SEND: RiskLevel.HIGH,
    ActionType.CALENDAR_CREATE: RiskLevel.MEDIUM,
    ActionType.CALENDAR_UPDATE: RiskLevel.MEDIUM,
    ActionType.CALENDAR_DELETE: RiskLevel.HIGH,
    ActionType.MEMORY_WRITE: RiskLevel.LOW,
}


def evaluate_policy(
    action_type: ActionType,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    context = context or {}
    risk = ACTION_RISK_MAP.get(action_type, RiskLevel.MEDIUM)

    if action_type == ActionType.EMAIL_SUMMARIZE:
        return {
            "decision": PolicyDecision.ALLOW,
            "risk": risk,
            "reason": "Email summarization is read-only.",
        }

    if action_type in {
        ActionType.EMAIL_DRAFT,
        ActionType.EMAIL_REPLY_DRAFT,
        ActionType.CALENDAR_CREATE,
        ActionType.CALENDAR_UPDATE,
    }:
        return {
            "decision": PolicyDecision.REQUIRE_APPROVAL,
            "risk": risk,
            "reason": "This action changes user-facing state and should be approved.",
        }

    if action_type in {ActionType.EMAIL_SEND, ActionType.CALENDAR_DELETE}:
        return {
            "decision": PolicyDecision.REQUIRE_APPROVAL,
            "risk": risk,
            "reason": "This is a high-risk external action.",
        }

    if action_type == ActionType.MEMORY_WRITE:
        return {
            "decision": PolicyDecision.ALLOW,
            "risk": risk,
            "reason": "Memory write is low-risk.",
        }

    return {
        "decision": PolicyDecision.CLARIFY,
        "risk": risk,
        "reason": "Unknown action. Need clarification.",
    }