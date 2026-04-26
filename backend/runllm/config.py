"""Application configuration loaded from environment variables.

All secrets are wrapped in :class:`pydantic.SecretStr` so they are never
logged or serialized accidentally. The settings object is intended to be
constructed once at startup and injected as a dependency.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the RunLLM backend.

    Attributes
    ----------
    supabase_url
        Base URL of the Supabase project.
    supabase_anon_key
        Public anon key, used for JWT verification (JWKS) and client SDK.
    supabase_service_key
        Service-role key, used for privileged server-side calls (Storage).
    database_url
        Async Postgres URL, e.g. ``postgresql+asyncpg://...``.
    anthropic_api_key
        API key for the Anthropic SDK.
    fernet_key
        Base64-encoded 32-byte key used by :mod:`cryptography.fernet`
        to encrypt user-provided third-party credentials at rest.
    environment
        Deployment environment label.
    log_level
        Root log level.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    supabase_url: str = "http://localhost:54321"
    supabase_anon_key: SecretStr = SecretStr("changeme")
    supabase_service_key: SecretStr = SecretStr("changeme")
    supabase_bucket: str = "activities"

    database_url: str = "sqlite+aiosqlite:///./runllm.db"

    anthropic_api_key: SecretStr = SecretStr("changeme")
    anthropic_model: str = "claude-sonnet-4-5"

    fernet_key: SecretStr = SecretStr("changeme")

    environment: Literal["dev", "prod", "test"] = "dev"
    log_level: str = "INFO"

    allowed_origins: str = "http://localhost:5173"

    host: str = "0.0.0.0"
    port: int = 8000


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance."""

    return Settings()

