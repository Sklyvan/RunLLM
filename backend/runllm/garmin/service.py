"""High-level orchestrator wiring crypto + DB + Garmin client.

The service is the only thing in the backend that holds the Garmin
auth state for a given user; it is responsible for decrypting cached
tokens, restoring the session, and re-encrypting refreshed tokens
before persisting them.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from runllm.garmin.crypto import CredentialCipher
from runllm.garmin.exceptions import GarminAuthError, GarminMfaRequiredError
from runllm.garmin.interface import GarminClientProtocol
from runllm.garmin.models import GarminActivitySummary, GarminAuthTokens
from runllm.models import User

logger = logging.getLogger(__name__)


SessionFactory = Callable[[], AsyncSession]


@dataclass(frozen=True, slots=True)
class AuthResult:
    """Result of an authentication attempt."""

    status: Literal["ok", "mfa_required"]


class GarminService:
    """Per-user Garmin orchestration."""

    def __init__(
        self,
        client: GarminClientProtocol,
        session_factory: SessionFactory,
        cipher: CredentialCipher,
    ) -> None:
        self._client = client
        self._session_factory = session_factory
        self._cipher = cipher

    async def authenticate_user(self, user_id: UUID, email: str, password: str) -> AuthResult:
        """Run a full username+password login and persist tokens."""

        try:
            tokens = await self._client.login(email, password)
        except GarminMfaRequiredError:
            await self._update_user(user_id, garmin_email=email)
            return AuthResult(status="mfa_required")
        except GarminAuthError:
            raise

        await self._persist_tokens(user_id, email, tokens)
        return AuthResult(status="ok")

    async def submit_mfa(self, user_id: UUID, code: str) -> AuthResult:
        """Submit an MFA code for a previously stalled login."""

        tokens = await self._client.submit_mfa(code)
        # The user was created/updated with the email already in
        # ``authenticate_user``; reuse it here.
        async with self._session_factory() as session:
            user = await session.get(User, user_id)
            if user is None or user.garmin_email is None:
                raise GarminAuthError("no garmin email on record")
            email = user.garmin_email
        await self._persist_tokens(user_id, email, tokens)
        return AuthResult(status="ok")

    async def fetch_activities_since(
        self, user_id: UUID, since: datetime
    ) -> list[GarminActivitySummary]:
        """List activities since ``since`` for the given user."""

        await self._restore_for(user_id)
        end = datetime.now(tz=UTC)
        return await self._client.list_activities(start=since, end=end)

    # ------------------------------------------------------------------ helpers

    async def _restore_for(self, user_id: UUID) -> None:
        async with self._session_factory() as session:
            user = await session.get(User, user_id)
            if user is None or user.garmin_credentials_encrypted is None:
                raise GarminAuthError("user has no stored garmin credentials")
            blob = self._cipher.decrypt_dict(user.garmin_credentials_encrypted)
            tokens = GarminAuthTokens(data=blob)
        ok = await self._client.restore_session(tokens)
        if not ok:
            raise GarminAuthError("stored garmin tokens were rejected")

    async def _persist_tokens(self, user_id: UUID, email: str, tokens: GarminAuthTokens) -> None:
        encrypted = self._cipher.encrypt_dict(tokens.data)
        await self._update_user(
            user_id,
            garmin_email=email,
            garmin_credentials_encrypted=encrypted,
            garmin_last_sync_at=datetime.now(tz=UTC),
        )

    async def _update_user(self, user_id: UUID, **fields: object) -> None:
        async with self._session_factory() as session:
            result = await session.exec(select(User).where(User.id == user_id))
            user = result.first()
            if user is None:
                raise GarminAuthError(f"user {user_id} not found")
            for name, value in fields.items():
                setattr(user, name, value)
            session.add(user)
            await session.commit()
