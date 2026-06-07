"""Invariance test — semantically equivalent rephrasings yield the same status.

If the gap classifier is robust, surface variations in wording must not flip
its decision. We allow a tolerance: at least M of N rephrasings agree with
the anchor.

Offline (stub) mode: harness smoke test only. The stub uses token overlap,
so rewordings that preserve the salient tokens will trivially match.
Real signal requires LIVE_LLM=1.
"""

from __future__ import annotations

import sys

from evals.behavioral._runner import capture_guards, classify_gap, print_mode_banner
from evals.component._common import assert_threshold, exit_on_failure, print_table

GUARD_FIRE_RATE_CEILING = 0.25

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
    print_mode_banner("invariance")
    per_scenario: list[float] = []
    failures: list[str] = []
    total_calls = 0
    with capture_guards() as guards:
        for case in CASES:
            anchor = classify_gap(case["variants"][0], case["matched_policies"])
            total_calls += 1
            matches = 1  # anchor counts as a match against itself
            for v in case["variants"][1:]:
                total_calls += 1
                if classify_gap(v, case["matched_policies"]) == anchor:
                    matches += 1
            consistency = matches / len(case["variants"])
            per_scenario.append(consistency)
            if consistency < CONSISTENCY_THRESHOLD:
                failures.append(
                    f"{case['scenario']}: {consistency:.2f} consistent (anchor={anchor})"
                )

    overall = sum(per_scenario) / len(per_scenario)
    guard_fire_rate = len(guards.fires) / total_calls if total_calls else 0.0
    print_table(
        "Invariance",
        [
            ("overall_consistency", overall),
            ("scenarios", len(CASES)),
            ("guard_fire_count", len(guards.fires)),
            ("guard_fire_rate", guard_fire_rate),
        ],
    )
    for f in failures:
        print(f"  ❌ {f}")
    for g in guards.fires:
        print(f"  ⚠️  {g['guard']}: {g['detail']}")

    failed: list[str] = []
    if not assert_threshold("overall_consistency", overall, CONSISTENCY_THRESHOLD):
        failed.append("overall_consistency")
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
