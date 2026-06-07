"""A2A JSON-RPC 2.0 client with OTel tracing and tenacity retries."""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx
from opentelemetry import trace
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from reglens.errors import A2ATransportError

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("reglens.a2a.client")

_RETRYABLE = (
    httpx.ConnectError,
    httpx.TimeoutException,
    httpx.RemoteProtocolError,
)


def _is_retryable_status(exc: BaseException) -> bool:
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500


def _raise_transport_error(retry_state: RetryCallState) -> None:
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    raise A2ATransportError(
        f"A2A agent unreachable after {retry_state.attempt_number} attempts: {exc}"
    )


class A2AError(Exception):
    pass


class A2AClient:
    """Async A2A client for a single remote agent endpoint."""

    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    async def call(
        self,
        method: str,
        params: dict[str, Any],
        *,
        model: str | None = None,
    ) -> Any:
        """Call a JSON-RPC method and return the result, with retries + OTel span."""
        attrs: dict[str, str] = {"a2a.method": method, "a2a.url": self._base_url}
        if model:
            attrs["a2a.model"] = model
        with tracer.start_as_current_span(f"a2a.{method}", attributes=attrs) as span:
            attempt_box = [0]
            try:
                return await self._call_with_retry(method, params, span, attempt_box)
            finally:
                span.set_attribute("a2a.attempt_count", attempt_box[0])

    @retry(
        retry=retry_if_exception_type(_RETRYABLE),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry_error_callback=_raise_transport_error,
    )
    async def _call_with_retry(
        self,
        method: str,
        params: dict[str, Any],
        span: trace.Span,
        attempt_box: list[int],
    ) -> Any:
        attempt_box[0] += 1
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": method,
            "params": params,
        }
        span.set_attribute("a2a.request_bytes", len(str(payload)))

        response = await self._client.post(
            f"{self._base_url}/jsonrpc",
            json=payload,
        )
        span.set_attribute("a2a.response_bytes", len(response.content))
        span.set_attribute("a2a.status_code", response.status_code)

        # Try to parse the JSON-RPC body first — the server always returns one,
        # even on 500s. This gives us the real error message before raise_for_status
        # discards it.
        try:
            body = response.json()
        except Exception:
            # Not JSON — treat as a raw infrastructure error
            response.raise_for_status()
            return None

        if "error" in body and body["error"] is not None:
            err = body["error"]
            msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            # Application-level errors are not retryable — raise A2AError directly.
            raise A2AError(f"[{method}] {msg}")

        # For non-JSON-RPC errors (e.g. proxy 502), still surface HTTP status.
        if response.is_error:
            response.raise_for_status()

        return body.get("result")

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> A2AClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()
