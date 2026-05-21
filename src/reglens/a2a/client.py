"""A2A JSON-RPC 2.0 client with OTel tracing and tenacity retries."""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx
from opentelemetry import trace
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("reglens.a2a.client")

_RETRYABLE = (
    httpx.ConnectError,
    httpx.TimeoutException,
    httpx.RemoteProtocolError,
)


def _is_retryable_status(exc: BaseException) -> bool:
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500


class A2AError(Exception):
    pass


class A2AClient:
    """Async A2A client for a single remote agent endpoint."""

    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    async def call(self, method: str, params: dict[str, Any]) -> Any:
        """Call a JSON-RPC method and return the result, with retries + OTel span."""
        with tracer.start_as_current_span(
            f"a2a.{method}",
            attributes={"a2a.method": method, "a2a.url": self._base_url},
        ) as span:
            result = await self._call_with_retry(method, params, span)
            return result

    @retry(
        retry=retry_if_exception_type(_RETRYABLE),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    async def _call_with_retry(
        self,
        method: str,
        params: dict[str, Any],
        span: trace.Span,
    ) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": method,
            "params": params,
        }
        req_bytes = len(str(payload))
        span.set_attribute("a2a.request_bytes", req_bytes)

        response = await self._client.post(
            f"{self._base_url}/jsonrpc",
            json=payload,
        )
        response.raise_for_status()

        span.set_attribute("a2a.response_bytes", len(response.content))
        span.set_attribute("a2a.status_code", response.status_code)

        body = response.json()
        if "error" in body and body["error"] is not None:
            raise A2AError(f"A2A error from {method}: {body['error']}")

        return body.get("result")

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> A2AClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()
