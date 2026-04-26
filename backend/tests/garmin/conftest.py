"""Shared fixtures for Garmin tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture()
def activities_payload() -> list[dict[str, Any]]:
    return _load("activities.json")


@pytest.fixture()
def details_payload() -> dict[str, Any]:
    return _load("details.json")


@pytest.fixture()
def splits_payload() -> dict[str, Any]:
    return _load("splits.json")


@pytest.fixture()
def timeseries_payload() -> dict[str, Any]:
    return _load("timeseries.json")
