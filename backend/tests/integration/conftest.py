"""Shared fixtures for cross-component integration tests.

These tests wire **real** services together (Activity processor,
ActivityStorage, ToolRegistry, LLMService, FastAPI app, prompt
builder) and only stub out the truly external boundaries:

* ``garminconnect`` — replaced by an in-process fake that returns
  deterministic JSON.
* Anthropic Messages API — replaced by a scripted client that lets
  each test drive the agent loop.
* Supabase Storage — replaced by an in-memory bucket. The Parquet
  bytes themselves are real; ``ActivityStorage`` is exercised end to
  end.

This way the suite catches contract drift between phases (mappers ↔
processor ↔ storage ↔ tools ↔ service ↔ API) which the per-layer
unit tests cannot see in isolation.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest_asyncio
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

import runllm.db as db_module
from runllm.api.app import create_app
from runllm.api.auth import get_current_user
from runllm.api.dependencies import (
    get_garmin_service,
    get_llm_service,
    get_processor_factory,
)
from runllm.db import get_session
from runllm.garmin.crypto import CredentialCipher
from runllm.garmin.interface import GarminClientProtocol
from runllm.garmin.models import (
    GarminActivityDetails,
    GarminActivitySummary,
    GarminAuthTokens,
    GarminSplit,
    GarminTimeSeries,
    GarminTimeSeriesSample,
)
from runllm.garmin.service import GarminService
from runllm.llm.service import LLMService
from runllm.models import User
from runllm.processing.processor import ActivityProcessor
from runllm.processing.storage import ActivityStorage

# --------------------------------------------------------------------- bucket


class InMemoryBucket:
    """Drop-in replacement for ``supabase.storage.from_(...)``."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def upload(self, path: str, data: bytes, options: dict[str, Any]) -> None:
        self.objects[path] = data

    def download(self, path: str) -> bytes:
        return self.objects[path]

    def remove(self, paths: list[str]) -> None:
        for p in paths:
            self.objects.pop(p, None)


class InMemoryStorageClient:
    def __init__(self) -> None:
        self.bucket = InMemoryBucket()

    def from_(self, name: str) -> InMemoryBucket:
        return self.bucket


# --------------------------------------------------------------------- garmin


class FakeGarminClient(GarminClientProtocol):
    """Deterministic Garmin client driven by lists pre-populated by tests."""

    def __init__(self) -> None:
        self.activities: list[GarminActivitySummary] = []
        self.tokens = GarminAuthTokens(data={"refresh": "rt"})
        self.session_alive = True

    async def login(self, email: str, password: str) -> GarminAuthTokens:
        return self.tokens

    async def submit_mfa(self, code: str) -> GarminAuthTokens:
        return self.tokens

    async def restore_session(self, tokens: GarminAuthTokens) -> bool:
        return self.session_alive

    async def list_activities(
        self, start: datetime, end: datetime, limit: int = 200
    ) -> list[GarminActivitySummary]:
        return [a for a in self.activities if start <= a.start_time <= end][:limit]

    async def get_activity_details(self, activity_id: str) -> GarminActivityDetails:
        return GarminActivityDetails(
            activity_id=activity_id,
            raw={"activityName": f"Run {activity_id}"},
        )

    async def get_activity_splits(self, activity_id: str) -> list[GarminSplit]:
        return [
            GarminSplit(
                index=i,
                distance_meters=1000.0,
                duration_seconds=290.0 + i * 5.0,
                avg_pace_seconds_per_km=290.0 + i * 5.0,
                avg_hr=145 + i,
                elevation_gain_meters=2.0,
            )
            for i in range(3)
        ]

    async def get_activity_timeseries(self, activity_id: str) -> GarminTimeSeries:
        base = datetime(2026, 4, 10, 7, 30, tzinfo=UTC)
        samples = [
            GarminTimeSeriesSample(
                timestamp=base + timedelta(seconds=i),
                lat=41.0 + i * 0.0001,
                lon=2.0 + i * 0.0001,
                elevation=10.0 + i * 0.1,
                heart_rate=140 + (i % 30),
                cadence=170,
                speed=3.0 + 0.05 * i,
            )
            for i in range(120)
        ]
        return GarminTimeSeries(activity_id=activity_id, samples=samples)


def make_summary(activity_id: str, days_ago: int = 1) -> GarminActivitySummary:
    """Build a deterministic summary for ingestion tests."""

    return GarminActivitySummary.model_validate(
        {
            "activity_id": activity_id,
            "activity_type": "running",
            "start_time": datetime.now(tz=UTC) - timedelta(days=days_ago),
            "distance_meters": 5000.0,
            "duration_seconds": 1500.0,
            "avg_hr": 150,
            "max_hr": 175,
            "elevation_gain": 35.0,
            "calories": 350,
        }
    )


# ------------------------------------------------------------------ anthropic


