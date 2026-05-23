"""FastAPI app factory."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from reglens.api.middleware.request_id import RequestIDMiddleware
from reglens.api.routers import health, runs
from reglens.config import get_settings
from reglens.errors import ReglensError
from reglens.observability.logging import configure_logging
from reglens.observability.tracing import configure_tracing

if TYPE_CHECKING:
    from reglens.config import Settings

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(level=settings.log_level)
    configure_tracing(
        service_name=settings.otel_service_name,
        otlp_endpoint=settings.otel_exporter_endpoint,
    )
    _configure_langsmith(settings)

    app = FastAPI(
        title="RegLens API",
        version="0.1.0",
        description="Multi-agent regulatory compliance automation.",
    )

    # Rate limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
    app.add_middleware(SlowAPIMiddleware)

    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(ReglensError)
    async def reglens_error_handler(
        request: Request, exc: ReglensError
    ) -> JSONResponse:
        logger.warning(
            "Application error",
            extra={"error_type": type(exc).__name__, "detail": exc.message},
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message, "error_type": type(exc).__name__},
        )

    app.include_router(health.router)
    app.include_router(runs.router)

    logger.info("RegLens API started", extra={"environment": settings.environment})
    return app


def _configure_langsmith(settings: Settings) -> None:
    """Enable LangSmith tracing when the API key is present and tracing is enabled."""
    if not settings.langsmith_tracing_enabled:
        return
    if settings.langsmith_api_key is None:
        logger.warning(
            "LANGSMITH_TRACING_ENABLED=true but LANGSMITH_API_KEY is not set"
        )
        return

    import os

    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key.get_secret_value()
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    logger.info(
        "LangSmith tracing enabled", extra={"project": settings.langsmith_project}
    )


app = create_app()
