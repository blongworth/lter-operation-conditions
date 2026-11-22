"""Nearest standard station lookup."""

import datetime as dt
import math

import polars as pl

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (
        math.sin((p2 - p1) / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def nearest(
    stations: pl.DataFrame, lat: float | None, lon: float | None, time: dt.datetime
) -> tuple[str | None, float | None]:
    """Nearest station valid at `time` as (name, distance_km); (None, None) without a position."""
    if lat is None or lon is None:
        return None, None
    valid = stations.filter(
        (pl.col("valid_from") <= time)
        & (pl.col("valid_to").is_null() | (pl.col("valid_to") >= time))
    )
    best: tuple[str | None, float | None] = (None, None)
    for station, slat, slon in valid.select(
        "station", "latitude", "longitude"
    ).iter_rows():
        d = haversine_km(lat, lon, slat, slon)
        if best[1] is None or d < best[1]:
            best = (station, d)
    return best
