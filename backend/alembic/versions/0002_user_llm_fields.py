"""Add preferred_language and max_hr to user.

Revision ID: 0002_user_llm_fields
Revises: 0001_initial
Create Date: 2026-04-26 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_user_llm_fields"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user",
        sa.Column(
            "preferred_language",
            sa.String(length=8),
            nullable=False,
            server_default="en",
        ),
    )
    op.add_column("user", sa.Column("max_hr", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("user", "max_hr")
    op.drop_column("user", "preferred_language")

