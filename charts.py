"""
charts.py
---------
Phase 3: Visualizations & Charting.

Every function here takes plain data (lists, dicts, arrays) and returns
a plotly Figure. None of these touch the Spotify API or do risk math —
they only visualize numbers that risk_engine.py and spotify_client.py
already produced. That separation makes each chart easy to test on its
own with fake data.
"""

from __future__ import annotations

import numpy as np
import plotly.graph_objects as go

# Shared color palette, matching the dashboard's dark theme reference design.
COLOR_BG = "#121826"       # card background
COLOR_GRID = "#232c3d"     # gridlines / borders
COLOR_TEXT = "#e8ecf3"     # primary text
COLOR_MUTED = "#9aa6bb"    # secondary/muted text
COLOR_CORAL = "#ff6b7f"    # highlight / "below break-even" / risk
COLOR_BLUE = "#3b82a6"     # neutral bars
COLOR_TEAL = "#2dd4bf"     # accent / "above break-even" / positive
COLOR_AMBER = "#f5b455"    # reference lines / watch state
COLOR_RED = "#ef4444"      # pure-decline growth scenario
COLOR_VIOLET = "#a78bfa"   # comeback-arc growth scenario

FONT_FAMILY = "Inter, system-ui, sans-serif"

# Shared scenario -> color mapping, used by both the KPI badges in app.py
# (imported there) and the comparison chart below, so a scenario always
# reads as the same color everywhere it shows up.
SCENARIO_COLORS = {
    "No growth": COLOR_AMBER,
    "Positive growth": COLOR_TEAL,
    "Positive, then negative": COLOR_CORAL,
    "Negative growth": COLOR_RED,
    "Negative, then positive": COLOR_VIOLET,
}


def _apply_dark_theme(fig: go.Figure, **extra_layout) -> go.Figure:
    """Apply the shared dark card styling to any chart's layout."""
    fig.update_layout(
        paper_bgcolor=COLOR_BG,
        plot_bgcolor=COLOR_BG,
        font=dict(family=FONT_FAMILY, color=COLOR_TEXT, size=13),
        title_font=dict(size=16, color=COLOR_TEXT),
        xaxis=dict(gridcolor=COLOR_GRID, zerolinecolor=COLOR_GRID, color=COLOR_MUTED),
        yaxis=dict(gridcolor=COLOR_GRID, zerolinecolor=COLOR_GRID, color=COLOR_MUTED),
        margin=dict(t=56, b=40, l=48, r=24),
        **extra_layout,
    )
    return fig


def plot_top_tracks_bar(tracks: list[dict]) -> go.Figure:
    """
    Chart 1: Bar chart of top track playcounts, highlighting track #1
    against the average of tracks 2-10 (visualizes Concentration Risk).

    Parameters
    ----------
    tracks : list[dict]
        Output of lastfm_client.get_top_tracks(), each with
        {"name": str, "playcount": int}, sorted descending.

    Returns
    -------
    go.Figure
    """
    names = [t["name"] for t in tracks]
    playcounts = [t["playcount"] for t in tracks]

    # Highlight the #1 track in a different color from the rest
    colors = [COLOR_CORAL] + [COLOR_BLUE] * (len(tracks) - 1)

    avg_rest = np.mean(playcounts[1:]) if len(playcounts) > 1 else 0

    fig = go.Figure(
        data=[
            go.Bar(
                x=names,
                y=playcounts,
                marker_color=colors,
                text=[f"{p:,}" for p in playcounts],
                textposition="outside",
                textfont=dict(color=COLOR_TEXT),
            )
        ]
    )

    fig.add_hline(
        y=avg_rest,
        line_dash="dash",
        line_color=COLOR_AMBER,
        line_width=2,
        annotation_text=f"Avg tracks 2-10: {avg_rest:,.0f}",
        annotation_position="top left",
        annotation_font_color=COLOR_AMBER,
    )

    _apply_dark_theme(
        fig,
        title="One song carries the catalog",
        xaxis_title="Track",
        yaxis_title="Playcount (Last.fm)",
        showlegend=False,
    )
    return fig


