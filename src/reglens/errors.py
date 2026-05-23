"""ReglensError hierarchy — all domain errors descend from ReglensError.

Each subclass maps to one HTTP status code via the FastAPI exception handler
registered in api/main.py. Adding a new error type only requires adding a
subclass here; the handler picks up the status_code automatically.
"""

from __future__ import annotations


class ReglensError(Exception):
    """Base class for all application errors."""

    status_code: int = 500
    default_message: str = "An internal error occurred."

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.default_message)
        self.message = message or self.default_message


# ---------------------------------------------------------------------------
# Ingestion


class IngestionError(ReglensError):
    """PDF parsing or obligation extraction failed."""

    status_code = 422
    default_message = "Failed to extract obligations from the document."


# ---------------------------------------------------------------------------
# A2A transport


class A2ATransportError(ReglensError):
    """Network-level failure communicating with an A2A agent after all retries."""

    status_code = 502
    default_message = "A2A agent is unavailable."


# ---------------------------------------------------------------------------
# LLM / validation


class LLMValidationError(ReglensError):
    """LLM returned a response that could not be parsed into the expected schema."""

    status_code = 422
    default_message = "LLM response did not conform to the expected schema."


class LLMEmptyResponseError(ReglensError):
    """LLM returned an empty response (blocked, MAX_TOKENS, etc.)."""

    status_code = 422
    default_message = "LLM returned an empty response."


# ---------------------------------------------------------------------------
# Pipeline / run state


class RunNotFoundError(ReglensError):
    """Referenced run_id does not exist."""

    status_code = 404
    default_message = "Run not found."


class RunStateError(ReglensError):
    """Operation not valid for the run's current status (e.g. approve a completed run)."""

    status_code = 409
    default_message = "Operation not valid for the run's current status."