class _Block:
    """Mirrors enough of an Anthropic content block for our service."""

    def __init__(self, **kwargs: Any) -> None:
        self.__dict__.update(kwargs)


class _Response:
    def __init__(self, content: list[_Block], stop_reason: str) -> None:
        self.content = content
        self.stop_reason = stop_reason


class ScriptedAnthropic:
    """Anthropic stand-in driven by a queue of scripted responses."""

    def __init__(self, responses: list[_Response]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []
        self.messages = self  # mimic ``client.messages.create``

    async def create(self, **kwargs: Any) -> _Response:
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("ran out of scripted Anthropic responses")
        return self._responses.pop(0)


def text_response(text: str) -> _Response:
    return _Response([_Block(type="text", text=text)], stop_reason="end_turn")


def tool_call_response(name: str, args: dict[str, Any], block_id: str = "t1") -> _Response:
    return _Response(
        [_Block(type="tool_use", id=block_id, name=name, input=args)],
        stop_reason="tool_use",
    )


# ---------------------------------------------------------------------- DB


@pytest_asyncio.fixture
async def session_factory() -> AsyncGenerator[Any, None]:
    """Yield a session factory backed by a private in-memory SQLite engine.

    The factory is also installed as the global ``runllm.db`` factory so
    ad-hoc accessors (e.g., the status endpoint) hit the same engine.
    """

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    def factory() -> SQLModelAsyncSession:
        return SQLModelAsyncSession(engine, expire_on_commit=False)

    original = db_module._session_factory  # type: ignore[attr-defined]
    db_module._session_factory = factory  # type: ignore[attr-defined]
    try:
        yield factory
    finally:
        db_module._session_factory = original  # type: ignore[attr-defined]
        await engine.dispose()


@pytest_asyncio.fixture
async def user(session_factory: Any) -> User:
    instance = User(
        supabase_user_id=uuid4(),
        email="alice@example.com",
        preferred_language="en",
        max_hr=180,
    )
    async with session_factory() as session:
        session.add(instance)
        await session.commit()
        await session.refresh(instance)
        return instance


# --------------------------------------------------------- real-service wiring


@pytest_asyncio.fixture
async def storage_client() -> InMemoryStorageClient:
    return InMemoryStorageClient()


@pytest_asyncio.fixture
async def storage(storage_client: InMemoryStorageClient) -> ActivityStorage:
    return ActivityStorage(storage_client, bucket="activities")


@pytest_asyncio.fixture
async def garmin_client() -> FakeGarminClient:
    return FakeGarminClient()


@pytest_asyncio.fixture
async def cipher() -> CredentialCipher:
    return CredentialCipher(key=Fernet.generate_key())


@pytest_asyncio.fixture
async def garmin_service(
    garmin_client: FakeGarminClient,
    cipher: CredentialCipher,
    session_factory: Any,
) -> GarminService:
    return GarminService(
        client=garmin_client,
        session_factory=session_factory,
        cipher=cipher,
    )


@pytest_asyncio.fixture
async def processor(
    garmin_client: FakeGarminClient,
    storage: ActivityStorage,
    session_factory: Any,
) -> ActivityProcessor:
    return ActivityProcessor(
        garmin=garmin_client,
        storage=storage,
        session_factory=session_factory,
        concurrency=2,
    )


# ------------------------------------------------------------------ FastAPI


@pytest_asyncio.fixture
async def integrated_app(
    session_factory: Any,
    user: User,
    garmin_service: GarminService,
    processor: ActivityProcessor,
    storage: ActivityStorage,
) -> AsyncGenerator[tuple[FastAPI, ScriptedAnthropic, FakeGarminClient], None]:
    """Build the FastAPI app with as much real wiring as possible.

    Only ``get_current_user`` and the LLM/Anthropic boundary are
    overridden; everything else (auth → garmin service → processor →
    storage → DB → llm tools) runs through real code paths.
    """

    app = create_app()

    async def _session_override() -> AsyncGenerator[Any, None]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_garmin_service] = lambda: garmin_service

    # Anthropic boundary — installed lazily so individual tests can mutate
    # the scripted queue.
    anthropic = ScriptedAnthropic([])
    real_llm = LLMService(anthropic, storage, session_factory)
    app.dependency_overrides[get_llm_service] = lambda: real_llm

    app.dependency_overrides[get_processor_factory] = lambda: (lambda: processor)

    yield app, anthropic, garmin_service._client  # type: ignore[attr-defined]


@pytest_asyncio.fixture
async def integrated_client(
    integrated_app: tuple[FastAPI, ScriptedAnthropic, FakeGarminClient],
) -> AsyncGenerator[AsyncClient, None]:
    app, *_ = integrated_app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


__all__ = [
    "FakeGarminClient",
    "InMemoryBucket",
    "InMemoryStorageClient",
    "ScriptedAnthropic",
    "make_summary",
    "text_response",
    "tool_call_response",
]
