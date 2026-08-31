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

import numpy as np
import plotly.graph_objects as go


def plot_top_tracks_bar(tracks: list[dict]) -> go.Figure:
    """
    Chart 1: Bar chart of top track popularities, highlighting track #1
    against the average of tracks 2-10 (visualizes Concentration Risk).

    Parameters
    ----------
    tracks : list[dict]
        Output of spotify_client.get_top_tracks(), each with
        {"name": str, "popularity": int, ...}, sorted descending.

    Returns
    -------
    go.Figure
    """
    names = [t["name"] for t in tracks]
    popularities = [t["popularity"] for t in tracks]

    # Highlight the #1 track in a different color from the rest
    colors = ["#E63946"] + ["#457B9D"] * (len(tracks) - 1)

    avg_rest = np.mean(popularities[1:]) if len(popularities) > 1 else 0

    fig = go.Figure(
        data=[
            go.Bar(
                x=names,
                y=popularities,
                marker_color=colors,
                text=popularities,
                textposition="outside",
            )
        ]
    )

    fig.add_hline(
        y=avg_rest,
        line_dash="dash",
        line_color="gray",
        annotation_text=f"Avg tracks 2-10: {avg_rest:.1f}",
        annotation_position="top left",
    )

    fig.update_layout(
        title="Top Track Popularity (Concentration Risk View)",
        xaxis_title="Track",
        yaxis_title="Popularity (0-100)",
        yaxis_range=[0, 105],
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
    fig = go.Figure(
        data=[
            go.Histogram(
                x=cumulative_revenue,
                nbinsx=50,
                marker_color="#457B9D",
                name="Simulated outcomes",
            )
        ]
    )

    fig.add_vline(
        x=advance,
        line_color="red",
        line_width=2,
        annotation_text=f"Break-even: ${advance:,.0f}",
        annotation_position="top right",
    )

    fig.update_layout(
        title="Monte Carlo Simulation: 24-Month Revenue Distribution",
        xaxis_title="Projected Revenue ($)",
        yaxis_title="Number of Simulations",
        bargap=0.02,
    )
    return fig


def plot_fan_loyalty_scale(flr: float, popularity: int) -> go.Figure:
    """
    Chart 3: A simple horizontal gauge-style comparison of Fan Loyalty
    Ratio against raw popularity, so a viewer can see at a glance whether
    an artist's popularity is backed by loyal followers or is more
    playlist-driven.

    Parameters
    ----------
    flr : float
        Fan Loyalty Ratio, from risk_engine.fan_loyalty_ratio().
    popularity : int
        Spotify popularity score (0-100).

    Returns
    -------
    go.Figure
    """
    # FLR is unbounded, so we cap the display scale at a sensible value
    # for visualization purposes only (doesn't affect the underlying number).
    display_flr = min(flr, 5.0)

    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            y=["Fan Loyalty Ratio"],
            x=[display_flr],
            orientation="h",
            marker_color="#2A9D8F",
            name="Fan Loyalty Ratio",
        )
    )
    fig.add_trace(
        go.Bar(
            y=["Popularity (scaled /20)"],
            x=[popularity / 20],  # scale 0-100 down to comparable 0-5 range
            orientation="h",
            marker_color="#E9C46A",
            name="Popularity (scaled)",
        )
    )

    fig.update_layout(
        title="Fan Loyalty vs. Popularity",
        xaxis_title="Relative Scale",
        barmode="group",
        showlegend=False,
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
                marker_color="#E63946",
            )
        ]
    )

    fig.update_layout(
        title="Label Alignment Scorecard",
        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
        showlegend=False,
    )
    return fig


if __name__ == "__main__":
    # Quick manual smoke test with fake data — writes HTML files you can
    # open in a browser to sanity-check the charts without Streamlit.
    fake_tracks = [
        {"name": f"Track {i}", "popularity": p}
        for i, p in enumerate(
            [88, 60, 55, 50, 48, 45, 40, 38, 35, 30], start=1
        )
    ]
    plot_top_tracks_bar(fake_tracks).write_html("test_chart1.html")

    fake_revenue = np.random.lognormal(mean=12.5, sigma=0.4, size=1000)
    plot_monte_carlo_distribution(fake_revenue, advance=250_000).write_html(
        "test_chart2.html"
    )

    plot_fan_loyalty_scale(flr=1.4, popularity=75).write_html("test_chart3.html")

    plot_label_radar(
        {"Dreamville / TDE": 80, "Cactus Jack / OVO": 45}
    ).write_html("test_chart4.html")

    print("Wrote test_chart1.html through test_chart4.html — open them in a browser.")
