import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    import polars as pl

    return mo, pl


@app.cell
def _(mo):
    mo.md("""
    # NES-LTER deployment operating conditions

    Wind and sea state at each core-gear deployment (mean over ±10 min of the underway data).
    Generate the data with `uv run lter-operation-conditions --all`.

    Three wave measures:

    - `wave_height_m` is a **ship-motion proxy**: 4 × std of IMU heave. Only cruises with a heave column (Endeavor IMU, Sharp) have it.
    - `buoy_wave_height_m` is **NOAA NDBC significant wave height** from the nearest buoy (44097, 44008 or 44025) within 60 min. It exists for all ships but is measured at the buoy, not the ship (see `buoy_distance_km`).
    - `gfs_wave_height_m` is **NOAA GFS-Wave (WaveWatch III, 0.25°) significant wave height** at the model grid point nearest the deployment (nearest hour). The archive starts 2021-03-30, so earlier deployments are null.
    """)


@app.cell
def _(pl):
    df = pl.read_parquet("conditions.parquet")
    return (df,)


@app.cell
def _(df, mo):
    ships = mo.ui.multiselect(
        sorted(df["ship"].unique().to_list()),
        value=sorted(df["ship"].unique().to_list()),
        label="Ship",
    )
    mo.output.replace(ships)
    return (ships,)


@app.cell
def _(df, pl, ships):
    SEASONS = ["winter", "spring", "summer", "fall"]
    data = df.filter(pl.col("ship").is_in(ships.value)).with_columns(
        season=(pl.col("timestamp").dt.month() % 12 // 3).replace_strict(
            dict(enumerate(SEASONS))
        )
    )
    return SEASONS, data


@app.cell
def _(SEASONS, mo, pl):
    import plotly.graph_objects as go

    SEASON_COLORS = {
        "winter": "#4c78a8",
        "spring": "#54a24b",
        "summer": "#e8a317",
        "fall": "#b5503c",
    }
    GEAR_COLORS = ["#8e6bbf", "#2aa198", "#8a8f98", "#d17ab0"]

    def season_box(data, y, ylabel, title):
        """Per ship, one box per deployment type (colored by type) with points colored by season."""
        data = data.filter(pl.col(y).is_not_null()).sort("ship", "deployment_type")
        ships = data["ship"].unique(maintain_order=True).to_list()
        gear = sorted(data["deployment_type"].unique().to_list())
        fig = go.Figure()
        for i, g in enumerate(gear):
            sub = data.filter(pl.col("deployment_type") == g)
            color = GEAR_COLORS[i % len(GEAR_COLORS)]
            fig.add_trace(
                go.Box(
                    x=sub["ship"],
                    y=sub[y],
                    name=g,
                    offsetgroup=g,
                    boxpoints=False,
                    fillcolor=color,
                    opacity=0.45,
                    line={"color": color},
                    legendgroup="gear",
                    legendgrouptitle_text="Deployment type",
                )
            )
        shown = set()
        for g in gear:
            for season in SEASONS:
                sub = data.filter(
                    (pl.col("deployment_type") == g) & (pl.col("season") == season)
                )
                if sub.is_empty():
                    continue
                fig.add_trace(
                    go.Box(
                        x=sub["ship"],
                        y=sub[y],
                        name=season,
                        offsetgroup=g,
                        boxpoints="all",
                        jitter=0.6,
                        pointpos=0,
                        fillcolor="rgba(0,0,0,0)",
                        line={"color": "rgba(0,0,0,0)"},
                        marker={"color": SEASON_COLORS[season], "opacity": 0.85},
                        hoveron="points",
                        hovertext=[
                            f"{g}<br>{c} {t:%Y-%m-%d %H:%M}<br>station {st}"
                            for c, t, st in sub.select(
                                "cruise", "timestamp", "nearest_station"
                            ).iter_rows()
                        ],
                        legendgroup="season",
                        legendgrouptitle_text="Season",
                        showlegend=season not in shown,
                    )
                )
                shown.add(season)
        fig.update_layout(
            boxmode="group",
            title=title,
            xaxis={"title": "Ship", "categoryorder": "array", "categoryarray": ships},
            yaxis_title=ylabel,
        )
        return mo.ui.plotly(fig)

    return (season_box,)


@app.cell
def _():
    METRICS = {
        "wind_speed_m_s": "Wind speed (m/s)",
        "wave_height_m": "Wave height, heave proxy (m)",
        "buoy_wave_height_m": "NDBC buoy wave height (m)",
        "gfs_wave_height_m": "GFS-Wave wave height (m)",
    }
    return (METRICS,)


@app.cell
def _(METRICS, data, mo, season_box):
    mo.vstack(
        [
            season_box(data, col, label, f"{label} by ship and deployment type")
            for col, label in METRICS.items()
        ]
    )


@app.cell
def _(data, pl):
    data.group_by("ship", "deployment_type").agg(
        pl.len().alias("n"),
        *[
            agg
            for col in ("wind_speed_m_s", "gfs_wave_height_m")
            for agg in (
                pl.col(col).median().round(1).alias(f"{col}_median"),
                pl.col(col).quantile(0.95).round(1).alias(f"{col}_p95"),
                pl.col(col).max().round(1).alias(f"{col}_max"),
            )
        ],
    ).sort("ship", "deployment_type")


if __name__ == "__main__":
    app.run()
