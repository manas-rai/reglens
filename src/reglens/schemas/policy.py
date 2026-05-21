"""Policy schema — an organisation's internal control/policy entry."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Policy(BaseModel):
    """A single policy or control in the organisation's control matrix."""

    id: str = Field(description="Unique policy identifier, e.g. 'CTL-KYC-001'")
    domain: str = Field(default="banking")
    section: str = Field(description="Policy section or category")
    title: str
    text: str = Field(description="Full policy text")
    owner: str | None = None
    last_reviewed: str | None = Field(
        default=None, description="ISO-8601 date of last review"
    )
    tags: list[str] = Field(default_factory=list)


class PolicyMatch(BaseModel):
    """A policy retrieved as relevant to a specific obligation."""

    policy: Policy
    relevance_score: float = Field(ge=0.0, le=1.0)
    matched_obligation_id: str
