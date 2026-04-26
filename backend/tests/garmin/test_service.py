"""Integration-style tests for :class:`GarminService`."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from runllm.garmin.crypto import CredentialCipher
from runllm.garmin.exceptions import GarminAuthError, GarminMfaRequiredError
from runllm.garmin.models import (
    GarminActivityDetails,
    GarminActivitySummary,
    GarminAuthTokens,
    GarminSplit,
    GarminTimeSeries,
)
from runllm.garmin.service import GarminService
from runllm.models import User


class _FakeClient:
    def __init__(self) -> None:
        self.tokens = GarminAuthTokens(data={"refresh": "r1"})
        self.next_login_raises: Exception | None = None
        self.restore_ok = True
        self.activities: list[GarminActivitySummary] = []
        self.calls: list[str] = []

    async def login(self, email: str, password: str) -> GarminAuthTokens:
        self.calls.append("login")
        if self.next_login_raises is not None:
            exc = self.next_login_raises
            self.next_login_raises = None
            raise exc
        return self.tokens

    async def submit_mfa(self, code: str) -> GarminAuthTokens:
        self.calls.append(f"mfa:{code}")
        return self.tokens

    async def restore_session(self, tokens: GarminAuthTokens) -> bool:
        self.calls.append("restore")
        return self.restore_ok

    async def list_activities(
        self, start: datetime, end: datetime, limit: int = 200
    ) -> list[GarminActivitySummary]:
        self.calls.append("list")
        return self.activities

    async def get_activity_details(self, activity_id: str) -> GarminActivityDetails:
        return GarminActivityDetails(activity_id=activity_id)

    async def get_activity_splits(self, activity_id: str) -> list[GarminSplit]:
        return []

    async def get_activity_timeseries(self, activity_id: str) -> GarminTimeSeries:
        return GarminTimeSeries(activity_id=activity_id)


@pytest_asyncio.fixture
async def session_factory() -> AsyncGenerator[
    tuple[type, SQLModelAsyncSession],
    None,
]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    def factory() -> SQLModelAsyncSession:
        return SQLModelAsyncSession(engine, expire_on_commit=False)

    yield factory  # type: ignore[misc]
    await engine.dispose()


@pytest_asyncio.fixture
async def user_id(session_factory) -> UUID:  # type: ignore[no-untyped-def]
    user = User(supabase_user_id=uuid4(), email="alice@example.com")
    async with session_factory() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user.id


@pytest.fixture()
def cipher() -> CredentialCipher:
    return CredentialCipher(key=Fernet.generate_key())


@pytest.fixture()
def service(session_factory, cipher: CredentialCipher) -> tuple[GarminService, _FakeClient]:  # type: ignore[no-untyped-def]
    fake = _FakeClient()
    return GarminService(client=fake, session_factory=session_factory, cipher=cipher), fake


@pytest.mark.asyncio
async def test_authenticate_persists_encrypted_tokens(
    service: tuple[GarminService, _FakeClient],
    user_id: UUID,
    session_factory,  # type: ignore[no-untyped-def]
    cipher: CredentialCipher,
) -> None:
    svc, fake = service
    result = await svc.authenticate_user(user_id, "alice@example.com", "pw")
    assert result.status == "ok"
    assert "login" in fake.calls

    async with session_factory() as session:
        user = await session.get(User, user_id)
        assert user is not None
        assert user.garmin_email == "alice@example.com"
        assert user.garmin_credentials_encrypted is not None
        decrypted = cipher.decrypt_dict(user.garmin_credentials_encrypted)
        assert decrypted == fake.tokens.data
        assert user.garmin_last_sync_at is not None


@pytest.mark.asyncio
async def test_authenticate_returns_mfa_required_and_remembers_email(
    service: tuple[GarminService, _FakeClient],
    user_id: UUID,
    session_factory,  # type: ignore[no-untyped-def]
) -> None:
    svc, fake = service
    fake.next_login_raises = GarminMfaRequiredError(state="x")
    result = await svc.authenticate_user(user_id, "alice@example.com", "pw")
    assert result.status == "mfa_required"

    async with session_factory() as session:
        user = await session.get(User, user_id)
        assert user is not None
        assert user.garmin_email == "alice@example.com"
        assert user.garmin_credentials_encrypted is None


@pytest.mark.asyncio
async def test_submit_mfa_persists_tokens(
    service: tuple[GarminService, _FakeClient],
    user_id: UUID,
    session_factory,  # type: ignore[no-untyped-def]
) -> None:
    svc, fake = service
    fake.next_login_raises = GarminMfaRequiredError(state="x")
    await svc.authenticate_user(user_id, "alice@example.com", "pw")
    result = await svc.submit_mfa(user_id, "654321")
    assert result.status == "ok"

    async with session_factory() as session:
        user = await session.get(User, user_id)
        assert user is not None
        assert user.garmin_credentials_encrypted is not None


@pytest.mark.asyncio
async def test_fetch_activities_restores_session(
    service: tuple[GarminService, _FakeClient],
    user_id: UUID,
) -> None:
    svc, fake = service
    await svc.authenticate_user(user_id, "alice@example.com", "pw")
    activities = await svc.fetch_activities_since(user_id, datetime(2026, 1, 1, tzinfo=UTC))
    assert activities == []
    assert "restore" in fake.calls
    assert "list" in fake.calls


@pytest.mark.asyncio
async def test_fetch_activities_without_credentials_raises(
    service: tuple[GarminService, _FakeClient],
    user_id: UUID,
) -> None:
    svc, _fake = service
    with pytest.raises(GarminAuthError):
        await svc.fetch_activities_since(user_id, datetime(2026, 1, 1, tzinfo=UTC))

