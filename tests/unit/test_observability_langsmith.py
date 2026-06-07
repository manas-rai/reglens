"""Unit tests for observability/langsmith.py."""

from __future__ import annotations

import logging

import pytest
from pydantic import SecretStr

from reglens.config import Settings
from reglens.observability.langsmith import configure_langsmith

_LANGSMITH_ENV_VARS = ("LANGSMITH_API_KEY", "LANGSMITH_PROJECT", "LANGCHAIN_TRACING_V2")


@pytest.fixture(autouse=True)
def _clear_langsmith_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _LANGSMITH_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "api_key": SecretStr("test"),
        "gemini_api_key": SecretStr("test"),
        "anthropic_api_key": SecretStr("test"),
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_disabled_by_default_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(
        langsmith_tracing_enabled=False,
        langsmith_api_key=SecretStr("sk-123"),
    )
    assert configure_langsmith(settings) is False
    for var in _LANGSMITH_ENV_VARS:
        assert var not in __import__("os").environ


def test_enabled_with_key_sets_env_vars() -> None:
    import os

    settings = _settings(
        langsmith_tracing_enabled=True,
        langsmith_api_key=SecretStr("sk-abc"),
        langsmith_project="reglens-test",
    )
    assert configure_langsmith(settings) is True
    assert os.environ["LANGSMITH_API_KEY"] == "sk-abc"
    assert os.environ["LANGSMITH_PROJECT"] == "reglens-test"
    assert os.environ["LANGCHAIN_TRACING_V2"] == "true"


def test_enabled_without_key_warns_and_skips(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import os

    settings = _settings(
        langsmith_tracing_enabled=True,
        langsmith_api_key=None,
    )
    with caplog.at_level(logging.WARNING, logger="reglens.observability.langsmith"):
        assert configure_langsmith(settings) is False
    assert any("LANGSMITH_API_KEY" in r.message for r in caplog.records)
    for var in _LANGSMITH_ENV_VARS:
        assert var not in os.environ
