"""Tests for :mod:`runllm.llm.prompt_builder`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from runllm.llm.exceptions import LLMTokenBudgetError
from runllm.llm.prompt_builder import (
    build_system_prompt,
    estimate_tokens,
    summarize_activity_for_prompt,
)
from runllm.models import Activity, User


def _user(language: str = "en") -> User:
    return User(supabase_user_id=uuid4(), email="a@b.com", preferred_language=language)


def _activity(days_ago: int, distance_km: float = 5.0, has_ts: bool = False) -> Activity:
    start = datetime.now(tz=UTC) - timedelta(days=days_ago)
    return Activity(
        user_id=uuid4(),
        garmin_activity_id=f"g-{days_ago}",
        activity_type="running",
        start_time=start,
        duration_seconds=int(distance_km * 300),
        distance_meters=distance_km * 1000.0,
        avg_hr=145,
        avg_pace_seconds_per_km=300.0,
        has_timeseries=has_ts,
        splits_json=[{"index": 0}],
    )


def test_summarize_activity_includes_pace_and_flag() -> None:
    line = summarize_activity_for_prompt(_activity(1, has_ts=True))
    assert "running" in line
    assert "5.00km" in line
    assert "5:00/km" in line
    assert "[ts]" in line
    assert "splits=1" in line


def test_summarize_activity_handles_missing_pace() -> None:
    act = _activity(1)
    act.avg_pace_seconds_per_km = None
    act.avg_hr = None
    line = summarize_activity_for_prompt(act)
    assert "—" in line
    assert "HR —" in line


def test_build_system_prompt_includes_persona_and_language() -> None:
    user = _user("es")
    prompt = build_system_prompt(user, [_activity(2), _activity(10)])
    assert "running coach" in prompt
    assert "(es)" in prompt
    assert "Activities:" in prompt
    assert "Tools you can use" in prompt


def test_build_system_prompt_no_activities_uses_placeholder() -> None:
    prompt = build_system_prompt(_user(), [])
    assert "Activities: none." in prompt


def test_build_system_prompt_truncates_when_over_budget() -> None:
    activities = [_activity(d) for d in range(60, 0, -1)]
    prompt = build_system_prompt(_user(), activities, token_budget=200)
    assert "older activities were truncated" in prompt


def test_build_system_prompt_raises_when_single_activity_too_large() -> None:
    activities = [_activity(1)]
    with pytest.raises(LLMTokenBudgetError):
        build_system_prompt(_user(), activities, token_budget=10)


def test_estimate_tokens_is_monotonic() -> None:
    assert estimate_tokens("a") <= estimate_tokens("a" * 100)
