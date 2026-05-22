"""Unit tests for persistence/db.py — session factory and context manager."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import reglens.persistence.db as db_module
from reglens.persistence.db import db_session


def test_get_session_factory_creates_engine() -> None:
    original_factory = db_module._session_factory
    db_module._session_factory = None  # reset cached factory

    mock_settings = MagicMock()
    mock_settings.database_url = "postgresql+psycopg://user:pass@localhost/db"
    mock_settings.database_pool_size = 10
    mock_settings.database_max_overflow = 20
    mock_settings.environment = "development"

    mock_engine = MagicMock()
    mock_factory = MagicMock()

    try:
        with (
            patch.object(db_module, "get_settings", return_value=mock_settings),
            patch(
                "reglens.persistence.db.create_async_engine", return_value=mock_engine
            ) as mock_create,
            patch(
                "reglens.persistence.db.async_sessionmaker", return_value=mock_factory
            ),
        ):
            result = db_module._get_session_factory()
        assert result is mock_factory
        mock_create.assert_called_once_with(
            mock_settings.database_url,
            pool_size=10,
            max_overflow=20,
            echo=True,  # "development" environment → echo=True
        )
    finally:
        db_module._session_factory = original_factory


def test_get_session_factory_returns_cached() -> None:
    original_factory = db_module._session_factory
    mock_factory = MagicMock()
    db_module._session_factory = mock_factory

    try:
        result = db_module._get_session_factory()
        assert result is mock_factory
    finally:
        db_module._session_factory = original_factory


async def test_db_session_yields_session() -> None:
    mock_session = AsyncMock()
    mock_factory = MagicMock()

    mock_begin = AsyncMock()
    mock_begin.__aenter__ = AsyncMock(return_value=mock_session)
    mock_begin.__aexit__ = AsyncMock(return_value=False)
    mock_factory.begin = MagicMock(return_value=mock_begin)

    with patch.object(db_module, "_get_session_factory", return_value=mock_factory):
        async with db_session() as session:
            assert session is mock_session
