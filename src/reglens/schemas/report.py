"""Compliance report schema — the final output of a run."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from reglens.schemas.gap import GapStatus
from reglens.schemas.risk import RiskLevel, RiskScore


class RunSummary(BaseModel):
    total_obligations: int
    compliant: int
    partial_gap: int
    gap: int
    not_applicable: int
    by_risk_level: dict[str, int] = Field(default_factory=dict)


class ComplianceReport(BaseModel):
    """Final structured compliance-gap report for a run."""

    run_id: str
    regulation_ref: str
    domain: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    summary: RunSummary
    risk_scores: list[RiskScore]
    markdown: str = Field(description="Human-readable markdown report")

    @classmethod
    def build(
        cls,
        run_id: str,
        regulation_ref: str,
        domain: str,
        risk_scores: list[RiskScore],
    ) -> ComplianceReport:
        total = len(risk_scores)
        counts: dict[GapStatus, int] = dict.fromkeys(GapStatus, 0)
        risk_counts: dict[str, int] = dict.fromkeys(RiskLevel, 0)

        for rs in risk_scores:
            counts[rs.gap_result.status] += 1
            risk_counts[rs.risk_level] += 1

        summary = RunSummary(
            total_obligations=total,
            compliant=counts[GapStatus.COMPLIANT],
            partial_gap=counts[GapStatus.PARTIAL_GAP],
            gap=counts[GapStatus.GAP],
            not_applicable=counts[GapStatus.NOT_APPLICABLE],
            by_risk_level=risk_counts,
        )
        markdown = _render_markdown(regulation_ref, domain, summary, risk_scores)
        return cls(
            run_id=run_id,
            regulation_ref=regulation_ref,
            domain=domain,
            summary=summary,
            risk_scores=risk_scores,
            markdown=markdown,
        )


def _render_markdown(
    regulation_ref: str,
    domain: str,
    summary: RunSummary,
    risk_scores: list[RiskScore],
) -> str:
    lines: list[str] = [
        f"# Compliance Gap Report - {regulation_ref}",
        f"**Domain:** {domain}  ",
        "",
        "## Executive Summary",
        "| Metric | Count |",
        "|--------|-------|",
        f"| Total obligations | {summary.total_obligations} |",
        f"| Compliant | {summary.compliant} |",
        f"| Partial gap | {summary.partial_gap} |",
        f"| Gap | {summary.gap} |",
        f"| Not applicable | {summary.not_applicable} |",
        "",
        "## Risk Distribution",
    ]
    for level in RiskLevel:
        count = summary.by_risk_level.get(level, 0)
        if count:
            lines.append(f"- **{level.upper()}**: {count}")

    lines += ["", "## Detailed Findings", ""]

    sorted_scores = sorted(
        risk_scores,
        key=lambda rs: list(RiskLevel).index(rs.risk_level),
    )
    for rs in sorted_scores:
        gap = rs.gap_result
        obl = gap.obligation
        lines += [
            f"### [{rs.risk_level.upper()}] {obl.id} — {obl.clause}",
            f"**Status:** {gap.status}  ",
            f"**Risk:** {rs.risk_level} (score: {rs.score:.1f})  ",
            f"> {obl.text}",
            "",
        ]
        if gap.gap_description:
            lines.append(f"**Gap:** {gap.gap_description}  ")
        if gap.recommendation:
            lines.append(f"**Recommendation:** {gap.recommendation}  ")
        lines.append(f"**Reasoning:** {gap.reasoning}  ")
        lines.append(f"**Justification:** {rs.justification}  ")
        lines.append("")

    return "\n".join(lines)
