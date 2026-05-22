"""Unit tests for agents/knowledge — retrieve_all_policies and retrieve_matching_policies."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

from reglens.agents.knowledge.node import retrieve_all_policies
from reglens.agents.knowledge.retriever import retrieve_matching_policies
from reglens.schemas.obligation import Obligation, ObligationType
from reglens.schemas.policy import PolicyMatch


def _make_obligation(obl_id: str = "OBL-001") -> Obligation:
    return Obligation(
        id=obl_id,
        regulation_ref="REG",
        clause="§1",
        text="Banks must KYC.",
        obligation_type=ObligationType.MANDATORY,
        domain="banking",
    )


def _make_db_row() -> dict:
    return {
        "id": "CTL-001",
        "domain": "banking",
        "section": "KYC",
        "title": "KYC Policy",
        "text": "Customer ID verification required.",
        "owner": "compliance",
        "tags": "kyc,aml",
        "relevance": 0.85,
    }


async def test_retrieve_matching_policies_returns_matches() -> None:
    obligation = _make_obligation()
    rows = [_make_db_row()]
    embedding = [0.1] * 768

    mock_session = AsyncMock()

    @asynccontextmanager
    async def mock_db_session():
        yield mock_session

    with (
        patch(
            "reglens.agents.knowledge.retriever.embed_text",
            new=AsyncMock(return_value=embedding),
        ),
        patch(
            "reglens.agents.knowledge.retriever.search_policies",
            new=AsyncMock(return_value=rows),
        ),
        patch("reglens.agents.knowledge.retriever.db_session", mock_db_session),
    ):
        matches = await retrieve_matching_policies(obligation, k=5)

    assert len(matches) == 1
    assert isinstance(matches[0], PolicyMatch)
    assert matches[0].policy.id == "CTL-001"
    assert matches[0].relevance_score == 0.85
    assert matches[0].matched_obligation_id == "OBL-001"


async def test_retrieve_matching_policies_parses_tags() -> None:
    obligation = _make_obligation()
    rows = [_make_db_row()]
    embedding = [0.1] * 768

    mock_session = AsyncMock()

    @asynccontextmanager
    async def mock_db_session():
        yield mock_session

    with (
        patch(
            "reglens.agents.knowledge.retriever.embed_text",
            new=AsyncMock(return_value=embedding),
        ),
        patch(
            "reglens.agents.knowledge.retriever.search_policies",
            new=AsyncMock(return_value=rows),
        ),
        patch("reglens.agents.knowledge.retriever.db_session", mock_db_session),
    ):
        matches = await retrieve_matching_policies(obligation)

    assert matches[0].policy.tags == ["kyc", "aml"]


async def test_retrieve_matching_policies_empty_tags() -> None:
    obligation = _make_obligation()
    row = {**_make_db_row(), "tags": ""}
    embedding = [0.1] * 768

    mock_session = AsyncMock()

    @asynccontextmanager
    async def mock_db_session():
        yield mock_session

    with (
        patch(
            "reglens.agents.knowledge.retriever.embed_text",
            new=AsyncMock(return_value=embedding),
        ),
        patch(
            "reglens.agents.knowledge.retriever.search_policies",
            new=AsyncMock(return_value=[row]),
        ),
        patch("reglens.agents.knowledge.retriever.db_session", mock_db_session),
    ):
        matches = await retrieve_matching_policies(obligation)

    assert matches[0].policy.tags == []


async def test_retrieve_matching_policies_no_tags_key() -> None:
    obligation = _make_obligation()
    row = {k: v for k, v in _make_db_row().items() if k != "tags"}
    embedding = [0.1] * 768

    mock_session = AsyncMock()

    @asynccontextmanager
    async def mock_db_session():
        yield mock_session

    with (
        patch(
            "reglens.agents.knowledge.retriever.embed_text",
            new=AsyncMock(return_value=embedding),
        ),
        patch(
            "reglens.agents.knowledge.retriever.search_policies",
            new=AsyncMock(return_value=[row]),
        ),
        patch("reglens.agents.knowledge.retriever.db_session", mock_db_session),
    ):
        matches = await retrieve_matching_policies(obligation)

    assert matches[0].policy.tags == []


async def test_retrieve_matching_policies_no_owner() -> None:
    obligation = _make_obligation()
    row = {**_make_db_row(), "owner": None}
    embedding = [0.1] * 768

    mock_session = AsyncMock()

    @asynccontextmanager
    async def mock_db_session():
        yield mock_session

    with (
        patch(
            "reglens.agents.knowledge.retriever.embed_text",
            new=AsyncMock(return_value=embedding),
        ),
        patch(
            "reglens.agents.knowledge.retriever.search_policies",
            new=AsyncMock(return_value=[row]),
        ),
        patch("reglens.agents.knowledge.retriever.db_session", mock_db_session),
    ):
        matches = await retrieve_matching_policies(obligation)

    assert matches[0].policy.owner is None


async def test_retrieve_all_policies_empty() -> None:
    result = await retrieve_all_policies([])
    assert result == {}


async def test_retrieve_all_policies_returns_mapping() -> None:
    obligations = [_make_obligation("OBL-001"), _make_obligation("OBL-002")]
    rows = [_make_db_row()]
    embedding = [0.1] * 768

    mock_session = AsyncMock()

    @asynccontextmanager
    async def mock_db_session():
        yield mock_session

    with (
        patch(
            "reglens.agents.knowledge.retriever.embed_text",
            new=AsyncMock(return_value=embedding),
        ),
        patch(
            "reglens.agents.knowledge.retriever.search_policies",
            new=AsyncMock(return_value=rows),
        ),
        patch("reglens.agents.knowledge.retriever.db_session", mock_db_session),
    ):
        result = await retrieve_all_policies(obligations, k=3)

    assert "OBL-001" in result
    assert "OBL-002" in result
    assert len(result["OBL-001"]) == 1
    assert len(result["OBL-002"]) == 1
