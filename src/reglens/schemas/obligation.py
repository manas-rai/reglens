"""Obligation schema — one regulatory requirement extracted from a PDF."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ObligationType(StrEnum):
    MANDATORY = "mandatory"
    ADVISORY = "advisory"
    PROHIBITED = "prohibited"
    DISCLOSURE = "disclosure"
    REPORTING = "reporting"
    OTHER = "other"


class Obligation(BaseModel):
    """A single regulatory obligation extracted from a regulatory document."""

    id: str = Field(description="Unique identifier, e.g. 'RBI-2024-01-§3.2'")
    regulation_ref: str = Field(description="Source regulation name / circular number")
    clause: str = Field(description="Clause or section reference, e.g. '§3.2(a)'")
    page: int | None = Field(default=None, description="Page number in source PDF")
    text: str = Field(description="Verbatim or paraphrased obligation text")
    obligation_type: ObligationType = Field(default=ObligationType.MANDATORY)
    domain: str = Field(default="banking", description="Regulatory domain")
    effective_date: str | None = Field(
        default=None, description="ISO-8601 date when obligation becomes effective"
    )
    tags: list[str] = Field(default_factory=list, description="Classification tags")
