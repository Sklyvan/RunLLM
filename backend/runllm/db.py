"""Async SQLAlchemy engine and session helpers."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from typing import cast

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from runllm.config import Settings, get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _build_engine(settings: Settings) -> AsyncEngine:
    """Create an :class:`AsyncEngine` from application settings."""

    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        future=True,
    )


def get_engine(settings: Settings | None = None) -> AsyncEngine:
    """Return a process-wide async engine, creating it lazily."""

    global _engine
    if _engine is None:
        _engine = _build_engine(settings or get_settings())
    return _engine


def get_session_factory(
    settings: Settings | None = None,
) -> async_sessionmaker[AsyncSession]:
    """Return a process-wide :class:`async_sessionmaker`."""

    global _session_factory
    if _session_factory is None:
        engine = get_engine(settings)
        _session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI-friendly dependency yielding a single session."""

    factory = get_session_factory()
    async with factory() as session:
        yield session


def reset_engine_for_tests() -> None:
    """Drop cached engine/session-factory; used by tests to swap URLs."""

    global _engine, _session_factory
    _engine = None
    _session_factory = None


SessionFactory = Callable[[], AsyncSession]


def session_factory_callable() -> SessionFactory:
    """Return a zero-arg callable that opens a new session.

    Useful for non-FastAPI components (services, processors) that need
    to create their own session in a context manager.
    """

    factory = get_session_factory()
    return cast(SessionFactory, factory)
