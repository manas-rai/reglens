"""Gap analyzer eval — per-class F1, macro F1, confusion matrix.

Offline mode: rule-based classifier driven by token overlap. Exercises the
metric pipeline and provides a deterministic floor.

Online mode (LIVE_LLM=1): calls real Claude via analyze_gap().
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections import defaultdict

from evals.component._common import (
    assert_threshold,
    exit_on_failure,
    load_dataset,
    print_table,
)
from reglens.schemas.gap import GapStatus

MACRO_F1_THRESHOLD = 0.55  # offline floor; live LLM should clear 0.75


def _stub_classify(obligation_text: str, matched_policies: list[dict]) -> str:
    """Cheap heuristic surrogate.

    - No matches at all -> GAP
    - At least one match, token overlap > 0.4 -> COMPLIANT
    - Match present but overlap weak -> PARTIAL_GAP
    - Obligation mentions out-of-domain terms (insurance, irdai) -> NOT_APPLICABLE
    """
    obl_toks = {t for t in obligation_text.lower().split() if len(t) > 4}
    if any(
        term in obligation_text.lower()
        for term in ("insurer", "irdai", "solvency ratio")
    ):
        return GapStatus.NOT_APPLICABLE.value
    if not matched_policies:
        return GapStatus.GAP.value
    best_overlap = 0.0
    for m in matched_policies:
        m_toks = {t for t in m["text"].lower().split() if len(t) > 4}
        if obl_toks:
            best_overlap = max(best_overlap, len(obl_toks & m_toks) / len(obl_toks))
    if best_overlap >= 0.4:
        return GapStatus.COMPLIANT.value
    if best_overlap >= 0.15:
        return GapStatus.PARTIAL_GAP.value
    return GapStatus.GAP.value


def _live_classify(obligation_text: str, matched_policies: list[dict]) -> str:
    from reglens.agents.gap_analyzer.analyzer import analyze_gap
    from reglens.schemas.obligation import Obligation
    from reglens.schemas.policy import Policy, PolicyMatch

    obl = Obligation(
        id="eval", regulation_ref="EVAL", clause="§eval", text=obligation_text
    )
    matches = [
        PolicyMatch(
            policy=Policy(
                id=m["id"],
                domain="banking",
                section="eval",
                title="eval",
                text=m["text"],
            ),
            relevance_score=0.7,
            matched_obligation_id=obl.id,
        )
        for m in matched_policies
    ]
    gap = asyncio.run(analyze_gap(obl, matches))
    return gap.status.value


def _f1_per_class(
    predicted: list[str], expected: list[str]
) -> tuple[dict[str, dict[str, float]], float, dict[tuple[str, str], int]]:
    classes = {
        GapStatus.COMPLIANT.value,
        GapStatus.PARTIAL_GAP.value,
        GapStatus.GAP.value,
        GapStatus.NOT_APPLICABLE.value,
    }
    tp: dict[str, int] = defaultdict(int)
    fp: dict[str, int] = defaultdict(int)
    fn: dict[str, int] = defaultdict(int)
    confusion: dict[tuple[str, str], int] = defaultdict(int)

    for p, e in zip(predicted, expected, strict=True):
        confusion[(e, p)] += 1
        if p == e:
            tp[e] += 1
        else:
            fp[p] += 1
            fn[e] += 1

    per_class: dict[str, dict[str, float]] = {}
    f1s = []
    for c in classes:
        prec = tp[c] / (tp[c] + fp[c]) if (tp[c] + fp[c]) else 0.0
        rec = tp[c] / (tp[c] + fn[c]) if (tp[c] + fn[c]) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        per_class[c] = {"precision": prec, "recall": rec, "f1": f1}
        f1s.append(f1)

    macro_f1 = sum(f1s) / len(f1s)
    return per_class, macro_f1, dict(confusion)


def main() -> int:
    dataset = load_dataset("gap/labeled_gaps.json")
    classify = _live_classify if os.environ.get("LIVE_LLM") == "1" else _stub_classify

    predicted, expected = [], []
    for item in dataset["items"]:
        predicted.append(classify(item["obligation_text"], item["matched_policies"]))
        expected.append(item["expected_status"])

    per_class, macro_f1, confusion = _f1_per_class(predicted, expected)

    rows = [("macro_f1", macro_f1), ("dataset_size", len(dataset["items"]))]
    for cls, m in sorted(per_class.items()):
        rows.append((f"{cls}.precision", m["precision"]))
        rows.append((f"{cls}.recall", m["recall"]))
        rows.append((f"{cls}.f1", m["f1"]))
    print_table("Gap eval", rows)

    print("\nConfusion (expected -> predicted):")
    for (e, p), c in sorted(confusion.items()):
        if e != p:
            print(f"  {e:14} -> {p:14}  {c}")

    failed: list[str] = []
    if not assert_threshold("macro_f1", macro_f1, MACRO_F1_THRESHOLD):
        failed.append("macro_f1")
    exit_on_failure(failed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
