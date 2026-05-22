"""Unit tests for rag/store.py — upsert_policy and search_policies."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from reglens.rag.store import search_policies, upsert_policy
from reglens.schemas.policy import Policy


def _make_policy() -> Policy:
    return Policy(
        id="CTL-001",
        domain="banking",
        section="KYC",
        title="KYC Policy",
        text="Customer identity verified.",
        owner="compliance",
        tags=["kyc", "aml"],
    )


async def test_upsert_policy_calls_execute() -> None:
    session = AsyncMock()
    policy = _make_policy()
    embedding = [0.1, 0.2, 0.3]

    await upsert_policy(session, policy, embedding)

    session.execute.assert_called_once()
    call_args = session.execute.call_args
    params = call_args[0][1]
    assert params["id"] == "CTL-001"
    assert params["domain"] == "banking"
    assert params["section"] == "KYC"
    assert params["title"] == "KYC Policy"
    assert params["owner"] == "compliance"
    assert params["tags"] == "kyc,aml"


async def test_upsert_policy_empty_tags() -> None:
    session = AsyncMock()
    policy = Policy(id="CTL-002", section="AML", title="AML", text="text")
    await upsert_policy(session, policy, [0.5])

    params = session.execute.call_args[0][1]
    assert params["tags"] == ""


async def test_search_policies_returns_list_of_dicts() -> None:
    row1 = {
        "id": "CTL-001",
        "domain": "banking",
        "section": "KYC",
        "title": "KYC",
        "text": "text",
        "owner": None,
        "tags": "",
        "relevance": 0.9,
    }
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [row1]

    session = AsyncMock()
    session.execute = AsyncMock(return_value=mock_result)

    rows = await search_policies(session, [0.1, 0.2], "banking", k=5)

    assert len(rows) == 1
    assert rows[0]["id"] == "CTL-001"
    assert rows[0]["relevance"] == 0.9
    session.execute.assert_called_once()


async def test_search_policies_passes_correct_params() -> None:
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = []

    session = AsyncMock()
    session.execute = AsyncMock(return_value=mock_result)

    embedding = [0.1, 0.2]
    await search_policies(session, embedding, "insurance", k=3)

    params = session.execute.call_args[0][1]
    assert params["domain"] == "insurance"
    assert params["k"] == 3
    assert str(embedding) in params["query_vec"]


async def test_search_policies_empty_result() -> None:
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = []

    session = AsyncMock()
    session.execute = AsyncMock(return_value=mock_result)

    rows = await search_policies(session, [0.1], "banking")
    assert rows == []
