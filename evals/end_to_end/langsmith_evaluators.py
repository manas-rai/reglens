"""LangSmith LLM-as-judge evaluators for end-to-end pipeline runs.

These evaluators are intentionally framework-light: each is a plain
callable that takes ``(run, example)`` (the LangSmith evaluator signature)
and returns a ``{"key": str, "score": float, "comment": str}`` dict.

They are designed to be registered against a LangSmith dataset built from
``evals/datasets/end_to_end/scenarios.json`` so the live evals workflow
can attach LLM-graded quality metrics alongside the deterministic ones
computed in ``scenarios.py``. Registration happens in the live evals
job, not at import time, so this module never requires an API key just
to be imported (CI must remain offline-clean).
"""

from __future__ import annotations

from typing import Any

from reglens.schemas.gap import GapStatus
from reglens.schemas.risk import RiskLevel

_GAP_POSITIVE = {GapStatus.GAP.value, GapStatus.PARTIAL_GAP.value}
_LEVEL_ORDER = [
    RiskLevel.NONE.value,
    RiskLevel.LOW.value,
    RiskLevel.MEDIUM.value,
    RiskLevel.HIGH.value,
    RiskLevel.CRITICAL.value,
]


def gap_classification_correctness(run: Any, example: Any) -> dict[str, Any]:
    """Exact-match score on `GapStatus` for a single obligation."""
    predicted = _extract_field(run, "predicted_status")
    expected = _extract_field(example, "expected_status")
    score = 1.0 if predicted == expected else 0.0
    return {
        "key": "gap_classification_correctness",
        "score": score,
        "comment": f"predicted={predicted} expected={expected}",
    }


def gap_deficiency_detection(run: Any, example: Any) -> dict[str, Any]:
    """Binary "did we flag a deficiency at all?" score.

    Treats GAP and PARTIAL_GAP as the positive class; COMPLIANT and
    NOT_APPLICABLE as negative. Catches the common failure where a
    classifier softens a real gap into "partial" but never to compliant.
    """
    predicted = _extract_field(run, "predicted_status")
    expected = _extract_field(example, "expected_status")
    p_pos = predicted in _GAP_POSITIVE
    e_pos = expected in _GAP_POSITIVE
    return {
        "key": "gap_deficiency_detection",
        "score": 1.0 if p_pos == e_pos else 0.0,
        "comment": f"predicted_positive={p_pos} expected_positive={e_pos}",
    }


def severity_adjacency(run: Any, example: Any) -> dict[str, Any]:
    """Partial-credit severity score: exact=1.0, off-by-one=0.5, else 0.

    Useful as an LLM-judge target because critical/high boundary
    disagreements are routine and shouldn't be punished as severely as
    none-vs-critical confusions.
    """
    predicted = _extract_field(run, "predicted_risk_level")
    expected = _extract_field(example, "expected_risk_level")
    try:
        d = abs(_LEVEL_ORDER.index(predicted) - _LEVEL_ORDER.index(expected))
    except ValueError:
        return {
            "key": "severity_adjacency",
            "score": 0.0,
            "comment": f"unknown level predicted={predicted} expected={expected}",
        }
    score = {0: 1.0, 1: 0.5}.get(d, 0.0)
    return {
        "key": "severity_adjacency",
        "score": score,
        "comment": f"distance={d} predicted={predicted} expected={expected}",
    }


def _extract_field(obj: Any, field: str) -> Any:
    """Pull a field from either a LangSmith Run/Example or a plain dict."""
    if hasattr(obj, "outputs") and obj.outputs:
        return obj.outputs.get(field)
    if hasattr(obj, "inputs") and obj.inputs and field in obj.inputs:
        return obj.inputs.get(field)
    if isinstance(obj, dict):
        return obj.get(field)
    return None


EVALUATORS = [
    gap_classification_correctness,
    gap_deficiency_detection,
    severity_adjacency,
]
