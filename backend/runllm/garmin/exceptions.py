"""Custom exception hierarchy for the Garmin integration."""

from __future__ import annotations


class GarminError(Exception):
    """Base class for any Garmin-related failure."""


class GarminAuthError(GarminError):
    """Authentication with Garmin Connect failed."""


class GarminMfaRequiredError(GarminAuthError):
    """Login requires a multi-factor code from the user.

    The carrier object holds whatever opaque state the underlying
    library needs to resume login once the code is provided.
    """

    def __init__(self, message: str = "MFA required", *, state: object | None = None) -> None:
        super().__init__(message)
        self.state = state


class GarminApiError(GarminError):
    """Garmin returned an unexpected response or an HTTP error."""
