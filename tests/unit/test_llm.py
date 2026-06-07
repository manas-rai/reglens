"""Unit tests for llm/claude.py and llm/gemini.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import anthropic
import pytest
from google.genai import errors as genai_errors
from pydantic import BaseModel

import reglens.llm.claude as claude_module
import reglens.llm.gemini as gemini_module
from reglens.llm.claude import structured_complete
from reglens.llm.gemini import embed_text, embed_texts, generate, generate_multimodal


@pytest.fixture(autouse=True)
def _skip_retry_sleeps():
    """Tenacity binds its default sleep at AsyncRetrying-construction time, so
    patching the module won't help — wrap llm_retrying in each consumer module
    so the returned AsyncRetrying has its sleep neutered."""
    from reglens.llm import _retry as retry_module

    async def _no_sleep(_seconds: float) -> None:
        return None

    original = retry_module.llm_retrying

    def _fast(max_attempts: int = retry_module.DEFAULT_MAX_ATTEMPTS):
        r = original(max_attempts=max_attempts)
        r.sleep = _no_sleep
        return r

    with (
        patch.object(claude_module, "llm_retrying", _fast),
        patch.object(gemini_module, "llm_retrying", _fast),
    ):
        yield


def _make_anthropic_error(cls):
    """Anthropic exception classes require a Response object — build a minimal one."""
    import httpx

    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    resp = httpx.Response(status_code=500, request=req)
    return cls(message="boom", response=resp, body=None)


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


async def test_structured_complete_retries_transient_then_succeeds() -> None:
    """Two InternalServerError responses, then success — should call 3 times."""
    mock_result = _SampleModel(value="ok")
    mock_completion = MagicMock()
    mock_completion.usage.input_tokens = 1
    mock_completion.usage.output_tokens = 1

    error = _make_anthropic_error(anthropic.InternalServerError)
    mock_instructor = AsyncMock()
    mock_instructor.messages.create_with_completion = AsyncMock(
        side_effect=[error, error, (mock_result, mock_completion)]
    )

    with patch.object(
        claude_module, "_get_instructor_client", return_value=mock_instructor
    ):
        result = await structured_complete(
            response_model=_SampleModel, system="s", user="u"
        )

    assert result.value == "ok"
    assert mock_instructor.messages.create_with_completion.call_count == 3


async def test_structured_complete_does_not_retry_bad_request() -> None:
    """BadRequestError is non-transient — should raise on first attempt."""
    import httpx

    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    resp = httpx.Response(status_code=400, request=req)
    err = anthropic.BadRequestError(message="bad", response=resp, body=None)

    mock_instructor = AsyncMock()
    mock_instructor.messages.create_with_completion = AsyncMock(side_effect=err)

    with (
        patch.object(
            claude_module, "_get_instructor_client", return_value=mock_instructor
        ),
        pytest.raises(anthropic.BadRequestError),
    ):
        await structured_complete(response_model=_SampleModel, system="s", user="u")

    assert mock_instructor.messages.create_with_completion.call_count == 1


async def test_structured_complete_gives_up_after_max_attempts() -> None:
    """Persistent transient error — raises after exhausting attempts (default 3)."""
    error = _make_anthropic_error(anthropic.InternalServerError)
    mock_instructor = AsyncMock()
    mock_instructor.messages.create_with_completion = AsyncMock(side_effect=error)

    with (
        patch.object(
            claude_module, "_get_instructor_client", return_value=mock_instructor
        ),
        pytest.raises(anthropic.InternalServerError),
    ):
        await structured_complete(response_model=_SampleModel, system="s", user="u")

    assert mock_instructor.messages.create_with_completion.call_count == 3


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


async def test_generate_retries_on_server_error() -> None:
    """Gemini ServerError → retry succeeds on third attempt."""
    ok_response = MagicMock()
    ok_response.text = "after retries"

    err = genai_errors.ServerError(code=503, response_json={"error": "unavailable"})
    mock_aio = AsyncMock()
    mock_aio.models.generate_content = AsyncMock(side_effect=[err, err, ok_response])
    mock_client = MagicMock()
    mock_client.aio = mock_aio

    with patch.object(
        gemini_module, "_get_generation_client", return_value=mock_client
    ):
        result = await generate(model="gemini-2.5-flash", prompt="hi")

    assert result == "after retries"
    assert mock_aio.models.generate_content.call_count == 3


async def test_generate_does_not_retry_on_client_error_400() -> None:
    """Gemini ClientError 400 → non-transient, fails on first attempt."""
    err = genai_errors.ClientError(code=400, response_json={"error": "bad request"})
    mock_aio = AsyncMock()
    mock_aio.models.generate_content = AsyncMock(side_effect=err)
    mock_client = MagicMock()
    mock_client.aio = mock_aio

    with (
        patch.object(gemini_module, "_get_generation_client", return_value=mock_client),
        pytest.raises(genai_errors.ClientError),
    ):
        await generate(model="gemini-2.5-flash", prompt="hi")

    assert mock_aio.models.generate_content.call_count == 1


async def test_generate_retries_on_rate_limit() -> None:
    """Gemini 429 → retryable."""
    ok_response = MagicMock()
    ok_response.text = "ok"
    err = genai_errors.ClientError(code=429, response_json={"error": "rate"})

    mock_aio = AsyncMock()
    mock_aio.models.generate_content = AsyncMock(side_effect=[err, ok_response])
    mock_client = MagicMock()
    mock_client.aio = mock_aio

    with patch.object(
        gemini_module, "_get_generation_client", return_value=mock_client
    ):
        result = await generate(model="gemini-2.5-flash", prompt="hi")

    assert result == "ok"
    assert mock_aio.models.generate_content.call_count == 2


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
