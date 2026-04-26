"""Full HTTP-level integration: Garmin sync → DB/Storage → Chat → tool use.

Only the network boundaries (Anthropic, garminconnect) are stubbed.
Auth, request/response (de)serialization, exception mappings, the
processor, the storage layer and the tool execution loop all run for
real.
"""

from __future__ import annotations

from typing import Any

import jwt
import pytest
from httpx import AsyncClient
from sqlmodel import select

from runllm.api.auth import get_current_user
from runllm.config import get_settings
from runllm.garmin.exceptions import GarminMfaRequiredError
from runllm.models import Activity, User
from tests.integration.conftest import (
    FakeGarminClient,
    ScriptedAnthropic,
    make_summary,
    text_response,
    tool_call_response,
)


@pytest.mark.asyncio
async def test_health_endpoints_are_reachable(integrated_client: AsyncClient) -> None:
    assert (await integrated_client.get("/healthz")).status_code == 200
    assert (await integrated_client.get("/readyz")).status_code == 200


@pytest.mark.asyncio
async def test_full_sync_then_chat_uses_tool_against_real_data(
    integrated_app: tuple[Any, ScriptedAnthropic, FakeGarminClient],
    integrated_client: AsyncClient,
    session_factory: Any,
    user: User,
) -> None:
    """A POST /sync persists rows, a POST /chat then drives a tool call
    that reads the very same rows + Parquet through the live stack."""

    _app, anthropic, garmin = integrated_app
    garmin.activities = [make_summary("g-1", days_ago=2), make_summary("g-2", days_ago=4)]

    # Authenticate first so the user has tokens on file (the real path).
    creds = await integrated_client.post(
        "/api/v1/garmin/credentials",
        json={"email": "alice@example.com", "password": "pw"},
    )
    assert creds.status_code == 200

    # /sync runs the real processor end to end.
    sync = await integrated_client.post("/api/v1/garmin/sync")
    assert sync.status_code == 200
    body = sync.json()
    assert body["created"] == 2
    assert body["failed"] == 0

    async with session_factory() as session:
        activities = (await session.exec(select(Activity).where(Activity.user_id == user.id))).all()
    assert len(activities) == 2
    target = activities[0]

    # Script Claude: first response asks the tool, second returns text.
    anthropic._responses = [  # type: ignore[attr-defined]
        tool_call_response(
            "get_activity_detail",
            {"activity_id": str(target.id)},
            block_id="t-detail",
        ),
        text_response("You ran 5 km."),
    ]

    chat = await integrated_client.post(
        "/api/v1/chat", json={"message": "tell me about my last run"}
    )
    assert chat.status_code == 200
    payload = chat.json()
    assert payload["response"] == "You ran 5 km."
    assert payload["tools_used"] == ["get_activity_detail"]

    # The second Anthropic call must have received the tool result block.
    second = anthropic.calls[1]
    final_user_msg = second["messages"][-1]
    assert final_user_msg["role"] == "user"
    tool_result = final_user_msg["content"][0]
    assert tool_result["type"] == "tool_result"
    # And the result content really came from our DB.
    assert str(target.id) in tool_result["content"]


@pytest.mark.asyncio
async def test_status_endpoint_reflects_recent_sync(
    integrated_app: tuple[Any, ScriptedAnthropic, FakeGarminClient],
    integrated_client: AsyncClient,
) -> None:
    _, _, garmin = integrated_app
    garmin.activities = [make_summary("g-status", days_ago=1)]

    await integrated_client.post(
        "/api/v1/garmin/credentials",
        json={"email": "alice@example.com", "password": "pw"},
    )
    await integrated_client.post("/api/v1/garmin/sync")
    response = await integrated_client.get("/api/v1/garmin/status")
    assert response.status_code == 200
    body = response.json()
    assert body["activity_count"] == 1


@pytest.mark.asyncio
async def test_credentials_then_mfa_flow(
    integrated_app: tuple[Any, ScriptedAnthropic, FakeGarminClient],
    integrated_client: AsyncClient,
    user: User,
    session_factory: Any,
) -> None:
    """Credentials → MFA returns ``ok`` and persists encrypted tokens."""

    response = await integrated_client.post(
        "/api/v1/garmin/credentials",
        json={"email": "alice@example.com", "password": "pw"},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    async with session_factory() as session:
        refreshed = await session.get(User, user.id)
        assert refreshed is not None
        assert refreshed.garmin_credentials_encrypted is not None
        assert refreshed.garmin_email == "alice@example.com"


@pytest.mark.asyncio
async def test_sync_translates_mfa_required_to_409(
    integrated_app: tuple[Any, ScriptedAnthropic, FakeGarminClient],
    integrated_client: AsyncClient,
) -> None:
    _, _, garmin = integrated_app

    await integrated_client.post(
        "/api/v1/garmin/credentials",
        json={"email": "alice@example.com", "password": "pw"},
    )

    async def _raise(*_a: Any, **_k: Any) -> Any:
        raise GarminMfaRequiredError()

    garmin.list_activities = _raise  # type: ignore[assignment]
    garmin.session_alive = True

    response = await integrated_client.post("/api/v1/garmin/sync")
    assert response.status_code == 409
    assert response.json() == {"detail": "mfa_required"}


@pytest.mark.asyncio
async def test_chat_validation_error_returns_422(
    integrated_client: AsyncClient,
) -> None:
    response = await integrated_client.post("/api/v1/chat", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_real_jwt_resolves_to_local_user_row(
    integrated_app: tuple[Any, ScriptedAnthropic, FakeGarminClient],
    integrated_client: AsyncClient,
    session_factory: Any,
) -> None:
    """End-to-end JWT → ``get_current_user`` upserts a fresh User row."""

    app, _, _ = integrated_app
    # Drop the override so the real auth dependency runs.
    app.dependency_overrides.pop(get_current_user, None)

    settings = get_settings()
    token = jwt.encode(
        {
            "sub": "00000000-0000-0000-0000-000000000abc",
            "email": "fresh@example.com",
        },
        settings.supabase_anon_key.get_secret_value(),
        algorithm="HS256",
    )

    response = await integrated_client.get(
        "/api/v1/garmin/status",
        headers={"authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200

    async with session_factory() as session:
        rows = (await session.exec(select(User).where(User.email == "fresh@example.com"))).all()
    assert len(rows) == 1
