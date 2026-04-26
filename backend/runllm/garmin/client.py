"""Concrete Garmin client backed by the unofficial ``garminconnect`` lib.

The library is synchronous and may break with upstream changes; we
isolate it behind :class:`GarminClientProtocol` and run blocking calls
in a thread pool via :func:`asyncio.to_thread`.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, cast

from runllm.garmin.exceptions import GarminApiError, GarminAuthError, GarminMfaRequiredError
from runllm.garmin.models import (
    GarminActivityDetails,
    GarminActivitySummary,
    GarminAuthTokens,
    GarminSplit,
    GarminTimeSeries,
    GarminTimeSeriesSample,
)

logger = logging.getLogger(__name__)


class GarminClient:
    """Async wrapper around ``garminconnect.Garmin``.

    The constructor accepts an optional factory so tests can inject a
    fake. The default factory imports the real library lazily — that
    keeps the import cost out of cold paths and makes it trivial to
    mock with ``monkeypatch``.
    """

    def __init__(self, garmin_factory: Any = None) -> None:
        self._garmin_factory = garmin_factory or _default_factory
        self._client: Any | None = None
        self._mfa_state: Any | None = None

    async def login(self, email: str, password: str) -> GarminAuthTokens:
        """Authenticate; raise :class:`GarminMfaRequiredError` on 2FA."""

        def _do_login() -> tuple[Any, Any]:
            client = self._garmin_factory(email, password)
            try:
                result = client.login()
            except Exception as exc:  # pragma: no cover - depends on lib internals
                self._raise_auth(exc)
            return client, result

        client, result = await asyncio.to_thread(_do_login)
        self._client = client

        if _is_mfa_pending(result):
            self._mfa_state = result
            raise GarminMfaRequiredError(state=result)

        return _extract_tokens(client)

    async def submit_mfa(self, code: str) -> GarminAuthTokens:
        """Resume a 2FA-pending login by submitting the MFA code."""

        if self._client is None or self._mfa_state is None:
            raise GarminAuthError("no MFA flow in progress")

        client = self._client
        state = self._mfa_state

        def _do_resume() -> None:
            try:
                client.resume_login(state, code)
            except Exception as exc:  # pragma: no cover - depends on lib
                self._raise_auth(exc)

        await asyncio.to_thread(_do_resume)
        self._mfa_state = None
        return _extract_tokens(client)

    async def restore_session(self, tokens: GarminAuthTokens) -> bool:
        """Restore tokens; return ``True`` if Garmin still accepts them."""

        def _do_restore() -> bool:
            try:
                client = self._garmin_factory(None, None)
                _apply_tokens(client, tokens)
                client.get_user_summary()  # cheap call to verify auth
                self._client = client
                return True
            except Exception:  # pragma: no cover - defensive
                return False

        return await asyncio.to_thread(_do_restore)

    async def list_activities(
        self,
        start: datetime,
        end: datetime,
        limit: int = 200,
    ) -> list[GarminActivitySummary]:
        client = self._require_client()

        def _do_list() -> list[dict[str, Any]]:
            try:
                return cast(
                    list[dict[str, Any]],
                    client.get_activities_by_date(
                        start.date().isoformat(), end.date().isoformat(), limit=limit
                    ),
                )
            except Exception as exc:
                raise GarminApiError(f"list_activities failed: {exc}") from exc

        rows = await asyncio.to_thread(_do_list)
        return [GarminActivitySummary.model_validate(r) for r in rows]

    async def get_activity_details(self, activity_id: str) -> GarminActivityDetails:
        client = self._require_client()

        def _do() -> dict[str, Any]:
            try:
                return cast(dict[str, Any], client.get_activity(activity_id))
            except Exception as exc:
                raise GarminApiError(f"get_activity failed: {exc}") from exc

        raw = await asyncio.to_thread(_do)
        return GarminActivityDetails(activity_id=activity_id, raw=raw)

    async def get_activity_splits(self, activity_id: str) -> list[GarminSplit]:
        client = self._require_client()

        def _do() -> list[dict[str, Any]]:
            try:
                payload = client.get_activity_splits(activity_id)
            except Exception as exc:
                raise GarminApiError(f"get_activity_splits failed: {exc}") from exc
            return cast(list[dict[str, Any]], payload.get("lapDTOs", []))

        rows = await asyncio.to_thread(_do)
        return [_split_from_lap(i, lap) for i, lap in enumerate(rows)]

    async def get_activity_timeseries(self, activity_id: str) -> GarminTimeSeries:
        client = self._require_client()

        def _do() -> dict[str, Any]:
            try:
                return cast(dict[str, Any], client.get_activity_details(activity_id))
            except Exception as exc:
                raise GarminApiError(f"get_activity_timeseries failed: {exc}") from exc

        raw = await asyncio.to_thread(_do)
        samples = _samples_from_details(raw)
        return GarminTimeSeries(activity_id=activity_id, samples=samples)

    # ------------------------------------------------------------------ helpers

    def _require_client(self) -> Any:
        if self._client is None:
            raise GarminAuthError("not authenticated; call login() first")
        return self._client

    @staticmethod
    def _raise_auth(exc: Exception) -> None:
        name = type(exc).__name__.lower()
        if "mfa" in name or "2fa" in name:
            raise GarminMfaRequiredError(str(exc), state=getattr(exc, "state", None)) from exc
        raise GarminAuthError(str(exc)) from exc


def _default_factory(email: str | None, password: str | None) -> Any:
    """Import ``garminconnect`` lazily and return a ``Garmin`` instance."""

    from garminconnect import Garmin

    return Garmin(email, password)


def _is_mfa_pending(result: Any) -> bool:
    if isinstance(result, tuple) and len(result) == 2:
        first = result[0]
        return bool(first) and "mfa" in str(first).lower()
    return False


def _extract_tokens(client: Any) -> GarminAuthTokens:
    raw = getattr(client, "garth", None)
    if raw is None:
        return GarminAuthTokens()
    dump = getattr(raw, "dumps", None)
    if callable(dump):
        return GarminAuthTokens(data={"garth": dump()})
    return GarminAuthTokens(data={})


def _apply_tokens(client: Any, tokens: GarminAuthTokens) -> None:
    garth = getattr(client, "garth", None)
    payload = tokens.data.get("garth")
    if garth is not None and payload and hasattr(garth, "loads"):
        garth.loads(payload)


def _split_from_lap(index: int, lap: dict[str, Any]) -> GarminSplit:
    return GarminSplit(
        index=index,
        distance_meters=float(lap.get("distance", 0.0)),
        duration_seconds=float(lap.get("duration", 0.0)),
        avg_pace_seconds_per_km=lap.get("averagePaceSecondsPerKm"),
        avg_hr=lap.get("averageHR"),
        elevation_gain_meters=lap.get("elevationGain"),
    )


def _samples_from_details(payload: dict[str, Any]) -> list[GarminTimeSeriesSample]:
    metrics = payload.get("activityDetailMetrics") or []
    samples: list[GarminTimeSeriesSample] = []
    for entry in metrics:
        ts_raw = entry.get("timestamp")
        if ts_raw is None:
            continue
        ts = ts_raw if isinstance(ts_raw, datetime) else datetime.fromisoformat(str(ts_raw))
        samples.append(
            GarminTimeSeriesSample(
                timestamp=ts,
                lat=entry.get("lat"),
                lon=entry.get("lon"),
                elevation=entry.get("elevation"),
                heart_rate=entry.get("heartRate"),
                cadence=entry.get("cadence"),
                speed=entry.get("speed"),
            )
        )
    return samples
