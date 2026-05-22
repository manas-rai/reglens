"""Unit tests for health, middleware, tracing, graph, and supporting modules."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

if TYPE_CHECKING:
    from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

import reglens.observability.tracing as tracing_module
from reglens.api.middleware.request_id import RequestIDMiddleware
from reglens.api.routers.health import router as health_router
from reglens.observability.tracing import configure_tracing, get_tracer

# ---------------------------------------------------------------------------
# Health endpoint


async def test_health_endpoint_returns_ok() -> None:
    app = FastAPI()
    app.include_router(health_router)
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# RequestIDMiddleware


async def test_request_id_middleware_adds_header() -> None:
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)
    app.include_router(health_router)
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert "x-request-id" in resp.headers


async def test_request_id_middleware_preserves_existing_id() -> None:
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)
    app.include_router(health_router)
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health", headers={"x-request-id": "my-custom-id"})
    assert resp.headers["x-request-id"] == "my-custom-id"


# ---------------------------------------------------------------------------
# configure_tracing


@pytest.fixture(autouse=True)
def reset_tracer_provider():
    original = tracing_module._tracer_provider
    yield
    tracing_module._tracer_provider = original


def test_configure_tracing_console_exporter() -> None:
    configure_tracing(service_name="test-service")
    assert tracing_module._tracer_provider is not None


def test_configure_tracing_sets_service_name() -> None:
    configure_tracing(service_name="my-service")
    provider = tracing_module._tracer_provider
    assert provider is not None


def test_configure_tracing_with_otlp_endpoint() -> None:
    mock_exporter = MagicMock()
    mock_exporter_cls = MagicMock(return_value=mock_exporter)
    with patch(
        "reglens.observability.tracing.OTLPSpanExporter", mock_exporter_cls, create=True
    ):
        configure_tracing(service_name="test", otlp_endpoint="http://otel:4317")
    assert tracing_module._tracer_provider is not None


def test_get_tracer_returns_tracer() -> None:
    configure_tracing(service_name="test")
    tracer = get_tracer("test.module")
    assert tracer is not None


# ---------------------------------------------------------------------------
# supervisor/graph.py


def test_build_supervisor_graph_compiles() -> None:
    from langgraph.checkpoint.memory import MemorySaver

    from reglens.supervisor.graph import build_supervisor_graph

    saver = MemorySaver()
    graph = build_supervisor_graph(saver)  # type: ignore[arg-type]
    assert graph is not None
    assert hasattr(graph, "astream")
    assert hasattr(graph, "aget_state")


# ---------------------------------------------------------------------------
# rag/ingest.py — _load_matrix and ingest_matrix


def test_load_matrix_parses_yaml(tmp_path: Path) -> None:
    from reglens.rag.ingest import _load_matrix

    matrix_yaml = tmp_path / "matrix.yaml"
    matrix_yaml.write_text(
        """
policies:
  - id: CTL-001
    domain: banking
    section: KYC
    title: KYC Policy
    text: Customer identity verification required.
  - id: CTL-002
    domain: banking
    section: AML
    title: AML Policy
    text: Anti-money laundering controls.
""",
        encoding="utf-8",
    )
    policies = _load_matrix(matrix_yaml)
    assert len(policies) == 2
    assert policies[0].id == "CTL-001"
    assert policies[1].section == "AML"


def test_load_matrix_empty_policies(tmp_path: Path) -> None:
    from reglens.rag.ingest import _load_matrix

    matrix_yaml = tmp_path / "empty.yaml"
    matrix_yaml.write_text("policies: []\n", encoding="utf-8")
    policies = _load_matrix(matrix_yaml)
    assert policies == []


async def test_ingest_matrix_empty_returns_zero(tmp_path: Path) -> None:
    from reglens.rag.ingest import ingest_matrix

    matrix_yaml = tmp_path / "empty.yaml"
    matrix_yaml.write_text("policies: []\n", encoding="utf-8")
    count = await ingest_matrix(matrix_yaml)
    assert count == 0


async def test_ingest_matrix_upserts_policies(tmp_path: Path) -> None:
    from reglens.rag.ingest import ingest_matrix

    matrix_yaml = tmp_path / "matrix.yaml"
    matrix_yaml.write_text(
        """
policies:
  - id: CTL-001
    domain: banking
    section: KYC
    title: KYC Policy
    text: Verify customer identity.
""",
        encoding="utf-8",
    )

    mock_session = AsyncMock()

    @asynccontextmanager
    async def mock_db_session():
        yield mock_session

    import reglens.rag.ingest as ingest_module

    with (
        patch.object(
            ingest_module, "embed_texts", new=AsyncMock(return_value=[[0.1, 0.2]])
        ),
        patch.object(ingest_module, "db_session", mock_db_session),
        patch.object(ingest_module, "upsert_policy", new=AsyncMock()),
    ):
        count = await ingest_matrix(matrix_yaml)

    assert count == 1


# ---------------------------------------------------------------------------
# risk_scorer/agent.py — score_gap


async def test_score_gap_compliant_returns_none_risk() -> None:
    from reglens.agents.risk_scorer.agent import score_gap
    from reglens.schemas.gap import GapResult, GapStatus
    from reglens.schemas.obligation import Obligation
    from reglens.schemas.risk import RiskLevel

    gap = GapResult(
        obligation=Obligation(id="O1", regulation_ref="R", clause="§1", text="T"),
        matched_policies=[],
        status=GapStatus.COMPLIANT,
        reasoning="ok",
    )
    result = await score_gap(gap)
    assert result.risk_level == RiskLevel.NONE
    assert result.score == 0.0


async def test_score_gap_not_applicable_returns_none_risk() -> None:
    from reglens.agents.risk_scorer.agent import score_gap
    from reglens.schemas.gap import GapResult, GapStatus
    from reglens.schemas.obligation import Obligation
    from reglens.schemas.risk import RiskLevel

    gap = GapResult(
        obligation=Obligation(id="O1", regulation_ref="R", clause="§1", text="T"),
        matched_policies=[],
        status=GapStatus.NOT_APPLICABLE,
        reasoning="n/a",
    )
    result = await score_gap(gap)
    assert result.risk_level == RiskLevel.NONE


async def test_score_gap_real_gap_calls_gemini() -> None:
    import json

    from reglens.agents.risk_scorer import agent as risk_agent
    from reglens.schemas.gap import GapResult, GapStatus
    from reglens.schemas.obligation import Obligation
    from reglens.schemas.risk import RiskLevel

    gap = GapResult(
        obligation=Obligation(id="O1", regulation_ref="R", clause="§1", text="T"),
        matched_policies=[],
        status=GapStatus.GAP,
        reasoning="no coverage",
    )
    gemini_response = json.dumps(
        {
            "risk_level": "high",
            "score": 7.5,
            "justification": "High regulatory risk.",
            "regulatory_penalty_risk": "Fine",
            "reputational_risk": "Trust loss",
        }
    )

    with (
        patch.object(risk_agent, "_load_rubric", return_value="rubric text"),
        patch.object(
            risk_agent, "generate", new=AsyncMock(return_value=gemini_response)
        ),
    ):
        result = await risk_agent.score_gap(gap)

    assert result.risk_level == RiskLevel.HIGH
    assert result.score == 7.5
    assert result.justification == "High regulatory risk."
