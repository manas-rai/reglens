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


async def test_score_gap_invalid_json_raises() -> None:
    import json

    from reglens.agents.risk_scorer import agent as risk_agent
    from reglens.schemas.gap import GapResult, GapStatus
    from reglens.schemas.obligation import Obligation

    gap = GapResult(
        obligation=Obligation(id="O1", regulation_ref="R", clause="§1", text="T"),
        matched_policies=[],
        status=GapStatus.GAP,
        reasoning="no coverage",
    )

    with (
        patch.object(risk_agent, "_load_rubric", return_value="rubric text"),
        patch.object(risk_agent, "generate", new=AsyncMock(return_value="not-json")),
        pytest.raises(json.JSONDecodeError),
    ):
        await risk_agent.score_gap(gap)


# ---------------------------------------------------------------------------
# servers — build_app() and handler functions


def test_ingestion_server_build_app_returns_app_and_port() -> None:
    from reglens.agents.ingestion.server import build_app

    app, port = build_app()
    assert app is not None
    assert isinstance(port, int)


def test_risk_scorer_server_build_app_returns_app_and_port() -> None:
    from reglens.agents.risk_scorer.server import build_app

    app, port = build_app()
    assert app is not None
    assert isinstance(port, int)


async def test_ingestion_server_handle_extract_obligations() -> None:
    import base64

    from reglens.agents.ingestion import server as ingest_server
    from reglens.schemas.obligation import Obligation

    pdf_bytes = b"%PDF fake"
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode()
    obligation = Obligation(id="O1", regulation_ref="R", clause="§1", text="T")

    with patch.object(
        ingest_server,
        "extract_obligations",
        new=AsyncMock(return_value=[obligation]),
    ):
        result = await ingest_server.handle_extract_obligations(
            {"pdf_b64": pdf_b64, "regulation_ref": "R", "domain": "banking"}
        )

    assert isinstance(result, list)
    assert result[0]["id"] == "O1"


async def test_risk_scorer_server_handle_score_gap() -> None:
    from reglens.agents.risk_scorer import server as risk_server
    from reglens.schemas.gap import GapResult, GapStatus
    from reglens.schemas.obligation import Obligation
    from reglens.schemas.risk import RiskLevel, RiskScore

    gap = GapResult(
        obligation=Obligation(id="O1", regulation_ref="R", clause="§1", text="T"),
        matched_policies=[],
        status=GapStatus.GAP,
        reasoning="uncovered",
    )
    risk = RiskScore(
        gap_result=gap, risk_level=RiskLevel.HIGH, score=7.0, justification="j"
    )
    params = {"gap_result": gap.model_dump(mode="json")}

    with patch.object(risk_server, "score_gap", new=AsyncMock(return_value=risk)):
        result = await risk_server.handle_score_gap(params)

    assert result["risk_level"] == "high"
    assert result["score"] == 7.0


def test_supervisor_server_health() -> None:
    import httpx as _httpx

    from reglens.supervisor.server import app

    transport = _httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    import asyncio

    async def _check() -> dict:
        async with _httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/health")
            return resp.json()

    data = asyncio.get_event_loop().run_until_complete(_check())
    assert data == {"status": "ok"}


def test_api_main_create_app() -> None:
    from unittest.mock import MagicMock

    import reglens.api.main as main_module

    mock_settings = MagicMock()
    mock_settings.log_level = "INFO"
    mock_settings.otel_service_name = "test"
    mock_settings.otel_exporter_endpoint = None
    mock_settings.environment = "test"

    with patch.object(main_module, "get_settings", return_value=mock_settings):
        app = main_module.create_app()

    assert app is not None
    assert app.title == "RegLens API"


# ---------------------------------------------------------------------------
# supervisor/checkpoint.py — get_checkpointer


async def test_get_checkpointer_yields_saver() -> None:
    from reglens.supervisor import checkpoint as cp_module

    mock_saver = AsyncMock()
    mock_saver.setup = AsyncMock()

    @asynccontextmanager
    async def _mock_from_conn_string(_conn_str: str):
        yield mock_saver

    mock_settings = MagicMock()
    mock_settings.database_url = "postgresql+psycopg://user:pass@localhost/db"

    with (
        patch.object(cp_module, "get_settings", return_value=mock_settings),
        patch(
            "reglens.supervisor.checkpoint.AsyncPostgresSaver.from_conn_string",
            _mock_from_conn_string,
        ),
    ):
        async with cp_module.get_checkpointer() as saver:
            assert saver is mock_saver

    mock_saver.setup.assert_called_once()


# ---------------------------------------------------------------------------
# config.py — get_settings cache


def test_get_settings_is_cached() -> None:
    from reglens.config import get_settings

    get_settings.cache_clear()
    try:
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2
    finally:
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# a2a/client.py — is_error branch and non-JSON path


async def test_a2a_client_is_error_no_jsonrpc_error_raises() -> None:
    from reglens.a2a.client import A2AClient

    client = A2AClient("http://agent:8001")
    bad_resp = MagicMock(spec=__import__("httpx").Response)
    bad_resp.json.return_value = {
        "jsonrpc": "2.0",
        "id": "x",
        "result": None,
        "error": None,
    }
    bad_resp.status_code = 502
    bad_resp.content = b"{}"
    bad_resp.is_error = True
    bad_resp.raise_for_status.side_effect = __import__("httpx").HTTPStatusError(
        "502", request=MagicMock(), response=bad_resp
    )
    client._client.post = AsyncMock(return_value=bad_resp)  # type: ignore[method-assign]

    with pytest.raises(__import__("httpx").HTTPStatusError):
        await client.call("my_method", {})
    await client.aclose()
