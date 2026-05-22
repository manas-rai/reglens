"""Unit tests for agents/gap_analyzer — analyze_gap and analyze_all_gaps."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from reglens.agents.gap_analyzer.analyzer import _GapAnalysis, analyze_gap
from reglens.agents.gap_analyzer.node import analyze_all_gaps
from reglens.schemas.gap import GapResult, GapStatus
from reglens.schemas.obligation import Obligation, ObligationType
from reglens.schemas.policy import Policy, PolicyMatch


def _make_obligation(obl_id: str = "OBL-001") -> Obligation:
    return Obligation(
        id=obl_id,
        regulation_ref="REG-2024",
        clause="§1.1",
        text="Banks must verify customer identity.",
        obligation_type=ObligationType.MANDATORY,
    )


def _make_match(obl_id: str = "OBL-001") -> PolicyMatch:
    policy = Policy(
        id="CTL-001",
        section="KYC",
        title="KYC Policy",
        text="Customer identity verified on onboarding.",
    )
    return PolicyMatch(policy=policy, relevance_score=0.9, matched_obligation_id=obl_id)


async def test_analyze_gap_compliant() -> None:
    analysis = _GapAnalysis(
        status=GapStatus.COMPLIANT,
        reasoning="Policy fully covers the obligation.",
    )
    with patch(
        "reglens.agents.gap_analyzer.analyzer.structured_complete",
        new=AsyncMock(return_value=analysis),
    ):
        result = await analyze_gap(_make_obligation(), [_make_match()])

    assert isinstance(result, GapResult)
    assert result.status == GapStatus.COMPLIANT
    assert result.reasoning == "Policy fully covers the obligation."
    assert result.gap_description is None
    assert result.recommendation is None


async def test_analyze_gap_gap_status() -> None:
    analysis = _GapAnalysis(
        status=GapStatus.GAP,
        reasoning="No CDD process found.",
        gap_description="Missing CDD workflow.",
        recommendation="Implement CDD.",
    )
    with patch(
        "reglens.agents.gap_analyzer.analyzer.structured_complete",
        new=AsyncMock(return_value=analysis),
    ):
        result = await analyze_gap(_make_obligation(), [])

    assert result.status == GapStatus.GAP
    assert result.gap_description == "Missing CDD workflow."
    assert result.recommendation == "Implement CDD."


async def test_analyze_gap_no_policies_context() -> None:
    analysis = _GapAnalysis(status=GapStatus.NOT_APPLICABLE, reasoning="N/A")
    mock_structured = AsyncMock(return_value=analysis)
    with patch(
        "reglens.agents.gap_analyzer.analyzer.structured_complete", new=mock_structured
    ):
        await analyze_gap(_make_obligation(), [])

    call_kwargs = mock_structured.call_args[1]
    assert "No relevant policies found" in call_kwargs["user"]


async def test_analyze_gap_with_policies_builds_context() -> None:
    analysis = _GapAnalysis(status=GapStatus.COMPLIANT, reasoning="ok")
    mock_structured = AsyncMock(return_value=analysis)
    with patch(
        "reglens.agents.gap_analyzer.analyzer.structured_complete", new=mock_structured
    ):
        match = _make_match()
        await analyze_gap(_make_obligation(), [match])

    call_kwargs = mock_structured.call_args[1]
    assert "CTL-001" in call_kwargs["user"]
    assert "KYC Policy" in call_kwargs["user"]


async def test_analyze_all_gaps_empty_obligations() -> None:
    results = await analyze_all_gaps([], {})
    assert results == []


async def test_analyze_all_gaps_returns_all_results() -> None:
    obligations = [_make_obligation(f"OBL-{i:03d}") for i in range(3)]
    analysis = _GapAnalysis(status=GapStatus.COMPLIANT, reasoning="ok")
    with patch(
        "reglens.agents.gap_analyzer.analyzer.structured_complete",
        new=AsyncMock(return_value=analysis),
    ):
        results = await analyze_all_gaps(obligations, {})

    assert len(results) == 3
    for r in results:
        assert r.status == GapStatus.COMPLIANT


async def test_analyze_all_gaps_uses_policy_matches() -> None:
    obligation = _make_obligation("OBL-001")
    match = _make_match("OBL-001")
    analysis = _GapAnalysis(status=GapStatus.COMPLIANT, reasoning="ok")
    mock_structured = AsyncMock(return_value=analysis)
    with patch(
        "reglens.agents.gap_analyzer.analyzer.structured_complete", new=mock_structured
    ):
        results = await analyze_all_gaps([obligation], {"OBL-001": [match]})

    assert len(results[0].matched_policies) == 1
