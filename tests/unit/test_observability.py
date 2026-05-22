"""Unit tests for observability/logging.py."""

from __future__ import annotations

import logging

import pytest

import reglens.observability.logging as logging_module
from reglens.observability.logging import configure_logging, shutdown_logging


@pytest.fixture(autouse=True)
def reset_listener():
    """Restore _listener state after each test."""
    original = logging_module._listener
    yield
    # Shut down any listener started during the test
    if (
        logging_module._listener is not None
        and logging_module._listener is not original
    ):
        logging_module._listener.stop()
    logging_module._listener = original


def test_configure_logging_starts_listener() -> None:
    logging_module._listener = None  # ensure clean state
    configure_logging(level="INFO")
    assert logging_module._listener is not None


def test_configure_logging_idempotent() -> None:
    logging_module._listener = None
    configure_logging(level="DEBUG")
    first_listener = logging_module._listener
    configure_logging(level="WARNING")  # second call — should be ignored
    assert logging_module._listener is first_listener  # same object, not replaced


def test_configure_logging_sets_level() -> None:
    logging_module._listener = None
    configure_logging(level="WARNING")
    root = logging.getLogger()
    assert root.level == logging.WARNING


def test_configure_logging_silences_noisy_loggers() -> None:
    logging_module._listener = None
    configure_logging(level="INFO")
    for name in ("httpx", "sqlalchemy.engine", "langgraph", "uvicorn.access"):
        assert logging.getLogger(name).level == logging.WARNING


def test_shutdown_logging_clears_listener() -> None:
    logging_module._listener = None
    configure_logging(level="INFO")
    assert logging_module._listener is not None
    shutdown_logging()
    assert logging_module._listener is None


def test_shutdown_logging_noop_when_no_listener() -> None:
    logging_module._listener = None
    # Should not raise
    shutdown_logging()
    assert logging_module._listener is None
