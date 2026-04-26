"""System-prompt construction for the running coach.

The prompt holds compact one-line summaries of the user's last 12
months of activities. Detailed splits and per-second time-series load
on demand via Claude tool calls — that is the design contract that
keeps the prompt bounded.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from math import ceil

from runllm.llm.exceptions import LLMTokenBudgetError
from runllm.models import Activity, User

# Conservative chars-per-token estimate when ``anthropic.count_tokens`` is
# not available (e.g. in tests). Real production calls should use the SDK.
_CHARS_PER_TOKEN = 4

DEFAULT_TOKEN_BUDGET = 25_000


def _ensure_utc(dt: datetime) -> datetime:
    """Normalize naive datetimes (e.g. from SQLite) to UTC-aware."""

    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def estimate_tokens(text: str) -> int:
    """Rough token estimate based on character count."""

    return ceil(len(text) / _CHARS_PER_TOKEN)


def summarize_activity_for_prompt(activity: Activity) -> str:
    """Return a single-line, compact summary of an activity."""

    date = _ensure_utc(activity.start_time).strftime("%Y-%m-%d")
    distance_km = activity.distance_meters / 1000.0
    duration_min = activity.duration_seconds / 60.0
    pace = (
        f"{int(activity.avg_pace_seconds_per_km // 60)}:"
        f"{int(activity.avg_pace_seconds_per_km % 60):02d}/km"
        if activity.avg_pace_seconds_per_km
        else "—"
    )
    hr = f"HR {activity.avg_hr}" if activity.avg_hr else "HR —"
    flag = " [ts]" if activity.has_timeseries else ""
    splits_n = len(activity.splits_json or [])
    return (
        f"{date} {activity.activity_type} {distance_km:.2f}km "
        f"{duration_min:.1f}min {pace} {hr} splits={splits_n}{flag}"
    )


def _stats_block(activities: list[Activity]) -> str:
    now = datetime.now(tz=UTC)
    windows = {"4w": 28, "12w": 84, "52w": 364}
    totals: dict[str, dict[str, float]] = defaultdict(lambda: {"distance_km": 0.0, "count": 0.0})

    for label, days in windows.items():
        threshold = now - timedelta(days=days)
        for act in activities:
            if _ensure_utc(act.start_time) >= threshold:
                totals[label]["distance_km"] += act.distance_meters / 1000.0
                totals[label]["count"] += 1

    lines = []
    for label in ("4w", "12w", "52w"):
        d = totals[label]["distance_km"]
        n = int(totals[label]["count"])
        lines.append(f"- last {label}: {n} activities, {d:.1f} km")
    return "\n".join(lines)


def build_system_prompt(
    user: User,
    activities: list[Activity],
    *,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
) -> str:
    """Compose the system prompt for a chat turn.

    Activities are listed chronologically (oldest first). If the
    activity block exceeds ``token_budget``, the oldest entries are
    dropped and an explicit note is added so the LLM knows it can call
    :func:`list_activities_by_filter` to recover them.
    """

    sorted_activities = sorted(activities, key=lambda a: _ensure_utc(a.start_time))

    persona = (
        "You are an experienced, evidence-based running coach. "
        "You communicate in the user's preferred language "
        f"({user.preferred_language}). You are cautious about "
        "overtraining and never recommend ignoring pain or symptoms."
    )

    today = datetime.now(tz=UTC).date().isoformat()
    stats = _stats_block(sorted_activities)
    header = f"Today is {today}.\n\nUser stats:\n{stats}"

    tools_doc = (
        "Tools you can use:\n"
        "- get_activity_detail: full splits and extended summary for one activity.\n"
        "- get_activity_timeseries: per-second GPS/HR/speed for one activity.\n"
        "- compute_pace_zones: HR-zone time distribution for one activity.\n"
        "- list_activities_by_filter: find activities not in this prompt."
    )

    activity_lines = [summarize_activity_for_prompt(a) for a in sorted_activities]
    truncated = False
    while activity_lines:
        body = "\n".join(activity_lines)
        full = f"{persona}\n\n{header}\n\nActivities:\n{body}\n\n{tools_doc}"
        if estimate_tokens(full) <= token_budget:
            break
        activity_lines.pop(0)
        truncated = True
    else:
        if not activities:
            full = f"{persona}\n\n{header}\n\nActivities: none.\n\n{tools_doc}"
        else:
            raise LLMTokenBudgetError("even one activity exceeds the configured token budget")

    if truncated:
        full += (
            "\n\nNote: older activities were truncated to fit the token budget. "
            "Use list_activities_by_filter to retrieve them when needed."
        )

    return full
