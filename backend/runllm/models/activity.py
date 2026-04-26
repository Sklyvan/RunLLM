"""Activity domain model."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Column, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlmodel import Field

from runllm.models.base import TimestampedBase, UUIDPrimaryKey

# Use JSONB on Postgres, fall back to JSON on SQLite for tests.
_JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")


class Activity(UUIDPrimaryKey, TimestampedBase, table=True):
    """A single Garmin activity, normalized for our domain.

    Persisted alongside an optional reference to a Parquet object in
    Supabase Storage that holds the per-second time-series.
    """

    __tablename__ = "activity"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "garmin_activity_id",
            name="uq_activity_user_garmin_id",
        ),
    )

    user_id: UUID = Field(
        sa_column=Column(
            ForeignKey("user.id", ondelete="CASCADE"),
            index=True,
            nullable=False,
        ),
    )

    garmin_activity_id: str = Field(index=True, nullable=False, max_length=64)

    activity_type: str = Field(nullable=False, max_length=64)
    start_time: datetime = Field(
        sa_column=Column(DateTime(timezone=True), index=True, nullable=False),
    )
    duration_seconds: int = Field(nullable=False)
    distance_meters: float = Field(nullable=False)

    avg_hr: int | None = Field(default=None)
    max_hr: int | None = Field(default=None)
    avg_pace_seconds_per_km: float | None = Field(default=None)
    avg_cadence: float | None = Field(default=None)
    elevation_gain_meters: float | None = Field(default=None)
    calories: int | None = Field(default=None)

    splits_json: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(_JSON_TYPE, nullable=False, default=list),
    )

    timeseries_storage_path: str | None = Field(default=None, max_length=512)
    has_timeseries: bool = Field(default=False, nullable=False)

    raw_summary_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(_JSON_TYPE, nullable=False, default=dict),
    )
