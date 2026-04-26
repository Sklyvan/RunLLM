"""Tests for :class:`runllm.garmin.client.GarminClient`.

We never import the real ``garminconnect`` library here. Instead we
inject a fake factory that returns objects exposing exactly the methods
our client touches.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from runllm.garmin.client import GarminClient
from runllm.garmin.exceptions import GarminApiError, GarminAuthError, GarminMfaRequiredError


class _FakeGarmin:
    """Minimal fake mirroring the surface of ``garminconnect.Garmin``."""

    def __init__(
        self,
        email: str | None,
        password: str | None,
        *,
        login_result: Any = None,
        login_error: Exception | None = None,
        activities: list[dict[str, Any]] | None = None,
        details: dict[str, Any] | None = None,
        splits: dict[str, Any] | None = None,
        timeseries: dict[str, Any] | None = None,
    ) -> None:
        self.email = email
        self.password = password
        self._login_result = login_result
        self._login_error = login_error
        self._activities = activities or []
        self._details = details or {}
        self._splits = splits or {"lapDTOs": []}
        self._timeseries = timeseries or {"activityDetailMetrics": []}
        self.resumed_with: tuple[Any, str] | None = None

        class _Garth:
            def dumps(self) -> str:
                return "tokens-blob"

            def loads(self, data: str) -> None:
                return None

        self.garth = _Garth()

    def login(self) -> Any:
        if self._login_error is not None:
            raise self._login_error
        return self._login_result

    def resume_login(self, state: Any, code: str) -> None:
        self.resumed_with = (state, code)

    def get_user_summary(self) -> dict[str, Any]:
        return {"ok": True}

    def get_activities_by_date(self, start: str, end: str, limit: int) -> list[dict[str, Any]]:
        return self._activities

    def get_activity(self, activity_id: str) -> dict[str, Any]:
        return self._details

    def get_activity_splits(self, activity_id: str) -> dict[str, Any]:
        return self._splits

    def get_activity_details(self, activity_id: str) -> dict[str, Any]:
        return self._timeseries


def _factory(**fake_kwargs: Any):
    def make(email: str | None, password: str | None) -> _FakeGarmin:
        return _FakeGarmin(email, password, **fake_kwargs)

    return make


@pytest.mark.asyncio
async def test_login_happy_path() -> None:
    client = GarminClient(garmin_factory=_factory(login_result=None))
    tokens = await client.login("a@b.com", "pw")
    assert "garth" in tokens.data


@pytest.mark.asyncio
async def test_login_mfa_required_then_resume() -> None:
    client = GarminClient(garmin_factory=_factory(login_result=("needs_mfa", {"state": 1})))
    with pytest.raises(GarminMfaRequiredError):
        await client.login("a@b.com", "pw")

    tokens = await client.submit_mfa("123456")
    assert "garth" in tokens.data


@pytest.mark.asyncio
async def test_login_auth_error_translated() -> None:
    class _LibAuthError(Exception):
        pass

    client = GarminClient(garmin_factory=_factory(login_error=_LibAuthError("bad password")))
    with pytest.raises(GarminAuthError):
        await client.login("a@b.com", "pw")


@pytest.mark.asyncio
async def test_submit_mfa_without_pending_state() -> None:
    client = GarminClient(garmin_factory=_factory())
    with pytest.raises(GarminAuthError):
        await client.submit_mfa("000")


@pytest.mark.asyncio
async def test_list_activities_parses_payload(
    activities_payload: list[dict[str, Any]],
) -> None:
    client = GarminClient(garmin_factory=_factory(activities=activities_payload))
    await client.login("a@b.com", "pw")
    rows = await client.list_activities(datetime(2026, 4, 1), datetime(2026, 4, 30), limit=10)
    assert len(rows) == 2
    assert rows[0].activity_id == "1001"
    assert rows[0].avg_hr == 150


@pytest.mark.asyncio
async def test_get_activity_details_wraps_raw(details_payload: dict[str, Any]) -> None:
    client = GarminClient(garmin_factory=_factory(details=details_payload))
    await client.login("a@b.com", "pw")
    details = await client.get_activity_details("1001")
    assert details.activity_id == "1001"
    assert details.raw["activityName"] == "Morning Run"


@pytest.mark.asyncio
async def test_get_activity_splits_indexes(splits_payload: dict[str, Any]) -> None:
    client = GarminClient(garmin_factory=_factory(splits=splits_payload))
    await client.login("a@b.com", "pw")
    splits = await client.get_activity_splits("1001")
    assert [s.index for s in splits] == [0, 1, 2]
    assert splits[0].avg_hr == 145


@pytest.mark.asyncio
async def test_get_activity_timeseries_parses_samples(
    timeseries_payload: dict[str, Any],
) -> None:
    client = GarminClient(garmin_factory=_factory(timeseries=timeseries_payload))
    await client.login("a@b.com", "pw")
    ts = await client.get_activity_timeseries("1001")
    assert len(ts.samples) == 3
    assert ts.samples[0].heart_rate == 130


@pytest.mark.asyncio
async def test_calls_before_login_raise() -> None:
    client = GarminClient(garmin_factory=_factory())
    with pytest.raises(GarminAuthError):
        await client.list_activities(datetime(2026, 4, 1), datetime(2026, 4, 2))


@pytest.mark.asyncio
async def test_list_activities_translates_lib_errors() -> None:
    class _BoomError(Exception):
        pass

    def make(email: str | None, password: str | None) -> _FakeGarmin:
        fake = _FakeGarmin(email, password, activities=[])

        def boom(*_a: Any, **_k: Any) -> None:
            raise _BoomError("upstream error")

        fake.get_activities_by_date = boom  # type: ignore[method-assign]
        return fake

    client = GarminClient(garmin_factory=make)
    await client.login("a@b.com", "pw")
    with pytest.raises(GarminApiError):
        await client.list_activities(datetime(2026, 4, 1), datetime(2026, 4, 2))
