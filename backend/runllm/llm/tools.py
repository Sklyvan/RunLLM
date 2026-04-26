"""Claude tool definitions and Python implementations.

The :data:`TOOL_SCHEMAS` constant is the JSON-schema list passed to the
Anthropic API. Each tool has a corresponding async implementation in
:class:`ToolRegistry` that the service calls when Claude requests it.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from runllm.llm.exceptions import LLMToolError
from runllm.models import Activity, User
from runllm.processing.storage import ActivityStorage
from runllm.processing.timeseries import parquet_bytes_to_arrow

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], AsyncSession]

# Approx. 4 chars per token; 8000 token cap → 32k chars.
_TIMESERIES_PAYLOAD_CHAR_LIMIT = 32_000


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "get_activity_detail",
        "description": (
            "Return the full splits array and extended summary fields for "
            "one activity. Use this when the one-line summary in the system "
            "prompt is not enough to answer the question."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "activity_id": {"type": "string"},
            },
            "required": ["activity_id"],
        },
    },
    {
        "name": "get_activity_timeseries",
        "description": (
            "Return downsampled per-second telemetry (timestamp, lat, lon, "
            "heart_rate, speed). Useful to inspect pacing within a run. "
            "Default downsample is 1 sample every 5 seconds."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "activity_id": {"type": "string"},
                "downsample_seconds": {"type": "integer", "minimum": 1, "default": 5},
            },
            "required": ["activity_id"],
        },
    },
    {
        "name": "compute_pace_zones",
        "description": (
            "Return time spent in heart-rate zones (Z1-Z5) for one activity. "
            "Zones are computed from the user's max HR (estimated as 220-age "
            "if unknown)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "activity_id": {"type": "string"},
            },
            "required": ["activity_id"],
        },
    },
    {
        "name": "list_activities_by_filter",
        "description": (
            "Find activities matching simple filters. Useful when the system "
            "prompt has been truncated."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "activity_type": {"type": ["string", "null"]},
                "min_distance_km": {"type": ["number", "null"]},
                "since_days": {"type": ["integer", "null"]},
            },
        },
    },
]


def _zone_thresholds(max_hr: int) -> list[tuple[str, float, float]]:
    """Return inclusive ``(label, low_pct, high_pct)`` triples for Z1-Z5."""

    return [
        ("Z1", 0.50, 0.60),
        ("Z2", 0.60, 0.70),
        ("Z3", 0.70, 0.80),
        ("Z4", 0.80, 0.90),
        ("Z5", 0.90, 1.10),  # cap a bit above max to capture spikes
    ]


class ToolRegistry:
    """Bound, async implementations of :data:`TOOL_SCHEMAS`."""

    def __init__(
        self,
        user_id: UUID,
        session_factory: SessionFactory,
        storage: ActivityStorage,
    ) -> None:
        self._user_id = user_id
        self._session_factory = session_factory
        self._storage = storage

    async def dispatch(self, name: str, arguments: dict[str, Any]) -> str:
        """Run a tool by name; always return a JSON string."""

        try:
            if name == "get_activity_detail":
                return await self.get_activity_detail(**arguments)
            if name == "get_activity_timeseries":
                return await self.get_activity_timeseries(**arguments)
            if name == "compute_pace_zones":
                return await self.compute_pace_zones(**arguments)
            if name == "list_activities_by_filter":
                return await self.list_activities_by_filter(**arguments)
        except LLMToolError:
            raise
        except Exception as exc:
            logger.exception("tool %s failed", name)
            raise LLMToolError(f"{name}: {exc}") from exc
        raise LLMToolError(f"unknown tool: {name}")

    async def get_activity_detail(self, activity_id: str) -> str:
        activity = await self._load_activity(activity_id)
        payload = {
            "id": str(activity.id),
            "garmin_activity_id": activity.garmin_activity_id,
            "type": activity.activity_type,
            "start_time": activity.start_time.astimezone(UTC).isoformat(),
            "duration_seconds": activity.duration_seconds,
            "distance_meters": activity.distance_meters,
            "avg_hr": activity.avg_hr,
            "max_hr": activity.max_hr,
            "avg_pace_seconds_per_km": activity.avg_pace_seconds_per_km,
            "avg_cadence": activity.avg_cadence,
            "elevation_gain_meters": activity.elevation_gain_meters,
            "calories": activity.calories,
            "splits": activity.splits_json,
            "has_timeseries": activity.has_timeseries,
        }
        return json.dumps(payload)

    async def get_activity_timeseries(self, activity_id: str, downsample_seconds: int = 5) -> str:
        activity = await self._load_activity(activity_id)
        if not activity.has_timeseries or not activity.timeseries_storage_path:
            return json.dumps({"error": "no timeseries available"})

        blob = await self._storage.download_timeseries(activity.timeseries_storage_path)
        table = parquet_bytes_to_arrow(blob)
        samples = _downsample(table, max(1, downsample_seconds))
        body = json.dumps({"samples": samples})
        if len(body) > _TIMESERIES_PAYLOAD_CHAR_LIMIT:
            return json.dumps({"summary": _summary_stats(table)})
        return body

    async def compute_pace_zones(self, activity_id: str) -> str:
        activity = await self._load_activity(activity_id)
        user = await self._load_user()

        max_hr = user.max_hr or 220 - 30  # default placeholder until we collect age
        zones = {label: 0 for label, _, _ in _zone_thresholds(max_hr)}

        if not activity.has_timeseries or not activity.timeseries_storage_path:
            return json.dumps({"error": "no timeseries available", "zones": zones})

        blob = await self._storage.download_timeseries(activity.timeseries_storage_path)
        table = parquet_bytes_to_arrow(blob)
        hr_col = table.column("heart_rate").to_pylist()
        for hr in hr_col:
            if hr is None:
                continue
            ratio = hr / max_hr
            for label, lo, hi in _zone_thresholds(max_hr):
                if lo <= ratio < hi:
                    zones[label] += 1
                    break
        return json.dumps({"max_hr": max_hr, "zones_seconds": zones})

    async def list_activities_by_filter(
        self,
        activity_type: str | None = None,
        min_distance_km: float | None = None,
        since_days: int | None = None,
    ) -> str:
        async with self._session_factory() as session:
            stmt = select(Activity).where(Activity.user_id == self._user_id)
            if activity_type is not None:
                stmt = stmt.where(Activity.activity_type == activity_type)
            if min_distance_km is not None:
                stmt = stmt.where(Activity.distance_meters >= min_distance_km * 1000.0)
            if since_days is not None:
                threshold = datetime.now(tz=UTC) - timedelta(days=since_days)
                stmt = stmt.where(Activity.start_time >= threshold)
            rows = (await session.exec(stmt.order_by(Activity.start_time.desc()))).all()  # type: ignore[attr-defined]

        from runllm.llm.prompt_builder import summarize_activity_for_prompt

        return json.dumps(
            {
                "activities": [
                    {"id": str(a.id), "summary": summarize_activity_for_prompt(a)} for a in rows
                ]
            }
        )

    # ------------------------------------------------------------------ helpers

    async def _load_activity(self, activity_id: str) -> Activity:
        async with self._session_factory() as session:
            stmt = select(Activity).where(
                Activity.user_id == self._user_id, Activity.id == UUID(activity_id)
            )
            result = await session.exec(stmt)
            activity = result.first()
        if activity is None:
            raise LLMToolError(f"activity {activity_id} not found")
        return activity

    async def _load_user(self) -> User:
        async with self._session_factory() as session:
            user = await session.get(User, self._user_id)
        if user is None:
            raise LLMToolError(f"user {self._user_id} not found")
        return user


def _downsample(table: Any, every_seconds: int) -> list[list[Any]]:
    rows: list[list[Any]] = []
    timestamps = table.column("timestamp").to_pylist()
    lats = table.column("lat").to_pylist()
    lons = table.column("lon").to_pylist()
    hrs = table.column("heart_rate").to_pylist()
    speeds = table.column("speed").to_pylist()
    last_ts: datetime | None = None
    for ts, lat, lon, hr, speed in zip(timestamps, lats, lons, hrs, speeds, strict=True):
        if last_ts is not None and (ts - last_ts).total_seconds() < every_seconds:
            continue
        last_ts = ts
        rows.append([ts.isoformat() if hasattr(ts, "isoformat") else ts, lat, lon, hr, speed])
    return rows


def _summary_stats(table: Any) -> dict[str, Any]:
    hr = [v for v in table.column("heart_rate").to_pylist() if v is not None]
    speed = [v for v in table.column("speed").to_pylist() if v is not None]
    return {
        "samples": table.num_rows,
        "avg_hr": sum(hr) / len(hr) if hr else None,
        "max_hr": max(hr) if hr else None,
        "avg_speed": sum(speed) / len(speed) if speed else None,
    }
