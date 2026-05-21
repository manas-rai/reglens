"""Report renderer — builds ComplianceReport from risk scores."""

from __future__ import annotations

from reglens.schemas.report import ComplianceReport
from reglens.schemas.risk import RiskScore


def render_report(
    run_id: str,
    regulation_ref: str,
    domain: str,
    risk_scores: list[RiskScore],
) -> ComplianceReport:
    return ComplianceReport.build(
        run_id=run_id,
        regulation_ref=regulation_ref,
        domain=domain,
        risk_scores=risk_scores,
    )
