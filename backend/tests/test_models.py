"""Unit tests for SQLModel domain shapes.

These tests exercise the model classes without hitting Postgres. They
validate field defaults, foreign-key wiring at the ORM level, and that
required fields raise validation errors when omitted.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from runllm.models import Activity, User


@pytest_asyncio.fixture
async def in_memory_session() -> SQLModelAsyncSession:
    """Yield a session bound to an in-memory SQLite database."""

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    async with SQLModelAsyncSession(engine) as session:
        yield session
    await engine.dispose()


def test_user_defaults_are_populated() -> None:
    user = User(
        supabase_user_id=uuid4(),
        email="alice@example.com",
    )
    assert isinstance(user.id, UUID)
    assert isinstance(user.created_at, datetime)
    assert user.created_at.tzinfo is not None
    assert user.garmin_email is None
    assert user.garmin_credentials_encrypted is None
    assert user.garmin_last_sync_at is None


def test_activity_defaults_and_required_fields() -> None:
    user_id = uuid4()
    activity = Activity(
        user_id=user_id,
        garmin_activity_id="abc-123",
        activity_type="running",
        start_time=datetime.fromisoformat("2026-01-01T08:00:00+00:00"),
        duration_seconds=1800,
        distance_meters=5000.0,
    )
    assert activity.user_id == user_id
    assert activity.has_timeseries is False
    assert activity.splits_json == []
    assert activity.raw_summary_json == {}


def test_activity_required_columns_are_not_nullable() -> None:
    # SQLModel with ``table=True`` is lenient on instance creation; we
    # instead assert the underlying SQL schema marks required columns
    # as NOT NULL, which is how integrity is actually enforced.
    table = Activity.__table__
    for required in (
        "user_id",
        "garmin_activity_id",
        "activity_type",
        "start_time",
        "duration_seconds",
        "distance_meters",
    ):
        assert table.columns[required].nullable is False, required


async def test_activity_persists_and_queries(in_memory_session: SQLModelAsyncSession) -> None:
    user = User(supabase_user_id=uuid4(), email="bob@example.com")
    in_memory_session.add(user)
    await in_memory_session.commit()
    await in_memory_session.refresh(user)
    user_id = user.id

    activity = Activity(
        user_id=user_id,
        garmin_activity_id="g-1",
        activity_type="trail_running",
        start_time=datetime.fromisoformat("2026-02-01T10:00:00+00:00"),
        duration_seconds=3600,
        distance_meters=10000.0,
        splits_json=[{"index": 1, "distance": 1000.0}],
    )
    in_memory_session.add(activity)
    await in_memory_session.commit()

    result = await in_memory_session.exec(select(Activity).where(Activity.user_id == user_id))
    rows = result.all()
    assert len(rows) == 1
    assert rows[0].splits_json == [{"index": 1, "distance": 1000.0}]
