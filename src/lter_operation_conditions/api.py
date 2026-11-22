"""Thin client for the NES-LTER API v3 (https://nes-lter-api.whoi.edu/api/v3/docs)."""

import functools
import io

import httpx
import polars as pl

BASE_URL = "https://nes-lter-api.whoi.edu/api/v3"
UNDERWAY_VARIABLES = (
    "true_wind_speed",  # m/s, harmonized across vessels
    "true_wind_direction",  # degrees, direction the wind comes from
    "imu_spatialdual_heave",  # m, Endeavor IMU
    "heave_m",  # m, Sharp
)


def _get(path: str, **params) -> httpx.Response:
    resp = httpx.get(f"{BASE_URL}/{path}", params=params, timeout=300)
    resp.raise_for_status()
    return resp


def _data(dataset: str, cruises: list[str], **params) -> pl.DataFrame:
    """Rows of a /data dataset for `cruises`, fetched in one request."""
    resp = _get(f"data/{dataset}", cruise=",".join(cruises), format="parquet", **params)
    return pl.read_parquet(io.BytesIO(resp.content))


@functools.cache
def cruises(cruise_type: str | None = "NES-LTER") -> pl.DataFrame:
    """Cruise catalog with the vessel's full name in `ship`."""
    params = {} if cruise_type is None else {"type": cruise_type}
    vessels = pl.DataFrame(_get("vessels").json()["vessels"])
    return (
        pl.DataFrame(_get("cruises", **params).json()["cruises"])
        .drop("datasets")
        .join(vessels.select("vessel", ship="name"), on="vessel", how="left")
    )


@functools.cache
def stations() -> pl.DataFrame:
    """Standard stations with positions and validity times (null `valid_to` = current)."""
    return pl.DataFrame(_get("stations").json()["stations"]).with_columns(
        pl.col("valid_from", "valid_to").str.to_datetime(time_zone="UTC")
    )


def events(cruises: list[str]) -> pl.DataFrame:
    """Elog events."""
    return _data("events", cruises)


def underway(cruises: list[str]) -> pl.DataFrame:
    """Underway wind and heave."""
    return _data("underway", cruises, variables=",".join(UNDERWAY_VARIABLES))
