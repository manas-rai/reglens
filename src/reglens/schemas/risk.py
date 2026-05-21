"""Risk scoring schema."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from reglens.schemas.gap import GapResult


class RiskLevel(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


class RiskScore(BaseModel):
    """Risk score assigned to a gap by the risk scorer agent."""

    gap_result: GapResult
    risk_level: RiskLevel
    score: float = Field(ge=0.0, le=10.0, description="Numeric score 0-10")
    justification: str
    regulatory_penalty_risk: str | None = None
    reputational_risk: str | None = None
