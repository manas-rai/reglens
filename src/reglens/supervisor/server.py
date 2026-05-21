"""Supervisor HTTP server — exposes a minimal internal API for the FastAPI service."""

from __future__ import annotations

import logging

import uvicorn
from fastapi import FastAPI

from reglens.observability.logging import configure_logging

app = FastAPI(title="reglens-supervisor", version="0.1.0")
logger = logging.getLogger(__name__)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    configure_logging()
    uvicorn.run(app, host="0.0.0.0", port=8010, log_config=None)
