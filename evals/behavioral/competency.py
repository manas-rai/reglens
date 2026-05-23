"""Competency test — planted gaps must be detected.

Each case asserts a specific (obligation, policy_matches) tuple yields the
expected GapStatus. Mirrors the "planted gap" verification from the MVP
spec; lets us regress on coverage of known-failure scenarios.

Offline (stub) mode: harness smoke test only — the stub classifier is
tuned to satisfy these cases. Real signal requires LIVE_LLM=1.
"""

from __future__ import annotations

import sys

from evals.behavioral._runner import classify_gap, print_mode_banner
from evals.component._common import exit_on_failure, print_table

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
    for obl, matches, expected, name in CASES:
        actual = classify_gap(obl, matches)
        if actual == expected:
            correct += 1
        else:
            mismatches.append(f"{name}: expected {expected}, got {actual}")

    accuracy = correct / len(CASES)
    print_table(
        "Competency",
        [("accuracy", accuracy), ("correct", correct), ("total", len(CASES))],
    )
    for m in mismatches:
        print(f"  ❌ {m}")

    failed = ["competency"] if accuracy < 1.0 else []
    exit_on_failure(failed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
