"""Build the deployment operating-conditions table for one or more cruises."""

import datetime as dt

import polars as pl

from lter_operation_conditions import api, buoy, stations, underway

# core gear, matched case-insensitively as instrument prefixes
CORE_GEAR = ("ctd", "bongo", "isaacs-kidd", "sting ray")
DEPLOY_ACTIONS = ("deploy", "deploy towed")

OUTPUT_SCHEMA = {
    "timestamp": pl.Datetime("us", "UTC"),
    "cruise": pl.String,
    "ship": pl.String,
    "latitude": pl.Float64,
    "longitude": pl.Float64,
    "nearest_station": pl.String,
    "station_distance_km": pl.Float64,
    "deployment_type": pl.String,
    "wind_speed_m_s": pl.Float64,
    "wind_direction_deg": pl.Float64,
    "wave_height_m": pl.Float64,
    "buoy_wave_height_m": pl.Float64,
    "buoy_station": pl.String,
    "buoy_distance_km": pl.Float64,
}


def core_deployments(events: pl.DataFrame) -> pl.DataFrame:
    mask = pl.any_horizontal(
        *[pl.col("instrument").str.to_lowercase().str.starts_with(g) for g in CORE_GEAR]
    )
    return events.filter(mask & pl.col("action").is_in(DEPLOY_ACTIONS)).sort("time")


def conditions(
    cruises: list[str], half_window: dt.timedelta = dt.timedelta(minutes=10)
) -> pl.DataFrame:
    """One row per core-gear deployment in the cruises' elogs with wind and wave conditions."""
    catalog = api.cruises(cruise_type=None)
    unknown = set(cruises) - set(catalog["cruise"])
    if unknown:
        raise ValueError(f"unknown cruise(s): {', '.join(sorted(unknown))}")
    ships = dict(catalog.select("cruise", "ship").iter_rows())

    deploys = core_deployments(api.events(cruises))
    raw = api.underway(cruises)
    stn = api.stations()

    rows = []
    for cruise in cruises:
        ts = underway.prepare(raw.filter(pl.col("cruise") == cruise))
        for ev in deploys.filter(pl.col("cruise") == cruise).iter_rows(named=True):
            lat, lon, time = ev["latitude"], ev["longitude"], ev["time"]
            name, dist = stations.nearest(stn, lat, lon, time)
            buoy_id, buoy_km, buoy_hs = buoy.wave_height(lat, lon, time)
            rows.append(
                {
                    "timestamp": time,
                    "cruise": cruise,
                    "ship": ships[cruise],
                    "latitude": lat,
                    "longitude": lon,
                    "nearest_station": name,
                    "station_distance_km": dist,
                    "deployment_type": ev["instrument"],
                    **underway.conditions(ts, time, half_window),
                    "buoy_wave_height_m": buoy_hs,
                    "buoy_station": buoy_id,
                    "buoy_distance_km": buoy_km,
                }
            )
    return pl.DataFrame(rows, schema=OUTPUT_SCHEMA)
