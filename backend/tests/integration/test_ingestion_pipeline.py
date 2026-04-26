"""Garmin → DB → Storage end-to-end ingestion test.

Wires the **real** processor, mappers, ActivityStorage, Parquet
serialization and SQL persistence; only the Garmin library boundary
and the Supabase Storage HTTP boundary are stubbed.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from sqlmodel import select

from runllm.models import Activity
from runllm.processing.processor import ActivityProcessor
from runllm.processing.storage import ActivityStorage
from runllm.processing.timeseries import parquet_bytes_to_arrow
from tests.integration.conftest import (
    FakeGarminClient,
    InMemoryStorageClient,
    make_summary,
)


@pytest.mark.asyncio
async def test_processor_writes_row_and_real_parquet(
    processor: ActivityProcessor,
    garmin_client: FakeGarminClient,
    storage: ActivityStorage,
    storage_client: InMemoryStorageClient,
    session_factory: Any,
    user: Any,
) -> None:
    """Activities flow into both the DB and the Storage bucket coherently."""

    summaries = [make_summary("g-1", days_ago=2), make_summary("g-2", days_ago=4)]
    garmin_client.activities = summaries

    report = await processor.process_batch(user.id, summaries)

    assert report.created == 2
    assert report.failed == 0
    assert len(storage_client.bucket.objects) == 2

    async with session_factory() as session:
        rows = (await session.exec(select(Activity).where(Activity.user_id == user.id))).all()
    assert len(rows) == 2

    # Each row points at a Parquet object that round-trips through Arrow.
    for row in rows:
        assert row.has_timeseries is True
        assert row.timeseries_storage_path is not None
        assert row.timeseries_storage_path.startswith(f"{user.id}/")
        blob = await storage.download_timeseries(row.timeseries_storage_path)
        table = parquet_bytes_to_arrow(blob)
        assert table.num_rows == 120  # FakeGarminClient yields 120 samples
        assert table.column_names == [
            "timestamp",
            "lat",
            "lon",
            "elevation",
            "heart_rate",
            "cadence",
            "speed",
        ]


@pytest.mark.asyncio
async def test_processor_is_idempotent_across_invocations(
    processor: ActivityProcessor,
    garmin_client: FakeGarminClient,
    storage_client: InMemoryStorageClient,
    user: Any,
) -> None:
    """Re-processing the same Garmin batch creates no duplicates."""

    summaries = [make_summary("g-1", days_ago=1)]
    garmin_client.activities = summaries
    first = await processor.process_batch(user.id, summaries)
    second = await processor.process_batch(user.id, summaries)
    assert first.created == 1
    assert second.created == 0
    assert second.skipped == 1
    assert len(storage_client.bucket.objects) == 1


@pytest.mark.asyncio
async def test_storage_path_matches_documented_layout(storage: ActivityStorage, user: Any) -> None:
    """The {user_id}/{activity_id}.parquet contract is honored."""

    activity_id = UUID("11111111-2222-3333-4444-555555555555")
    path = ActivityStorage.storage_path(user.id, activity_id)
    assert path == f"{user.id}/{activity_id}.parquet"
    returned = await storage.upload_timeseries(user.id, activity_id, b"x")
    assert returned == path
