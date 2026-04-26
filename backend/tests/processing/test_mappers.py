"""Tests for :mod:`runllm.processing.mappers`."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest

from runllm.garmin.models import GarminActivitySummary, GarminSplit
from runllm.processing.mappers import avg_pace_seconds_per_km, garmin_summary_to_activity_kwargs


def _summary(**overrides: object) -> GarminActivitySummary:
    base = {
        "activity_id": "1001",
        "activity_type": "running",
        "start_time": datetime.fromisoformat("2026-04-10T07:30:00+00:00"),
        "distance_meters": 5000.0,
        "duration_seconds": 1500.0,
        "avg_hr": 150,
        "max_hr": 175,
    }
    base.update(overrides)
    return GarminActivitySummary.model_validate(base)


@pytest.mark.parametrize(
    "distance, duration, expected",
    [
        (5000.0, 1500.0, 300.0),
        (10000.0, 3000.0, 300.0),
        (0.0, 1500.0, None),
        (1000.0, 0.0, None),
        (-1.0, 100.0, None),
    ],
)
def test_avg_pace_seconds_per_km(distance: float, duration: float, expected: float | None) -> None:
    assert avg_pace_seconds_per_km(distance, duration) == expected


def test_garmin_summary_to_activity_kwargs_full_payload() -> None:
    user_id = uuid4()
    splits = [
        GarminSplit(index=0, distance_meters=1000.0, duration_seconds=290.0, avg_hr=145),
        GarminSplit(index=1, distance_meters=1000.0, duration_seconds=295.0, avg_hr=148),
    ]
    kwargs = garmin_summary_to_activity_kwargs(_summary(), user_id, splits=splits)
    assert kwargs["user_id"] == user_id
    assert kwargs["distance_meters"] == 5000.0
    assert kwargs["duration_seconds"] == 1500
    assert kwargs["avg_pace_seconds_per_km"] == 300.0
    assert len(kwargs["splits_json"]) == 2
    assert kwargs["splits_json"][0]["index"] == 0
    assert kwargs["splits_json"][0]["avg_hr"] == 145


def test_garmin_summary_handles_missing_optional_fields() -> None:
    user_id = uuid4()
    kwargs = garmin_summary_to_activity_kwargs(
        _summary(avg_hr=None, max_hr=None, elevation_gain_meters=None), user_id
    )
    assert kwargs["avg_hr"] is None
    assert kwargs["max_hr"] is None
    assert kwargs["elevation_gain_meters"] is None
    assert kwargs["splits_json"] == []


def test_garmin_summary_zero_distance_returns_no_pace() -> None:
    user_id = uuid4()
    kwargs = garmin_summary_to_activity_kwargs(_summary(distance_meters=0.0), user_id)
    assert kwargs["avg_pace_seconds_per_km"] is None
