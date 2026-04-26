"""Pure functions converting Garmin DTOs to ``Activity`` model fields.

Everything is normalized to metric units (meters, seconds, m/s) so the
downstream LLM prompt sees a consistent schema regardless of the user's
Garmin display preferences.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from runllm.garmin.models import GarminActivityDetails, GarminActivitySummary, GarminSplit


def avg_pace_seconds_per_km(distance_meters: float, duration_seconds: float) -> float | None:
    """Compute average pace as seconds per kilometer.

    Returns ``None`` for non-positive distances to avoid divide-by-zero
    surprises (e.g., a strength workout logged as a "run").
    """

    if distance_meters <= 0 or duration_seconds <= 0:
        return None
    return duration_seconds / (distance_meters / 1000.0)


def garmin_summary_to_activity_kwargs(
    summary: GarminActivitySummary,
    user_id: UUID,
    *,
    details: GarminActivityDetails | None = None,
    splits: list[GarminSplit] | None = None,
) -> dict[str, Any]:
    """Translate a :class:`GarminActivitySummary` to ``Activity`` kwargs."""

    duration = float(summary.duration_seconds)
    distance = float(summary.distance_meters)
    pace = avg_pace_seconds_per_km(distance, duration)

    splits_payload: list[dict[str, Any]] = []
    for split in splits or []:
        splits_payload.append(
            {
                "index": split.index,
                "distance": split.distance_meters,
                "duration": split.duration_seconds,
                "avg_pace": split.avg_pace_seconds_per_km,
                "avg_hr": split.avg_hr,
                "elevation_gain": split.elevation_gain_meters,
            }
        )

    raw = summary.model_dump(mode="json", by_alias=True)
    if details is not None:
        raw = {**raw, "details": details.raw}

    return {
        "user_id": user_id,
        "garmin_activity_id": summary.activity_id,
        "activity_type": summary.activity_type,
        "start_time": summary.start_time,
        "duration_seconds": round(duration),
        "distance_meters": distance,
        "avg_hr": summary.avg_hr,
        "max_hr": summary.max_hr,
        "avg_pace_seconds_per_km": pace,
        "avg_cadence": summary.avg_cadence,
        "elevation_gain_meters": summary.elevation_gain_meters,
        "calories": summary.calories,
        "splits_json": splits_payload,
        "raw_summary_json": raw,
    }

