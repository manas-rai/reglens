"""Tier 0 guards — inline per-call quality checks.

Guards are SOFT by default: they log warnings and emit OTel span events
but do NOT raise. The only hard failures are schema/contract violations
already enforced by Pydantic upstream.

Each guard returns a `GuardResult` describing what was checked, whether
the check passed, and any metric value worth recording.
"""

from evals.guards.a2a_guards import check_a2a_latency
from evals.guards.llm_guards import (
    check_gap_reasoning_grounding,
    check_obligation_density,
    check_risk_score_consistency,
)
from evals.guards.rag_guards import (
    check_retrieval_coverage,
    check_retrieval_relevance_floor,
)
from evals.guards.types import GuardResult, GuardSeverity

__all__ = [
    "GuardResult",
    "GuardSeverity",
    "check_a2a_latency",
    "check_gap_reasoning_grounding",
    "check_obligation_density",
    "check_retrieval_coverage",
    "check_retrieval_relevance_floor",
    "check_risk_score_consistency",
]
