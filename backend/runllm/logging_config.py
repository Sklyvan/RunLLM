"""Logging configuration for the RunLLM backend."""

from __future__ import annotations

import logging
import sys

_FORMAT = "%(asctime)s %(levelname)-8s [%(name)s] %(message)s"
_DATEFMT = "%Y-%m-%dT%H:%M:%S%z"


def setup_logging(level: str = "INFO") -> None:
    """Configure the root logger with a clean stream formatter.

    Parameters
    ----------
    level
        Logging level name (e.g. ``"INFO"`` or ``"DEBUG"``).
    """

    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(logging.Formatter(fmt=_FORMAT, datefmt=_DATEFMT))
    root.addHandler(handler)
    root.setLevel(level.upper())

