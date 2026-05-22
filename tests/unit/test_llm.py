"""Unit tests for llm/claude.py and llm/gemini.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from pydantic import BaseModel

import reglens.llm.claude as claude_module
import reglens.llm.gemini as gemini_module
from reglens.llm.claude import structured_complete
from reglens.llm.gemini import embed_text, embed_texts, generate, generate_multimodal

# ---------------------------------------------------------------------------
# claude.py


class _SampleModel(BaseModel):
    value: str


async def test_structured_complete_returns_model() -> None:
    mock_result = _SampleModel(value="test")
    mock_completion = MagicMock()
    mock_completion.usage.input_tokens = 10
    mock_completion.usage.output_tokens = 5

    mock_instructor = AsyncMock()
    mock_instructor.messages.create_with_completion = AsyncMock(
        return_value=(mock_result, mock_completion)
    )

    with patch.object(
        claude_module, "_get_instructor_client", return_value=mock_instructor
    ):
        result = await structured_complete(
            response_model=_SampleModel,
            system="You are a test assistant.",
            user="Return a model.",
        )

    assert isinstance(result, _SampleModel)
    assert result.value == "test"


async def test_structured_complete_passes_model_and_tokens() -> None:
    mock_result = _SampleModel(value="ok")
    mock_completion = MagicMock()
    mock_completion.usage.input_tokens = 100
    mock_completion.usage.output_tokens = 50

    mock_instructor = AsyncMock()
    mock_instructor.messages.create_with_completion = AsyncMock(
        return_value=(mock_result, mock_completion)
    )

    with patch.object(
        claude_module, "_get_instructor_client", return_value=mock_instructor
    ):
        await structured_complete(
            response_model=_SampleModel,
            system="sys",
            user="usr",
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
        )

    call_kwargs = mock_instructor.messages.create_with_completion.call_args[1]
    assert call_kwargs["model"] == "claude-haiku-4-5-20251001"
    assert call_kwargs["max_tokens"] == 1024


# ---------------------------------------------------------------------------
# gemini.py — embed_text and embed_texts


def _make_embedding_client(values: list[float]) -> MagicMock:
    mock_embedding = MagicMock()
    mock_embedding.values = values
    mock_response = MagicMock()
    mock_response.embeddings = [mock_embedding]

    mock_aio = AsyncMock()
    mock_aio.models.embed_content = AsyncMock(return_value=mock_response)

    mock_client = MagicMock()
    mock_client.aio = mock_aio
    return mock_client


async def test_embed_text_returns_float_list() -> None:
    values = [0.1, 0.2, 0.3]
    mock_client = _make_embedding_client(values)

    with patch.object(gemini_module, "_get_embedding_client", return_value=mock_client):
        result = await embed_text("some text to embed")

    assert result == values


async def test_embed_texts_returns_list_of_lists() -> None:
    values = [0.5, 0.6]
    mock_client = _make_embedding_client(values)

    with patch.object(gemini_module, "_get_embedding_client", return_value=mock_client):
        result = await embed_texts(["text1", "text2"])

    assert result == [values, values]
    assert len(result) == 2


async def test_embed_texts_empty_returns_empty() -> None:
    mock_client = _make_embedding_client([])
    with patch.object(gemini_module, "_get_embedding_client", return_value=mock_client):
        result = await embed_texts([])
    assert result == []


# ---------------------------------------------------------------------------
# gemini.py — generate


def _make_generation_client(text: str) -> MagicMock:
    mock_response = MagicMock()
    mock_response.text = text

    mock_aio = AsyncMock()
    mock_aio.models.generate_content = AsyncMock(return_value=mock_response)

    mock_client = MagicMock()
    mock_client.aio = mock_aio
    return mock_client


async def test_generate_returns_text() -> None:
    mock_client = _make_generation_client("Hello there")
    with patch.object(
        gemini_module, "_get_generation_client", return_value=mock_client
    ):
        result = await generate(model="gemini-2.5-flash", prompt="Say hello")
    assert result == "Hello there"


async def test_generate_with_system_instruction() -> None:
    mock_client = _make_generation_client("result")
    with patch.object(
        gemini_module, "_get_generation_client", return_value=mock_client
    ):
        result = await generate(
            model="gemini-2.5-flash",
            prompt="Do something",
            system_instruction="Be concise",
        )
    assert result == "result"
    call_kwargs = mock_client.aio.models.generate_content.call_args[1]
    assert "system_instruction" in str(call_kwargs["config"])


async def test_generate_with_response_schema() -> None:
    mock_client = _make_generation_client('{"key": "value"}')
    with patch.object(
        gemini_module, "_get_generation_client", return_value=mock_client
    ):
        result = await generate(
            model="gemini-2.5-flash",
            prompt="Return JSON",
            response_schema={"type": "object"},
        )
    assert result == '{"key": "value"}'


async def test_generate_empty_response_returns_empty_string() -> None:
    mock_response = MagicMock()
    mock_response.text = None

    mock_aio = AsyncMock()
    mock_aio.models.generate_content = AsyncMock(return_value=mock_response)

    mock_client = MagicMock()
    mock_client.aio = mock_aio

    with patch.object(
        gemini_module, "_get_generation_client", return_value=mock_client
    ):
        result = await generate(model="gemini-2.5-flash", prompt="test")
    assert result == ""


# ---------------------------------------------------------------------------
# gemini.py — generate_multimodal


async def test_generate_multimodal_returns_text() -> None:
    from google.genai import types as genai_types

    mock_client = _make_generation_client("Extracted text")
    with patch.object(
        gemini_module, "_get_generation_client", return_value=mock_client
    ):
        result = await generate_multimodal(
            model="gemini-2.5-pro",
            parts=[genai_types.Part(text="some text")],
        )
    assert result == "Extracted text"


async def test_generate_multimodal_logs_on_empty() -> None:
    from google.genai import types as genai_types

    mock_response = MagicMock()
    mock_response.text = None
    mock_response.prompt_feedback = "blocked"

    mock_candidate = MagicMock()
    mock_candidate.finish_reason = "MAX_TOKENS"
    mock_response.candidates = [mock_candidate]

    mock_aio = AsyncMock()
    mock_aio.models.generate_content = AsyncMock(return_value=mock_response)

    mock_client = MagicMock()
    mock_client.aio = mock_aio

    with patch.object(
        gemini_module, "_get_generation_client", return_value=mock_client
    ):
        result = await generate_multimodal(
            model="gemini-2.5-pro",
            parts=[genai_types.Part(text="test")],
        )
    assert result == ""


async def test_generate_multimodal_no_candidates_on_empty() -> None:
    from google.genai import types as genai_types

    mock_response = MagicMock()
    mock_response.text = None
    mock_response.candidates = []
    mock_response.prompt_feedback = None

    mock_aio = AsyncMock()
    mock_aio.models.generate_content = AsyncMock(return_value=mock_response)

    mock_client = MagicMock()
    mock_client.aio = mock_aio

    with patch.object(
        gemini_module, "_get_generation_client", return_value=mock_client
    ):
        result = await generate_multimodal(
            model="gemini-2.5-pro",
            parts=[genai_types.Part(text="test")],
        )
    assert result == ""
