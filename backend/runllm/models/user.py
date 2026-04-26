"""User domain model."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Column, DateTime, LargeBinary
from sqlmodel import Field

from runllm.models.base import TimestampedBase, UUIDPrimaryKey


class User(UUIDPrimaryKey, TimestampedBase, table=True):
    """Application user, linked one-to-one to a Supabase Auth user.

    Garmin credentials are stored encrypted with Fernet; the ciphertext
    is opaque to the database and only decryptable by the backend.
    """

    __tablename__ = "user"

    supabase_user_id: UUID = Field(unique=True, index=True, nullable=False)
    email: str = Field(unique=True, index=True, nullable=False, max_length=320)

    garmin_email: str | None = Field(default=None, max_length=320)
    garmin_credentials_encrypted: bytes | None = Field(
        default=None,
        sa_column=Column(LargeBinary, nullable=True),
    )
    garmin_last_sync_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
