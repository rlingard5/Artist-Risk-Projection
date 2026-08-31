"""
app.py
------
Phase 4: Streamlit Web Dashboard.

Single-page UI that ties together spotify_client.py, risk_engine.py,
and charts.py. This file should stay "thin" — it wires inputs to the
other modules and lays out the results, but doesn't contain any Spotify
calls or risk math itself.

Run with:
    streamlit run app.py
"""

import streamlit as st

from spotify_client import search_artist
from risk_engine import (
    concentration_risk,
    fan_loyalty_ratio,
    run_monte_carlo_recoupment,
    label_benchmark_fit,
)
from charts import (
    plot_top_tracks_bar,
    plot_monte_carlo_distribution,
    plot_fan_loyalty_scale,
    plot_label_radar,
)

st.set_page_config(
    page_title="A&R Artist Investment & Risk Analytics",
    layout="wide",
)

# --- Sidebar inputs ------------------------------------------------------

st.sidebar.title("Scouting Inputs")

artist_name = st.sidebar.text_input("Artist Name", value="Central Cee")
advance_amount = st.sidebar.number_input(
    "Proposed Advance ($)", min_value=10_000, max_value=5_000_000,
    value=250_000, step=10_000,
)
label_target = st.sidebar.selectbox(
    "Label Target",
    options=["Dreamville", "TDE", "Cactus Jack", "OVO", "Motown",
             "Interscope", "Opium", "UMG", "Def Jam Recordings",
             "Death Row Records", "Cash Money Records", "Bad Boy Records",
             "Aftermath Entertainment", "Collective Music Group", "pgLang"],
)

st.sidebar.markdown("---")
st.sidebar.caption(
    "Manual Stats — Spotify's API restricts followers/popularity/genres/"
    "top-tracks to apps with Extended Quota Mode approval, so enter these "
    "by hand (check the artist's Spotify profile page)."
)
manual_followers = st.sidebar.number_input(
    "Followers", min_value=0, value=1_000_000, step=10_000,
)
manual_genres = st.sidebar.text_input(
    "Genres (comma-separated, optional)", value="uk hip hop, drill",
)
manual_track_popularities_raw = st.sidebar.text_area(
    "Top Track Popularities (comma-separated, highest first, 2-10 values)",
    value="88, 60, 55, 50, 48, 45, 40, 38, 35, 30",
    help="Find these by opening each track on open.spotify.com and checking "
         "the popularity indicator, or estimate based on chart performance.",
)

st.sidebar.markdown("---")
st.sidebar.caption("Monte Carlo Assumptions")
starting_streams = st.sidebar.number_input(
    "Est. current monthly streams", min_value=10_000, value=3_000_000, step=50_000,
)
mu = st.sidebar.slider(
    "Expected monthly growth (mu)", min_value=-0.10, max_value=0.20,
    value=0.02, step=0.01, format="%.2f",
)
sigma = st.sidebar.slider(
    "Monthly volatility (sigma)", min_value=0.01, max_value=0.50,
    value=0.15, step=0.01, format="%.2f",
)

run_button = st.sidebar.button("Run Analysis", type="primary")

# --- Main view ------------------------------------------------------------

st.title("🎧 A&R Artist Investment & Risk Analytics")

if not run_button:
    st.info("Enter an artist and advance amount in the sidebar, then click **Run Analysis**.")
    st.stop()

with st.spinner(f"Looking up '{artist_name}' on Spotify..."):
    artist = search_artist(artist_name)

if artist is None:
    st.error(f"No artist found for '{artist_name}'. Check the spelling and try again.")
    st.stop()

# Parse the comma-separated track popularity input into a list of ints.
try:
    track_popularities = [
        int(p.strip()) for p in manual_track_popularities_raw.split(",") if p.strip()
    ]
except ValueError:
    st.error(
        "Couldn't parse Top Track Popularities — make sure it's a "
        "comma-separated list of whole numbers, e.g. '88, 60, 55'."
    )
    st.stop()

if not track_popularities:
    st.error("Enter at least one track popularity value to continue.")
    st.stop()

