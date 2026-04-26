"""Tests for time-series Arrow / Parquet helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from runllm.garmin.models import GarminTimeSeries, GarminTimeSeriesSample
from runllm.processing.timeseries import (
    arrow_to_parquet_bytes,
    parquet_bytes_to_arrow,
    timeseries_to_arrow,
)


def _make_series(n: int = 5) -> GarminTimeSeries:
    base = datetime(2026, 4, 10, 7, 30, tzinfo=UTC)
    samples = [
        GarminTimeSeriesSample(
            timestamp=base + timedelta(seconds=i),
            lat=41.0 + i * 0.0001,
            lon=2.0 + i * 0.0001,
            elevation=10.0 + i,
            heart_rate=130 + i,
            cadence=170 + i,
            speed=3.0 + 0.1 * i,
        )
        for i in range(n)
    ]
    return GarminTimeSeries(activity_id="1001", samples=samples)


def test_arrow_table_has_expected_schema() -> None:
    table = timeseries_to_arrow(_make_series())
    names = table.column_names
    assert names == [
        "timestamp",
        "lat",
        "lon",
        "elevation",
        "heart_rate",
        "cadence",
        "speed",
    ]
    assert table.num_rows == 5


def test_parquet_roundtrip_preserves_data() -> None:
    series = _make_series()
    table = timeseries_to_arrow(series)
    blob = arrow_to_parquet_bytes(table)
    back = parquet_bytes_to_arrow(blob)
    assert back.num_rows == table.num_rows
    assert back.column_names == table.column_names
    assert back.column("heart_rate").to_pylist() == [130, 131, 132, 133, 134]


def test_uint8_clipping_handles_out_of_range_values() -> None:
    samples = [
        GarminTimeSeriesSample(
            timestamp=datetime(2026, 4, 10, 7, 30, tzinfo=UTC),
            heart_rate=999,
            cadence=-5,
        )
    ]
    table = timeseries_to_arrow(GarminTimeSeries(activity_id="x", samples=samples))
    assert table.column("heart_rate").to_pylist() == [255]
    assert table.column("cadence").to_pylist() == [0]


def test_empty_series_produces_empty_table() -> None:
    table = timeseries_to_arrow(GarminTimeSeries(activity_id="x"))
    assert table.num_rows == 0
