"""Shared API test fixtures.

The app is built once per test using a fresh in-memory SQLite engine,
and the auth + service dependencies are overridden so tests never need
real JWTs or external clients.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID, uuid4

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from runllm.api.app import create_app
from runllm.api.auth import get_current_user
from runllm.api.dependencies import (
    get_garmin_service,
    get_llm_service,
    get_processor_factory,
)
from runllm.db import get_session, get_session_factory
from runllm.models import User


class _FakeGarminService:
    def __init__(self) -> None:
        self.last_call: tuple[str, ...] | None = None
        self.next_status = "ok"
        self.activities: list[Any] = []

    async def authenticate_user(self, user_id: UUID, email: str, password: str):  # type: ignore[no-untyped-def]
        self.last_call = ("auth", str(user_id), email)
        from runllm.garmin.service import AuthResult

        return AuthResult(status=self.next_status)  # type: ignore[arg-type]

    async def submit_mfa(self, user_id: UUID, code: str):  # type: ignore[no-untyped-def]
        self.last_call = ("mfa", str(user_id), code)
        from runllm.garmin.service import AuthResult

        return AuthResult(status="ok")

    async def fetch_activities_since(self, user_id: UUID, since: Any) -> list[Any]:
        return self.activities


class _FakeProcessor:
    def __init__(self) -> None:
        self.last_batch: list[Any] | None = None

    async def process_batch(self, user_id: UUID, summaries: list[Any]):  # type: ignore[no-untyped-def]
        from runllm.processing.processor import ProcessingReport

        self.last_batch = summaries
        return ProcessingReport(created=len(summaries))


class _FakeLLMService:
    def __init__(self) -> None:
        self.last_message: tuple[UUID, str] | None = None

    async def chat(self, user_id: UUID, message: str):  # type: ignore[no-untyped-def]
        from runllm.llm.service import ChatResponse

        self.last_message = (user_id, message)
        return ChatResponse(response="ack: " + message, tools_used=["get_activity_detail"])


@pytest_asyncio.fixture
async def app_and_user() -> (
    AsyncGenerator[tuple[FastAPI, User, _FakeGarminService, _FakeProcessor, _FakeLLMService], None]
):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    def factory() -> SQLModelAsyncSession:
        return SQLModelAsyncSession(engine, expire_on_commit=False)

    user = User(supabase_user_id=uuid4(), email="alice@example.com")
    async with factory() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)

    app = create_app()

    async def _session_override() -> AsyncGenerator[Any, None]:
        async with factory() as session:
            yield session

    fake_garmin = _FakeGarminService()
    fake_processor = _FakeProcessor()
    fake_llm = _FakeLLMService()

    def _factory_override() -> Any:
        return factory

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_garmin_service] = lambda: fake_garmin
    app.dependency_overrides[get_llm_service] = lambda: fake_llm
    app.dependency_overrides[get_processor_factory] = lambda: (lambda: fake_processor)

    # Patch the global session factory used by ad-hoc accessors in routers.
    import runllm.db as db_module

    original = db_module._session_factory  # type: ignore[attr-defined]
    db_module._session_factory = factory  # type: ignore[attr-defined]

    yield app, user, fake_garmin, fake_processor, fake_llm

    db_module._session_factory = original  # type: ignore[attr-defined]
    await engine.dispose()


@pytest_asyncio.fixture
async def client(
    app_and_user: tuple[FastAPI, User, Any, Any, Any],
) -> AsyncGenerator[AsyncClient, None]:
    app, *_ = app_and_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# Silence unused warning when only the wrapper fixtures are imported.
__all__ = ["app_and_user", "client", "get_session_factory"]
