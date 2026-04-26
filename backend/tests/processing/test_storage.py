"""Tests for :class:`runllm.processing.storage.ActivityStorage`."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from runllm.processing.storage import ActivityStorage


class _FakeBucket:
    def __init__(self) -> None:
        self.uploaded: list[tuple[str, bytes, dict[str, Any]]] = []
        self.downloaded: list[str] = []
        self.removed: list[list[str]] = []
        self.objects: dict[str, bytes] = {}

    def upload(self, path: str, data: bytes, options: dict[str, Any]) -> None:
        self.uploaded.append((path, data, options))
        self.objects[path] = data

    def download(self, path: str) -> bytes:
        self.downloaded.append(path)
        return self.objects.get(path, b"")

    def remove(self, paths: list[str]) -> None:
        self.removed.append(paths)
        for p in paths:
            self.objects.pop(p, None)


class _FakeClient:
    def __init__(self) -> None:
        self.bucket = _FakeBucket()

    def from_(self, name: str) -> _FakeBucket:
        return self.bucket


@pytest.mark.asyncio
async def test_upload_returns_path_and_invokes_bucket() -> None:
    client = _FakeClient()
    storage = ActivityStorage(client, bucket="activities")
    user_id, activity_id = uuid4(), uuid4()
    path = await storage.upload_timeseries(user_id, activity_id, b"parquet")
    assert path == f"{user_id}/{activity_id}.parquet"
    assert client.bucket.uploaded[0][0] == path
    assert client.bucket.uploaded[0][1] == b"parquet"


@pytest.mark.asyncio
async def test_download_returns_bytes() -> None:
    client = _FakeClient()
    user_id, activity_id = uuid4(), uuid4()
    storage = ActivityStorage(client, bucket="activities")
    path = await storage.upload_timeseries(user_id, activity_id, b"abc")
    assert await storage.download_timeseries(path) == b"abc"


@pytest.mark.asyncio
async def test_delete_invokes_remove() -> None:
    client = _FakeClient()
    storage = ActivityStorage(client, bucket="activities")
    user_id, activity_id = uuid4(), uuid4()
    path = await storage.upload_timeseries(user_id, activity_id, b"x")
    await storage.delete_timeseries(path)
    assert client.bucket.removed == [[path]]
    assert path not in client.bucket.objects
