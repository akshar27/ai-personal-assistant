import json
from pprint import pprint

from eval.dataset import TEST_CASES
from eval.evaluators import (
    evaluate_common_fields,
    evaluate_email_draft,
    evaluate_calendar,
)
from graph.assistant_graph import build_graph


def run_single_test(graph, test_case: dict) -> dict:
    user_id = "eval_user"
    thread_id = f"eval_{test_case['name']}"

    initial_state = {
        "user_id": user_id,
        "message": test_case["input"],
    }

    result = graph.invoke(
        initial_state,
        config={"configurable": {"thread_id": thread_id}},
    )

    errors = []
    errors.extend(evaluate_common_fields(result, test_case))
    errors.extend(evaluate_email_draft(result, test_case))
    errors.extend(evaluate_calendar(result, test_case))

    return {
        "name": test_case["name"],
        "input": test_case["input"],
        "passed": len(errors) == 0,
        "errors": errors,
        "result": result,
    }


def main():
    graph = build_graph()
    outputs = []

    for test_case in TEST_CASES:
        print(f"\nRunning: {test_case['name']}")
        output = run_single_test(graph, test_case)
        outputs.append(output)

        if output["passed"]:
            print("PASS")
        else:
            print("FAIL")
            for err in output["errors"]:
                print(" -", err)

    passed = sum(1 for x in outputs if x["passed"])
    total = len(outputs)

    print(f"\nSummary: {passed}/{total} passed")

    with open("eval_results.json", "w") as f:
        json.dump(outputs, f, indent=2, default=str)

    print("Saved results to eval_results.json")


if __name__ == "__main__":
    main()