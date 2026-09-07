from graph.policy import ActionType, PolicyDecision, RiskLevel, evaluate_policy


def test_read_only_actions_are_allowed():
    for action in (ActionType.EMAIL_SUMMARIZE, ActionType.MEMORY_WRITE):
        result = evaluate_policy(action)
        assert result["decision"] == PolicyDecision.ALLOW
        assert result["risk"] == RiskLevel.LOW


def test_state_changing_actions_need_approval():
    for action in (
        ActionType.EMAIL_DRAFT,
        ActionType.EMAIL_REPLY_DRAFT,
        ActionType.CALENDAR_CREATE,
        ActionType.CALENDAR_UPDATE,
    ):
        result = evaluate_policy(action)
        assert result["decision"] == PolicyDecision.REQUIRE_APPROVAL
        assert result["risk"] == RiskLevel.MEDIUM


def test_high_risk_external_actions_need_approval_and_are_high_risk():
    for action in (ActionType.EMAIL_SEND, ActionType.CALENDAR_DELETE):
        result = evaluate_policy(action)
        assert result["decision"] == PolicyDecision.REQUIRE_APPROVAL
        assert result["risk"] == RiskLevel.HIGH


def test_unknown_action_asks_for_clarification():
    result = evaluate_policy("something_new")  # not in the enum / risk map
    assert result["decision"] == PolicyDecision.CLARIFY
