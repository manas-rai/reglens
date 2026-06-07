"""Unit tests for evals.end_to_end — metric math and LangSmith evaluators."""

from __future__ import annotations

from evals.end_to_end.langsmith_evaluators import (
    gap_classification_correctness,
    gap_deficiency_detection,
    severity_adjacency,
)
from evals.end_to_end.scenarios import _gap_metrics, _severity_accuracy


def test_gap_metrics_all_correct() -> None:
    p, r, f1 = _gap_metrics(["gap", "gap", "compliant"], ["gap", "gap", "compliant"])
    assert p == 1.0
    assert r == 1.0
    assert f1 == 1.0


def test_gap_metrics_treats_partial_gap_as_positive() -> None:
    # predicted partial_gap should count as a true positive vs expected gap
    p, r, f1 = _gap_metrics(["partial_gap"], ["gap"])
    assert p == 1.0
    assert r == 1.0
    assert f1 == 1.0


def test_gap_metrics_missed_gap_drops_recall() -> None:
    # predicted compliant for an actual gap → false negative
    p, r, _ = _gap_metrics(
        ["compliant", "gap"],
        ["gap", "gap"],
    )
    assert r == 0.5
    assert p == 1.0


def test_gap_metrics_false_alarm_drops_precision() -> None:
    p, r, _ = _gap_metrics(
        ["gap", "gap"],
        ["compliant", "gap"],
    )
    assert p == 0.5
    assert r == 1.0


def test_gap_metrics_empty_returns_zero() -> None:
    p, r, f1 = _gap_metrics([], [])
    assert (p, r, f1) == (0.0, 0.0, 0.0)


def test_severity_accuracy_basic() -> None:
    assert (
        _severity_accuracy(["high", "low", "medium"], ["high", "low", "high"]) == 2 / 3
    )


def test_severity_accuracy_empty() -> None:
    assert _severity_accuracy([], []) == 0.0


def test_gap_classification_correctness_exact_match() -> None:
    run = {"predicted_status": "gap"}
    example = {"expected_status": "gap"}
    result = gap_classification_correctness(run, example)
    assert result["score"] == 1.0
    assert result["key"] == "gap_classification_correctness"


def test_gap_classification_correctness_mismatch() -> None:
    run = {"predicted_status": "partial_gap"}
    example = {"expected_status": "gap"}
    assert gap_classification_correctness(run, example)["score"] == 0.0


def test_gap_deficiency_detection_partial_counts_as_positive() -> None:
    # predicted partial_gap when expected gap: both positive → 1.0
    assert (
        gap_deficiency_detection(
            {"predicted_status": "partial_gap"},
            {"expected_status": "gap"},
        )["score"]
        == 1.0
    )


def test_gap_deficiency_detection_false_negative() -> None:
    assert (
        gap_deficiency_detection(
            {"predicted_status": "compliant"},
            {"expected_status": "gap"},
        )["score"]
        == 0.0
    )


def test_severity_adjacency_exact() -> None:
    assert (
        severity_adjacency(
            {"predicted_risk_level": "high"}, {"expected_risk_level": "high"}
        )["score"]
        == 1.0
    )


def test_severity_adjacency_off_by_one() -> None:
    # high vs critical are adjacent → 0.5
    assert (
        severity_adjacency(
            {"predicted_risk_level": "high"}, {"expected_risk_level": "critical"}
        )["score"]
        == 0.5
    )


def test_severity_adjacency_far_apart() -> None:
    assert (
        severity_adjacency(
            {"predicted_risk_level": "none"}, {"expected_risk_level": "critical"}
        )["score"]
        == 0.0
    )


def test_severity_adjacency_unknown_level() -> None:
    result = severity_adjacency(
        {"predicted_risk_level": "bogus"}, {"expected_risk_level": "high"}
    )
    assert result["score"] == 0.0
    assert "unknown" in result["comment"]


def test_scenarios_dataset_loads_and_is_well_formed() -> None:
    """Catch malformed scenario items at PR time, not at CI run time."""
    from evals.component._common import load_dataset

    data = load_dataset("end_to_end/scenarios.json")
    scenarios = data["scenarios"]
    assert len(scenarios) >= 5
    seen_ids = set()
    for sc in scenarios:
        assert sc["id"] not in seen_ids, f"duplicate scenario id {sc['id']}"
        seen_ids.add(sc["id"])
        assert sc["obligations"], f"scenario {sc['id']} has no obligations"
        for obl in sc["obligations"]:
            assert obl["expected_status"] in {
                "compliant",
                "partial_gap",
                "gap",
                "not_applicable",
            }
            assert obl["expected_risk_level"] in {
                "none",
                "low",
                "medium",
                "high",
                "critical",
            }
