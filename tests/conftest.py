"""Shared pytest fixtures for RegLens test suites."""

from __future__ import annotations

import pytest

from reglens.schemas.gap import GapResult, GapStatus
from reglens.schemas.obligation import Obligation, ObligationType
from reglens.schemas.policy import Policy, PolicyMatch
from reglens.schemas.risk import RiskLevel, RiskScore


@pytest.fixture
def sample_obligation() -> Obligation:
    return Obligation(
        id="TEST-OBL-001",
        regulation_ref="TEST-REG-2024",
        clause="§1.1",
        text="Banks must maintain adequate KYC procedures.",
        obligation_type=ObligationType.MANDATORY,
        domain="banking",
    )


@pytest.fixture
def sample_policy() -> Policy:
    return Policy(
        id="CTL-KYC-001",
        domain="banking",
        section="KYC",
        title="Know Your Customer Policy",
        text="The bank shall verify customer identity before onboarding.",
    )


@pytest.fixture
def sample_policy_match(
    sample_obligation: Obligation, sample_policy: Policy
) -> PolicyMatch:
    return PolicyMatch(
        policy=sample_policy,
        relevance_score=0.85,
        matched_obligation_id=sample_obligation.id,
    )


@pytest.fixture
def sample_gap_result(
    sample_obligation: Obligation, sample_policy_match: PolicyMatch
) -> GapResult:
    return GapResult(
        obligation=sample_obligation,
        matched_policies=[sample_policy_match],
        status=GapStatus.GAP,
        reasoning="No adequate procedures found.",
        gap_description="Missing CDD process.",
        recommendation="Implement CDD workflow.",
    )


@pytest.fixture
def sample_risk_score(sample_gap_result: GapResult) -> RiskScore:
    return RiskScore(
        gap_result=sample_gap_result,
        risk_level=RiskLevel.HIGH,
        score=7.5,
        justification="High regulatory penalty risk.",
        regulatory_penalty_risk="Regulatory fine",
        reputational_risk="Public trust impact",
    )
