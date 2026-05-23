"""Unit tests for evals.metrics.run_metrics — pure metric computation."""

from __future__ import annotations

from evals.metrics.run_metrics import (
    _is_subsequence,
    _step_efficiency,
    _trajectory_valid,
    compute_run_metrics,
)
from reglens.schemas.gap import GapResult, GapStatus
from reglens.schemas.obligation import Obligation
from reglens.schemas.policy import Policy, PolicyMatch
from reglens.schemas.risk import RiskLevel, RiskScore


def _obl(oid: str = "o1") -> Obligation:
    return Obligation(id=oid, regulation_ref="EVAL", clause="§1", text="text")


def _match(score: float, oid: str = "o1") -> PolicyMatch:
    return PolicyMatch(
        policy=Policy(id=f"p-{oid}", section="s", title="t", text="text"),
        relevance_score=score,
        matched_obligation_id=oid,
    )


def _gap(status: GapStatus, oid: str = "o1", top_score: float = 0.6) -> GapResult:
    return GapResult(
        obligation=_obl(oid),
        matched_policies=[_match(top_score, oid)],
        status=status,
        reasoning="r",
    )


def _risk(level: RiskLevel, score: float) -> RiskScore:
    return RiskScore(
        gap_result=_gap(GapStatus.GAP),
        risk_level=level,
        score=score,
        justification="j",
    )


def test_is_subsequence_true():
    assert _is_subsequence(["a", "b", "c"], ["a", "x", "b", "y", "c"])


def test_is_subsequence_false():
    assert not _is_subsequence(["a", "b", "c"], ["a", "c", "b"])


def test_trajectory_valid_full():
    seq = [
        "ingest",
        "retrieve_policies",
        "analyze_gaps",
        "score_risks",
        "generate_report",
    ]
    assert _trajectory_valid(seq)


def test_trajectory_valid_empty_report_path():
    assert _trajectory_valid(["ingest", "empty_report"])


def test_trajectory_invalid():
    assert not _trajectory_valid(["ingest", "score_risks", "analyze_gaps"])


def test_step_efficiency_zero_obligations():
    assert _step_efficiency(0, 5) is None


def test_step_efficiency_zero_calls():
    assert _step_efficiency(3, 0) is None


def test_step_efficiency_optimal():
    # 3 obligations -> 1 ingest + 3 risk = 4 calls
    assert _step_efficiency(3, 4) == 1.0


def test_step_efficiency_extra_calls():
    assert _step_efficiency(3, 8) == 0.5


def test_compute_run_metrics_full():
    gaps = [
        _gap(GapStatus.GAP, "o1", 0.7),
        _gap(GapStatus.COMPLIANT, "o2", 0.3),
        _gap(GapStatus.PARTIAL_GAP, "o3", 0.5),
    ]
    risks = [
        _risk(RiskLevel.HIGH, 7.0),
        _risk(RiskLevel.HIGH, 8.0),
        _risk(RiskLevel.LOW, 2.0),
    ]
    seq = [
        "ingest",
        "retrieve_policies",
        "analyze_gaps",
        "score_risks",
        "generate_report",
    ]
    m = compute_run_metrics(
        run_id="r1",
        node_sequence=seq,
        obligations_count=3,
        gap_results=gaps,
        risk_scores=risks,
        a2a_call_count=4,
        pipeline_wall_ms=1234.5,
    )
    assert m["run_id"] == "r1"
    assert m["trajectory"]["valid"] is True
    assert m["trajectory"]["node_count"] == 5
    assert m["throughput"]["step_efficiency"] == 1.0
    assert m["throughput"]["wall_clock_ms"] == 1234.5
    assert m["gap_distribution"] == {"gap": 1, "compliant": 1, "partial_gap": 1}
    assert m["risk_distribution"] == {"high": 2, "low": 1}
    # strong match: o1 (0.7) and o3 (0.5) clear 0.5; o2 (0.3) does not.
    assert m["rag_quality"]["strong_match_rate"] == 2 / 3
    assert m["risk_calibration"]["mean_score_by_level"]["high"] == 7.5
    assert m["risk_calibration"]["mean_score_by_level"]["low"] == 2.0


def test_compute_run_metrics_empty():
    m = compute_run_metrics(
        run_id="r2",
        node_sequence=["ingest", "empty_report"],
        obligations_count=0,
        gap_results=None,
        risk_scores=None,
        a2a_call_count=1,
        pipeline_wall_ms=10.0,
    )
    assert m["gap_distribution"] == {}
    assert m["risk_distribution"] == {}
    assert m["rag_quality"]["strong_match_rate"] is None
    assert m["risk_calibration"]["mean_score_by_level"] == {}
    assert m["throughput"]["step_efficiency"] is None


def test_compute_run_metrics_gap_without_matches():
    g = GapResult(
        obligation=_obl(),
        matched_policies=[],
        status=GapStatus.GAP,
        reasoning="r",
    )
    m = compute_run_metrics(
        run_id="r3",
        node_sequence=["ingest"],
        obligations_count=1,
        gap_results=[g],
        risk_scores=[],
        a2a_call_count=1,
        pipeline_wall_ms=1.0,
    )
    assert m["rag_quality"]["strong_match_rate"] == 0.0
