"""Smoke test: package imports and exposes a version string."""

from __future__ import annotations

import re

import reglens


def test_version_is_present() -> None:
    assert isinstance(reglens.__version__, str)
    assert re.fullmatch(r"\d+\.\d+\.\d+", reglens.__version__)
