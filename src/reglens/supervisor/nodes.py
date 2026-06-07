"""LangGraph node functions — each receives SupervisorState, returns a partial update."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langgraph.types import interrupt

from reglens.a2a.client import A2AClient
from reglens.agents.gap_analyzer.node import analyze_all_gaps
from reglens.agents.knowledge.node import retrieve_all_policies
from reglens.agents.report.renderer import render_report
from reglens.config import get_settings
from reglens.persistence.db import db_session
from reglens.schemas.gap import GapResult, GapStatus
from reglens.schemas.obligation import Obligation
from reglens.schemas.policy import PolicyMatch
from reglens.schemas.risk import RiskScore
from reglens.supervisor.state import SupervisorState

logger = logging.getLogger(__name__)

_RISK_CONCURRENCY = 5


async def _write_audit(run_id: str, node: str, payload: dict[str, Any]) -> None:
    import json

    from sqlalchemy import text

    async with db_session() as session:
        await session.execute(
            text(
                "INSERT INTO audit_log (run_id, node, payload)"
                " VALUES (CAST(:run_id AS uuid), :node, CAST(:payload AS jsonb))"
            ),
            {"run_id": run_id, "node": node, "payload": json.dumps(payload)},
        )


async def node_empty_report(state: SupervisorState) -> dict[str, Any]:
    """Produce an empty compliance report when ingestion found no obligations."""
    run_id = state["run_id"]
    regulation_ref = state.get("regulation_ref", "UNKNOWN")
    domain = state.get("domain", "banking")

    logger.warning("node_empty_report: no obligations extracted for run %s", run_id)
    report = render_report(run_id, regulation_ref, domain, [])
    await _write_audit(run_id, "empty_report", {"reason": "no obligations extracted"})
    return {"final_report": report}


async def node_ingest(state: SupervisorState) -> dict[str, Any]:
    """Call the ingestion A2A agent to extract obligations from the PDF."""
    import base64

    settings = get_settings()
    run_id = state["run_id"]
    pdf_bytes = state["pdf_bytes"]
    regulation_ref = state.get("regulation_ref", "UNKNOWN")
    domain = state.get("domain", "banking")

    logger.info("node_ingest: extracting obligations for run %s", run_id)

    async with A2AClient(
        settings.a2a_ingestion_url, timeout=settings.a2a_timeout_seconds
    ) as client:
        raw = await client.call(
            "extract_obligations",
            {
                "pdf_b64": base64.standard_b64encode(pdf_bytes).decode(),
                "regulation_ref": regulation_ref,
                "domain": domain,
            },
            idempotency_key=f"{run_id}:ingest",
        )

    obligations = [Obligation.model_validate(o) for o in raw]
    await _write_audit(run_id, "ingest", {"obligation_count": len(obligations)})
    return {"obligations": obligations}


async def node_retrieve_policies(state: SupervisorState) -> dict[str, Any]:
    """Retrieve policy matches for all obligations via pgvector RAG."""
    run_id = state["run_id"]
    obligations: list[Obligation] = state["obligations"]

    logger.info(
        "node_retrieve_policies: %d obligations for run %s", len(obligations), run_id
    )
    policy_matches = await retrieve_all_policies(obligations)
    await _write_audit(
        run_id, "retrieve_policies", {"matched_obligations": len(policy_matches)}
    )
    return {"policy_matches": policy_matches}


async def node_analyze_gaps(state: SupervisorState) -> dict[str, Any]:
    """Run gap analysis for all obligations (bounded concurrency via Claude)."""
    run_id = state["run_id"]
    obligations: list[Obligation] = state["obligations"]
    policy_matches: dict[str, list[PolicyMatch]] = state.get("policy_matches", {})

    logger.info(
        "node_analyze_gaps: %d obligations for run %s", len(obligations), run_id
    )
    gap_results = await analyze_all_gaps(obligations, policy_matches)
    gap_summary = {s: sum(1 for g in gap_results if g.status == s) for s in GapStatus}
    await _write_audit(run_id, "analyze_gaps", {"gap_summary": gap_summary})
    return {"gap_results": gap_results}


async def node_score_risks(state: SupervisorState) -> dict[str, Any]:
    """Score all gaps via the risk scorer A2A agent (bounded concurrency)."""
    settings = get_settings()
    run_id = state["run_id"]
    gap_results: list[GapResult] = state["gap_results"]

    logger.info("node_score_risks: %d gaps for run %s", len(gap_results), run_id)

    semaphore = asyncio.Semaphore(_RISK_CONCURRENCY)

    async def _score_one(gap: GapResult) -> RiskScore:
        async with semaphore:
            async with A2AClient(
                settings.a2a_risk_scorer_url, timeout=settings.a2a_timeout_seconds
            ) as client:
                raw = await client.call(
                    "score_gap",
                    {"gap_result": gap.model_dump(mode="json")},
                    idempotency_key=f"{run_id}:score_risks:{gap.obligation.id}",
                )
            return RiskScore.model_validate(raw)

    risk_scores = list(await asyncio.gather(*[_score_one(g) for g in gap_results]))
    await _write_audit(run_id, "score_risks", {"scored_count": len(risk_scores)})
    return {"risk_scores": risk_scores}


async def node_generate_report(state: SupervisorState) -> dict[str, Any]:
    """Generate draft report and pause for HITL approval via interrupt()."""
    run_id = state["run_id"]
    risk_scores: list[RiskScore] = state["risk_scores"]
    regulation_ref = state.get("regulation_ref", "UNKNOWN")
    domain = state.get("domain", "banking")

    draft = render_report(run_id, regulation_ref, domain, risk_scores)
    await _write_audit(
        run_id,
        "generate_report",
        {"total_obligations": draft.summary.total_obligations},
    )

    # HITL gate — pause until POST /runs/{id}/approve resumes the graph
    human_input: dict[str, Any] = interrupt(
        {"draft_report": draft.model_dump(mode="json")}
    )

    approved: bool = human_input.get("approved", False)
    edits: list[dict[str, Any]] = human_input.get("edits", [])

    if not approved:
        return {"error": "Run rejected by human reviewer", "draft_report": draft}

    final = _apply_edits(draft, edits)
    await _write_audit(run_id, "approved", {"edit_count": len(edits)})

    async with db_session() as session:
        from sqlalchemy import text

        await session.execute(
            text(
                "UPDATE runs SET status = 'completed', updated_at = now() WHERE id = CAST(:id AS uuid)"
            ),
            {"id": run_id},
        )

    return {
        "draft_report": draft,
        "final_report": final,
        "approved": True,
        "edits": edits,
    }


def _apply_edits(
    report: Any,
    edits: list[dict[str, Any]],
) -> Any:
    """Apply human reviewer edits to the draft report."""
    from reglens.schemas.gap import GapStatus
    from reglens.schemas.report import ComplianceReport

    if not edits:
        return report

    # Build a mutable map of risk scores by obligation id
    scores_by_id = {rs.gap_result.obligation.id: rs for rs in report.risk_scores}

    for edit in edits:
        gap_id = edit.get("gap_id")
        if not gap_id or gap_id not in scores_by_id:
            continue
        rs = scores_by_id[gap_id]
        new_status = edit.get("status")
        if new_status:
            gap = rs.gap_result.model_copy(update={"status": GapStatus(new_status)})
            scores_by_id[gap_id] = rs.model_copy(update={"gap_result": gap})

    updated_scores = list(scores_by_id.values())
    return ComplianceReport.build(
        run_id=report.run_id,
        regulation_ref=report.regulation_ref,
        domain=report.domain,
        risk_scores=updated_scores,
    )
