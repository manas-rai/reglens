"""Unit tests for evals.guards.* — L1 guard logic."""

from __future__ import annotations

import logging

from evals.guards.a2a_guards import (
    LATENCY_SLO_MS,
    PAYLOAD_BLOAT_BYTES,
    check_a2a_latency,
    check_a2a_payload_size,
)
from evals.guards.llm_guards import (
    MIN_REASONING_LEN,
    check_compliant_no_gap_description,
    check_gap_reasoning_grounding,
    check_obligation_density,
    check_risk_score_consistency,
)
from evals.guards.rag_guards import (
    RELEVANCE_FLOOR,
    check_retrieval_coverage,
    check_retrieval_relevance_floor,
)
from evals.guards.types import GuardResult, GuardSeverity
from reglens.schemas.gap import GapResult, GapStatus
from reglens.schemas.obligation import Obligation
from reglens.schemas.policy import Policy, PolicyMatch
from reglens.schemas.risk import RiskLevel, RiskScore


def _obl(
    oid: str = "o1", text: str = "Banks must verify customer identity."
) -> Obligation:
    return Obligation(id=oid, regulation_ref="EVAL", clause="§1", text=text)


def _match(
    score: float, text: str = "Verify customer identity per KYC policy."
) -> PolicyMatch:
    return PolicyMatch(
        policy=Policy(id="p1", section="kyc", title="KYC", text=text),
        relevance_score=score,
        matched_obligation_id="o1",
    )


# --- types.GuardResult.emit ---


def test_emit_failed_warning_logs(caplog):
    res = GuardResult(name="x", passed=False, detail="nope")
    with caplog.at_level(logging.WARNING, logger="reglens.guards"):
        res.emit()
    assert any("guard_failed" in r.message for r in caplog.records)


def test_emit_failed_error_logs_error(caplog):
    res = GuardResult(
        name="x", passed=False, severity=GuardSeverity.ERROR, detail="bad"
    )
    with caplog.at_level(logging.ERROR, logger="reglens.guards"):
        res.emit()
    assert any(r.levelno == logging.ERROR for r in caplog.records)


def test_emit_passed_silent(caplog):
    res = GuardResult(name="x", passed=True, metric_value=1.0)
    with caplog.at_level(logging.WARNING, logger="reglens.guards"):
        res.emit()
    assert not any("guard_failed" in r.message for r in caplog.records)


# --- rag_guards ---


def test_coverage_pass():
    r = check_retrieval_coverage("o1", [_match(0.7)])
    assert r.passed and r.metric_value == 1.0


def test_coverage_fail_empty():
    r = check_retrieval_coverage("o1", [])
    assert not r.passed and "No policies" in r.detail


def test_relevance_floor_pass():
    r = check_retrieval_relevance_floor("o1", [_match(RELEVANCE_FLOOR + 0.1)])
    assert r.passed


def test_relevance_floor_fail_below():
    r = check_retrieval_relevance_floor("o1", [_match(RELEVANCE_FLOOR - 0.1)])
    assert not r.passed and "Top relevance" in r.detail


def test_relevance_floor_empty_matches():
    r = check_retrieval_relevance_floor("o1", [])
    assert not r.passed and r.metric_value == 0.0


# --- llm_guards.check_obligation_density ---


def test_density_unknown_pages():
    r = check_obligation_density([_obl()], None)
    assert r.passed and r.metric_value is None


def test_density_zero_pages():
    r = check_obligation_density([_obl()], 0)
    assert r.passed


def test_density_pass():
    r = check_obligation_density([_obl(), _obl("o2")], 10)
    assert r.passed and r.metric_value == 0.2


def test_density_fail_sparse():
    r = check_obligation_density([_obl()], 1000)
    assert not r.passed and "Sparse" in r.detail


# --- llm_guards.check_gap_reasoning_grounding ---


