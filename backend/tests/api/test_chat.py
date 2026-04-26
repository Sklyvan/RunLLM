"""Tests for the chat endpoint."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_chat_returns_response_and_tools(
    app_and_user: tuple[Any, ...], client: AsyncClient
) -> None:
    _, _, _, _, fake_llm = app_and_user
    response = await client.post("/api/v1/chat", json={"message": "hello"})
    assert response.status_code == 200
    body = response.json()
    assert body["response"] == "ack: hello"
    assert body["tools_used"] == ["get_activity_detail"]
    assert fake_llm.last_message[1] == "hello"


@pytest.mark.asyncio
async def test_chat_validation_error_on_missing_message(client: AsyncClient) -> None:
    response = await client.post("/api/v1/chat", json={})
    assert response.status_code == 422
