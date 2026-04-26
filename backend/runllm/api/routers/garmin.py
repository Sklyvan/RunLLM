"""Garmin-related endpoints: credentials, MFA, sync, status."""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from runllm.api.auth import get_current_user
from runllm.api.dependencies import get_garmin_service, get_processor_factory
from runllm.garmin.exceptions import GarminAuthError, GarminMfaRequiredError
from runllm.garmin.service import GarminService
from runllm.models import User
from runllm.processing.processor import ProcessingReport

router = APIRouter(prefix="/garmin", tags=["garmin"])
logger = logging.getLogger(__name__)

SYNC_TIMEOUT_SECONDS = 300
DEFAULT_LOOKBACK_DAYS = 365


class CredentialsBody(BaseModel):
    email: EmailStr
    password: str


class MfaBody(BaseModel):
    code: str


class StatusResponse(BaseModel):
    has_credentials: bool
    last_sync_at: str | None
    activity_count: int


class SyncReportResponse(BaseModel):
    created: int
    skipped: int
    failed: int
    errors: list[tuple[str, str]]


@router.post("/credentials")
async def submit_credentials(
    body: CredentialsBody,
    user: Annotated[User, Depends(get_current_user)],
    garmin: Annotated[GarminService, Depends(get_garmin_service)],
) -> dict[str, str]:
    try:
        result = await garmin.authenticate_user(user.id, str(body.email), body.password)
    except GarminAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return {"status": result.status}


@router.post("/mfa")
async def submit_mfa(
    body: MfaBody,
    user: Annotated[User, Depends(get_current_user)],
    garmin: Annotated[GarminService, Depends(get_garmin_service)],
) -> dict[str, str]:
    try:
        result = await garmin.submit_mfa(user.id, body.code)
    except GarminAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return {"status": result.status}


@router.post("/sync", response_model=SyncReportResponse)
async def sync(
    user: Annotated[User, Depends(get_current_user)],
    garmin: Annotated[GarminService, Depends(get_garmin_service)],
    processor_factory: Annotated[object, Depends(get_processor_factory)],
) -> SyncReportResponse:
    from datetime import UTC, datetime, timedelta

    since = user.garmin_last_sync_at or (
        datetime.now(tz=UTC) - timedelta(days=DEFAULT_LOOKBACK_DAYS)
    )

    try:
        summaries = await asyncio.wait_for(
            garmin.fetch_activities_since(user.id, since), timeout=SYNC_TIMEOUT_SECONDS
        )
    except GarminMfaRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="mfa_required") from exc
    except GarminAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="garmin sync timed out",
        ) from exc

    processor = processor_factory()  # type: ignore[operator]
    report: ProcessingReport = await processor.process_batch(user.id, summaries)
    return SyncReportResponse(
        created=report.created,
        skipped=report.skipped,
        failed=report.failed,
        errors=report.errors,
    )


@router.get("/status", response_model=StatusResponse)
async def get_status(
    user: Annotated[User, Depends(get_current_user)],
) -> StatusResponse:
    from sqlalchemy import func, select

    from runllm.db import get_session_factory
    from runllm.models import Activity

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(func.count())
            .select_from(Activity)
            .where(Activity.user_id == user.id)  # type: ignore[arg-type]
        )
        count = int(result.scalar_one())

    return StatusResponse(
        has_credentials=user.garmin_credentials_encrypted is not None,
        last_sync_at=user.garmin_last_sync_at.isoformat() if user.garmin_last_sync_at else None,
        activity_count=count,
    )
