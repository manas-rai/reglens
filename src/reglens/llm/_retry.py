"""Shared tenacity retry policy for LLM clients.

We retry only on *transient* upstream failures — network blips, timeouts,
rate limits, and 5xx server errors. Validation errors, auth failures, and
4xx client errors (except 429) are surfaced immediately because retrying
them would just waste tokens.
"""

from __future__ import annotations

import anthropic
from google.genai import errors as genai_errors
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

DEFAULT_MAX_ATTEMPTS = 3


def _is_transient_anthropic(exc: BaseException) -> bool:
    if isinstance(
        exc,
        (
            anthropic.APIConnectionError,
            anthropic.APITimeoutError,
            anthropic.RateLimitError,
            anthropic.InternalServerError,
        ),
    ):
        return True
    if isinstance(exc, anthropic.APIStatusError):
        return exc.status_code >= 500
    return False


def _is_transient_genai(exc: BaseException) -> bool:
    if isinstance(exc, genai_errors.ServerError):
        return True
    if isinstance(exc, genai_errors.APIError):
        # 429 = rate limit (retryable), other 4xx are not
        return exc.code == 429
    return False


def _is_transient(exc: BaseException) -> bool:
    return _is_transient_anthropic(exc) or _is_transient_genai(exc)


def llm_retrying(max_attempts: int = DEFAULT_MAX_ATTEMPTS) -> AsyncRetrying:
    """Tenacity AsyncRetrying configured for LLM calls.

    Use as ``async for attempt in llm_retrying(): with attempt: ...``.
    """
    return AsyncRetrying(
        retry=retry_if_exception(_is_transient),
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
