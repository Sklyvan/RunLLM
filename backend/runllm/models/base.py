"""Reusable SQLModel mixins for primary keys and timestamps."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    """Return the current UTC time as a timezone-aware ``datetime``."""

    return datetime.now(tz=UTC)


class UUIDPrimaryKey(SQLModel):
    """Mixin contributing a UUID primary key column."""

    id: UUID = Field(default_factory=uuid4, primary_key=True, nullable=False)


class TimestampedBase(SQLModel):
    """Mixin contributing ``created_at`` and ``updated_at`` columns.

    Both fields are timezone-aware UTC timestamps. ``updated_at`` is
    refreshed automatically by SQLAlchemy on every row update via
    ``sa_column_kwargs`` so each subclass gets its own column instance.
    """

    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column_kwargs={"nullable": False},
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_column_kwargs={"nullable": False, "onupdate": _utcnow},
    )
