"""Anthropic Claude client — structured output via instructor."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

import anthropic
import instructor
from pydantic import BaseModel

from reglens.config import get_settings
from reglens.llm._retry import llm_retrying

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-6"


@lru_cache(maxsize=1)
def _get_instructor_client() -> instructor.AsyncInstructor:
    settings = get_settings()
    raw = anthropic.AsyncAnthropic(
        api_key=settings.anthropic_api_key.get_secret_value()
    )
    return instructor.from_anthropic(raw)


async def structured_complete[T: BaseModel](
    response_model: type[T],
    system: str,
    user: str,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 4096,
    **kwargs: Any,
) -> T:
    """Call Claude and parse the response into a Pydantic model via instructor."""
    client = _get_instructor_client()
    result: T | None = None
    completion: Any = None
    async for attempt in llm_retrying():
        with attempt:
            result, completion = await client.messages.create_with_completion(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                response_model=response_model,
                **kwargs,
            )
    assert result is not None and completion is not None
    usage = completion.usage
    logger.debug(
        "Claude call",
        extra={
            "model": model,
            "prompt_tokens": usage.input_tokens,
            "completion_tokens": usage.output_tokens,
        },
    )
    return result
