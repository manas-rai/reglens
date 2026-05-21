"""Google Gemini client via google-genai SDK."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from google import genai
from google.genai import types as genai_types

from reglens.config import get_settings

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-004"
EMBEDDING_DIM = 768


@lru_cache(maxsize=1)
def _get_client() -> genai.Client:
    settings = get_settings()
    return genai.Client(api_key=settings.gemini_api_key.get_secret_value())


async def embed_text(text: str) -> list[float]:
    """Embed a single text string using Gemini text-embedding-004."""
    client = _get_client()
    response = await client.aio.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
    )
    values: list[float] = response.embeddings[0].values  # type: ignore[index]
    return values


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch embed multiple texts."""
    client = _get_client()
    response = await client.aio.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=texts,
    )
    return [e.values for e in response.embeddings]  # type: ignore[union-attr]


async def generate(
    model: str,
    prompt: str,
    system_instruction: str | None = None,
    response_schema: Any = None,
    max_output_tokens: int = 8192,
) -> str:
    """Generate text with an optional structured JSON schema."""
    client = _get_client()
    config_kwargs: dict[str, Any] = {"max_output_tokens": max_output_tokens}
    if system_instruction:
        config_kwargs["system_instruction"] = system_instruction
    if response_schema is not None:
        config_kwargs["response_mime_type"] = "application/json"
        config_kwargs["response_schema"] = response_schema

    config = genai_types.GenerateContentConfig(**config_kwargs)
    response = await client.aio.models.generate_content(
        model=model,
        contents=prompt,
        config=config,
    )
    return response.text or ""  # type: ignore[return-value]


async def generate_multimodal(
    model: str,
    parts: list[genai_types.Part],
    system_instruction: str | None = None,
    response_schema: Any = None,
    max_output_tokens: int = 8192,
) -> str:
    """Generate with multimodal content (text + inline bytes)."""
    client = _get_client()
    config_kwargs: dict[str, Any] = {"max_output_tokens": max_output_tokens}
    if system_instruction:
        config_kwargs["system_instruction"] = system_instruction
    if response_schema is not None:
        config_kwargs["response_mime_type"] = "application/json"
        config_kwargs["response_schema"] = response_schema

    config = genai_types.GenerateContentConfig(**config_kwargs)
    response = await client.aio.models.generate_content(
        model=model,
        contents=parts,
        config=config,
    )
    return response.text or ""  # type: ignore[return-value]
