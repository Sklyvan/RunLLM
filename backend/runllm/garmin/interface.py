"""Abstract Garmin client protocol.

Concrete implementations live alongside this module (real one in
``client.py``, fakes in tests). The protocol exists so the rest of the
codebase never imports the unofficial ``garminconnect`` library
directly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from runllm.garmin.models import (
    GarminActivityDetails,
    GarminActivitySummary,
    GarminAuthTokens,
    GarminSplit,
    GarminTimeSeries,
)


@runtime_checkable
class GarminClientProtocol(Protocol):
    """Minimum surface required to drive the activity pipeline."""

    async def login(self, email: str, password: str) -> GarminAuthTokens:
        """Authenticate with email and password.

        Raises
        ------
        GarminMfaRequiredError
            If the account has 2FA enabled. Caller must follow up with
            :meth:`submit_mfa`.
        GarminAuthError
            For any other authentication failure.
        """

    async def submit_mfa(self, code: str) -> GarminAuthTokens:
        """Complete an MFA-pending login with the user-supplied code."""

    async def restore_session(self, tokens: GarminAuthTokens) -> bool:
        """Reuse cached tokens; return ``True`` if the session is alive."""

    async def list_activities(
        self,
        start: datetime,
        end: datetime,
        limit: int = 200,
    ) -> list[GarminActivitySummary]:
        """List activities in the given date range."""

    async def get_activity_details(self, activity_id: str) -> GarminActivityDetails:
        """Fetch the full summary blob for an activity."""

    async def get_activity_splits(self, activity_id: str) -> list[GarminSplit]:
        """Fetch per-km/mile splits for an activity."""

    async def get_activity_timeseries(self, activity_id: str) -> GarminTimeSeries:
        """Fetch the per-second time-series for an activity."""
