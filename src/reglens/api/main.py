"""FastAPI app factory."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from reglens.api.middleware.request_id import RequestIDMiddleware
from reglens.api.routers import health, runs
from reglens.config import get_settings
from reglens.observability.logging import configure_logging
from reglens.observability.tracing import configure_tracing

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(level=settings.log_level)
    configure_tracing(
        service_name=settings.otel_service_name,
        endpoint=settings.otel_exporter_endpoint,
    )

    app = FastAPI(
        title="RegLens API",
        version="0.1.0",
        description="Multi-agent regulatory compliance automation.",
    )

    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(runs.router)

    logger.info("RegLens API started", extra={"environment": settings.environment})
    return app


app = create_app()
