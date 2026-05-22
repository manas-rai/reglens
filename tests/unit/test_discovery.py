"""Unit tests for a2a/discovery.py — Agent Card fetching."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from reglens.a2a.card import AgentCard
from reglens.a2a.discovery import fetch_agent_card


async def test_fetch_agent_card_success() -> None:
    card_data = {
        "name": "TestAgent",
        "description": "A test agent",
        "url": "http://agent:8001",
        "version": "1.0.0",
        "protocol_version": "0.2.5",
        "capabilities": {
            "streaming": False,
            "push_notifications": False,
            "state_transition_history": False,
        },
        "skills": [],
        "default_input_mode": "application/json",
        "default_output_mode": "application/json",
    }

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.json.return_value = card_data
    mock_response.raise_for_status.return_value = None

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("reglens.a2a.discovery.httpx.AsyncClient", return_value=mock_client):
        card = await fetch_agent_card("http://agent:8001")

    assert isinstance(card, AgentCard)
    assert card.name == "TestAgent"
    assert card.url == "http://agent:8001"


async def test_fetch_agent_card_strips_trailing_slash() -> None:
    card_data = {
        "name": "A",
        "description": "B",
        "url": "http://x",
        "version": "1.0.0",
        "protocol_version": "0.2.5",
        "capabilities": {
            "streaming": False,
            "push_notifications": False,
            "state_transition_history": False,
        },
        "skills": [],
        "default_input_mode": "application/json",
        "default_output_mode": "application/json",
    }

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.json.return_value = card_data
    mock_response.raise_for_status.return_value = None

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("reglens.a2a.discovery.httpx.AsyncClient", return_value=mock_client):
        await fetch_agent_card("http://agent:8001/")

    call_args = mock_client.get.call_args[0][0]
    assert not call_args.endswith("//")
    assert call_args.endswith("/.well-known/agent-card.json")


async def test_fetch_agent_card_raises_on_http_error() -> None:
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "404", request=MagicMock(), response=mock_response
    )

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("reglens.a2a.discovery.httpx.AsyncClient", return_value=mock_client),
        pytest.raises(httpx.HTTPStatusError),
    ):
        await fetch_agent_card("http://agent:8001")
