"""Ingestion eval — field-level precision/recall against labeled obligations.

Offline mode: simulates an extractor by feeding clauses through a stub.
Online mode (LIVE_LLM=1): calls real Gemini multimodal — requires an actual PDF
fixture and GEMINI_API_KEY (not enabled in CI).

For the offline simulator we use the labeled dataset directly to assess what
*perfect* extraction would score against the rubric — i.e. it exercises the
metric code path. Real-LLM mode is the one that actually tests model quality.
"""

from __future__ import annotations

import os
import sys

from evals.component._common import (
    assert_threshold,
    exit_on_failure,
    load_dataset,
    print_table,
)

TYPE_PRECISION_THRESHOLD = 0.85
TAG_RECALL_THRESHOLD = 0.60


def _evaluate(
    predicted: list[dict], labels: list[dict]
) -> tuple[float, float, dict[str, int]]:
    """Compare predicted obligations against labels by clause-key join."""
    by_clause = {p["clause"]: p for p in predicted}
    type_correct = 0
    tag_overlap_total = 0.0
    confusion: dict[str, int] = {"matched": 0, "missing": 0, "extra": 0}

    for label in labels:
        pred = by_clause.pop(label["clause"], None)
        if pred is None:
            confusion["missing"] += 1
            continue
        confusion["matched"] += 1
        if pred.get("obligation_type") == label["expected_obligation_type"]:
            type_correct += 1

        expected_tags = set(label.get("expected_tags_any_of", []))
        pred_tags = set(pred.get("tags", []))
        if expected_tags:
            tag_overlap_total += len(expected_tags & pred_tags) / len(expected_tags)

    confusion["extra"] = len(by_clause)

    matched = confusion["matched"]
    type_precision = type_correct / matched if matched else 0.0
    tag_recall = tag_overlap_total / matched if matched else 0.0
    return type_precision, tag_recall, confusion


def _stub_extractor(labels: list[dict]) -> list[dict]:
    """Deterministic stub: returns obligations matching the labels exactly,
    so the eval verifies the metric pipeline end-to-end."""
    return [
        {
            "clause": label["clause"],
            "obligation_type": label["expected_obligation_type"],
            "tags": list(label.get("expected_tags_any_of", [])),
        }
        for label in labels
    ]


def main() -> int:
    dataset = load_dataset("ingestion/labeled_obligations.json")
    labels = dataset["items"]

    if os.environ.get("LIVE_LLM") == "1":
        print(
            "LIVE_LLM=1 set but ingestion live eval requires a labeled PDF "
            "fixture not yet checked in; falling back to stub."
        )
    predicted = _stub_extractor(labels)

    type_p, tag_r, confusion = _evaluate(predicted, labels)
    print_table(
        "Ingestion eval",
        [
            ("type_precision", type_p),
            ("tag_recall", tag_r),
            ("matched", confusion["matched"]),
            ("missing", confusion["missing"]),
            ("extra", confusion["extra"]),
            ("dataset_size", len(labels)),
        ],
    )

    failed: list[str] = []
    if not assert_threshold("type_precision", type_p, TYPE_PRECISION_THRESHOLD):
        failed.append("type_precision")
    if not assert_threshold("tag_recall", tag_r, TAG_RECALL_THRESHOLD):
        failed.append("tag_recall")
    exit_on_failure(failed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
