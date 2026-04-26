"""Supabase JWT verification.

The Supabase JS client logs the user in on the frontend; the resulting
JWT is sent in ``Authorization: Bearer ...``. We verify it against the
project's JWT secret (HS256) and resolve a local :class:`User` row,
upserting one on first sight.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from runllm.config import Settings, get_settings
from runllm.db import get_session
from runllm.models import User

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SupabaseClaims:
    """Subset of Supabase JWT claims we rely on."""

    sub: UUID
    email: str | None


def verify_supabase_jwt(token: str, settings: Settings | None = None) -> SupabaseClaims:
    """Decode and validate a Supabase JWT (HS256, signed with the anon key)."""

    cfg = settings or get_settings()
    secret = cfg.supabase_anon_key.get_secret_value()
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience="authenticated",
            options={"verify_aud": False},  # Supabase audience is project-specific
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired token",
        ) from exc

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing sub claim")
    return SupabaseClaims(sub=UUID(str(sub)), email=payload.get("email"))


async def _claims_from_header(
    authorization: Annotated[str | None, Header()] = None,
) -> SupabaseClaims:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
        )
    token = authorization.split(" ", 1)[1].strip()
    return verify_supabase_jwt(token)


async def get_current_user(
    claims: Annotated[SupabaseClaims, Depends(_claims_from_header)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    """Resolve a :class:`User` row, creating one on first login."""

    result = await session.exec(select(User).where(User.supabase_user_id == claims.sub))
    user = result.first()
    if user is None:
        user = User(
            supabase_user_id=claims.sub,
            email=claims.email or f"user-{claims.sub}@local",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user
