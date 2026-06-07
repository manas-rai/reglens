"""Counterfactual test — removing the matching policy must flip status.

For each case: with the supporting policy present, status should be
COMPLIANT (or at least not GAP). After removing the policy, the same
obligation must classify as GAP or PARTIAL_GAP. Catches classifiers
that ignore the retrieved evidence and rely on prior alone.

Offline (stub) mode: harness smoke test only. The stub returns GAP
whenever matched_policies is empty by construction, so this test
trivially passes against it. Real signal requires LIVE_LLM=1.
"""

from __future__ import annotations

import sys

from evals.behavioral._runner import capture_guards, classify_gap, print_mode_banner
from evals.component._common import assert_threshold, exit_on_failure, print_table

GUARD_FIRE_RATE_CEILING = 0.25

CASES: list[dict] = [
    {
        "scenario": "leverage_ratio",
        "obligation_text": "Maintain leverage ratio above 4% per Basel III framework.",
        "supporting_policy": {
            "id": "p1",
            "text": "Leverage ratio target is 4.5% per Basel III framework reviewed quarterly.",
        },
        "expected_with": "compliant",
        "expected_without": "gap",
    },
    {
        "scenario": "audit_committee",
        "obligation_text": "An independent audit committee must oversee financial reporting controls.",
        "supporting_policy": {
            "id": "p2",
            "text": "Independent audit committee oversees financial reporting controls quarterly.",
        },
        "expected_with": "compliant",
        "expected_without": "gap",
    },
]


def main() -> int:
    print_mode_banner("counterfactual")
    pass_count = 0
    failures: list[str] = []
    total_calls = 0
    with capture_guards() as guards:
        for case in CASES:
            with_status = classify_gap(
                case["obligation_text"], [case["supporting_policy"]]
            )
            without_status = classify_gap(case["obligation_text"], [])
            total_calls += 2
            ok_with = with_status == case["expected_with"]
            ok_without = without_status == case["expected_without"]
            if ok_with and ok_without:
                pass_count += 1
            else:
                failures.append(
                    f"{case['scenario']}: with={with_status} (expected {case['expected_with']}), "
                    f"without={without_status} (expected {case['expected_without']})"
                )

    accuracy = pass_count / len(CASES)
    guard_fire_rate = len(guards.fires) / total_calls if total_calls else 0.0
    print_table(
        "Counterfactual",
        [
            ("accuracy", accuracy),
            ("passed", pass_count),
            ("total", len(CASES)),
            ("guard_fire_count", len(guards.fires)),
            ("guard_fire_rate", guard_fire_rate),
        ],
    )
    for f in failures:
        print(f"  ❌ {f}")
    for g in guards.fires:
        print(f"  ⚠️  {g['guard']}: {g['detail']}")

    failed: list[str] = []
    if accuracy < 1.0:
        failed.append("accuracy")
    if not assert_threshold(
        "guard_fire_rate (inverted)",
        1 - guard_fire_rate,
        1 - GUARD_FIRE_RATE_CEILING,
    ):
        failed.append("guard_fire_rate")
    exit_on_failure(failed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
