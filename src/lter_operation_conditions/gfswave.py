"""NOAA GFS-Wave (WaveWatch III, 0.25 deg) wave conditions at deployment locations.

Reads the public NOAA GFS archive on AWS (https://registry.opendata.aws/noaa-gfs-bdp-pds/),
which holds GFS-Wave from 2021-03-30. For each deployment only the three needed GRIB
messages (HTSGW, PERPW, DIRPW) are fetched with HTTP range requests, and only the grid
point nearest the ship is kept.
"""

import datetime as dt
from concurrent.futures import ThreadPoolExecutor

import eccodes
import httpx
import polars as pl

BASE = "https://noaa-gfs-bdp-pds.s3.amazonaws.com"
CYCLE_HOURS = 6
# GRIB short name in the .idx file -> output column
FIELDS = {
    "HTSGW": "gfs_wave_height_m",
    "PERPW": "gfs_wave_period_s",
    "DIRPW": "gfs_wave_direction_deg",
}
MISSING = 9e3  # eccodes returns 9999 for masked (land) points
KEYS = ["cruise", "timestamp", "latitude", "longitude"]

SCHEMA = {
    "gfs_valid_time": pl.Datetime("ms", "UTC"),
    "gfs_grid_distance_km": pl.Float64,
    **{col: pl.Float64 for col in FIELDS.values()},
}


def _url(valid: dt.datetime) -> str:
    """GFS-Wave file whose analysis or short forecast is valid at the (whole-hour) `valid` time."""
    cycle = valid.replace(hour=valid.hour // CYCLE_HOURS * CYCLE_HOURS)
    fhr = valid.hour - cycle.hour
    return (
        f"{BASE}/gfs.{cycle:%Y%m%d}/{cycle:%H}/wave/gridded/"
        f"gfswave.t{cycle:%H}z.global.0p25.f{fhr:03d}.grib2"
    )


def _sample(url: str, points: list[tuple[float, float]]) -> list[dict] | None:
    """Nearest-grid-point values at (lat, lon) `points` from one GFS-Wave file; None if the file is not archived."""
    resp = httpx.get(f"{url}.idx", timeout=60)
    if resp.status_code in (403, 404):
        return None
    resp.raise_for_status()
    idx = [line.split(":") for line in resp.text.splitlines()]
    out = [{} for _ in points]
    for i, (_, start, _, name, *_) in enumerate(idx):
        if name not in FIELDS:
            continue
        end = int(idx[i + 1][1]) - 1 if i + 1 < len(idx) else ""
        msg = httpx.get(
            url, headers={"Range": f"bytes={start}-{end}"}, timeout=120
        ).content
        handle = eccodes.codes_new_from_message(msg)
        try:
            for rec, (lat, lon) in zip(out, points, strict=True):
                near = eccodes.codes_grib_find_nearest(handle, lat, lon % 360)[0]
                rec[FIELDS[name]] = None if near.value >= MISSING else near.value
                rec["gfs_grid_distance_km"] = near.distance
        finally:
            eccodes.codes_release(handle)
    return out


def compile_wave(deployments: pl.DataFrame) -> pl.DataFrame:
    """GFS-Wave Hs, peak period and direction at each deployment, keyed by cruise/timestamp/lat/lon.

    Values are taken from the model file valid nearest the deployment hour. Deployments
    before the archive starts or without a position get nulls.
    """
    deployments = deployments.filter(
        pl.col("latitude").is_not_null() & pl.col("longitude").is_not_null()
    ).with_columns(
        gfs_valid_time=(pl.col("timestamp") + pl.duration(minutes=30)).dt.truncate("1h")
    )
    by_file: dict[str, list[dict]] = {}
    for row in deployments.iter_rows(named=True):
        by_file.setdefault(_url(row["gfs_valid_time"]), []).append(row)

    def run(item: tuple[str, list[dict]]) -> list[dict]:
        url, rows = item
        try:
            sampled = _sample(url, [(r["latitude"], r["longitude"]) for r in rows])
        except httpx.HTTPError as err:
            print(f"skipping {url}: {err}")
            sampled = None
        sampled = sampled or [{} for _ in rows]
        return [
            {**{k: r[k] for k in KEYS}, "gfs_valid_time": r["gfs_valid_time"], **s}
            for r, s in zip(rows, sampled, strict=True)
        ]

    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = [rec for recs in pool.map(run, by_file.items()) for rec in recs]
    key_schema = {k: deployments.schema[k] for k in KEYS}
    return pl.DataFrame(rows, schema=key_schema | SCHEMA).sort("timestamp")
