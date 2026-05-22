"""Unit tests for the A2A layer — card, server, and client."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from reglens.a2a.card import AgentCapabilities, AgentCard, AgentSkill
from reglens.a2a.client import A2AClient, A2AError
from reglens.a2a.server import JsonRpcRequest, JsonRpcResponse, make_a2a_app

# ---------------------------------------------------------------------------
# AgentCard and related models


def test_agent_skill_defaults() -> None:
    skill = AgentSkill(id="s1", name="Extract", description="Extracts text")
    assert skill.input_modes == ["application/json"]
    assert skill.output_modes == ["application/json"]


def test_agent_skill_custom_modes() -> None:
    skill = AgentSkill(
        id="s2",
        name="Ingest",
        description="Ingests PDF",
        input_modes=["application/pdf"],
        output_modes=["application/json", "text/plain"],
    )
    assert "application/pdf" in skill.input_modes


def test_agent_capabilities_defaults() -> None:
    caps = AgentCapabilities()
    assert caps.streaming is False
    assert caps.push_notifications is False
    assert caps.state_transition_history is False


def test_agent_card_minimal() -> None:
    card = AgentCard(
        name="TestAgent", description="A test agent", url="http://test:8001"
    )
    assert card.version == "1.0.0"
    assert card.protocol_version == "0.2.5"
    assert card.skills == []
    assert card.default_input_mode == "application/json"


def test_agent_card_with_skills() -> None:
    card = AgentCard(
        name="Ingest",
        description="Ingests PDFs",
        url="http://ingest:8001",
        version="2.0.0",
        skills=[AgentSkill(id="extract", name="Extract", description="Extracts")],
    )
    assert len(card.skills) == 1
    assert card.version == "2.0.0"


def test_agent_card_model_dump() -> None:
    card = AgentCard(name="A", description="B", url="http://x")
    d = card.model_dump(mode="json")
    assert d["name"] == "A"
    assert "capabilities" in d


# ---------------------------------------------------------------------------
# JsonRpc models


def test_jsonrpc_request_defaults() -> None:
    r = JsonRpcRequest(method="test")
    assert r.jsonrpc == "2.0"
    assert r.id is None
    assert r.params == {}


def test_jsonrpc_response_defaults() -> None:
    r = JsonRpcResponse(id="1")
    assert r.jsonrpc == "2.0"
    assert r.result is None
    assert r.error is None


# ---------------------------------------------------------------------------
# A2A server (make_a2a_app)


def _make_test_app() -> tuple[Any, AgentCard]:
    card = AgentCard(name="TestAgent", description="Test", url="http://test")

    async def greet(params: dict[str, Any]) -> dict[str, str]:
        return {"greeting": f"Hello, {params.get('name', 'world')}!"}

    async def fail(params: dict[str, Any]) -> None:
        raise ValueError("intentional error")

    app = make_a2a_app(card, {"greet": greet, "fail": fail})
    return app, card


async def test_agent_card_endpoint() -> None:
    app, _ = _make_test_app()
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/.well-known/agent-card.json")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "TestAgent"
    assert data["url"] == "http://test"


async def test_health_endpoint() -> None:
    app, _ = _make_test_app()
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["agent"] == "TestAgent"


async def test_jsonrpc_valid_call() -> None:
    app, _ = _make_test_app()
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/jsonrpc",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "greet",
                "params": {"name": "Alice"},
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "1"
    assert body["error"] is None
    assert body["result"]["greeting"] == "Hello, Alice!"


async def test_jsonrpc_method_not_found() -> None:
    app, _ = _make_test_app()
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/jsonrpc",
            json={"jsonrpc": "2.0", "id": "2", "method": "nonexistent", "params": {}},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is not None
    assert body["error"]["code"] == -32601
    assert "Method not found" in body["error"]["message"]


async def test_jsonrpc_handler_exception_returns_500() -> None:
    app, _ = _make_test_app()
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/jsonrpc",
            json={"jsonrpc": "2.0", "id": "3", "method": "fail", "params": {}},
        )
    assert resp.status_code == 500
    body = resp.json()
    assert body["error"] is not None
    assert body["error"]["code"] == -32000
    assert "intentional error" in body["error"]["message"]


async def test_jsonrpc_no_id_generates_uuid() -> None:
    app, _ = _make_test_app()
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/jsonrpc",
            json={"jsonrpc": "2.0", "method": "greet", "params": {}},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] is not None  # server generated a UUID


# ---------------------------------------------------------------------------
# A2A client


def _make_httpx_response(
    json_data: dict[str, Any], status_code: int = 200
) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = json_data
    resp.status_code = status_code
    resp.content = b"{}"
    resp.is_error = status_code >= 400
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status_code}", request=MagicMock(), response=resp
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


async def test_client_successful_call() -> None:
    client = A2AClient("http://agent:8001")
    mock_post = AsyncMock(
        return_value=_make_httpx_response(
            {"jsonrpc": "2.0", "id": "x", "result": {"ok": True}, "error": None}
        )
    )
    client._client.post = mock_post  # type: ignore[method-assign]
    result = await client.call("test_method", {"key": "val"})
    assert result == {"ok": True}
    mock_post.assert_called_once()
    await client.aclose()


async def test_client_raises_a2a_error_on_jsonrpc_error() -> None:
    client = A2AClient("http://agent:8001")
    mock_post = AsyncMock(
        return_value=_make_httpx_response(
            {
                "jsonrpc": "2.0",
                "id": "x",
                "result": None,
                "error": {"code": -32000, "message": "Agent exploded"},
            }
        )
    )
    client._client.post = mock_post  # type: ignore[method-assign]
    with pytest.raises(A2AError, match="Agent exploded"):
        await client.call("test_method", {})
    await client.aclose()


async def test_client_raises_a2a_error_string_error() -> None:
    client = A2AClient("http://agent:8001")
    mock_post = AsyncMock(
        return_value=_make_httpx_response(
            {
                "jsonrpc": "2.0",
                "id": "x",
                "result": None,
                "error": "simple error string",
            }
        )
    )
    client._client.post = mock_post  # type: ignore[method-assign]
    with pytest.raises(A2AError, match="simple error string"):
        await client.call("test_method", {})
    await client.aclose()


async def test_client_raises_on_non_json_http_error() -> None:
    client = A2AClient("http://agent:8001")
    bad_resp = MagicMock(spec=httpx.Response)
    bad_resp.json.side_effect = ValueError("Not JSON")
    bad_resp.status_code = 502
    bad_resp.content = b"Bad Gateway"
    bad_resp.is_error = True
    bad_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "502", request=MagicMock(), response=bad_resp
    )
    client._client.post = AsyncMock(return_value=bad_resp)  # type: ignore[method-assign]
    with pytest.raises(httpx.HTTPStatusError):
        await client.call("test_method", {})
    await client.aclose()


async def test_client_context_manager() -> None:
    async with A2AClient("http://agent:8001") as client:
        assert isinstance(client, A2AClient)


async def test_client_aclose() -> None:
    client = A2AClient("http://agent:8001")
    mock_aclose = AsyncMock()
    client._client.aclose = mock_aclose  # type: ignore[method-assign]
    await client.aclose()
    mock_aclose.assert_called_once()


async def test_client_sets_otel_attributes_on_call() -> None:
    client = A2AClient("http://agent:8001", timeout=60.0)
    mock_post = AsyncMock(
        return_value=_make_httpx_response(
            {"jsonrpc": "2.0", "id": "1", "result": "done", "error": None}
        )
    )
    client._client.post = mock_post  # type: ignore[method-assign]
    result = await client.call("my_method", {})
    assert result == "done"
    await client.aclose()