def plot_monte_carlo_distribution(
    cumulative_revenue: np.ndarray, advance: float
) -> go.Figure:
    """
    Chart 2: Histogram of the 1,000 Monte Carlo revenue outcomes with a
    red break-even line at the advance amount.

    Parameters
    ----------
    cumulative_revenue : np.ndarray
        Per-simulation total revenue, from
        risk_engine.run_monte_carlo_recoupment()["cumulative_revenue"].
    advance : float
        The proposed advance amount in dollars.

    Returns
    -------
    go.Figure
    """
    # Build the histogram manually (rather than go.Histogram) so each bin
    # can be colored by whether it clears the advance — coral below
    # break-even, teal above it — matching the reference design's split.
    counts, bin_edges = np.histogram(cumulative_revenue, bins=50)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    bin_width = bin_edges[1] - bin_edges[0]
    bar_colors = [COLOR_TEAL if c >= advance else COLOR_CORAL for c in bin_centers]

    fig = go.Figure(
        data=[
            go.Bar(
                x=bin_centers,
                y=counts,
                width=bin_width * 0.95,
                marker_color=bar_colors,
                name="Simulated outcomes",
            )
        ]
    )

    fig.add_vline(
        x=advance,
        line_color=COLOR_TEXT,
        line_width=2,
        annotation_text=f"Break-even: ${advance:,.0f}",
        annotation_position="top right",
        annotation_font_color=COLOR_TEXT,
    )

    _apply_dark_theme(
        fig,
        title=f"{(cumulative_revenue >= advance).mean() * 100:.0f}% of outcomes clear the advance",
        xaxis_title="Projected Revenue ($)",
        yaxis_title="Number of Simulations",
        bargap=0.02,
        showlegend=False,
    )
    return fig


def plot_fan_loyalty_scale(listeners: int, playcount: int, flr: float) -> go.Figure:
    """
    Chart 3: Shows the Fan Loyalty Ratio (average plays per listener)
    as a bar, with the raw listeners/playcount numbers it's built from
    labeled alongside it for context.

    NOTE: this chart changed from comparing FLR against a 0-100 Spotify
    popularity score (no longer available) to instead showing FLR's own
    two raw ingredients — listeners and playcount — since there's no
    longer a second "popularity" number to compare it against. See
    risk_engine.fan_loyalty_ratio() for the formula.

    Parameters
    ----------
    listeners : int
        Unique Last.fm listeners.
    playcount : int
        Total plays across all listeners.
    flr : float
        Fan Loyalty Ratio (playcount / listeners), from
        risk_engine.fan_loyalty_ratio().

    Returns
    -------
    go.Figure
    """
    fig = go.Figure(
        data=[
            go.Bar(
                x=["Fan Loyalty Ratio<br>(avg plays per listener)"],
                y=[flr],
                marker_color=COLOR_TEAL,
                text=[f"{flr:.1f}"],
                textposition="outside",
                textfont=dict(color=COLOR_TEXT),
            )
        ]
    )

    _apply_dark_theme(
        fig,
        title="Fan Loyalty Ratio",
        yaxis_title="Avg. plays per listener",
        showlegend=False,
        annotations=[
            dict(
                text=(
                    f"{listeners:,} listeners  ·  {playcount:,} total plays"
                ),
                xref="paper", yref="paper",
                x=0.5, y=1.15,
                showarrow=False,
                font=dict(size=12, color=COLOR_MUTED),
            )
        ],
    )
    return fig


def plot_label_radar(label_scores: dict) -> go.Figure:
    """
    Chart 4: Radar chart showing how well an artist aligns with each
    label profile.

    Parameters
    ----------
    label_scores : dict
        Maps label name -> a 0-100 alignment score, e.g.
        {"Dreamville / TDE": 80, "Cactus Jack / OVO": 45}
        (Compute this in app.py from risk_engine.label_benchmark_fit(),
        e.g. 100 if fits else some partial score based on how close it is.)

    Returns
    -------
    go.Figure
    """
    labels = list(label_scores.keys())
    values = list(label_scores.values())

    # Radar charts need the first point repeated at the end to close the loop
    labels_closed = labels + [labels[0]]
    values_closed = values + [values[0]]

    fig = go.Figure(
        data=[
            go.Scatterpolar(
                r=values_closed,
                theta=labels_closed,
                fill="toself",
                marker_color=COLOR_TEAL,
                line_color=COLOR_TEAL,
                fillcolor="rgba(45, 212, 191, 0.25)",
            )
        ]
    )

    _apply_dark_theme(
        fig,
        title="Label Alignment Scorecard",
        polar=dict(
            bgcolor=COLOR_BG,
            radialaxis=dict(
                visible=True, range=[0, 100],
                gridcolor=COLOR_GRID, color=COLOR_MUTED,
            ),
            angularaxis=dict(gridcolor=COLOR_GRID, color=COLOR_MUTED),
        ),
        showlegend=False,
    )
    return fig


def plot_scenario_paths(scenario_results: dict) -> go.Figure:
    """
    Chart 5: Overlays the median simulated monthly-stream path for every
    growth scenario on one log-scale line chart, so you can see the
    shape of each trajectory side by side rather than just its final
    recoupment odds.

    Parameters
    ----------
    scenario_results : dict
        Maps scenario name -> the dict returned by
        risk_engine.run_monte_carlo_recoupment(), each containing a
        "paths" array of shape (simulations, months + 1) with monthly
        stream counts (month 0 = starting streams).

    Returns
    -------
    go.Figure
    """
    fig = go.Figure()

    for name, result in scenario_results.items():
        paths = result["paths"]
        median_path = np.median(paths, axis=0)
        months = np.arange(len(median_path))
        color = SCENARIO_COLORS.get(name, COLOR_BLUE)

        fig.add_trace(
            go.Scatter(
                x=months,
                y=median_path,
                mode="lines",
                name=name,
                line=dict(color=color, width=2.5),
            )
        )

    _apply_dark_theme(
        fig,
        title="Median projected monthly streams by scenario",
        xaxis_title="Month",
        yaxis_title="Monthly streams (log scale)",
        yaxis_type="log",
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
            font=dict(color=COLOR_TEXT, size=11),
        ),
    )
    return fig


