"""Google Gemini client via google-genai SDK."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from reglens.config import get_settings
from reglens.llm._retry import llm_retrying

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIM = 768  # truncated via output_dimensionality — HNSW index cap is 2000


@lru_cache(maxsize=1)
def _get_generation_client() -> genai.Client:
    """v1beta client — required for gemini-2.5-pro/flash (experimental models)."""
    settings = get_settings()
    return genai.Client(
        api_key=settings.gemini_api_key.get_secret_value(),
        http_options=genai_types.HttpOptions(api_version="v1beta"),
    )


@lru_cache(maxsize=1)
def _get_embedding_client() -> genai.Client:
    """v1 client — text-embedding-004 is only available in the stable v1 API."""
    settings = get_settings()
    return genai.Client(
        api_key=settings.gemini_api_key.get_secret_value(),
        http_options=genai_types.HttpOptions(api_version="v1"),
    )


async def embed_text(text: str) -> list[float]:
    """Embed a single text string, truncated to EMBEDDING_DIM dimensions."""
    client = _get_embedding_client()
    config = genai_types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIM)
    response: Any = None
    async for attempt in llm_retrying():
        with attempt:
            response = await client.aio.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=text,
                config=config,
            )
    return list(response.embeddings[0].values)


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed multiple texts sequentially (embedContent does not support true batching)."""
    return [await embed_text(t) for t in texts]


async def generate(
    model: str,
    prompt: str,
    system_instruction: str | None = None,
    response_schema: Any = None,
    max_output_tokens: int = 8192,
    fallback_model: str | None = None,
) -> str:
    """Generate text with an optional structured JSON schema.

    If ``fallback_model`` is provided, a final ``ServerError`` (5xx — e.g.
    Gemini-side overload) raised after retries are exhausted will trigger
    a single transparent retry against the fallback model. This trades a
    small quality regression during outages for end-user availability.
    """
    client = _get_generation_client()
    config = _build_generation_config(
        system_instruction, response_schema, max_output_tokens
    )
    try:
        return await _generate_with_retries(client, model, prompt, config)
    except genai_errors.ServerError as exc:
        if not fallback_model:
            raise
        logger.warning(
            "Primary model %s failed after retries (%s); falling back to %s",
            model,
            exc,
            fallback_model,
        )
        return await _generate_with_retries(client, fallback_model, prompt, config)


async def _generate_with_retries(
    client: genai.Client,
    model: str,
    prompt: str,
    config: genai_types.GenerateContentConfig,
) -> str:
    response: Any = None
    async for attempt in llm_retrying():
        with attempt:
            response = await client.aio.models.generate_content(
                model=model,
                contents=prompt,
                config=config,
            )
    return response.text or ""


def _build_generation_config(
    system_instruction: str | None,
    response_schema: Any,
    max_output_tokens: int,
) -> genai_types.GenerateContentConfig:
    config_kwargs: dict[str, Any] = {"max_output_tokens": max_output_tokens}
    if system_instruction:
        config_kwargs["system_instruction"] = system_instruction
    if response_schema is not None:
        config_kwargs["response_mime_type"] = "application/json"
        config_kwargs["response_schema"] = response_schema
    return genai_types.GenerateContentConfig(**config_kwargs)


async def generate_multimodal(
    model: str,
    parts: list[genai_types.Part],
    system_instruction: str | None = None,
    response_schema: Any = None,
    max_output_tokens: int = 8192,
    fallback_model: str | None = None,
) -> str:
    """Generate with multimodal content (text + inline bytes).

    ``fallback_model`` behaves identically to ``generate`` — only triggers
    on a post-retry ``ServerError`` from the primary model.
    """
    client = _get_generation_client()
    config = _build_generation_config(
        system_instruction, response_schema, max_output_tokens
    )
    try:
        return await _generate_multimodal_with_retries(client, model, parts, config)
    except genai_errors.ServerError as exc:
        if not fallback_model:
            raise
        logger.warning(
            "Primary multimodal model %s failed after retries (%s); falling back to %s",
            model,
            exc,
            fallback_model,
        )
        return await _generate_multimodal_with_retries(
            client, fallback_model, parts, config
        )


async def _generate_multimodal_with_retries(
    client: genai.Client,
    model: str,
    parts: list[genai_types.Part],
    config: genai_types.GenerateContentConfig,
) -> str:
    response: Any = None
    async for attempt in llm_retrying():
        with attempt:
            response = await client.aio.models.generate_content(
                model=model,
                contents=parts,
                config=config,
            )
    if not response.text:
        candidate = response.candidates[0] if response.candidates else None
        finish_reason = candidate.finish_reason if candidate else "NO_CANDIDATES"
        logger.error(
            "Gemini returned empty text. finish_reason=%s prompt_feedback=%s",
            finish_reason,
            response.prompt_feedback,
        )
    return response.text or ""
