"""policies_vector_3072 — no-op, column stays at vector(768) with output_dimensionality

gemini-embedding-001 natively outputs 3072 dims but pgvector HNSW caps at 2000.
We truncate to 768 via output_dimensionality on every embed call; schema unchanged.

Revision ID: 003
Revises: 002
Create Date: 2026-05-22
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "003"
down_revision: str | Sequence[str] | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass  # vector(768) column from migration 002 is already correct


def downgrade() -> None:
    pass