# Fold in the manually-entered stats. Popularity is no longer a separate
# input — it's derived as the average of the entered track popularities,
# since Spotify's API no longer returns an artist-level popularity score
# for standard apps, and this keeps Fan Loyalty Ratio meaningful without
# asking for one more number.
derived_popularity = sum(track_popularities) / len(track_popularities)
artist["followers"] = manual_followers
artist["popularity"] = derived_popularity
artist["genres"] = [g.strip() for g in manual_genres.split(",") if g.strip()]

# charts.py expects a list of track dicts (it only reads .name/.popularity),
# so wrap the plain numbers to match that shape.
tracks = [
    {"name": f"Track {i}", "popularity": p}
    for i, p in enumerate(track_popularities, start=1)
]

if len(track_popularities) < 2:
    st.warning(
        "Enter at least 2 track popularity values — Concentration Risk "
        "and some charts may not be meaningful with fewer."
    )

# --- Run the math ---------------------------------------------------------

cr = concentration_risk(track_popularities)
flr = fan_loyalty_ratio(followers=artist["followers"], popularity=artist["popularity"])

mc_result = run_monte_carlo_recoupment(
    advance=advance_amount,
    starting_monthly_streams=starting_streams,
    mu=mu,
    sigma=sigma,
)

fit_results = label_benchmark_fit(cr=cr, flr=flr, mu=mu)

# Simple 0-100 alignment score per label for the radar chart:
# 100 if it fits outright, otherwise a partial credit score based on
# how many of that label's individual checks passed.
radar_scores = {}
for label, result in fit_results.items():
    if result["fits"]:
        radar_scores[label] = 100
    else:
        # crude partial credit: fewer failure reasons = higher score
        num_failures = len([r for r in result["reasons"] if "exceeds" in r or "below" in r])
        radar_scores[label] = max(20, 100 - num_failures * 30)

# --- Artist header ----------------------------------------------------

col_img, col_info = st.columns([1, 4])
with col_img:
    if artist["image_url"]:
        st.image(artist["image_url"], width=120)
with col_info:
    st.subheader(artist["name"])
    st.caption(", ".join(artist["genres"]) if artist["genres"] else "No genre data")

# --- KPI cards ----------------------------------------------------------

k1, k2, k3, k4 = st.columns(4)
k1.metric("Probability of Recoupment", f"{mc_result['probability_of_recoupment']:.1f}%")

risk_level = "High" if cr > 2.5 else ("Low" if cr < 1.5 else "Moderate")
k2.metric("Concentration Risk (CR)", f"{cr:.2f}", help=risk_level)

k3.metric("Fan Loyalty Ratio (FLR)", f"{flr:.2f}")

target_fits = fit_results[label_target]["fits"]
k4.metric(
    "Signability",
    "FITS" if target_fits else "Does Not Fit",
    help=f"vs. {label_target} profile",
)

st.markdown("---")

# --- Charts grid --------------------------------------------------------

row1_col1, row1_col2 = st.columns(2)
with row1_col1:
    st.plotly_chart(plot_top_tracks_bar(tracks), use_container_width=True)
with row1_col2:
    st.plotly_chart(
        plot_monte_carlo_distribution(mc_result["cumulative_revenue"], advance_amount),
        use_container_width=True,
    )

row2_col1, row2_col2 = st.columns(2)
with row2_col1:
    st.plotly_chart(
        plot_fan_loyalty_scale(flr, artist["popularity"]), use_container_width=True
    )
with row2_col2:
    st.plotly_chart(plot_label_radar(radar_scores), use_container_width=True)

# --- Label fit detail -----------------------------------------------------

st.markdown("---")
st.subheader("Label Benchmark Detail")

for label, result in fit_results.items():
    with st.expander(f"{label} — {'✅ Fits' if result['fits'] else '❌ Does not fit'}"):
        for reason in result["reasons"]:
            st.write(f"- {reason}")

st.caption(
    "⚠️ This tool uses a simplified GBM-based simulation and a blended "
    "$0.0035/stream royalty estimate. Treat outputs as directional, not "
    "as financial advice."
)
