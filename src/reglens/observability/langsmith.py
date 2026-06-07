"""LangSmith client setup.

LangGraph and LangChain auto-instrument when ``LANGCHAIN_TRACING_V2`` is set
and ``LANGSMITH_API_KEY`` is present in the environment. This module is the
single place that flips those env vars based on application settings — so the
pipeline stays a no-op when tracing is disabled or no key is configured.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from reglens.config import Settings

logger = logging.getLogger(__name__)


def configure_langsmith(settings: Settings) -> bool:
    """Enable LangSmith tracing when configured.

    Returns ``True`` if tracing was enabled, ``False`` otherwise. Safe to call
    multiple times — later calls overwrite the env vars with current settings.
    """
    if not settings.langsmith_tracing_enabled:
        return False
    if settings.langsmith_api_key is None:
        logger.warning(
            "LANGSMITH_TRACING_ENABLED=true but LANGSMITH_API_KEY is not set"
        )
        return False

    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key.get_secret_value()
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    logger.info(
        "LangSmith tracing enabled", extra={"project": settings.langsmith_project}
    )
    return True
