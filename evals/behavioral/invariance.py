"""Invariance test — semantically equivalent rephrasings yield the same status.

If the gap classifier is robust, surface variations in wording must not flip
its decision. We allow a tolerance: at least M of N rephrasings agree with
the anchor.
"""

from __future__ import annotations

import sys

from evals.behavioral._runner import classify_gap
from evals.component._common import assert_threshold, exit_on_failure, print_table

CASES: list[dict] = [
    {
        "scenario": "cyber_6hr_reporting",
        "matched_policies": [],
        "variants": [
            "Banks must report cyber security incidents to RBI within 6 hours of detection.",
            "Any cyber security incident must be reported to RBI within 6 hours after it is detected.",
            "Report all cyber security incidents within a 6-hour window to RBI.",
        ],
    },
    {
        "scenario": "leverage_ratio_covered",
        "matched_policies": [
            {
                "id": "p1",
                "text": "Leverage ratio target is 4.5% per Basel III framework reviewed quarterly.",
            }
        ],
        "variants": [
            "Maintain leverage ratio above 4% per Basel III framework.",
            "Banks must keep their Basel III leverage ratio above 4%.",
            "Basel III leverage ratio shall not fall below 4%.",
        ],
    },
]

CONSISTENCY_THRESHOLD = 0.66  # at least 2/3 variants match the anchor


def main() -> int:
    per_scenario: list[float] = []
    failures: list[str] = []
    for case in CASES:
        anchor = classify_gap(case["variants"][0], case["matched_policies"])
        matches = sum(
            1
            for v in case["variants"]
            if classify_gap(v, case["matched_policies"]) == anchor
        )
        consistency = matches / len(case["variants"])
        per_scenario.append(consistency)
        if consistency < CONSISTENCY_THRESHOLD:
            failures.append(
                f"{case['scenario']}: {consistency:.2f} consistent (anchor={anchor})"
            )

    overall = sum(per_scenario) / len(per_scenario)
    print_table(
        "Invariance",
        [("overall_consistency", overall), ("scenarios", len(CASES))],
    )
    for f in failures:
        print(f"  ❌ {f}")

    failed: list[str] = []
    if not assert_threshold("overall_consistency", overall, CONSISTENCY_THRESHOLD):
        failed.append("overall_consistency")
    exit_on_failure(failed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
