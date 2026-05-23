"""Routing eval — replay state snapshots, assert route_after_ingest returns
the expected node. Pure logic; no LLM."""

from __future__ import annotations

import sys

from evals.component._common import (
    assert_threshold,
    exit_on_failure,
    load_dataset,
    print_table,
)
from reglens.schemas.obligation import Obligation
from reglens.supervisor.nodes import route_after_ingest

ACCURACY_THRESHOLD = 1.0  # Routing must be perfect — deterministic logic.


def main() -> int:
    dataset = load_dataset("routing/scenarios.json")
    correct = 0
    mismatches: list[str] = []
    for item in dataset["items"]:
        raw_state = item["state"]
        obligations = raw_state.get("obligations") or []
        state = {
            **raw_state,
            "obligations": [Obligation.model_validate(o) for o in obligations],
        }
        actual = route_after_ingest(state)  # type: ignore[arg-type]
        if actual == item["expected_node"]:
            correct += 1
        else:
            mismatches.append(
                f"{item['scenario']}: expected {item['expected_node']}, got {actual}"
            )

    accuracy = correct / len(dataset["items"])
    print_table(
        "Routing eval",
        [
            ("accuracy", accuracy),
            ("correct", correct),
            ("total", len(dataset["items"])),
        ],
    )
    for m in mismatches:
        print(f"  ❌ {m}")

    failed: list[str] = []
    if not assert_threshold("accuracy", accuracy, ACCURACY_THRESHOLD):
        failed.append("accuracy")
    exit_on_failure(failed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
