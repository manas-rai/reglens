"""Unit tests for all Pydantic schema models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from reglens.schemas.gap import GapResult, GapStatus
from reglens.schemas.obligation import Obligation, ObligationType
from reglens.schemas.policy import Policy, PolicyMatch
from reglens.schemas.report import ComplianceReport, RunSummary
from reglens.schemas.risk import RiskLevel, RiskScore
from reglens.schemas.run import (
    ApproveRequest,
    ApproveResponse,
    RunCreatedResponse,
    RunStatusResponse,
)

# ---------------------------------------------------------------------------
# ObligationType


def test_obligation_type_values() -> None:
    assert ObligationType.MANDATORY == "mandatory"
    assert ObligationType.ADVISORY == "advisory"
    assert ObligationType.PROHIBITED == "prohibited"
    assert ObligationType.DISCLOSURE == "disclosure"
    assert ObligationType.REPORTING == "reporting"
    assert ObligationType.OTHER == "other"


# ---------------------------------------------------------------------------
# Obligation


def test_obligation_full(sample_obligation: Obligation) -> None:
    assert sample_obligation.id == "TEST-OBL-001"
    assert sample_obligation.regulation_ref == "TEST-REG-2024"
    assert sample_obligation.clause == "§1.1"
    assert sample_obligation.domain == "banking"
    assert sample_obligation.obligation_type == ObligationType.MANDATORY
    assert sample_obligation.page is None
    assert sample_obligation.tags == []


def test_obligation_with_optional_fields() -> None:
    obl = Obligation(
        id="OBL-002",
        regulation_ref="REG-2024",
        clause="§2.0",
        text="Disclosure required.",
        obligation_type=ObligationType.DISCLOSURE,
        page=5,
        effective_date="2024-01-01",
        tags=["kyc", "aml"],
    )
    assert obl.page == 5
    assert obl.effective_date == "2024-01-01"
    assert obl.tags == ["kyc", "aml"]


def test_obligation_default_type() -> None:
    obl = Obligation(
        id="X",
        regulation_ref="R",
        clause="§1",
        text="Text",
    )
    assert obl.obligation_type == ObligationType.MANDATORY
    assert obl.domain == "banking"


# ---------------------------------------------------------------------------
# Policy and PolicyMatch


def test_policy_minimal() -> None:
    p = Policy(
        id="P1", section="AML", title="AML Policy", text="Anti-money laundering."
    )
    assert p.domain == "banking"
    assert p.owner is None
    assert p.last_reviewed is None
    assert p.tags == []


def test_policy_full(sample_policy: Policy) -> None:
    assert sample_policy.id == "CTL-KYC-001"
    assert sample_policy.section == "KYC"


def test_policy_with_optional_fields() -> None:
    p = Policy(
        id="P2",
        domain="insurance",
        section="Claims",
        title="Claims Policy",
        text="Policy text.",
        owner="compliance-team",
        last_reviewed="2024-06-01",
        tags=["claims"],
    )
    assert p.owner == "compliance-team"
    assert p.last_reviewed == "2024-06-01"
    assert p.tags == ["claims"]


def test_policy_match_relevance_bounds(sample_policy: Policy) -> None:
    pm = PolicyMatch(
        policy=sample_policy, relevance_score=0.0, matched_obligation_id="O1"
    )
    assert pm.relevance_score == 0.0

    pm2 = PolicyMatch(
        policy=sample_policy, relevance_score=1.0, matched_obligation_id="O1"
    )
    assert pm2.relevance_score == 1.0


def test_policy_match_invalid_relevance(sample_policy: Policy) -> None:
    with pytest.raises(ValidationError):
        PolicyMatch(
            policy=sample_policy, relevance_score=1.5, matched_obligation_id="O1"
        )

    with pytest.raises(ValidationError):
        PolicyMatch(
            policy=sample_policy, relevance_score=-0.1, matched_obligation_id="O1"
        )


# ---------------------------------------------------------------------------
# GapStatus and GapResult


def test_gap_status_values() -> None:
    assert GapStatus.COMPLIANT == "compliant"
    assert GapStatus.PARTIAL_GAP == "partial_gap"
    assert GapStatus.GAP == "gap"
    assert GapStatus.NOT_APPLICABLE == "not_applicable"


def test_gap_result_full(sample_gap_result: GapResult) -> None:
    assert sample_gap_result.status == GapStatus.GAP
    assert sample_gap_result.gap_description == "Missing CDD process."
    assert sample_gap_result.recommendation == "Implement CDD workflow."
    assert len(sample_gap_result.matched_policies) == 1


def test_gap_result_minimal(sample_obligation: Obligation) -> None:
    g = GapResult(
        obligation=sample_obligation,
        matched_policies=[],
        status=GapStatus.COMPLIANT,
        reasoning="Policy covers this.",
    )
    assert g.gap_description is None
    assert g.recommendation is None
    assert g.matched_policies == []


def test_gap_result_all_statuses(sample_obligation: Obligation) -> None:
    for status in GapStatus:
        g = GapResult(
            obligation=sample_obligation,
            matched_policies=[],
            status=status,
            reasoning="Reasoning.",
        )
        assert g.status == status


# ---------------------------------------------------------------------------
# RiskLevel and RiskScore


def test_risk_level_values() -> None:
    assert RiskLevel.CRITICAL == "critical"
    assert RiskLevel.HIGH == "high"
    assert RiskLevel.MEDIUM == "medium"
    assert RiskLevel.LOW == "low"
    assert RiskLevel.NONE == "none"


def test_risk_score_full(sample_risk_score: RiskScore) -> None:
    assert sample_risk_score.risk_level == RiskLevel.HIGH
    assert sample_risk_score.score == 7.5
    assert sample_risk_score.regulatory_penalty_risk == "Regulatory fine"
    assert sample_risk_score.reputational_risk == "Public trust impact"


def test_risk_score_bounds(sample_gap_result: GapResult) -> None:
    rs = RiskScore(
        gap_result=sample_gap_result,
        risk_level=RiskLevel.NONE,
        score=0.0,
        justification="No risk.",
    )
    assert rs.score == 0.0
    assert rs.regulatory_penalty_risk is None

    rs2 = RiskScore(
        gap_result=sample_gap_result,
        risk_level=RiskLevel.CRITICAL,
        score=10.0,
        justification="Critical.",
    )
    assert rs2.score == 10.0


def test_risk_score_invalid_bounds(sample_gap_result: GapResult) -> None:
    with pytest.raises(ValidationError):
        RiskScore(
            gap_result=sample_gap_result,
            risk_level=RiskLevel.HIGH,
            score=10.1,
            justification="Over.",
        )
    with pytest.raises(ValidationError):
        RiskScore(
            gap_result=sample_gap_result,
            risk_level=RiskLevel.HIGH,
            score=-0.1,
            justification="Under.",
        )


# ---------------------------------------------------------------------------
# RunSummary


def test_run_summary_defaults() -> None:
    s = RunSummary(
        total_obligations=10,
        compliant=5,
        partial_gap=2,
        gap=2,
        not_applicable=1,
    )
    assert s.by_risk_level == {}


def test_run_summary_with_risk() -> None:
    s = RunSummary(
        total_obligations=5,
        compliant=1,
        partial_gap=1,
        gap=2,
        not_applicable=1,
        by_risk_level={"critical": 1, "high": 1},
    )
    assert s.by_risk_level["critical"] == 1


# ---------------------------------------------------------------------------
# ComplianceReport.build()


def test_compliance_report_build_empty(sample_obligation: Obligation) -> None:
    report = ComplianceReport.build(
        run_id="run-001",
        regulation_ref="TEST-REG",
        domain="banking",
        risk_scores=[],
    )
    assert report.run_id == "run-001"
    assert report.regulation_ref == "TEST-REG"
    assert report.domain == "banking"
    assert report.summary.total_obligations == 0
    assert report.summary.compliant == 0
    assert report.summary.gap == 0
    assert isinstance(report.markdown, str)
    assert "TEST-REG" in report.markdown


def test_compliance_report_build_with_scores(sample_risk_score: RiskScore) -> None:
    report = ComplianceReport.build(
        run_id="run-002",
        regulation_ref="REG-001",
        domain="banking",
        risk_scores=[sample_risk_score],
    )
    assert report.summary.total_obligations == 1
    assert report.summary.gap == 1
    assert report.summary.compliant == 0
    assert report.summary.by_risk_level.get("high") == 1
    assert "HIGH" in report.markdown
    assert "TEST-OBL-001" in report.markdown


def test_compliance_report_build_mixed_statuses(
    sample_obligation: Obligation, sample_policy_match: PolicyMatch
) -> None:
    def make_rs(status: GapStatus, risk_level: RiskLevel, score: float) -> RiskScore:
        gap = GapResult(
            obligation=Obligation(
                id=f"OBL-{status}",
                regulation_ref="R",
                clause="§1",
                text="Text",
            ),
            matched_policies=[],
            status=status,
            reasoning="r",
        )
        return RiskScore(
            gap_result=gap, risk_level=risk_level, score=score, justification="j"
        )

    scores = [
        make_rs(GapStatus.COMPLIANT, RiskLevel.NONE, 0.0),
        make_rs(GapStatus.PARTIAL_GAP, RiskLevel.MEDIUM, 5.0),
        make_rs(GapStatus.GAP, RiskLevel.HIGH, 7.5),
        make_rs(GapStatus.NOT_APPLICABLE, RiskLevel.NONE, 0.0),
    ]
    report = ComplianceReport.build("run-003", "R", "banking", scores)
    assert report.summary.total_obligations == 4
    assert report.summary.compliant == 1
    assert report.summary.partial_gap == 1
    assert report.summary.gap == 1
    assert report.summary.not_applicable == 1


def test_compliance_report_markdown_contains_risk_distribution(
    sample_risk_score: RiskScore,
) -> None:
    report = ComplianceReport.build("r", "REG", "banking", [sample_risk_score])
    assert "## Risk Distribution" in report.markdown
    assert "## Detailed Findings" in report.markdown
    assert "## Executive Summary" in report.markdown


def test_compliance_report_markdown_optional_fields(
    sample_obligation: Obligation,
) -> None:
    gap = GapResult(
        obligation=sample_obligation,
        matched_policies=[],
        status=GapStatus.COMPLIANT,
        reasoning="All good.",
    )
    rs = RiskScore(
        gap_result=gap, risk_level=RiskLevel.NONE, score=0.0, justification="j"
    )
    report = ComplianceReport.build("r", "REG", "banking", [rs])
    assert "All good." in report.markdown


# ---------------------------------------------------------------------------
# Run API schemas


def test_run_created_response() -> None:
    r = RunCreatedResponse(run_id="abc-123")
    assert r.run_id == "abc-123"
    assert r.status == "pending"


def test_run_status_response() -> None:
    r = RunStatusResponse(
        run_id="abc-123",
        status="running",
        domain="banking",
        pdf_filename="test.pdf",
        error_message=None,
        created_at="2024-01-01T00:00:00",
        updated_at="2024-01-01T00:01:00",
    )
    assert r.status == "running"
    assert r.pdf_filename == "test.pdf"
    assert r.error_message is None


def test_run_status_response_optional_fields() -> None:
    r = RunStatusResponse(
        run_id="x",
        status="error",
        domain="banking",
        pdf_filename=None,
        error_message="Something went wrong",
        created_at="2024-01-01T00:00:00",
        updated_at="2024-01-01T00:01:00",
    )
    assert r.pdf_filename is None
    assert r.error_message == "Something went wrong"


def test_approve_request_defaults() -> None:
    r = ApproveRequest(approved=True)
    assert r.approved is True
    assert r.edits == []


def test_approve_request_with_edits() -> None:
    r = ApproveRequest(
        approved=False, edits=[{"gap_id": "G1", "status": "not_applicable"}]
    )
    assert r.approved is False
    assert len(r.edits) == 1


def test_approve_response() -> None:
    r = ApproveResponse(run_id="abc", status="resuming")
    assert r.run_id == "abc"
    assert r.status == "resuming"
