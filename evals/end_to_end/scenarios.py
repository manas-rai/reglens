"""End-to-end pipeline scenarios — aggregate gap + severity metrics.

Each scenario bundles one or more (obligation, matched policies) pairs with
expected `GapStatus` and `RiskLevel` ground truth. We run the same gap
classifier + risk scorer used by the component evals, then aggregate across
all scenarios to produce the Phase 2 acceptance metrics from
``docs/IMPLEMENTATION_PLAN.md``:

- gap recall   ≥ 0.85
- gap precision≥ 0.75
- severity accuracy (RiskLevel exact match on scored items) ≥ 0.70

Offline mode (default) uses the deterministic stubs from
``evals.component.{gap_eval,risk_eval}`` so CI runs without API keys.
``LIVE_LLM=1`` swaps in real Claude/Gemini calls.
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict

from evals.component._common import (
    assert_threshold,
    exit_on_failure,
    load_dataset,
    print_table,
)
from evals.component.gap_eval import _live_classify, _stub_classify
from evals.component.risk_eval import _live_score, _stub_score
from reglens.schemas.gap import GapStatus

GAP_RECALL_THRESHOLD = 0.85
GAP_PRECISION_THRESHOLD = 0.75
SEVERITY_ACCURACY_THRESHOLD = 0.70


def _gap_metrics(
    predicted: list[str], expected: list[str]
) -> tuple[float, float, float]:
    """Compute gap precision/recall/F1 treating GAP and PARTIAL_GAP as positive.

    The Phase 2 acceptance metric is whether the pipeline flags a real
    deficiency (gap or partial gap) versus passing it as compliant or NA.
    So we binarize against the "has a deficiency" class.
    """
    positive = {GapStatus.GAP.value, GapStatus.PARTIAL_GAP.value}
    tp = fp = fn = 0
    for p, e in zip(predicted, expected, strict=True):
        p_pos = p in positive
        e_pos = e in positive
        if p_pos and e_pos:
            tp += 1
        elif p_pos and not e_pos:
            fp += 1
        elif not p_pos and e_pos:
            fn += 1

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1


def _severity_accuracy(
    predicted_levels: list[str], expected_levels: list[str]
) -> float:
    if not predicted_levels:
        return 0.0
    correct = sum(
        1 for p, e in zip(predicted_levels, expected_levels, strict=True) if p == e
    )
    return correct / len(predicted_levels)


def main() -> int:
    dataset = load_dataset("end_to_end/scenarios.json")
    classify = _live_classify if os.environ.get("LIVE_LLM") == "1" else _stub_classify
    score = _live_score if os.environ.get("LIVE_LLM") == "1" else _stub_score

    gap_preds: list[str] = []
    gap_truth: list[str] = []
    sev_preds: list[str] = []
    sev_truth: list[str] = []
    per_scenario: list[tuple[str, int, int]] = []  # (id, total_obls, correct_gap)

    for scenario in dataset["scenarios"]:
        sc_correct = 0
        sc_total = len(scenario["obligations"])
        for obl in scenario["obligations"]:
            predicted_status = classify(obl["obligation_text"], obl["matched_policies"])
            expected_status = obl["expected_status"]
            gap_preds.append(predicted_status)
            gap_truth.append(expected_status)
            if predicted_status == expected_status:
                sc_correct += 1

            risk_item = {
                "obligation_text": obl["obligation_text"],
                "obligation_type": obl.get("obligation_type", "mandatory"),
                "gap_status": predicted_status,
                "gap_description": obl.get("gap_description"),
            }
            pred_level, _ = score(risk_item)
            sev_preds.append(pred_level)
            sev_truth.append(obl["expected_risk_level"])

        per_scenario.append((scenario["id"], sc_total, sc_correct))

    precision, recall, f1 = _gap_metrics(gap_preds, gap_truth)
    severity_accuracy = _severity_accuracy(sev_preds, sev_truth)

    print_table(
        "End-to-end pipeline eval",
        [
            ("scenario_count", len(dataset["scenarios"])),
            ("obligation_count", len(gap_preds)),
            ("gap_precision", precision),
            ("gap_recall", recall),
            ("gap_f1", f1),
            ("severity_accuracy", severity_accuracy),
        ],
    )

    print("\nPer-scenario gap classification (correct / total):")
    for sid, total, correct in per_scenario:
        marker = "" if correct == total else "  ⚠"
        print(f"  {sid:48}  {correct}/{total}{marker}")

    confusion: dict[tuple[str, str], int] = defaultdict(int)
    for p, e in zip(sev_preds, sev_truth, strict=True):
        confusion[(e, p)] += 1
    print("\nSeverity confusion (expected -> predicted):")
    for (e, p), c in sorted(confusion.items()):
        marker = "" if e == p else "  ❌"
        print(f"  {e:9} -> {p:9}  {c}{marker}")

    failed: list[str] = []
    if not assert_threshold("gap_precision", precision, GAP_PRECISION_THRESHOLD):
        failed.append("gap_precision")
    if not assert_threshold("gap_recall", recall, GAP_RECALL_THRESHOLD):
        failed.append("gap_recall")
    if not assert_threshold(
        "severity_accuracy", severity_accuracy, SEVERITY_ACCURACY_THRESHOLD
    ):
        failed.append("severity_accuracy")
    exit_on_failure(failed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
