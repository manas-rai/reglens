"""Monotonicity test — worse gap status should not produce lower risk.

For the same obligation, when we move from COMPLIANT -> PARTIAL_GAP -> GAP,
the assigned risk_score must be non-decreasing. Catches inverted scoring
logic and noisy outputs.
"""

from __future__ import annotations

import sys

from evals.behavioral._runner import score_risk
from evals.component._common import exit_on_failure, print_table

_LEVEL_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}

# Each case = same obligation, ordered worst-to-best (so risk is monotonically NON-INCREASING).
CASES: list[dict] = [
    {
        "scenario": "pmla_obligation",
        "obligation_text": "PMLA compliance requires identifying beneficial owners holding >=10% stake.",
        "obligation_type": "mandatory",
        "ladder": [
            {"gap_status": "gap", "gap_description": "no PMLA control documented"},
            {
                "gap_status": "partial_gap",
                "gap_description": "PMLA control covers only direct owners",
            },
            {"gap_status": "compliant", "gap_description": None},
        ],
    },
    {
        "scenario": "cyber_reporting",
        "obligation_text": "Banks must report cyber security incidents to RBI within 6 hours of detection.",
        "obligation_type": "reporting",
        "ladder": [
            {"gap_status": "gap", "gap_description": "no incident reporting policy"},
            {
                "gap_status": "partial_gap",
                "gap_description": "policy exists but no 6-hour SLA",
            },
            {"gap_status": "compliant", "gap_description": None},
        ],
    },
]


def main() -> int:
    violations: list[str] = []
    checks = 0
    for case in CASES:
        prev_rank: int | None = None
        prev_score: float | None = None
        for step in case["ladder"]:
            item = {
                "obligation_text": case["obligation_text"],
                "obligation_type": case["obligation_type"],
                **step,
            }
            level, score = score_risk(item)
            rank = _LEVEL_RANK[level]
            if prev_rank is not None:
                checks += 1
                if rank > prev_rank or score > (prev_score or 0) + 0.01:
                    violations.append(
                        f"{case['scenario']}: rank/score not monotonic "
                        f"({prev_rank}->{rank}, {prev_score}->{score})"
                    )
            prev_rank = rank
            prev_score = score

    print_table(
        "Monotonicity",
        [("checks", checks), ("violations", len(violations))],
    )
    for v in violations:
        print(f"  ❌ {v}")

    failed = ["monotonicity"] if violations else []
    exit_on_failure(failed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