def plot_hit_timeline(tracks: list[dict], track_years_ago: list[float | None]) -> go.Figure:
    """
    Chart 6: Scatter of each top track's playcount against how long ago
    it was released, with shaded reference bands for the "stale" and
    "recent" zones used by risk_engine.analyze_hit_timeline(). Tracks
    with no confident release-date match are left out (can't place them
    on a timeline).

    Parameters
    ----------
    tracks : list[dict]
        lastfm_client.get_top_tracks() output, {"name": str, "playcount": int}.
    track_years_ago : list[float | None]
        Years since release per track, same order as `tracks`, from
        spotify_client.get_track_release_years().

    Returns
    -------
    go.Figure
    """
    # Import here (not at module load) to avoid a hard dependency for
    # callers that only use the other charts; these thresholds mirror
    # risk_engine.py's own constants but are duplicated rather than
    # imported, to keep charts.py free of a risk_engine dependency.
    STALE_THRESHOLD_YEARS = 6.0
    RECENT_WINDOW_YEARS = 2.0

    points = [
        (t["name"], t["playcount"], years)
        for t, years in zip(tracks, track_years_ago)
        if years is not None
    ]

    if not points:
        fig = go.Figure()
        _apply_dark_theme(
            fig,
            title="Hit Timeline — no release-date data available",
            showlegend=False,
        )
        return fig

    names, playcounts, years = zip(*points)
    colors = [
        COLOR_TEAL if y <= RECENT_WINDOW_YEARS
        else COLOR_CORAL if y > STALE_THRESHOLD_YEARS
        else COLOR_BLUE
        for y in years
    ]

    fig = go.Figure(
        data=[
            go.Scatter(
                x=list(years),
                y=list(playcounts),
                mode="markers+text",
                text=list(names),
                textposition="top center",
                textfont=dict(color=COLOR_MUTED, size=10),
                marker=dict(size=14, color=colors, line=dict(width=1, color=COLOR_BG)),
            )
        ]
    )

    max_x = max(max(years), STALE_THRESHOLD_YEARS) + 0.5

    # Shade the "recent" zone (left edge, newest) and "stale" zone (right
    # edge, oldest) so the timeline's two red/green flags are visible at
    # a glance, not just inferable from dot color.
    fig.add_vrect(
        x0=-0.1, x1=RECENT_WINDOW_YEARS,
        fillcolor=COLOR_TEAL, opacity=0.08, line_width=0,
        annotation_text="Recent", annotation_position="top left",
        annotation_font_color=COLOR_TEAL,
    )
    fig.add_vrect(
        x0=STALE_THRESHOLD_YEARS, x1=max_x,
        fillcolor=COLOR_CORAL, opacity=0.08, line_width=0,
        annotation_text="Stale", annotation_position="top right",
        annotation_font_color=COLOR_CORAL,
    )

    _apply_dark_theme(
        fig,
        title="Hit Timeline — are the hits recent, or carried by old material?",
        xaxis_title="Years since release (0 = today)",
        yaxis_title="Playcount (Last.fm)",
        showlegend=False,
    )
    fig.update_xaxes(autorange="reversed")  # newest on the right, like a timeline
    return fig


if __name__ == "__main__":
    # Quick manual smoke test with fake data — writes HTML files you can
    # open in a browser to sanity-check the charts without Streamlit.
    fake_tracks = [
        {"name": f"Track {i}", "playcount": p}
        for i, p in enumerate(
            [8_800_000, 6_000_000, 5_500_000, 5_000_000, 4_800_000,
             4_500_000, 4_000_000, 3_800_000, 3_500_000, 3_000_000],
            start=1,
        )
    ]
    plot_top_tracks_bar(fake_tracks).write_html("test_chart1.html")

    fake_revenue = np.random.lognormal(mean=12.5, sigma=0.4, size=1000)
    plot_monte_carlo_distribution(fake_revenue, advance=250_000).write_html(
        "test_chart2.html"
    )

    plot_fan_loyalty_scale(
        listeners=1_200_000, playcount=18_000_000, flr=15.0
    ).write_html("test_chart3.html")

    plot_label_radar(
        {"Dreamville": 80, "Cactus Jack": 45}
    ).write_html("test_chart4.html")

    print("Wrote test_chart1.html through test_chart4.html — open them in a browser.")
