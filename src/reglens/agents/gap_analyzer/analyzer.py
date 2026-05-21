"""Gap analysis logic — Claude + instructor for structured GapResult output."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from reglens.agents.gap_analyzer.prompts import SYSTEM_PROMPT
from reglens.llm.claude import structured_complete
from reglens.schemas.gap import GapResult, GapStatus
from reglens.schemas.obligation import Obligation
from reglens.schemas.policy import PolicyMatch

logger = logging.getLogger(__name__)


class _GapAnalysis(BaseModel):
    """Intermediate response model for Claude structured output."""

    status: GapStatus
    reasoning: str = Field(
        description="Step-by-step reasoning referencing specific policy text"
    )
    gap_description: str | None = Field(
        default=None,
        description="Specific description of what is missing (for PARTIAL_GAP or GAP)",
    )
    recommendation: str | None = Field(
        default=None,
        description="Concrete remediation recommendation",
    )


async def analyze_gap(
    obligation: Obligation,
    matches: list[PolicyMatch],
) -> GapResult:
    """Classify the compliance status of one obligation against retrieved policies."""
    policy_context = "\n\n".join(
        f"Policy {m.policy.id} ({m.policy.title}, relevance={m.relevance_score:.2f}):\n{m.policy.text}"
        for m in matches
    )
    if not policy_context:
        policy_context = "No relevant policies found in control matrix."

    user_prompt = (
        f"Obligation:\n"
        f"ID: {obligation.id}\n"
        f"Clause: {obligation.clause}\n"
        f"Type: {obligation.obligation_type}\n"
        f"Text: {obligation.text}\n\n"
        f"Retrieved Policies:\n{policy_context}\n\n"
        "Classify the compliance status for this obligation."
    )

    analysis = await structured_complete(
        response_model=_GapAnalysis,
        system=SYSTEM_PROMPT,
        user=user_prompt,
    )

    logger.debug("Gap analysis for %s: %s", obligation.id, analysis.status)

    return GapResult(
        obligation=obligation,
        matched_policies=matches,
        status=analysis.status,
        reasoning=analysis.reasoning,
        gap_description=analysis.gap_description,
        recommendation=analysis.recommendation,
    )
