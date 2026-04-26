"""End-to-end activity processing pipeline.

For every Garmin activity we:

* skip it if we already have a row for ``(user_id, garmin_activity_id)``;
* fetch details + splits + per-second time-series;
* normalize the summary and persist a row in ``activity``;
* upload Parquet bytes for the time-series to Supabase Storage.

Errors are isolated per activity so one bad row does not abort the
batch — the caller receives a :class:`ProcessingReport`.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from runllm.garmin.interface import GarminClientProtocol
from runllm.garmin.models import GarminActivitySummary
from runllm.models import Activity
from runllm.processing.mappers import garmin_summary_to_activity_kwargs
from runllm.processing.storage import ActivityStorage
from runllm.processing.timeseries import arrow_to_parquet_bytes, timeseries_to_arrow

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], AsyncSession]


@dataclass(slots=True)
class ProcessingReport:
    """Aggregate result of processing a batch of activities."""

    created: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)


class ActivityProcessor:
    """Idempotent batch processor for Garmin activities."""

    def __init__(
        self,
        garmin: GarminClientProtocol,
        storage: ActivityStorage,
        session_factory: SessionFactory,
        *,
        concurrency: int = 4,
    ) -> None:
        self._garmin = garmin
        self._storage = storage
        self._session_factory = session_factory
        self._concurrency = concurrency

    async def process_activity(
        self, user_id: UUID, garmin_summary: GarminActivitySummary
    ) -> Activity | None:
        """Process a single activity. Returns ``None`` if already stored."""

        if await self._already_stored(user_id, garmin_summary.activity_id):
            logger.info("skipping existing activity %s", garmin_summary.activity_id)
            return None

        details = await self._garmin.get_activity_details(garmin_summary.activity_id)
        splits = await self._garmin.get_activity_splits(garmin_summary.activity_id)
        timeseries = await self._garmin.get_activity_timeseries(garmin_summary.activity_id)

        kwargs = garmin_summary_to_activity_kwargs(
            garmin_summary, user_id, details=details, splits=splits
        )
        activity = Activity(**kwargs)

        if timeseries.samples:
            table = timeseries_to_arrow(timeseries)
            parquet = arrow_to_parquet_bytes(table)
            path = await self._storage.upload_timeseries(user_id, activity.id, parquet)
            activity.timeseries_storage_path = path
            activity.has_timeseries = True

        async with self._session_factory() as session:
            session.add(activity)
            await session.commit()
        return activity

    async def process_batch(
        self, user_id: UUID, summaries: list[GarminActivitySummary]
    ) -> ProcessingReport:
        """Process a list of activities concurrently with isolated errors."""

        report = ProcessingReport()
        semaphore = asyncio.Semaphore(self._concurrency)

        async def _wrapped(summary: GarminActivitySummary) -> None:
            async with semaphore:
                try:
                    activity = await self.process_activity(user_id, summary)
                except Exception as exc:
                    logger.exception("failed to process activity %s", summary.activity_id)
                    report.failed += 1
                    report.errors.append((summary.activity_id, str(exc)))
                    return
                if activity is None:
                    report.skipped += 1
                else:
                    report.created += 1

        await asyncio.gather(*(_wrapped(s) for s in summaries))
        return report

    # ------------------------------------------------------------------ helpers

    async def _already_stored(self, user_id: UUID, garmin_activity_id: str) -> bool:
        async with self._session_factory() as session:
            result = await session.exec(
                select(Activity.id).where(
                    Activity.user_id == user_id,
                    Activity.garmin_activity_id == garmin_activity_id,
                )
            )
            return result.first() is not None
