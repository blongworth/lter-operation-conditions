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

    return go, season_box


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
def _(mo):
    mo.md("""
    ## CTD upper tail by ship

    Only casts that happened are recorded (weather cancellations are not), so these
    show the conditions CTDs were done in, not hard operating limits.
    """)


@app.cell
def _(data, go, mo, pl):
    ctd = data.filter(pl.col("deployment_type") == "CTD911")
    ctd_ships = sorted(ctd["ship"].unique().to_list())
    SHIP_COLORS = dict(
        zip(
            ctd_ships,
            ["#4c78a8", "#e45756", "#54a24b", "#b279a2", "#f58518", "#72b7b2"],
        )
    )

    def exceedance(col, label):
        """Fraction of CTD casts at or above each value, per ship (log y)."""
        fig = go.Figure()
        for ship in ctd_ships:
            v = ctd.filter((pl.col("ship") == ship) & pl.col(col).is_not_null())[
                col
            ].sort(descending=True)
            n = len(v)
            if n == 0:
                continue
            fig.add_trace(
                go.Scatter(
                    x=v,
                    y=[(i + 1) / n for i in range(n)],
                    mode="lines+markers",
                    line={"shape": "hv", "color": SHIP_COLORS[ship]},
                    marker={"size": 4},
                    name=f"{ship} (n={n})",
                    hovertemplate="%{x:.1f}: %{y:.1%} of casts at or above<extra>"
                    + ship
                    + "</extra>",
                )
            )
        for p, dash in ((0.10, "dash"), (0.05, "dot")):
            fig.add_hline(
                y=p,
                line={"dash": dash, "color": "#888", "width": 1},
                annotation_text=f"p{round((1 - p) * 100)}",
                annotation_position="right",
            )
        fig.update_layout(
            title=f"CTD exceedance: {label}",
            xaxis_title=label,
            yaxis={
                "title": "Fraction of casts ≥ value",
                "type": "log",
                "tickformat": ".0%",
            },
        )
        return mo.ui.plotly(fig)

    def hull(points):
        """Convex hull (monotone chain), closed for plotting."""
        pts = sorted(set(points))
        if len(pts) < 3:
            return pts

        def cross(o, a, b):
            return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

        lower, upper = [], []
        for p in pts:
            while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
                lower.pop()
            lower.append(p)
        for p in reversed(pts):
            while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
                upper.pop()
            upper.append(p)
        h = lower[:-1] + upper[:-1]
        return h + h[:1]

    def wind_wave_scatter():
        """Wind vs GFS wave height per CTD cast, with each ship's convex-hull envelope."""
        fig = go.Figure()
        both = ctd.filter(
            pl.col("wind_speed_m_s").is_not_null()
            & pl.col("gfs_wave_height_m").is_not_null()
        )
        for ship in ctd_ships:
            sub = both.filter(pl.col("ship") == ship)
            if sub.is_empty():
                continue
            color = SHIP_COLORS[ship]
            fig.add_trace(
                go.Scatter(
                    x=sub["wind_speed_m_s"],
                    y=sub["gfs_wave_height_m"],
                    mode="markers",
                    marker={"color": color, "size": 5, "opacity": 0.6},
                    name=f"{ship} (n={len(sub)})",
                    legendgroup=ship,
                    hovertext=[
                        f"{c} {t:%Y-%m-%d %H:%M}<br>station {st}"
                        for c, t, st in sub.select(
                            "cruise", "timestamp", "nearest_station"
                        ).iter_rows()
                    ],
                )
            )
            h = hull(list(zip(sub["wind_speed_m_s"], sub["gfs_wave_height_m"])))
            fig.add_trace(
                go.Scatter(
                    x=[p[0] for p in h],
                    y=[p[1] for p in h],
                    mode="lines",
                    line={"color": color, "width": 1.5},
                    legendgroup=ship,
                    showlegend=False,
                    hoverinfo="skip",
                )
            )
        fig.update_layout(
            title="CTD casts: wind vs GFS-Wave height (since 2021-03-30)",
            xaxis_title="Wind speed (m/s)",
            yaxis_title="GFS-Wave wave height (m)",
        )
        return mo.ui.plotly(fig)

    mo.vstack(
        [
            exceedance("wind_speed_m_s", "Wind speed (m/s)"),
            exceedance("gfs_wave_height_m", "GFS-Wave wave height (m)"),
            wind_wave_scatter(),
        ]
    )


if __name__ == "__main__":
    app.run()
