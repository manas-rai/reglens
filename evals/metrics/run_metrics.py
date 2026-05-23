"""Per-run metrics: trajectory, step efficiency, output distributions.

Called from supervisor/pipeline.py once a run reaches a terminal state
(HITL gate or natural END). Writes a single audit_log row with node='metrics'.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from reglens.persistence.db import db_session

if TYPE_CHECKING:
    from reglens.schemas.gap import GapResult
    from reglens.schemas.risk import RiskLevel, RiskScore

logger = logging.getLogger(__name__)


def _gap_distribution(gap_results: list[GapResult]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for g in gap_results:
        counts[g.status.value] += 1
    return dict(counts)


def _risk_distribution(risk_scores: list[RiskScore]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for r in risk_scores:
        counts[r.risk_level.value] += 1
    return dict(counts)


def _step_efficiency(obligations_count: int, actual_a2a_calls: int) -> float | None:
    """Minimum A2A calls = 1 ingest + N risk scorings (one per gap).
    Step efficiency = minimum / actual. 1.0 = optimal.
    """
    if obligations_count == 0 or actual_a2a_calls == 0:
        return None
    minimum = 1 + obligations_count
    return min(1.0, minimum / actual_a2a_calls)


def _trajectory_valid(node_sequence: list[str]) -> bool:
    """Valid sequences: ingest -> retrieve -> analyze -> score -> report,
    OR ingest -> empty_report.
    """
    valid_paths = (
        [
            "ingest",
            "retrieve_policies",
            "analyze_gaps",
            "score_risks",
            "generate_report",
        ],
        ["ingest", "empty_report"],
    )
    # Tolerant: ignore extra entries (e.g. interrupt markers), check the
    # ordered subsequence appears.
    return any(_is_subsequence(path, node_sequence) for path in valid_paths)


def _is_subsequence(needle: list[str], haystack: list[str]) -> bool:
    it = iter(haystack)
    return all(n in it for n in needle)


def compute_run_metrics(
    run_id: str,
    node_sequence: list[str],
    obligations_count: int,
    gap_results: list[GapResult] | None,
    risk_scores: list[RiskScore] | None,
    a2a_call_count: int,
    pipeline_wall_ms: float,
) -> dict[str, Any]:
    """Compute per-run metrics. Pure function — no side effects."""
    gap_dist = _gap_distribution(gap_results or [])
    risk_dist = _risk_distribution(risk_scores or [])

    # Strong-match rate from the gap results: % of obligations whose top match
    # cleared the 0.5 relevance bar.
    strong_match_count = 0
    if gap_results:
        for g in gap_results:
            if (
                g.matched_policies
                and max(m.relevance_score for m in g.matched_policies) >= 0.5
            ):
                strong_match_count += 1
    strong_match_rate = strong_match_count / len(gap_results) if gap_results else None

    # Mean risk score per level (calibration sanity).
    score_by_level: dict[str, float] = {}
    if risk_scores:
        by_level: dict[RiskLevel, list[float]] = {}
        for r in risk_scores:
            by_level.setdefault(r.risk_level, []).append(r.score)
        for lvl, vals in by_level.items():
            score_by_level[lvl.value] = sum(vals) / len(vals)

    return {
        "run_id": run_id,
        "trajectory": {
            "node_sequence": node_sequence,
            "valid": _trajectory_valid(node_sequence),
            "node_count": len(node_sequence),
        },
        "throughput": {
            "obligations_count": obligations_count,
            "a2a_call_count": a2a_call_count,
            "step_efficiency": _step_efficiency(obligations_count, a2a_call_count),
            "wall_clock_ms": pipeline_wall_ms,
        },
        "gap_distribution": gap_dist,
        "risk_distribution": risk_dist,
        "rag_quality": {
            "strong_match_rate": strong_match_rate,
        },
        "risk_calibration": {
            "mean_score_by_level": score_by_level,
        },
    }


async def write_run_metrics(run_id: str, metrics: dict[str, Any]) -> None:
    """Persist computed metrics to audit_log under node='metrics'."""
    async with db_session() as session:
        await session.execute(
            text(
                "INSERT INTO audit_log (run_id, node, payload)"
                " VALUES (CAST(:run_id AS uuid), :node, CAST(:payload AS jsonb))"
            ),
            {
                "run_id": run_id,
                "node": "metrics",
                "payload": json.dumps(metrics),
            },
        )
    logger.info("run_metrics_written", extra={"run_id": run_id, "metrics": metrics})
