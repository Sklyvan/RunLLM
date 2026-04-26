"""Shared FastAPI dependencies for service construction.

Each request gets a freshly-constructed service so tests can override
them with ``app.dependency_overrides``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from runllm.config import get_settings
from runllm.db import get_session_factory
from runllm.garmin.client import GarminClient
from runllm.garmin.crypto import CredentialCipher
from runllm.garmin.service import GarminService
from runllm.llm.service import LLMService
from runllm.processing.processor import ActivityProcessor
from runllm.processing.storage import ActivityStorage


def _supabase_storage_client() -> Any:  # pragma: no cover - real Supabase client
    from supabase import create_client

    settings = get_settings()
    client = create_client(
        settings.supabase_url,
        settings.supabase_service_key.get_secret_value(),
    )
    return client.storage


def _anthropic_client() -> Any:  # pragma: no cover - real Anthropic client
    import anthropic

    return anthropic.AsyncAnthropic(api_key=get_settings().anthropic_api_key.get_secret_value())


def get_garmin_service() -> GarminService:
    cipher = CredentialCipher()
    return GarminService(
        client=GarminClient(),
        session_factory=cast(Any, get_session_factory()),
        cipher=cipher,
    )


def get_storage() -> ActivityStorage:
    return ActivityStorage(_supabase_storage_client())


def get_llm_service() -> LLMService:
    return LLMService(
        anthropic_client=_anthropic_client(),
        storage=get_storage(),
        session_factory=cast(Any, get_session_factory()),
        model=get_settings().anthropic_model,
    )


def get_processor_factory() -> Callable[[], ActivityProcessor]:
    def _make() -> ActivityProcessor:
        return ActivityProcessor(
            garmin=GarminClient(),
            storage=get_storage(),
            session_factory=cast(Any, get_session_factory()),
        )

    return _make
