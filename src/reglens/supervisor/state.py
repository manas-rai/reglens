"""SupervisorState — the shared state TypedDict for the LangGraph workflow."""

from __future__ import annotations

from typing import Any

from typing_extensions import TypedDict

from reglens.schemas.gap import GapResult
from reglens.schemas.obligation import Obligation
from reglens.schemas.policy import PolicyMatch
from reglens.schemas.report import ComplianceReport
from reglens.schemas.risk import RiskScore


class SupervisorState(TypedDict, total=False):
    # Run metadata
    run_id: str
    pdf_bytes: bytes
    pdf_filename: str
    matrix_path: str
    regulation_ref: str
    domain: str

    # Pipeline outputs (populated incrementally)
    obligations: list[Obligation]
    policy_matches: dict[str, list[PolicyMatch]]
    gap_results: list[GapResult]
    risk_scores: list[RiskScore]

    # Draft and final report
    draft_report: ComplianceReport
    final_report: ComplianceReport

    # HITL approval payload (set after interrupt)
    approved: bool
    edits: list[dict[str, Any]]

    # Error state
    error: str | None
