"""drop matrix_filename from runs — control matrix is seeded once via seed_rag.py, not per-run

Revision ID: 004
Revises: 003
Create Date: 2026-05-23
"""

from __future__ import annotations

from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("runs", "matrix_filename")


def downgrade() -> None:
    import sqlalchemy as sa

    op.add_column("runs", sa.Column("matrix_filename", sa.String(500), nullable=True))
