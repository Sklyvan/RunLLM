"""Tests for :class:`LLMService` with a mocked Anthropic client."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from runllm.llm.exceptions import LLMError
from runllm.llm.service import LLMService
from runllm.models import Activity, User
from runllm.processing.storage import ActivityStorage


class _Block:
    def __init__(self, **kwargs: Any) -> None:
        self.__dict__.update(kwargs)


class _Response:
    def __init__(self, content: list[_Block], stop_reason: str) -> None:
        self.content = content
        self.stop_reason = stop_reason


class _FakeMessages:
    def __init__(self, scripted: list[_Response]) -> None:
        self._scripted = list(scripted)
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> _Response:
        self.calls.append(kwargs)
        if not self._scripted:
            raise AssertionError("ran out of scripted responses")
        return self._scripted.pop(0)


class _FakeAnthropic:
    def __init__(self, responses: list[_Response]) -> None:
        self.messages = _FakeMessages(responses)


class _FakeStorageClient:
    def from_(self, name: str) -> Any:
        class _B:
            def upload(self, *_a: Any, **_k: Any) -> None: ...
            def download(self, *_a: Any, **_k: Any) -> bytes:
                return b""

            def remove(self, *_a: Any, **_k: Any) -> None: ...

        return _B()


@pytest_asyncio.fixture
async def session_factory() -> AsyncGenerator[Any, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    def factory() -> SQLModelAsyncSession:
        return SQLModelAsyncSession(engine, expire_on_commit=False)

    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def user_with_activity(session_factory: Any) -> tuple[UUID, UUID]:
    user = User(supabase_user_id=uuid4(), email="alice@example.com")
    activity_user_id: UUID
    async with session_factory() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)
        activity_user_id = user.id

        activity = Activity(
            user_id=activity_user_id,
            garmin_activity_id="g-1",
            activity_type="running",
            start_time=datetime(2026, 4, 10, 7, 30, tzinfo=UTC),
            duration_seconds=1500,
            distance_meters=5000.0,
            avg_hr=150,
            avg_pace_seconds_per_km=300.0,
        )
        session.add(activity)
        await session.commit()
        await session.refresh(activity)
        return activity_user_id, activity.id


def _storage() -> ActivityStorage:
    return ActivityStorage(_FakeStorageClient(), bucket="activities")


@pytest.mark.asyncio
async def test_chat_simple_text_response(
    session_factory: Any, user_with_activity: tuple[UUID, UUID]
) -> None:
    user_id, _ = user_with_activity
    anthro = _FakeAnthropic(
        [_Response([_Block(type="text", text="Hello!")], stop_reason="end_turn")]
    )
    svc = LLMService(anthro, _storage(), session_factory)
    result = await svc.chat(user_id, "hi")
    assert result.response == "Hello!"
    assert result.tools_used == []


@pytest.mark.asyncio
async def test_chat_executes_single_tool_then_text(
    session_factory: Any, user_with_activity: tuple[UUID, UUID]
) -> None:
    user_id, activity_id = user_with_activity
    anthro = _FakeAnthropic(
        [
            _Response(
                [
                    _Block(
                        type="tool_use",
                        id="t1",
                        name="get_activity_detail",
                        input={"activity_id": str(activity_id)},
                    )
                ],
                stop_reason="tool_use",
            ),
            _Response([_Block(type="text", text="You ran 5 km.")], stop_reason="end_turn"),
        ]
    )
    svc = LLMService(anthro, _storage(), session_factory)
    result = await svc.chat(user_id, "details please")
    assert result.response == "You ran 5 km."
    assert result.tools_used == ["get_activity_detail"]
    # Two API calls: initial + after tool result
    assert len(anthro.messages.calls) == 2


@pytest.mark.asyncio
async def test_chat_tool_error_recovers(
    session_factory: Any, user_with_activity: tuple[UUID, UUID]
) -> None:
    user_id, _ = user_with_activity
    bogus_id = str(uuid4())
    anthro = _FakeAnthropic(
        [
            _Response(
                [
                    _Block(
                        type="tool_use",
                        id="t1",
                        name="get_activity_detail",
                        input={"activity_id": bogus_id},
                    )
                ],
                stop_reason="tool_use",
            ),
            _Response([_Block(type="text", text="sorry")], stop_reason="end_turn"),
        ]
    )
    svc = LLMService(anthro, _storage(), session_factory)
    result = await svc.chat(user_id, "x")
    assert "sorry" in result.response
    # The tool result block sent to Claude must be marked as an error.
    second_call = anthro.messages.calls[1]
    final_user_msg = second_call["messages"][-1]
    assert final_user_msg["role"] == "user"
    assert final_user_msg["content"][0].get("is_error") is True


@pytest.mark.asyncio
async def test_chat_enforces_turn_limit(
    session_factory: Any, user_with_activity: tuple[UUID, UUID]
) -> None:
    user_id, activity_id = user_with_activity
    looping = [
        _Response(
            [
                _Block(
                    type="tool_use",
                    id=f"t{i}",
                    name="get_activity_detail",
                    input={"activity_id": str(activity_id)},
                )
            ],
            stop_reason="tool_use",
        )
        for i in range(10)
    ]
    anthro = _FakeAnthropic(looping)
    svc = LLMService(anthro, _storage(), session_factory, max_turns=3)
    with pytest.raises(LLMError):
        await svc.chat(user_id, "x")
    assert len(anthro.messages.calls) == 3
