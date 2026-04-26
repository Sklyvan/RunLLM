"""Garmin integration package."""

from runllm.garmin.exceptions import (
    GarminApiError,
    GarminAuthError,
    GarminError,
    GarminMfaRequiredError,
)
from runllm.garmin.interface import GarminClientProtocol
from runllm.garmin.models import (
    GarminActivityDetails,
    GarminActivitySummary,
    GarminAuthTokens,
    GarminSplit,
    GarminTimeSeries,
    GarminTimeSeriesSample,
)

__all__ = [
    "GarminActivityDetails",
    "GarminActivitySummary",
    "GarminApiError",
    "GarminAuthError",
    "GarminAuthTokens",
    "GarminClientProtocol",
    "GarminError",
    "GarminMfaRequiredError",
    "GarminSplit",
    "GarminTimeSeries",
    "GarminTimeSeriesSample",
]
