"""Supabase Storage wrapper for activity time-series Parquet files.

The wrapper is intentionally thin and accepts an injectable client so
tests can substitute a fake without monkey-patching ``supabase``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol
from uuid import UUID

from runllm.config import Settings, get_settings

logger = logging.getLogger(__name__)


class _StorageBucketLike(Protocol):
    def upload(self, path: str, file: bytes, file_options: dict[str, Any]) -> Any: ...

    def download(self, path: str) -> bytes: ...

    def remove(self, paths: list[str]) -> Any: ...


class _StorageClientLike(Protocol):
    def from_(self, bucket: str) -> _StorageBucketLike: ...


class ActivityStorage:
    """Read/write Parquet objects keyed by ``{user_id}/{activity_id}.parquet``."""

    def __init__(
        self,
        storage_client: _StorageClientLike,
        bucket: str | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._client = storage_client
        self._bucket = bucket or (settings or get_settings()).supabase_bucket

    @staticmethod
    def storage_path(user_id: UUID, activity_id: UUID) -> str:
        """Return the canonical storage path for an activity's time-series."""

        return f"{user_id}/{activity_id}.parquet"

    async def upload_timeseries(
        self, user_id: UUID, activity_id: UUID, parquet_bytes: bytes
    ) -> str:
        """Upload Parquet bytes; return the storage path."""

        path = self.storage_path(user_id, activity_id)
        bucket = self._client.from_(self._bucket)

        def _do() -> None:
            bucket.upload(
                path,
                parquet_bytes,
                {"content-type": "application/octet-stream", "upsert": "true"},
            )

        await asyncio.to_thread(_do)
        return path

    async def download_timeseries(self, path: str) -> bytes:
        bucket = self._client.from_(self._bucket)
        return await asyncio.to_thread(bucket.download, path)

    async def delete_timeseries(self, path: str) -> None:
        bucket = self._client.from_(self._bucket)
        await asyncio.to_thread(bucket.remove, [path])
