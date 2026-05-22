"""Unit tests for api/deps.py — API key authentication."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from reglens.api.deps import require_api_key


async def test_require_api_key_valid() -> None:
    mock_settings = MagicMock()
    mock_settings.api_key.get_secret_value.return_value = "secret-key"
    with patch("reglens.api.deps.get_settings", return_value=mock_settings):
        # Should complete without raising
        await require_api_key(x_api_key="secret-key")


async def test_require_api_key_invalid() -> None:
    mock_settings = MagicMock()
    mock_settings.api_key.get_secret_value.return_value = "correct-key"
    with (
        patch("reglens.api.deps.get_settings", return_value=mock_settings),
        pytest.raises(HTTPException) as exc_info,
    ):
        await require_api_key(x_api_key="wrong-key")
    assert exc_info.value.status_code == 401
    assert "Invalid API key" in exc_info.value.detail


async def test_require_api_key_empty_string_rejected() -> None:
    mock_settings = MagicMock()
    mock_settings.api_key.get_secret_value.return_value = "real-key"
    with (
        patch("reglens.api.deps.get_settings", return_value=mock_settings),
        pytest.raises(HTTPException) as exc_info,
    ):
        await require_api_key(x_api_key="")
    assert exc_info.value.status_code == 401
