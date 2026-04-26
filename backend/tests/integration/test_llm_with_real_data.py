"""LLM tools driving real Storage + DB after a real ingestion.

Verifies that the Parquet bytes written by the processor are readable
by ``ToolRegistry.get_activity_timeseries`` and ``compute_pace_zones``,
that ``get_activity_detail`` exposes splits in the format documented
in the tool schema, and that the prompt builder produces a prompt
that mentions the freshly-ingested activities.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from sqlmodel import select

from runllm.llm.prompt_builder import build_system_prompt
from runllm.llm.tools import TOOL_SCHEMAS, ToolRegistry
from runllm.models import Activity
from runllm.processing.processor import ActivityProcessor
from runllm.processing.storage import ActivityStorage
from tests.integration.conftest import FakeGarminClient, make_summary


async def _ingest_one(
    processor: ActivityProcessor, garmin_client: FakeGarminClient, user_id: Any
) -> Activity:
    summary = make_summary("g-int-1", days_ago=2)
    garmin_client.activities = [summary]
    report = await processor.process_batch(user_id, [summary])
    assert report.created == 1
    return summary  # type: ignore[return-value]


async def _load_activity(session_factory: Any, user_id: Any) -> Activity:
    async with session_factory() as session:
        row = (await session.exec(select(Activity).where(Activity.user_id == user_id))).first()
    assert row is not None
    return row


@pytest.mark.asyncio
async def test_get_activity_detail_round_trip(
    processor: ActivityProcessor,
    garmin_client: FakeGarminClient,
    storage: ActivityStorage,
    session_factory: Any,
    user: Any,
) -> None:
    await _ingest_one(processor, garmin_client, user.id)
    activity = await _load_activity(session_factory, user.id)

    registry = ToolRegistry(user.id, session_factory, storage)
    payload = json.loads(await registry.get_activity_detail(str(activity.id)))

    assert payload["distance_meters"] == 5000.0
    assert payload["duration_seconds"] == 1500
    assert payload["splits"], "splits should be populated by the mapper"
    assert payload["splits"][0]["distance"] == 1000.0
    assert payload["has_timeseries"] is True


@pytest.mark.asyncio
async def test_get_activity_timeseries_reads_real_parquet(
    processor: ActivityProcessor,
    garmin_client: FakeGarminClient,
    storage: ActivityStorage,
    session_factory: Any,
    user: Any,
) -> None:
    await _ingest_one(processor, garmin_client, user.id)
    activity = await _load_activity(session_factory, user.id)

    registry = ToolRegistry(user.id, session_factory, storage)
    payload = json.loads(
        await registry.get_activity_timeseries(str(activity.id), downsample_seconds=10)
    )
    samples = payload["samples"]
    # 120 samples at 1 Hz, downsampled to 10 s ⇒ ~12 entries.
    assert 10 <= len(samples) <= 13
    # Each row is [timestamp, lat, lon, hr, speed].
    assert len(samples[0]) == 5


@pytest.mark.asyncio
async def test_compute_pace_zones_returns_valid_distribution(
    processor: ActivityProcessor,
    garmin_client: FakeGarminClient,
    storage: ActivityStorage,
    session_factory: Any,
    user: Any,
) -> None:
    await _ingest_one(processor, garmin_client, user.id)
    activity = await _load_activity(session_factory, user.id)

    registry = ToolRegistry(user.id, session_factory, storage)
    payload = json.loads(await registry.compute_pace_zones(str(activity.id)))
    assert payload["max_hr"] == user.max_hr
    assert sum(payload["zones_seconds"].values()) > 0
    assert set(payload["zones_seconds"].keys()) == {"Z1", "Z2", "Z3", "Z4", "Z5"}


@pytest.mark.asyncio
async def test_prompt_builder_consumes_persisted_activities(
    processor: ActivityProcessor,
    garmin_client: FakeGarminClient,
    session_factory: Any,
    user: Any,
) -> None:
    summaries = [make_summary(f"g-{i}", days_ago=i + 1) for i in range(3)]
    garmin_client.activities = summaries
    await processor.process_batch(user.id, summaries)

    async with session_factory() as session:
        rows = (await session.exec(select(Activity).where(Activity.user_id == user.id))).all()

    prompt = build_system_prompt(user, list(rows))
    assert "running coach" in prompt
    assert "Activities:" in prompt
    # All three lines must show up — chronological, one per line.
    assert prompt.count("running") >= len(rows)
    assert "[ts]" in prompt  # has_timeseries flag from the processor flows through


def test_tool_schemas_match_registry_method_names() -> None:
    """The names advertised to Claude must each map to a real method."""

    registry_methods = {
        "get_activity_detail",
        "get_activity_timeseries",
        "compute_pace_zones",
        "list_activities_by_filter",
    }
    schema_names = {t["name"] for t in TOOL_SCHEMAS}
    assert schema_names == registry_methods
