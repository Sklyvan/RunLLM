"""Health endpoints for liveness and readiness probes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, status
from sqlalchemy import text

from runllm.db import get_engine

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/healthz", status_code=status.HTTP_200_OK)
async def liveness() -> dict[str, str]:
    """Simple liveness probe."""

    return {"status": "ok"}


@router.get("/readyz")
async def readiness() -> dict[str, str]:
    """Readiness probe — checks the database is reachable."""

    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as exc:
        logger.warning("readiness check failed: %s", exc)
        return {"status": "degraded"}
