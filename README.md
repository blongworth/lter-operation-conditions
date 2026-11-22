# lter-operation-conditions

Wind and sea state at every core-gear deployment (CTD, bongo, Isaacs-Kidd, Sting Ray) on NES-LTER cruises.

## Usage

```sh
uv sync
uv run lter-operation-conditions en715            # one or more cruises
uv run lter-operation-conditions --all            # every NES-LTER cruise
uv run lter-operation-conditions --all --no-gfs   # skip the (slow) GFS-Wave lookup
uv run lter-operation-conditions en715 --csv      # also write conditions.csv
uv run marimo edit notebooks/conditions.py        # plots and summary table
```

Output: `conditions.parquet`, one row per deployment.

## Data sources

- **Deployments, ship underway data, stations**: [NES-LTER API v3](https://nes-lter-api.whoi.edu/api/v3/docs). Deployments are elog events with action `deploy` or `deploy towed`.
- **Wind**: underway `true_wind_speed` (m/s) and `true_wind_direction` (degrees, direction the wind comes from). The API harmonizes these across vessels. Values are means over ±10 min of the deployment time, with a vector mean for direction.
- **Wave height**, three independent estimates:
  - `wave_height_m`: a ship-motion proxy, 4 × std of IMU heave over ±10 min. Only available where the underway data has a heave column (Endeavor IMU, Sharp).
  - `buoy_wave_height_m`: NOAA NDBC significant wave height from the nearest of buoys 44097, 44008 and 44025, taken from the observation nearest in time within 60 min. It is measured at the buoy, not the ship (see `buoy_distance_km`).
  - `gfs_wave_height_m` (plus period and direction): NOAA GFS-Wave (WaveWatch III, 0.25°) at the grid point nearest the deployment, for the nearest whole hour. The archive starts 2021-03-30, so earlier deployments are null.

## Output columns

| column | units | notes |
|---|---|---|
| `timestamp` | UTC | elog event time |
| `cruise`, `ship` | | cruise names are lowercase, as in API v3 |
| `latitude`, `longitude` | degrees | elog position |
| `nearest_station`, `station_distance_km` | km | nearest NES-LTER station valid at the deployment time |
| `deployment_type` | | elog instrument |
| `wind_speed_m_s`, `wind_direction_deg` | m/s, degrees | null if fewer than 3 samples in the window |
| `wave_height_m` | m | heave proxy |
| `buoy_wave_height_m`, `buoy_station`, `buoy_distance_km` | m, km | NDBC |
| `gfs_valid_time`, `gfs_grid_distance_km`, `gfs_wave_height_m`, `gfs_wave_period_s`, `gfs_wave_direction_deg` | UTC, km, m, s, degrees | GFS-Wave; absent with `--no-gfs` |
