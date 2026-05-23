"""Competency test — planted gaps must be detected.

Each case asserts a specific (obligation, policy_matches) tuple yields the
expected GapStatus. Mirrors the "planted gap" verification from the MVP
spec; lets us regress on coverage of known-failure scenarios.

Offline (stub) mode: harness smoke test only — the stub classifier is
tuned to satisfy these cases. Real signal requires LIVE_LLM=1.
"""

from __future__ import annotations

import sys

from evals.behavioral._runner import capture_guards, classify_gap, print_mode_banner
from evals.component._common import assert_threshold, exit_on_failure, print_table

# At most ~25% of cases may trip a guard before we count the run as unhealthy.
# Guards are soft signals, but a high fire rate means "correct answer via
# ungrounded reasoning" — exactly what behavioral evals exist to catch.
GUARD_FIRE_RATE_CEILING = 0.25

# (obligation_text, matched_policies, expected_status, scenario_name)
CASES: list[tuple[str, list[dict], str, str]] = [
    (
        "Banks must report cyber security incidents to RBI within 6 hours of detection.",
        [],
        "gap",
        "no_policy_for_6hr_cyber_reporting",
    ),
    (
        "PMLA compliance requires identifying beneficial owners holding >=10% stake.",
        [
            {
                "id": "p1",
                "text": "Onboarding requires basic KYC documents identifying owners of accounts.",
            }
        ],
        "partial_gap",
        "weak_pmla_coverage",
    ),
    (
        "Insurers must maintain a solvency ratio of 1.5x as per IRDAI norms.",
        [{"id": "p1", "text": "Bank capital adequacy follows Basel III."}],
        "not_applicable",
        "insurance_out_of_banking_scope",
    ),
    (
        "Maintain leverage ratio above 4% per Basel III framework.",
        [
            {
                "id": "p1",
                "text": "Leverage ratio target is 4.5% per Basel III framework reviewed quarterly.",
            }
        ],
        "compliant",
        "leverage_ratio_covered",
    ),
]


def main() -> int:
    print_mode_banner("competency")
    correct = 0
    mismatches: list[str] = []
    with capture_guards() as guards:
        for obl, matches, expected, name in CASES:
            actual = classify_gap(obl, matches)
            if actual == expected:
                correct += 1
            else:
                mismatches.append(f"{name}: expected {expected}, got {actual}")

    accuracy = correct / len(CASES)
    # Fire rate = guard fires / total cases. >1.0 means multiple guards
    # tripped per case on average.
    guard_fire_rate = len(guards.fires) / len(CASES)
    print_table(
        "Competency",
        [
            ("accuracy", accuracy),
            ("correct", correct),
            ("total", len(CASES)),
            ("guard_fire_count", len(guards.fires)),
            ("guard_fire_rate", guard_fire_rate),
        ],
    )
    for m in mismatches:
        print(f"  ❌ {m}")
    for g in guards.fires:
        print(f"  ⚠️  {g['guard']}: {g['detail']}")

    failed: list[str] = []
    if accuracy < 1.0:
        failed.append("accuracy")
    # Lower is better — invert for assert_threshold.
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
