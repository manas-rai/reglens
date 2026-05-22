"""Request/response schemas for the runs API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class RunCreatedResponse(BaseModel):
    run_id: str
    status: str = "pending"


class RunStatusResponse(BaseModel):
    run_id: str
    status: str
    domain: str
    pdf_filename: str | None
    error_message: str | None
    created_at: str
    updated_at: str


class ApproveRequest(BaseModel):
    approved: bool
    edits: list[dict[str, Any]] = []


class ApproveResponse(BaseModel):
    run_id: str
    status: str
