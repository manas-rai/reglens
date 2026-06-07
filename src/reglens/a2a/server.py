"""A2A JSON-RPC 2.0 server factory.

Each ADK agent wraps itself with this factory.  The resulting FastAPI app:
  - Serves the Agent Card at GET /.well-known/agent-card.json
  - Handles A2A method calls at POST /jsonrpc
  - Exposes GET /health for Docker health checks
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from reglens.a2a.card import AgentCard
from reglens.a2a.idempotency import IdempotencyStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JSON-RPC 2.0 envelope models


class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int | None = None
    method: str
    params: dict[str, Any] = {}
    idempotency_key: str | None = None


class JsonRpcResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int | None = None
    result: Any = None
    error: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Handler type: async fn(params) -> result

Handler = Callable[[dict[str, Any]], Awaitable[Any]]


def make_a2a_app(
    card: AgentCard,
    handlers: Mapping[str, Handler],
    idempotency_store: IdempotencyStore | None = None,
) -> FastAPI:
    """Create a FastAPI app that speaks A2A JSON-RPC 2.0.

    When ``idempotency_store`` is provided, requests carrying an
    ``idempotency_key`` field have their results cached by ``(method, key)``
    — subsequent duplicate calls within the TTL return the cached result
    without re-invoking the handler.
    """

    app = FastAPI(title=card.name, version=card.version)
    store = idempotency_store or IdempotencyStore()

    @app.get("/.well-known/agent-card.json")
    async def agent_card() -> dict[str, Any]:
        return card.model_dump(mode="json")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "agent": card.name}

    @app.post("/jsonrpc")
    async def jsonrpc(request: Request) -> JSONResponse:
        body = await request.json()
        req = JsonRpcRequest.model_validate(body)
        req_id = req.id or str(uuid.uuid4())

        handler = handlers.get(req.method)
        if handler is None:
            return JSONResponse(
                JsonRpcResponse(
                    id=req_id,
                    error={
                        "code": -32601,
                        "message": f"Method not found: {req.method}",
                    },
                ).model_dump(mode="json")
            )

        try:
            if req.idempotency_key:
                hit, cached = await store.get(req.method, req.idempotency_key)
                if hit:
                    logger.info(
                        "idempotency_hit method=%s key=%s",
                        req.method,
                        req.idempotency_key,
                    )
                    return JSONResponse(
                        JsonRpcResponse(id=req_id, result=cached).model_dump(
                            mode="json"
                        )
                    )

            result = await handler(req.params)

            if req.idempotency_key:
                await store.set(req.method, req.idempotency_key, result)

            return JSONResponse(
                JsonRpcResponse(id=req_id, result=result).model_dump(mode="json")
            )
        except Exception as exc:
            logger.exception("A2A handler error for method %s", req.method)
            return JSONResponse(
                JsonRpcResponse(
                    id=req_id,
                    error={"code": -32000, "message": str(exc)},
                ).model_dump(mode="json"),
                status_code=500,
            )

    return app
