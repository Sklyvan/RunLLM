"""Tests for the Claude tool implementations."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from runllm.garmin.models import GarminTimeSeries, GarminTimeSeriesSample
from runllm.llm.exceptions import LLMToolError
from runllm.llm.tools import TOOL_SCHEMAS, ToolRegistry
from runllm.models import Activity, User
from runllm.processing.storage import ActivityStorage
from runllm.processing.timeseries import arrow_to_parquet_bytes, timeseries_to_arrow


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


def _build_timeseries(n: int = 60) -> GarminTimeSeries:
    base = datetime(2026, 4, 10, 7, 30, tzinfo=UTC)
    samples = [
        GarminTimeSeriesSample(
            timestamp=base + timedelta(seconds=i),
            lat=41.0,
            lon=2.0,
            elevation=10.0,
            heart_rate=140 + (i % 30),
            cadence=170,
            speed=3.0,
        )
        for i in range(n)
    ]
    return GarminTimeSeries(activity_id="x", samples=samples)


@pytest_asyncio.fixture
async def setup(
    session_factory: Any,
) -> AsyncGenerator[
    tuple[UUID, UUID, ActivityStorage, _FakeStorageClient],
    None,
]:
    user = User(supabase_user_id=uuid4(), email="alice@example.com", max_hr=180)
    activity = Activity(
        user_id=uuid4(),  # placeholder, replaced below
        garmin_activity_id="g-1",
        activity_type="running",
        start_time=datetime(2026, 4, 10, 7, 30, tzinfo=UTC),
        duration_seconds=1500,
        distance_meters=5000.0,
        avg_hr=150,
        max_hr=175,
        avg_pace_seconds_per_km=300.0,
        splits_json=[{"index": 0, "distance": 1000.0}],
    )

    client = _FakeStorageClient()
    storage = ActivityStorage(client, bucket="activities")

    async with session_factory() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)
        activity.user_id = user.id
        # Pre-upload a parquet file and link it.
        table = timeseries_to_arrow(_build_timeseries())
        blob = arrow_to_parquet_bytes(table)
        await storage.upload_timeseries(user.id, activity.id, blob)
        activity.has_timeseries = True
        activity.timeseries_storage_path = ActivityStorage.storage_path(user.id, activity.id)
        session.add(activity)
        await session.commit()
        await session.refresh(activity)
        yield user.id, activity.id, storage, client


def test_tool_schemas_have_required_fields() -> None:
    names = {t["name"] for t in TOOL_SCHEMAS}
    assert names == {
        "get_activity_detail",
        "get_activity_timeseries",
        "compute_pace_zones",
        "list_activities_by_filter",
    }
    for tool in TOOL_SCHEMAS:
        assert "input_schema" in tool


@pytest.mark.asyncio
async def test_get_activity_detail_returns_full_payload(
    setup: tuple[UUID, UUID, ActivityStorage, Any],
    session_factory: Any,
) -> None:
    user_id, activity_id, storage, _ = setup
    registry = ToolRegistry(user_id, session_factory, storage)
    payload = json.loads(await registry.get_activity_detail(str(activity_id)))
    assert payload["distance_meters"] == 5000.0
    assert payload["splits"][0]["distance"] == 1000.0


@pytest.mark.asyncio
async def test_get_activity_timeseries_downsamples(
    setup: tuple[UUID, UUID, ActivityStorage, Any],
    session_factory: Any,
) -> None:
    user_id, activity_id, storage, _ = setup
    registry = ToolRegistry(user_id, session_factory, storage)
    payload = json.loads(
        await registry.get_activity_timeseries(str(activity_id), downsample_seconds=10)
    )
    # 60 samples at 1Hz, downsample to 10s → roughly 6 samples
    assert 5 <= len(payload["samples"]) <= 7


@pytest.mark.asyncio
async def test_compute_pace_zones_returns_zone_seconds(
    setup: tuple[UUID, UUID, ActivityStorage, Any],
    session_factory: Any,
) -> None:
    user_id, activity_id, storage, _ = setup
    registry = ToolRegistry(user_id, session_factory, storage)
    payload = json.loads(await registry.compute_pace_zones(str(activity_id)))
    assert payload["max_hr"] == 180
    assert sum(payload["zones_seconds"].values()) > 0


@pytest.mark.asyncio
async def test_list_activities_by_filter(
    setup: tuple[UUID, UUID, ActivityStorage, Any],
    session_factory: Any,
) -> None:
    user_id, _, storage, _ = setup
    registry = ToolRegistry(user_id, session_factory, storage)
    out = json.loads(
        await registry.list_activities_by_filter(activity_type="running", since_days=365)
    )
    assert len(out["activities"]) == 1


@pytest.mark.asyncio
async def test_dispatch_unknown_tool_raises(
    setup: tuple[UUID, UUID, ActivityStorage, Any],
    session_factory: Any,
) -> None:
    user_id, _, storage, _ = setup
    registry = ToolRegistry(user_id, session_factory, storage)
    with pytest.raises(LLMToolError):
        await registry.dispatch("nope", {})


@pytest.mark.asyncio
async def test_get_activity_detail_unknown_activity_raises(
    setup: tuple[UUID, UUID, ActivityStorage, Any],
    session_factory: Any,
) -> None:
    user_id, _, storage, _ = setup
    registry = ToolRegistry(user_id, session_factory, storage)
    with pytest.raises(LLMToolError):
        await registry.get_activity_detail(str(uuid4()))
