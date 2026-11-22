"""Wind and sea-state values from the underway data around a point in time."""

import datetime as dt
import math
import statistics

import polars as pl

# Heave std -> significant wave height proxy (Hs ~ 4 * sigma for a narrow-band sea)
HS_FACTOR = 4.0
MIN_SAMPLES = 3
HEAVE_COLUMNS = ("imu_spatialdual_heave", "heave_m")


def prepare(raw: pl.DataFrame) -> pl.DataFrame:
    """Numeric time series of wind speed (m/s), wind direction (deg) and heave (m)."""
    heave = [pl.col(c) for c in HEAVE_COLUMNS if c in raw.columns]
    return raw.select(
        "time",
        # the API returns wind as strings in parquet
        wind_speed=pl.col("true_wind_speed").cast(pl.Float64, strict=False),
        wind_direction=pl.col("true_wind_direction").cast(pl.Float64, strict=False),
        heave=pl.coalesce(heave) if heave else pl.lit(None, dtype=pl.Float64),
    ).sort("time")


def _circular_mean_deg(values: list[float]) -> float:
    s = sum(math.sin(math.radians(v)) for v in values)
    c = sum(math.cos(math.radians(v)) for v in values)
    return math.degrees(math.atan2(s, c)) % 360


def conditions(
    ts: pl.DataFrame, time: dt.datetime, half_window: dt.timedelta
) -> dict[str, float | None]:
    """Mean wind (vector-mean direction) and heave-derived wave height within time +/- half_window.

    Each value is None when fewer than MIN_SAMPLES valid samples fall in the window.
    """
    win = ts.filter(pl.col("time").is_between(time - half_window, time + half_window))
    speed = win["wind_speed"].drop_nulls().to_list()
    direction = win["wind_direction"].drop_nulls().to_list()
    heave = win["heave"].drop_nulls().to_list()
    return {
        "wind_speed_m_s": statistics.fmean(speed)
        if len(speed) >= MIN_SAMPLES
        else None,
        "wind_direction_deg": _circular_mean_deg(direction)
        if len(direction) >= MIN_SAMPLES
        else None,
        "wave_height_m": HS_FACTOR * statistics.stdev(heave)
        if len(heave) >= MIN_SAMPLES
        else None,
    }
