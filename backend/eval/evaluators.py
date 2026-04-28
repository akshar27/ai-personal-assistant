def evaluate_common_fields(result: dict, test_case: dict) -> list[str]:
    errors = []

    if result.get("intent") != test_case.get("expected_intent"):
        errors.append(
            f"intent mismatch: expected={test_case.get('expected_intent')} actual={result.get('intent')}"
        )

    if result.get("action_type") != test_case.get("expected_action_type"):
        errors.append(
            f"action_type mismatch: expected={test_case.get('expected_action_type')} actual={result.get('action_type')}"
        )

    expected_requires_approval = test_case.get("expected_requires_approval")
    if expected_requires_approval is not None:
        if bool(result.get("approval_required")) != expected_requires_approval:
            errors.append(
                f"approval_required mismatch: expected={expected_requires_approval} actual={result.get('approval_required')}"
            )

    expected_policy = test_case.get("expected_policy_decision")
    if expected_policy is not None:
        if result.get("policy_decision") != expected_policy:
            errors.append(
                f"policy_decision mismatch: expected={expected_policy} actual={result.get('policy_decision')}"
            )

    return errors


def evaluate_email_draft(result: dict, test_case: dict) -> list[str]:
    errors = []
    if test_case["name"] == "draft_email_valid":
        draft = result.get("draft_email", {})
        if not draft.get("to"):
            errors.append("draft_email missing recipient")
        if not draft.get("body"):
            errors.append("draft_email missing body")
    return errors


def evaluate_calendar(result: dict, test_case: dict) -> list[str]:
    errors = []
    if result.get("intent") == "draft_calendar_event":
        draft_event = result.get("draft_event", {})
        if test_case.get("expected_policy_decision") != "clarify":
            if not draft_event.get("summary"):
                errors.append("draft_event missing summary")
            if not draft_event.get("start"):
                errors.append("draft_event missing start")
            if not draft_event.get("end"):
                errors.append("draft_event missing end")

        expected_conference_type = test_case.get("expected_conference_type")
        if expected_conference_type:
            if draft_event.get("conference_type") != expected_conference_type:
                errors.append(
                    f"conference_type mismatch: expected={expected_conference_type} actual={draft_event.get('conference_type')}"
                )

    return errors