"""Time-series Arrow / Parquet helpers.

All conversions are pure: no I/O. The processor decides where the
resulting bytes are stored.
"""

from __future__ import annotations

import io

import pyarrow as pa
import pyarrow.parquet as pq

from runllm.garmin.models import GarminTimeSeries

_SCHEMA = pa.schema(
    [
        ("timestamp", pa.timestamp("ms", tz="UTC")),
        ("lat", pa.float64()),
        ("lon", pa.float64()),
        ("elevation", pa.float32()),
        ("heart_rate", pa.uint8()),
        ("cadence", pa.uint8()),
        ("speed", pa.float32()),
    ]
)


def timeseries_to_arrow(ts: GarminTimeSeries) -> pa.Table:
    """Build a typed :class:`pyarrow.Table` from a Garmin time-series."""

    columns: dict[str, list[object]] = {name: [] for name in _SCHEMA.names}
    for sample in ts.samples:
        columns["timestamp"].append(sample.timestamp)
        columns["lat"].append(sample.lat)
        columns["lon"].append(sample.lon)
        columns["elevation"].append(sample.elevation)
        columns["heart_rate"].append(_clip_uint8(sample.heart_rate))
        columns["cadence"].append(_clip_uint8(sample.cadence))
        columns["speed"].append(sample.speed)

    arrays = [
        pa.array(columns[name], type=field.type)
        for name, field in zip(_SCHEMA.names, _SCHEMA, strict=True)
    ]
    return pa.Table.from_arrays(arrays, schema=_SCHEMA)


def arrow_to_parquet_bytes(table: pa.Table) -> bytes:
    """Serialize a Table to Parquet bytes with Snappy compression."""

    buf = io.BytesIO()
    pq.write_table(table, buf, compression="snappy")  # type: ignore[no-untyped-call]
    return buf.getvalue()


def parquet_bytes_to_arrow(data: bytes) -> pa.Table:
    """Deserialize Parquet bytes back to an Arrow Table."""

    return pq.read_table(io.BytesIO(data))  # type: ignore[no-untyped-call]


def _clip_uint8(value: int | None) -> int | None:
    if value is None:
        return None
    if value < 0:
        return 0
    if value > 255:
        return 255
    return value
