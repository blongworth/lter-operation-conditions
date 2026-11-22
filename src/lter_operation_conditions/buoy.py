"""Significant wave height from NOAA NDBC buoys (standard meteorological data)."""

import calendar
import datetime as dt
import functools
import gzip

import httpx
import polars as pl

from lter_operation_conditions.stations import haversine_km

NDBC = "https://www.ndbc.noaa.gov/data"

# buoys around the NES shelf: id -> (lat, lon)
BUOYS: dict[str, tuple[float, float]] = {
    "44097": (40.967, -71.126),  # Block Island
    "44008": (40.504, -69.248),  # Nantucket
    "44025": (40.251, -73.164),  # Long Island
}
MAX_GAP = dt.timedelta(minutes=60)

SCHEMA = {"time": pl.Datetime("ms", "UTC"), "wvht": pl.Float64}


def _get(url: str) -> str | None:
    resp = httpx.get(url, timeout=60, follow_redirects=True)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    content = resp.content
    return (gzip.decompress(content) if url.endswith(".gz") else content).decode()


def _parse(text: str) -> pl.DataFrame:
    """Parse an NDBC stdmet text file into (time UTC, wvht m); missing values (99.0 / MM) are dropped."""
    lines = text.splitlines()
    header = lines[0].lstrip("#").split()
    rows = []
    for line in lines[2:]:
        rec = dict(zip(header, line.split(), strict=False))
        try:
            year = int(rec[header[0]])
            year += 2000 if year < 100 else 0
            wvht = float(rec["WVHT"])
            time = dt.datetime(
                year,
                int(rec["MM"]),
                int(rec["DD"]),
                int(rec["hh"]),
                int(rec.get("mm", 0)),
                tzinfo=dt.UTC,
            )
        except KeyError, ValueError:
            continue  # "MM" (missing) or malformed rows
        if wvht < 90:
            rows.append((time, wvht))
    return pl.DataFrame(rows, schema=SCHEMA, orient="row")


@functools.cache
def _historical(buoy: str, year: int) -> pl.DataFrame | None:
    text = _get(f"{NDBC}/historical/stdmet/{buoy}h{year}.txt.gz")
    return None if text is None else _parse(text)


@functools.cache
def _recent(buoy: str, year: int, month: int) -> pl.DataFrame:
    """Monthly file, else the realtime file (last 45 days); empty if none covers the month."""
    mon = f"{NDBC}/stdmet/{calendar.month_abbr[month]}"
    text = (
        _get(f"{mon}/{buoy}{month}{year}.txt.gz")  # completed month of the current year
        or _get(f"{mon}/{buoy}.txt")  # most recent month
        or _get(f"{NDBC}/realtime2/{buoy}.txt")
    )
    if text is None:
        return pl.DataFrame(schema=SCHEMA)
    return _parse(text).filter(
        (pl.col("time").dt.year() == year) & (pl.col("time").dt.month() == month)
    )


def _month(buoy: str, year: int, month: int) -> pl.DataFrame:
    """Wave heights for one buoy-month, preferring the yearly historical file once NDBC has published it."""
    hist = _historical(buoy, year)
    if hist is not None:
        return hist.filter(pl.col("time").dt.month() == month)
    return _recent(buoy, year, month)


def wave_height(
    lat: float | None, lon: float | None, time: dt.datetime
) -> tuple[str | None, float | None, float | None]:
    """(buoy, distance_km, Hs m) from the nearest buoy with a wave observation within MAX_GAP of `time`."""
    if lat is None or lon is None:
        return None, None, None
    for buoy, (blat, blon) in sorted(
        BUOYS.items(), key=lambda b: haversine_km(lat, lon, *b[1])
    ):
        data = _month(buoy, time.year, time.month)
        near = data.filter((pl.col("time") - time).abs() <= MAX_GAP)
        if not near.is_empty():
            best = near.sort((pl.col("time") - time).abs()).row(0, named=True)
            return buoy, haversine_km(lat, lon, blat, blon), best["wvht"]
    return None, None, None
