"""Request ID middleware — injects x-request-id header on every response."""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: object) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        response: Response = await call_next(request)  # type: ignore[operator]
        response.headers["x-request-id"] = request_id
        return response
