"""Tests for the Garmin endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient

from runllm.garmin.exceptions import GarminAuthError, GarminMfaRequiredError
from runllm.garmin.models import GarminActivitySummary


def _summary(activity_id: str = "g-1") -> GarminActivitySummary:
    return GarminActivitySummary.model_validate(
        {
            "activity_id": activity_id,
            "activity_type": "running",
            "start_time": datetime(2026, 4, 10, 7, 30, tzinfo=UTC),
            "distance_meters": 5000.0,
            "duration_seconds": 1500.0,
        }
    )


@pytest.mark.asyncio
async def test_credentials_happy_path(app_and_user: tuple[Any, ...], client: AsyncClient) -> None:
    _, _, fake_garmin, *_ = app_and_user
    response = await client.post(
        "/api/v1/garmin/credentials",
        json={"email": "alice@example.com", "password": "pw"},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert fake_garmin.last_call[0] == "auth"


@pytest.mark.asyncio
async def test_credentials_returns_mfa_required(
    app_and_user: tuple[Any, ...], client: AsyncClient
) -> None:
    _, _, fake_garmin, *_ = app_and_user
    fake_garmin.next_status = "mfa_required"
    response = await client.post(
        "/api/v1/garmin/credentials",
        json={"email": "alice@example.com", "password": "pw"},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "mfa_required"}


@pytest.mark.asyncio
async def test_mfa_endpoint(app_and_user: tuple[Any, ...], client: AsyncClient) -> None:
    response = await client.post("/api/v1/garmin/mfa", json={"code": "654321"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_sync_with_no_new_activities(
    app_and_user: tuple[Any, ...], client: AsyncClient
) -> None:
    _, _, fake_garmin, fake_processor, _ = app_and_user
    fake_garmin.activities = []
    response = await client.post("/api/v1/garmin/sync")
    assert response.status_code == 200
    body = response.json()
    assert body["created"] == 0
    assert fake_processor.last_batch == []


@pytest.mark.asyncio
async def test_sync_processes_returned_activities(
    app_and_user: tuple[Any, ...], client: AsyncClient
) -> None:
    _, _, fake_garmin, fake_processor, _ = app_and_user
    fake_garmin.activities = [_summary("g-1"), _summary("g-2")]
    response = await client.post("/api/v1/garmin/sync")
    assert response.status_code == 200
    body = response.json()
    assert body["created"] == 2
    assert fake_processor.last_batch is not None
    assert len(fake_processor.last_batch) == 2


@pytest.mark.asyncio
async def test_sync_returns_409_on_mfa_required(
    app_and_user: tuple[Any, ...], client: AsyncClient
) -> None:
    _, _, fake_garmin, *_ = app_and_user

    async def _raise(*_a: Any, **_k: Any) -> Any:
        raise GarminMfaRequiredError("need code")

    fake_garmin.fetch_activities_since = _raise  # type: ignore[assignment]
    response = await client.post("/api/v1/garmin/sync")
    assert response.status_code == 409
    assert response.json() == {"detail": "mfa_required"}


@pytest.mark.asyncio
async def test_sync_returns_401_on_auth_error(
    app_and_user: tuple[Any, ...], client: AsyncClient
) -> None:
    _, _, fake_garmin, *_ = app_and_user

    async def _raise(*_a: Any, **_k: Any) -> Any:
        raise GarminAuthError("expired")

    fake_garmin.fetch_activities_since = _raise  # type: ignore[assignment]
    response = await client.post("/api/v1/garmin/sync")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_status_returns_zero_activities(
    app_and_user: tuple[Any, ...], client: AsyncClient
) -> None:
    response = await client.get("/api/v1/garmin/status")
    assert response.status_code == 200
    body = response.json()
    assert body["activity_count"] == 0
    assert body["has_credentials"] is False
