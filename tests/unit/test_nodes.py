"""Unit tests for supervisor/nodes.py — node functions."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import reglens.supervisor.nodes as nodes_module
from reglens.schemas.gap import GapResult, GapStatus
from reglens.schemas.obligation import Obligation
from reglens.schemas.risk import RiskLevel, RiskScore
from reglens.supervisor.routing import route_after_ingest

if TYPE_CHECKING:
    from reglens.supervisor.state import SupervisorState

# ---------------------------------------------------------------------------
# Helpers


def _mock_db_session() -> tuple[Any, AsyncMock]:
    mock_session = AsyncMock()

    @asynccontextmanager
    async def _ctx():
        yield mock_session

    return _ctx, mock_session


def _make_obligation(obl_id: str = "OBL-001") -> Obligation:
    return Obligation(id=obl_id, regulation_ref="REG", clause="§1", text="Text")


def _make_gap(obl_id: str = "OBL-001", status: GapStatus = GapStatus.GAP) -> GapResult:
    return GapResult(
        obligation=_make_obligation(obl_id),
        matched_policies=[],
        status=status,
        reasoning="r",
    )


def _make_risk_score(obl_id: str = "OBL-001") -> RiskScore:
    return RiskScore(
        gap_result=_make_gap(obl_id),
        risk_level=RiskLevel.HIGH,
        score=7.5,
        justification="j",
    )


def _make_state(**overrides: Any) -> SupervisorState:
    base: dict[str, Any] = {
        "run_id": "run-001",
        "pdf_bytes": b"%PDF fake",
        "regulation_ref": "REG-2024",
        "domain": "banking",
    }
    base.update(overrides)
    return base  # type: ignore[return-value]


def _mock_settings() -> MagicMock:
    settings = MagicMock()
    settings.a2a_ingestion_url = "http://ingest:8001"
    settings.a2a_risk_scorer_url = "http://risk:8002"
    settings.a2a_timeout_seconds = 30.0
    return settings


# ---------------------------------------------------------------------------
# route_after_ingest


def test_route_after_ingest_with_obligations() -> None:
    state = _make_state(obligations=[_make_obligation("OBL-001")])
    assert route_after_ingest(state) == "retrieve_policies"


def test_route_after_ingest_empty_list() -> None:
    state = _make_state(obligations=[])
    assert route_after_ingest(state) == "empty_report"


def test_route_after_ingest_missing_key() -> None:
    # obligations key not yet in state (before node_ingest has run — should not happen
    # in practice, but the router must not crash)
    state = _make_state()
    assert route_after_ingest(state) == "empty_report"


# ---------------------------------------------------------------------------
# node_empty_report


async def test_node_empty_report_returns_final_report() -> None:
    db_ctx, _ = _mock_db_session()
    with patch.object(nodes_module, "db_session", db_ctx):
        result = await nodes_module.node_empty_report(_make_state())

    assert "final_report" in result
    report = result["final_report"]
    assert report.summary.total_obligations == 0
    assert report.risk_scores == []


async def test_node_empty_report_writes_audit() -> None:
    db_ctx, session = _mock_db_session()
    with patch.object(nodes_module, "db_session", db_ctx):
        await nodes_module.node_empty_report(_make_state(regulation_ref="RBI-2024"))

    session.execute.assert_called_once()


async def test_node_empty_report_uses_state_metadata() -> None:
    db_ctx, _ = _mock_db_session()
    with patch.object(nodes_module, "db_session", db_ctx):
        result = await nodes_module.node_empty_report(
            _make_state(regulation_ref="RBI-2024", domain="banking")
        )

    report = result["final_report"]
    assert report.regulation_ref == "RBI-2024"
    assert report.domain == "banking"


# ---------------------------------------------------------------------------
# _write_audit


async def test_write_audit_executes_sql() -> None:
    db_ctx, session = _mock_db_session()
    with patch.object(nodes_module, "db_session", db_ctx):
        await nodes_module._write_audit("run-001", "ingest", {"count": 5})
    session.execute.assert_called_once()


async def test_write_audit_defaults_actor_to_system() -> None:
    db_ctx, session = _mock_db_session()
    with patch.object(nodes_module, "db_session", db_ctx):
        await nodes_module._write_audit("run-001", "ingest", {"count": 5})
    params = session.execute.call_args[0][1]
    assert params["actor"] == "system"


async def test_write_audit_human_actor() -> None:
    db_ctx, session = _mock_db_session()
    with patch.object(nodes_module, "db_session", db_ctx):
        await nodes_module._write_audit(
            "run-001", "approved", {"edit_count": 1}, actor="human"
        )
    params = session.execute.call_args[0][1]
    assert params["actor"] == "human"


# ---------------------------------------------------------------------------
# node_ingest


async def test_node_ingest_returns_obligations() -> None:
    obligations = [_make_obligation("OBL-001"), _make_obligation("OBL-002")]
    obligation_dicts = [o.model_dump() for o in obligations]

    db_ctx, _ = _mock_db_session()
    mock_client = AsyncMock()
    mock_client.call = AsyncMock(return_value=obligation_dicts)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch.object(nodes_module, "db_session", db_ctx),
        patch.object(nodes_module, "get_settings", return_value=_mock_settings()),
        patch("reglens.supervisor.nodes.A2AClient", return_value=mock_client),
    ):
        result = await nodes_module.node_ingest(_make_state())

    assert "obligations" in result
    assert len(result["obligations"]) == 2
    assert result["obligations"][0].id == "OBL-001"


async def test_node_ingest_uses_state_fields() -> None:
    db_ctx, _ = _mock_db_session()
    mock_client = AsyncMock()
    mock_client.call = AsyncMock(return_value=[])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    state = _make_state(regulation_ref="RBI-2024", domain="insurance")
    with (
        patch.object(nodes_module, "db_session", db_ctx),
        patch.object(nodes_module, "get_settings", return_value=_mock_settings()),
        patch("reglens.supervisor.nodes.A2AClient", return_value=mock_client),
    ):
        await nodes_module.node_ingest(state)

    call_params = mock_client.call.call_args[0][1]
    assert call_params["regulation_ref"] == "RBI-2024"
    assert call_params["domain"] == "insurance"


# ---------------------------------------------------------------------------
# node_retrieve_policies


async def test_node_retrieve_policies_returns_matches() -> None:
    obligations = [_make_obligation("OBL-001")]
    policy_map = {"OBL-001": []}

    db_ctx, _ = _mock_db_session()
    with (
        patch.object(nodes_module, "db_session", db_ctx),
        patch.object(
            nodes_module,
            "retrieve_all_policies",
            new=AsyncMock(return_value=policy_map),
        ),
    ):
        result = await nodes_module.node_retrieve_policies(
            _make_state(obligations=obligations)
        )

    assert "policy_matches" in result
    assert result["policy_matches"] == policy_map


# ---------------------------------------------------------------------------
# node_analyze_gaps


async def test_node_analyze_gaps_returns_gap_results() -> None:
    obligations = [_make_obligation("OBL-001")]
    gap_results = [_make_gap("OBL-001")]

    db_ctx, _ = _mock_db_session()
    with (
        patch.object(nodes_module, "db_session", db_ctx),
        patch.object(
            nodes_module, "analyze_all_gaps", new=AsyncMock(return_value=gap_results)
        ),
    ):
        result = await nodes_module.node_analyze_gaps(
            _make_state(obligations=obligations, policy_matches={})
        )

    assert "gap_results" in result
    assert len(result["gap_results"]) == 1


# ---------------------------------------------------------------------------
# node_score_risks


async def test_node_score_risks_returns_scored_gaps() -> None:
    gap_results = [_make_gap("OBL-001"), _make_gap("OBL-002")]
    risk_score = _make_risk_score("OBL-001")

    db_ctx, _ = _mock_db_session()
    mock_client = AsyncMock()
    mock_client.call = AsyncMock(return_value=risk_score.model_dump(mode="json"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch.object(nodes_module, "db_session", db_ctx),
        patch.object(nodes_module, "get_settings", return_value=_mock_settings()),
        patch("reglens.supervisor.nodes.A2AClient", return_value=mock_client),
    ):
        result = await nodes_module.node_score_risks(
            _make_state(gap_results=gap_results)
        )

    assert "risk_scores" in result
    assert len(result["risk_scores"]) == 2


# ---------------------------------------------------------------------------
# node_generate_report


async def test_node_generate_report_approved() -> None:
    risk_scores = [_make_risk_score()]
    db_ctx, _ = _mock_db_session()

    with (
        patch.object(nodes_module, "db_session", db_ctx),
        patch(
            "reglens.supervisor.nodes.interrupt",
            return_value={"approved": True, "edits": []},
        ),
    ):
        result = await nodes_module.node_generate_report(
            _make_state(risk_scores=risk_scores)
        )

    assert result["approved"] is True
    assert "final_report" in result
    assert "draft_report" in result


async def test_node_generate_report_rejected() -> None:
    risk_scores = [_make_risk_score()]
    db_ctx, _ = _mock_db_session()

    with (
        patch.object(nodes_module, "db_session", db_ctx),
        patch(
            "reglens.supervisor.nodes.interrupt",
            return_value={"approved": False, "edits": []},
        ),
    ):
        result = await nodes_module.node_generate_report(
            _make_state(risk_scores=risk_scores)
        )

    assert "error" in result
    assert "rejected" in result["error"].lower()
    assert "final_report" not in result


async def test_node_generate_report_with_edits() -> None:
    gap = _make_gap("OBL-001", GapStatus.GAP)
    rs = RiskScore(
        gap_result=gap, risk_level=RiskLevel.HIGH, score=7.0, justification="j"
    )
    db_ctx, _ = _mock_db_session()

    edits = [{"gap_id": "OBL-001", "status": "not_applicable"}]
    with (
        patch.object(nodes_module, "db_session", db_ctx),
        patch(
            "reglens.supervisor.nodes.interrupt",
            return_value={"approved": True, "edits": edits},
        ),
    ):
        result = await nodes_module.node_generate_report(_make_state(risk_scores=[rs]))

    final = result["final_report"]
    assert final.risk_scores[0].gap_result.status == GapStatus.NOT_APPLICABLE


async def test_node_generate_report_audits_edit_diffs_as_human() -> None:
    """Approval with edits writes a 'human' audit row that captures from/to per gap."""
    import json as _json

    gap = _make_gap("OBL-001", GapStatus.GAP)
    rs = RiskScore(
        gap_result=gap, risk_level=RiskLevel.HIGH, score=7.0, justification="j"
    )
    db_ctx, session = _mock_db_session()

    edits = [{"gap_id": "OBL-001", "status": "not_applicable"}]
    with (
        patch.object(nodes_module, "db_session", db_ctx),
        patch(
            "reglens.supervisor.nodes.interrupt",
            return_value={"approved": True, "edits": edits},
        ),
    ):
        await nodes_module.node_generate_report(_make_state(risk_scores=[rs]))

    audit_calls = [c for c in session.execute.call_args_list if "actor" in c[0][1]]
    human_calls = [c for c in audit_calls if c[0][1]["actor"] == "human"]
    assert human_calls, "expected at least one human-actor audit row"
    approved_call = next(c for c in human_calls if c[0][1]["node"] == "approved")
    payload = _json.loads(approved_call[0][1]["payload"])
    assert payload["edit_count"] == 1
    assert payload["edits"] == [
        {"gap_id": "OBL-001", "from": "gap", "to": "not_applicable"}
    ]


async def test_node_generate_report_rejection_audits_as_human() -> None:
    risk_scores = [_make_risk_score()]
    db_ctx, session = _mock_db_session()

    with (
        patch.object(nodes_module, "db_session", db_ctx),
        patch(
            "reglens.supervisor.nodes.interrupt",
            return_value={"approved": False, "edits": []},
        ),
    ):
        await nodes_module.node_generate_report(_make_state(risk_scores=risk_scores))

    audit_calls = [c for c in session.execute.call_args_list if "actor" in c[0][1]]
    rejected_calls = [c for c in audit_calls if c[0][1]["node"] == "rejected"]
    assert len(rejected_calls) == 1
    assert rejected_calls[0][0][1]["actor"] == "human"


async def test_node_generate_report_approval_emits_status_transition() -> None:
    risk_scores = [_make_risk_score()]
    db_ctx, session = _mock_db_session()

    with (
        patch.object(nodes_module, "db_session", db_ctx),
        patch(
            "reglens.supervisor.nodes.interrupt",
            return_value={"approved": True, "edits": []},
        ),
    ):
        await nodes_module.node_generate_report(_make_state(risk_scores=risk_scores))

    audit_calls = [c for c in session.execute.call_args_list if "actor" in c[0][1]]
    nodes_seen = [c[0][1]["node"] for c in audit_calls]
    assert "status_transition" in nodes_seen