def _gap(
    reasoning: str, matches: list[PolicyMatch], status: GapStatus = GapStatus.GAP
) -> GapResult:
    return GapResult(
        obligation=_obl(),
        matched_policies=matches,
        status=status,
        reasoning=reasoning,
        gap_description="missing control"
        if status in (GapStatus.GAP, GapStatus.PARTIAL_GAP)
        else None,
    )


def test_reasoning_too_short():
    r = check_gap_reasoning_grounding(_gap("short", [_match(0.7)]))
    assert not r.passed and "too short" in r.detail


def test_reasoning_no_matches_passes():
    long = "x" * (MIN_REASONING_LEN + 1)
    r = check_gap_reasoning_grounding(_gap(long, []))
    assert r.passed


def test_reasoning_cites_policy_tokens():
    reasoning = (
        "The policy requires verification of customer identity through "
        "documented procedures and periodic review."
    )
    r = check_gap_reasoning_grounding(
        _gap(
            reasoning, [_match(0.7, "customer identity verification procedures review")]
        )
    )
    assert r.passed and r.metric_value is not None and r.metric_value >= 2


def test_reasoning_does_not_cite():
    reasoning = "xxxxxx yyyyyy zzzzzz aaaaaa bbbbbb cccccc dddddd"
    r = check_gap_reasoning_grounding(_gap(reasoning, [_match(0.7, "qqqqqq wwwwww")]))
    assert not r.passed


def test_reasoning_empty_policy_text():
    long = "a" * (MIN_REASONING_LEN + 5) + " more words here"
    # Policy text with no tokens of length>=4
    r = check_gap_reasoning_grounding(_gap(long, [_match(0.7, "a b c")]))
    assert r.passed  # policy_toks empty -> skipped


# --- llm_guards.check_risk_score_consistency ---


def _risk(level: RiskLevel, score: float) -> RiskScore:
    return RiskScore(
        gap_result=_gap("ok reasoning long enough to pass " * 2, [_match(0.7)]),
        risk_level=level,
        score=score,
        justification="because",
    )


def test_risk_consistency_in_band():
    r = check_risk_score_consistency(_risk(RiskLevel.HIGH, 7.0))
    assert r.passed


def test_risk_consistency_out_of_band():
    r = check_risk_score_consistency(_risk(RiskLevel.CRITICAL, 2.0))
    assert not r.passed and "outside band" in r.detail


def test_risk_consistency_none_level():
    r = check_risk_score_consistency(_risk(RiskLevel.NONE, 0.0))
    assert r.passed


# --- llm_guards.check_compliant_no_gap_description ---


def test_compliant_with_description_fails():
    g = _gap(
        "long reasoning text here for grounding",
        [_match(0.7)],
        status=GapStatus.COMPLIANT,
    )
    g.gap_description = "oops"
    r = check_compliant_no_gap_description(g)
    assert not r.passed


def test_compliant_clean_passes():
    g = _gap(
        "long reasoning text here for grounding",
        [_match(0.7)],
        status=GapStatus.COMPLIANT,
    )
    g.gap_description = None
    assert check_compliant_no_gap_description(g).passed


def test_gap_status_always_passes():
    g = _gap(
        "long reasoning text here for grounding", [_match(0.7)], status=GapStatus.GAP
    )
    assert check_compliant_no_gap_description(g).passed


# --- a2a_guards ---


def test_a2a_latency_pass():
    assert check_a2a_latency("message/send", LATENCY_SLO_MS - 1).passed


def test_a2a_latency_fail():
    r = check_a2a_latency("message/send", LATENCY_SLO_MS + 1)
    assert not r.passed and "SLO" in r.detail


def test_a2a_payload_pass():
    assert check_a2a_payload_size("message/send", 1024).passed


def test_a2a_payload_fail():
    r = check_a2a_payload_size("message/send", PAYLOAD_BLOAT_BYTES + 1)
    assert not r.passed and "budget" in r.detail
