"""Static-import & contract sanity checks across the whole package.

These tests catch the most common cross-phase compatibility regressions
(typo in re-exports, accidental circular imports, mismatched protocol
signatures) before any business logic runs.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil

import pytest

import runllm
from runllm.garmin.client import GarminClient
from runllm.garmin.interface import GarminClientProtocol


@pytest.mark.parametrize(
    "module",
    sorted(
        m.name
        for m in pkgutil.walk_packages(runllm.__path__, prefix="runllm.")
        if not m.name.endswith(".__main__")
    ),
)
def test_every_submodule_imports(module: str) -> None:
    """Every module under ``runllm`` imports without side effects."""

    importlib.import_module(module)


def test_garmin_client_satisfies_protocol() -> None:
    """``GarminClient`` exposes every method declared on the Protocol."""

    protocol_methods = {
        name
        for name, value in inspect.getmembers(GarminClientProtocol, inspect.isfunction)
        if not name.startswith("_")
    }
    client_methods = {
        name
        for name, value in inspect.getmembers(GarminClient, inspect.isfunction)
        if not name.startswith("_")
    }
    assert protocol_methods.issubset(client_methods), protocol_methods - client_methods


def test_public_facade_re_exports() -> None:
    """The package surface advertised in the docs is actually importable."""

    from runllm.api import create_app  # noqa: F401
    from runllm.garmin import GarminClientProtocol as _Protocol  # noqa: F401
    from runllm.llm import TOOL_SCHEMAS, LLMService  # noqa: F401
    from runllm.models import Activity, User  # noqa: F401
    from runllm.processing import (  # noqa: F401
        ActivityProcessor,
        ActivityStorage,
        ProcessingReport,
    )
