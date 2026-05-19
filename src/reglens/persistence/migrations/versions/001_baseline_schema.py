"""baseline_schema

Revision ID: 001
Revises:
Create Date: 2026-05-20

"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa

if TYPE_CHECKING:
    from collections.abc import Sequence
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # pgvector extension — required before creating vector columns
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ------------------------------------------------------------------
    # runs
    op.create_table(
        "runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("domain", sa.String(100), nullable=False, server_default="banking"),
        sa.Column("pdf_filename", sa.String(500), nullable=True),
        sa.Column("matrix_filename", sa.String(500), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
    )
    op.create_index("ix_runs_status", "runs", ["status"])
    op.create_index("ix_runs_created_at", "runs", ["created_at"])

    # ------------------------------------------------------------------
    # audit_log
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("node", sa.String(100), nullable=False),
        sa.Column("actor", sa.String(50), nullable=False, server_default="system"),
        sa.Column("payload", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
    )
    op.create_index("ix_audit_log_run_id", "audit_log", ["run_id"])

    # ------------------------------------------------------------------
    # cost_records
    op.create_table(
        "cost_records",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent", sa.String(100), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("prompt_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "cost_usd",
            sa.Numeric(precision=10, scale=6),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
    )
    op.create_index("ix_cost_records_run_id", "cost_records", ["run_id"])

    # ------------------------------------------------------------------
    # policies (pgvector RAG store)
    # The vector dimension is 768 for text-embedding-004 output.
    op.execute("""
        CREATE TABLE IF NOT EXISTS policies (
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
    op.execute("CREATE INDEX IF NOT EXISTS ix_policies_domain ON policies (domain)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_policies_embedding_hnsw "
        "ON policies USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS policies")
    op.drop_table("cost_records")
    op.drop_table("audit_log")
    op.drop_table("runs")
    op.execute("DROP EXTENSION IF EXISTS vector")
