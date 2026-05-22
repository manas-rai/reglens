"""Unit tests for agent utilities — ingestion, renderer, and _apply_edits."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from reglens.agents.ingestion.agent import _strip_markdown_fences, extract_obligations
from reglens.agents.report.renderer import render_report
from reglens.schemas.gap import GapResult, GapStatus
from reglens.schemas.obligation import Obligation, ObligationType
from reglens.schemas.risk import RiskLevel, RiskScore
from reglens.supervisor.nodes import _apply_edits

# ---------------------------------------------------------------------------
# _strip_markdown_fences


def test_strip_fences_plain_json() -> None:
    text = '[{"id": "x"}]'
    assert _strip_markdown_fences(text) == '[{"id": "x"}]'


def test_strip_fences_json_fence() -> None:
    text = '```json\n[{"id": "x"}]\n```'
    result = _strip_markdown_fences(text)
    assert result == '[{"id": "x"}]'


def test_strip_fences_plain_fence() -> None:
    text = '```\n[{"id": "x"}]\n```'
    result = _strip_markdown_fences(text)
    assert result == '[{"id": "x"}]'


def test_strip_fences_with_leading_trailing_whitespace() -> None:
    text = '  ```json\n[{"id": "x"}]\n```  '
    result = _strip_markdown_fences(text)
    assert result == '[{"id": "x"}]'


def test_strip_fences_empty_string() -> None:
    result = _strip_markdown_fences("")
    assert result == ""


def test_strip_fences_only_opening_fence() -> None:
    # Fence with no closing — strips the opening line, keeps rest
    text = "```json\n[1, 2, 3]"
    result = _strip_markdown_fences(text)
    assert result == "[1, 2, 3]"


def test_strip_fences_multiline_json() -> None:
    json_content = '[\n  {"id": "a"},\n  {"id": "b"}\n]'
    text = f"```json\n{json_content}\n```"
    result = _strip_markdown_fences(text)
    assert result == json_content


# ---------------------------------------------------------------------------
# extract_obligations


async def test_extract_obligations_success() -> None:
    obligation_data = [
        {
            "id": "OBL-001",
            "regulation_ref": "RBI-2024",
            "clause": "§1.1",
            "text": "Banks must KYC.",
            "obligation_type": "mandatory",
            "domain": "banking",
        }
    ]
    import json

    mock_response = json.dumps(obligation_data)

    with patch(
        "reglens.agents.ingestion.agent.generate_multimodal",
        new=AsyncMock(return_value=mock_response),
    ):
        obligations = await extract_obligations(
            pdf_bytes=b"%PDF fake bytes",
            regulation_ref="RBI-2024",
            domain="banking",
        )

    assert len(obligations) == 1
    assert obligations[0].id == "OBL-001"
    assert obligations[0].obligation_type == ObligationType.MANDATORY


async def test_extract_obligations_with_markdown_fence() -> None:
    obligation_data = [
        {
            "id": "OBL-002",
            "regulation_ref": "RBI-2024",
            "clause": "§2.0",
            "text": "Disclosure required.",
            "obligation_type": "disclosure",
        }
    ]
    import json

    mock_response = f"```json\n{json.dumps(obligation_data)}\n```"

    with patch(
        "reglens.agents.ingestion.agent.generate_multimodal",
        new=AsyncMock(return_value=mock_response),
    ):
        obligations = await extract_obligations(b"pdf", "RBI-2024")

    assert len(obligations) == 1
    assert obligations[0].obligation_type == ObligationType.DISCLOSURE


async def test_extract_obligations_invalid_json_raises() -> None:
    with (
        patch(
            "reglens.agents.ingestion.agent.generate_multimodal",
            new=AsyncMock(return_value="not json"),
        ),
        pytest.raises((ValueError, Exception)),
    ):
        await extract_obligations(b"pdf", "REG")


async def test_extract_obligations_empty_list() -> None:
    with patch(
        "reglens.agents.ingestion.agent.generate_multimodal",
        new=AsyncMock(return_value="[]"),
    ):
        obligations = await extract_obligations(b"pdf", "REG")
    assert obligations == []


# ---------------------------------------------------------------------------
# render_report


def _make_risk_score(
    obl_id: str, status: GapStatus, risk_level: RiskLevel, score: float
) -> RiskScore:
    obligation = Obligation(id=obl_id, regulation_ref="REG", clause="§1", text="Text")
    gap = GapResult(
        obligation=obligation,
        matched_policies=[],
        status=status,
        reasoning="reasoning",
        gap_description="Gap desc" if status == GapStatus.GAP else None,
        recommendation="Fix it" if status == GapStatus.GAP else None,
    )
    return RiskScore(
        gap_result=gap, risk_level=risk_level, score=score, justification="j"
    )


def test_render_report_empty() -> None:
    report = render_report("run-1", "REG", "banking", [])
    assert report.run_id == "run-1"
    assert report.regulation_ref == "REG"
    assert report.domain == "banking"
    assert report.summary.total_obligations == 0


def test_render_report_with_scores() -> None:
    scores = [
        _make_risk_score("OBL-001", GapStatus.GAP, RiskLevel.HIGH, 7.5),
        _make_risk_score("OBL-002", GapStatus.COMPLIANT, RiskLevel.NONE, 0.0),
    ]
    report = render_report("run-2", "REG-001", "banking", scores)
    assert report.summary.total_obligations == 2
    assert report.summary.gap == 1
    assert report.summary.compliant == 1
    assert "HIGH" in report.markdown


# ---------------------------------------------------------------------------
# _apply_edits (supervisor/nodes.py)


def _build_report_with_gap(gap_id: str, status: GapStatus) -> Any:
    from reglens.schemas.report import ComplianceReport

    rs = _make_risk_score(gap_id, status, RiskLevel.HIGH, 7.0)
    return ComplianceReport.build("run-x", "REG", "banking", [rs])


def test_apply_edits_no_edits_returns_same_structure() -> None:
    report = _build_report_with_gap("OBL-001", GapStatus.GAP)
    result = _apply_edits(report, [])
    # No edits: returns original report unchanged
    assert result is report


def test_apply_edits_changes_gap_status() -> None:
    report = _build_report_with_gap("OBL-001", GapStatus.GAP)
    edits = [{"gap_id": "OBL-001", "status": "not_applicable"}]
    result = _apply_edits(report, edits)
    assert result.risk_scores[0].gap_result.status == GapStatus.NOT_APPLICABLE


def test_apply_edits_ignores_unknown_gap_id() -> None:
    report = _build_report_with_gap("OBL-001", GapStatus.GAP)
    edits = [{"gap_id": "NONEXISTENT", "status": "compliant"}]
    result = _apply_edits(report, edits)
    # Original status unchanged
    assert result.risk_scores[0].gap_result.status == GapStatus.GAP


def test_apply_edits_ignores_edit_without_gap_id() -> None:
    report = _build_report_with_gap("OBL-001", GapStatus.GAP)
    edits = [{"status": "compliant"}]  # no gap_id key
    result = _apply_edits(report, edits)
    assert result.risk_scores[0].gap_result.status == GapStatus.GAP


def test_apply_edits_ignores_edit_without_status() -> None:
    report = _build_report_with_gap("OBL-001", GapStatus.GAP)
    edits = [{"gap_id": "OBL-001"}]  # no status key
    result = _apply_edits(report, edits)
    # No status change applied — returns rebuilt report with same status
    assert result.risk_scores[0].gap_result.status == GapStatus.GAP


def test_apply_edits_multiple_obligations() -> None:
    from reglens.schemas.report import ComplianceReport

    scores = [
        _make_risk_score("OBL-001", GapStatus.GAP, RiskLevel.HIGH, 7.0),
        _make_risk_score("OBL-002", GapStatus.PARTIAL_GAP, RiskLevel.MEDIUM, 5.0),
    ]
    report = ComplianceReport.build("run-y", "REG", "banking", scores)
    edits = [
        {"gap_id": "OBL-001", "status": "compliant"},
        {"gap_id": "OBL-002", "status": "not_applicable"},
    ]
    result = _apply_edits(report, edits)
    statuses = {
        rs.gap_result.obligation.id: rs.gap_result.status for rs in result.risk_scores
    }
    assert statuses["OBL-001"] == GapStatus.COMPLIANT
    assert statuses["OBL-002"] == GapStatus.NOT_APPLICABLE
