"""End-to-end pipeline tests for :class:`ActivityProcessor`."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from runllm.garmin.models import (
    GarminActivityDetails,
    GarminActivitySummary,
    GarminSplit,
    GarminTimeSeries,
    GarminTimeSeriesSample,
)
from runllm.models import Activity, User
from runllm.processing.processor import ActivityProcessor
from runllm.processing.storage import ActivityStorage


def _summary(activity_id: str = "1001") -> GarminActivitySummary:
    return GarminActivitySummary.model_validate(
        {
            "activity_id": activity_id,
            "activity_type": "running",
            "start_time": datetime(2026, 4, 10, 7, 30, tzinfo=UTC),
            "distance_meters": 5000.0,
            "duration_seconds": 1500.0,
            "avg_hr": 150,
        }
    )


class _FakeGarmin:
    def __init__(self, with_timeseries: bool = True, fail_on: set[str] | None = None) -> None:
        self.with_timeseries = with_timeseries
        self.fail_on = fail_on or set()
        self.calls: list[tuple[str, str]] = []

    def _check(self, kind: str, activity_id: str) -> None:
        self.calls.append((kind, activity_id))
        if activity_id in self.fail_on:
            raise RuntimeError(f"upstream error for {activity_id}")

    async def get_activity_details(self, activity_id: str) -> GarminActivityDetails:
        self._check("details", activity_id)
        return GarminActivityDetails(activity_id=activity_id, raw={"x": 1})

    async def get_activity_splits(self, activity_id: str) -> list[GarminSplit]:
        self._check("splits", activity_id)
        return [GarminSplit(index=0, distance_meters=1000.0, duration_seconds=290.0)]

    async def get_activity_timeseries(self, activity_id: str) -> GarminTimeSeries:
        self._check("ts", activity_id)
        if not self.with_timeseries:
            return GarminTimeSeries(activity_id=activity_id, samples=[])
        base = datetime(2026, 4, 10, 7, 30, tzinfo=UTC)
        samples = [
            GarminTimeSeriesSample(timestamp=base + timedelta(seconds=i), heart_rate=130 + i)
            for i in range(3)
        ]
        return GarminTimeSeries(activity_id=activity_id, samples=samples)

    # Methods unused by the processor but required by the protocol.
    async def login(self, email: str, password: str) -> Any: ...  # pragma: no cover

    async def submit_mfa(self, code: str) -> Any: ...  # pragma: no cover

    async def restore_session(self, tokens: Any) -> bool:  # pragma: no cover
        return True

    async def list_activities(
        self, start: Any, end: Any, limit: int = 200
    ) -> list[Any]:  # pragma: no cover
        return []


class _FakeBucket:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def upload(self, path: str, data: bytes, options: dict[str, Any]) -> None:
        self.objects[path] = data

    def download(self, path: str) -> bytes:
        return self.objects[path]

    def remove(self, paths: list[str]) -> None:
        for p in paths:
            self.objects.pop(p, None)


class _FakeStorageClient:
    def __init__(self) -> None:
        self.bucket = _FakeBucket()

    def from_(self, name: str) -> _FakeBucket:
        return self.bucket


@pytest_asyncio.fixture
async def session_factory() -> AsyncGenerator[Any, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    def factory() -> SQLModelAsyncSession:
        return SQLModelAsyncSession(engine, expire_on_commit=False)

    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def user_id(session_factory: Any) -> UUID:
    user = User(supabase_user_id=uuid4(), email="alice@example.com")
    async with session_factory() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user.id


def _make_processor(
    session_factory: Any, with_timeseries: bool = True, fail_on: set[str] | None = None
) -> tuple[ActivityProcessor, _FakeGarmin, _FakeStorageClient]:
    garmin = _FakeGarmin(with_timeseries=with_timeseries, fail_on=fail_on)
    client = _FakeStorageClient()
    storage = ActivityStorage(client, bucket="activities")
    processor = ActivityProcessor(garmin, storage, session_factory, concurrency=2)
    return processor, garmin, client


@pytest.mark.asyncio
async def test_process_activity_creates_row_and_uploads_parquet(
    session_factory: Any, user_id: UUID
) -> None:
    processor, _, client = _make_processor(session_factory)
    activity = await processor.process_activity(user_id, _summary())
    assert activity is not None
    assert activity.has_timeseries is True
    assert activity.timeseries_storage_path is not None
    assert client.bucket.objects[activity.timeseries_storage_path]


@pytest.mark.asyncio
async def test_process_activity_without_timeseries_marks_flag_false(
    session_factory: Any, user_id: UUID
) -> None:
    processor, _, _ = _make_processor(session_factory, with_timeseries=False)
    activity = await processor.process_activity(user_id, _summary())
    assert activity is not None
    assert activity.has_timeseries is False
    assert activity.timeseries_storage_path is None


@pytest.mark.asyncio
async def test_process_activity_is_idempotent(session_factory: Any, user_id: UUID) -> None:
    processor, _, _ = _make_processor(session_factory)
    first = await processor.process_activity(user_id, _summary())
    second = await processor.process_activity(user_id, _summary())
    assert first is not None
    assert second is None  # already stored


@pytest.mark.asyncio
async def test_process_batch_isolates_errors(session_factory: Any, user_id: UUID) -> None:
    processor, _, _ = _make_processor(session_factory, fail_on={"bad"})
    summaries = [_summary("ok-1"), _summary("bad"), _summary("ok-2")]
    report = await processor.process_batch(user_id, summaries)
    assert report.created == 2
    assert report.failed == 1
    assert report.skipped == 0
    assert report.errors[0][0] == "bad"


@pytest.mark.asyncio
async def test_process_batch_counts_skips(session_factory: Any, user_id: UUID) -> None:
    processor, _, _ = _make_processor(session_factory)
    summaries = [_summary("a"), _summary("b")]
    first = await processor.process_batch(user_id, summaries)
    second = await processor.process_batch(user_id, summaries)
    assert first.created == 2
    assert second.skipped == 2
    assert second.created == 0

    async with session_factory() as session:
        rows = (await session.exec(select(Activity).where(Activity.user_id == user_id))).all()
        assert len(rows) == 2
