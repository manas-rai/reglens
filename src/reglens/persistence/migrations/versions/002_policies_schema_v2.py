"""policies_schema_v2 — align policies table with Policy schema

Revision ID: 002
Revises: 001
Create Date: 2026-05-22
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

from alembic import op

revision: str = "002"
down_revision: str | Sequence[str] | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Drop the old policies table (no production data yet) and recreate with
    # the schema matching the Policy Pydantic model used by the RAG layer.
    op.execute("DROP TABLE IF EXISTS policies")
    op.execute("""
        CREATE TABLE policies (
            id          VARCHAR(255) PRIMARY KEY,
            domain      VARCHAR(100) NOT NULL DEFAULT 'banking',
            section     VARCHAR(500) NOT NULL DEFAULT '',
            title       VARCHAR(500) NOT NULL DEFAULT '',
            text        TEXT NOT NULL,
            owner       VARCHAR(255),
            tags        TEXT NOT NULL DEFAULT '',
            embedding   vector(768),
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_policies_domain ON policies (domain)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_policies_embedding_hnsw "
        "ON policies USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS policies")
    op.execute("""
        CREATE TABLE policies (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            domain      VARCHAR(100) NOT NULL DEFAULT 'banking',
            policy_id   VARCHAR(255) NOT NULL,
            section     VARCHAR(500),
            text        TEXT NOT NULL,
            embedding   vector(768),
            metadata    JSONB NOT NULL DEFAULT '{}',
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
