"""Gap analysis result schema."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from reglens.schemas.obligation import Obligation
from reglens.schemas.policy import PolicyMatch


class GapStatus(StrEnum):
    COMPLIANT = "compliant"
    PARTIAL_GAP = "partial_gap"
    GAP = "gap"
    NOT_APPLICABLE = "not_applicable"


class GapResult(BaseModel):
    """Gap analysis result for a single obligation."""

    obligation: Obligation
    matched_policies: list[PolicyMatch]
    status: GapStatus
    reasoning: str = Field(description="LLM reasoning for the classification")
    gap_description: str | None = Field(
        default=None,
        description="Specific description of what is missing (populated when status is GAP or PARTIAL_GAP)",
    )
    recommendation: str | None = Field(
        default=None,
        description="Recommended remediation action",
    )
