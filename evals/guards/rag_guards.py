"""Per-call guards for the RAG / retrieval layer."""

from __future__ import annotations

from typing import TYPE_CHECKING

from evals.guards.types import GuardResult, GuardSeverity

if TYPE_CHECKING:
    from reglens.schemas.policy import PolicyMatch

# Minimum top-1 cosine similarity to consider retrieval "confident".
# Below this, we still proceed but flag the obligation for review.
RELEVANCE_FLOOR = 0.25


def check_retrieval_coverage(
    obligation_id: str, matches: list[PolicyMatch]
) -> GuardResult:
    """At least one policy must be returned per obligation."""
    passed = len(matches) > 0
    return GuardResult(
        name="rag.coverage",
        passed=passed,
        severity=GuardSeverity.WARNING,
        detail=f"No policies retrieved for obligation {obligation_id}"
        if not passed
        else "",
        metric_value=float(len(matches)),
    )


def check_retrieval_relevance_floor(
    obligation_id: str, matches: list[PolicyMatch]
) -> GuardResult:
    """Top-1 relevance must clear the floor; below it = low-confidence retrieval."""
    if not matches:
        return GuardResult(
            name="rag.relevance_floor",
            passed=False,
            severity=GuardSeverity.WARNING,
            detail=f"No matches to check relevance for {obligation_id}",
            metric_value=0.0,
        )

    top_score = max(m.relevance_score for m in matches)
    passed = top_score >= RELEVANCE_FLOOR
    return GuardResult(
        name="rag.relevance_floor",
        passed=passed,
        severity=GuardSeverity.WARNING,
        detail=(
            f"Top relevance {top_score:.3f} < floor {RELEVANCE_FLOOR} for {obligation_id}"
            if not passed
            else ""
        ),
        metric_value=top_score,
    )
