"""Pydantic DTOs for Garmin Connect data.

These models intentionally use ``extra="allow"`` so that fields we
don't explicitly know about pass through to ``raw_summary_json``. They
are deliberately decoupled from our SQL models — the mapping happens
in :mod:`runllm.processing.mappers`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GarminAuthTokens(BaseModel):
    """Opaque, JSON-serializable auth tokens cached by ``garth``.

    The exact shape depends on the underlying library; we only treat
    them as a dict so encryption and round-tripping are straightforward.
    """

    model_config = ConfigDict(extra="allow")

    data: dict[str, Any] = Field(default_factory=dict)


class GarminActivitySummary(BaseModel):
    """A single entry in Garmin's activity list response."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    activity_id: str = Field(alias="activityId")
    activity_type: str = Field(alias="activityType")
    start_time: datetime = Field(alias="startTimeGMT")
    distance_meters: float = Field(alias="distance")
    duration_seconds: float = Field(alias="duration")
    avg_hr: int | None = Field(default=None, alias="averageHR")
    max_hr: int | None = Field(default=None, alias="maxHR")
    avg_speed_mps: float | None = Field(default=None, alias="averageSpeed")
    avg_cadence: float | None = Field(default=None, alias="averageRunningCadenceInStepsPerMinute")
    elevation_gain_meters: float | None = Field(default=None, alias="elevationGain")
    calories: int | None = Field(default=None, alias="calories")


class GarminActivityDetails(BaseModel):
    """Full activity payload — kept opaque for forward compatibility."""

    model_config = ConfigDict(extra="allow")

    activity_id: str
    raw: dict[str, Any] = Field(default_factory=dict)


class GarminSplit(BaseModel):
    """A single per-km/per-mile split."""

    model_config = ConfigDict(extra="allow")

    index: int
    distance_meters: float
    duration_seconds: float
    avg_pace_seconds_per_km: float | None = None
    avg_hr: int | None = None
    elevation_gain_meters: float | None = None


class GarminTimeSeriesSample(BaseModel):
    """One sample in a per-second time-series."""

    model_config = ConfigDict(extra="allow")

    timestamp: datetime
    lat: float | None = None
    lon: float | None = None
    elevation: float | None = None
    heart_rate: int | None = None
    cadence: int | None = None
    speed: float | None = None


class GarminTimeSeries(BaseModel):
    """A list of per-second samples for a single activity."""

    model_config = ConfigDict(extra="allow")

    activity_id: str
    samples: list[GarminTimeSeriesSample] = Field(default_factory=list)
