"""Risk scorer eval — weighted accuracy + MAE on numeric score.

Weighted accuracy gives partial credit when the predicted RiskLevel is adjacent
to the expected one (CRITICAL <-> HIGH, HIGH <-> MEDIUM, etc.).
"""

from __future__ import annotations

import asyncio
import os
import sys
from statistics import mean

from evals.component._common import (
    assert_threshold,
    exit_on_failure,
    load_dataset,
    print_table,
)
from reglens.schemas.risk import RiskLevel

WEIGHTED_ACCURACY_THRESHOLD = 0.70
MAE_THRESHOLD_INVERTED = 2.5  # MAE must be <= 2.5; we report as 10 - MAE for the helper

_LEVEL_ORDER = [
    RiskLevel.NONE.value,
    RiskLevel.LOW.value,
    RiskLevel.MEDIUM.value,
    RiskLevel.HIGH.value,
    RiskLevel.CRITICAL.value,
]


def _adjacent_credit(predicted: str, expected: str) -> float:
    if predicted == expected:
        return 1.0
    try:
        d = abs(_LEVEL_ORDER.index(predicted) - _LEVEL_ORDER.index(expected))
    except ValueError:
        return 0.0
    if d == 1:
        return 0.5
    return 0.0


def _stub_score(item: dict) -> tuple[str, float]:
    """Heuristic scorer: maps obligation type + gap status to a level/score.

    Treats prohibited and reporting obligations as more severe, and the
    presence of certain high-stakes terms (e.g. 'compensate', 'cyber',
    '6 hours', 'pmla') as critical signals.
    """
    if item["gap_status"] in ("compliant", "not_applicable"):
        return RiskLevel.NONE.value, 0.0
    text = (
        (item.get("gap_description") or "").lower()
        + " "
        + item["obligation_text"].lower()
    )
    critical_terms = (
        "pmla",
        "cyber security incidents",
        "6 hours",
        "related parties",
        "connected lending",
    )
    high_terms = (
        "pep",
        "wire transfer",
        "unauthorized",
        "leverage ratio",
        "nsfr",
        "whistleblower",
        "large exposure",
    )
    medium_terms = ("audit committee", "bcp", "vendor", "fair value")
    low_terms = ("mclr", "ebr", "disclosure")

    if any(t in text for t in critical_terms):
        return RiskLevel.CRITICAL.value, 9.0
    if any(t in text for t in high_terms):
        return RiskLevel.HIGH.value, 7.0
    if any(t in text for t in medium_terms):
        return RiskLevel.MEDIUM.value, 5.0
    if any(t in text for t in low_terms):
        return RiskLevel.LOW.value, 3.0
    return RiskLevel.MEDIUM.value, 5.0


def _live_score(item: dict) -> tuple[str, float]:
    from reglens.agents.risk_scorer.agent import score_gap
    from reglens.schemas.gap import GapResult, GapStatus
    from reglens.schemas.obligation import Obligation, ObligationType

    obl_type_str = item.get("obligation_type", "mandatory")
    obl = Obligation(
        id="eval",
        regulation_ref="EVAL",
        clause="§eval",
        text=item["obligation_text"],
        obligation_type=ObligationType(obl_type_str),
    )
    gap = GapResult(
        obligation=obl,
        matched_policies=[],
        status=GapStatus(item["gap_status"]),
        reasoning="eval",
        gap_description=item.get("gap_description"),
    )
    score = asyncio.run(score_gap(gap))
    return score.risk_level.value, score.score


def main() -> int:
    dataset = load_dataset("risk/labeled_risks.json")
    scorer = _live_score if os.environ.get("LIVE_LLM") == "1" else _stub_score

    weighted_correct = 0.0
    abs_errors = []
    confusion: dict[tuple[str, str], int] = {}

    for item in dataset["items"]:
        pred_level, pred_score = scorer(item)
        exp_level = item["expected_risk_level"]
        weighted_correct += _adjacent_credit(pred_level, exp_level)

        lo, hi = item["expected_score_range"]
        target_mid = (lo + hi) / 2
        abs_errors.append(abs(pred_score - target_mid))

        confusion[(exp_level, pred_level)] = (
            confusion.get((exp_level, pred_level), 0) + 1
        )

    n = len(dataset["items"])
    weighted_accuracy = weighted_correct / n
    mae = mean(abs_errors)

    print_table(
        "Risk eval",
        [
            ("weighted_accuracy", weighted_accuracy),
            ("mae_on_score", mae),
            ("dataset_size", n),
        ],
    )

    print("\nConfusion (expected -> predicted):")
    for (e, p), c in sorted(confusion.items()):
        marker = "" if e == p else "  ❌"
        print(f"  {e:9} -> {p:9}  {c}{marker}")

    failed: list[str] = []
    if not assert_threshold(
        "weighted_accuracy", weighted_accuracy, WEIGHTED_ACCURACY_THRESHOLD
    ):
        failed.append("weighted_accuracy")
    # MAE: lower is better. Convert via (10 - mae) for the helper.
    if not assert_threshold(
        "score_mae (10-mae)", 10 - mae, 10 - MAE_THRESHOLD_INVERTED
    ):
        failed.append("score_mae")
    exit_on_failure(failed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
