"""Initial schema: user and activity tables.

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-26 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "supabase_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            unique=True,
        ),
        sa.Column("email", sa.String(length=320), nullable=False, unique=True),
        sa.Column("garmin_email", sa.String(length=320), nullable=True),
        sa.Column("garmin_credentials_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("garmin_last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_user_supabase_user_id", "user", ["supabase_user_id"], unique=True)
    op.create_index("ix_user_email", "user", ["email"], unique=True)

    op.create_table(
        "activity",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("garmin_activity_id", sa.String(length=64), nullable=False),
        sa.Column("activity_type", sa.String(length=64), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("distance_meters", sa.Float(), nullable=False),
        sa.Column("avg_hr", sa.Integer(), nullable=True),
        sa.Column("max_hr", sa.Integer(), nullable=True),
        sa.Column("avg_pace_seconds_per_km", sa.Float(), nullable=True),
        sa.Column("avg_cadence", sa.Float(), nullable=True),
        sa.Column("elevation_gain_meters", sa.Float(), nullable=True),
        sa.Column("calories", sa.Integer(), nullable=True),
        sa.Column("splits_json", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("timeseries_storage_path", sa.String(length=512), nullable=True),
        sa.Column(
            "has_timeseries", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("raw_summary_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "user_id", "garmin_activity_id", name="uq_activity_user_garmin_id"
        ),
    )
    op.create_index("ix_activity_user_id", "activity", ["user_id"])
    op.create_index("ix_activity_garmin_activity_id", "activity", ["garmin_activity_id"])
    op.create_index("ix_activity_start_time", "activity", ["start_time"])


def downgrade() -> None:
    op.drop_index("ix_activity_start_time", table_name="activity")
    op.drop_index("ix_activity_garmin_activity_id", table_name="activity")
    op.drop_index("ix_activity_user_id", table_name="activity")
    op.drop_table("activity")
    op.drop_index("ix_user_email", table_name="user")
    op.drop_index("ix_user_supabase_user_id", table_name="user")
    op.drop_table("user")

