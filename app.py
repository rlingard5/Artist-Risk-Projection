"""
app.py
------
Phase 4: Streamlit Web Dashboard.

Single-page UI that ties together spotify_client.py, lastfm_client.py,
risk_engine.py, and charts.py. This file should stay "thin" on the data
side — it wires inputs to the other modules and lays out the results,
but doesn't contain any API calls or risk math itself. The styling below
(CSS + small HTML card helpers) is presentation only, matching a dark
dashboard reference design: dark navy background, card-based KPIs with
colored status badges, and a prominent "verdict" banner.

The per-artist pipeline (fetch data -> compute metrics -> run Monte Carlo
-> label fit) lives in evaluate_artist(), and the rendering lives in
render_report() — both take explicit arguments/a bundle dict rather than
reading module-level globals, so the same code can run once (single-artist
mode) or twice side by side (compare mode) without duplication.

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import os
import streamlit as st

# Bridge Streamlit Community Cloud's "Secrets" (st.secrets) into regular
# environment variables, so the exact same os.getenv() calls in
# spotify_client.py / lastfm_client.py work whether credentials come
# from a local .env file (python-dotenv) or from Cloud's secrets.toml.
# Locally, st.secrets just finds no secrets file and this quietly does
# nothing — .env (loaded separately via python-dotenv) still works as before.
try:
    for _key, _value in st.secrets.items():
        os.environ.setdefault(_key, str(_value))
except Exception:
    pass

from spotify_client import search_artist, get_track_release_years, get_latest_album_years_ago
from lastfm_client import get_artist_stats, get_top_tracks
from risk_engine import (
    concentration_risk,
    fan_loyalty_ratio,
    catalog_recency,
    analyze_hit_timeline,
    data_confidence,
    run_monte_carlo_recoupment,
    label_benchmark_fit,
    compute_investment_boost,
    DEFAULT_PRICE_PER_STREAM,
    LABEL_PROFILES,
)
from charts import (
    plot_top_tracks_bar,
    plot_monte_carlo_distribution,
    plot_fan_loyalty_scale,
    plot_label_radar,
    plot_scenario_paths,
    plot_hit_timeline,
)

st.set_page_config(
    page_title="A&R Artist Investment & Risk Analytics",
    layout="wide",
)

# How many months' worth of "current" streaming activity a track's total
# Last.fm playcount is assumed to represent, for the auto-estimate below.
# This is a rough heuristic, not a measured number — there's no free API
# that gives real current monthly stream counts. Lower this for very new
# artists (most of whose plays are genuinely recent); raise it for an
# artist you think is coasting on old catalog plays rather than current
# activity.
ASSUMED_ACCUMULATION_MONTHS = 12

# How much of the advance the label is assumed to spend on promotion, and
# how many simulated paths each growth scenario runs. Both are modeling
# choices for this app, not published industry figures.
MARKETING_SPEND_FRACTION = 0.10
SIMULATIONS_PER_SCENARIO = 5_000
SCENARIO_MONTHS = 24

# Same random seed across all scenarios (and across both artists in
# compare mode), so random noise isn't what distinguishes them — only the
# growth assumption (or the artist's own data) differs.
SHARED_SEED = 42

# --- Styling ---------------------------------------------------------------
# Matches a dark dashboard reference: #0b0f17 page bg, #121826 cards,
# #232c3d borders, #2dd4bf teal accent, Inter font, pill-style badges.

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    section[data-testid="stSidebar"] {
        background-color: #0f1521;
        border-right: 1px solid #232c3d;
    }

    .kpi-card {
        background: #121826;
        border: 1px solid #232c3d;
        border-radius: 14px;
        padding: 20px;
        display: flex;
        flex-direction: column;
        gap: 10px;
        height: 100%;
        box-sizing: border-box;
    }
    .kpi-label { font-size: 14px; font-weight: 500; color: #9aa6bb; }
    .kpi-value-row { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
    .kpi-value { font-size: 34px; font-weight: 700; line-height: 1; color: #e8ecf3; }
    .kpi-sub { margin: 0; font-size: 13px; color: #aeb9cc; }

    .badge {
        padding: 2px 9px; border-radius: 999px; font-size: 12px; font-weight: 600;
        white-space: nowrap;
    }
    .badge-green { background: #12301f; color: #4ade80; }
    .badge-amber { background: #3a2d12; color: #f5b455; }
    .badge-red   { background: #3a1620; color: #ff8fa0; }

    .progress-track { height: 6px; border-radius: 3px; background: #232c3d; margin-top: 2px; }
    .progress-fill { height: 6px; border-radius: 3px; }

    .verdict-banner {
        background: #2a2113; border: 1px solid #5a4620; border-radius: 16px;
        padding: 24px 28px; display: flex; gap: 20px; align-items: center;
        flex-wrap: wrap; margin-bottom: 8px;
    }
    .verdict-banner.good { background: #0f2a1d; border-color: #1d5a3a; }
    .verdict-banner.bad { background: #2a1317; border-color: #5a2430; }
    .verdict-icon {
        width: 48px; height: 48px; border-radius: 50%; background: #f5b455; color: #2a1c05;
        display: flex; align-items: center; justify-content: center; font-size: 24px;
        font-weight: 700; flex-shrink: 0;
    }
    .verdict-icon.good { background: #4ade80; color: #06231f; }
    .verdict-icon.bad { background: #ff8fa0; color: #2a0b10; }
    .verdict-eyebrow {
        font-size: 12px; font-weight: 600; letter-spacing: 0.08em;
        text-transform: uppercase; color: #f5b455;
    }
    .verdict-eyebrow.good { color: #4ade80; }
    .verdict-eyebrow.bad { color: #ff8fa0; }
    .verdict-title { margin: 4px 0 6px; font-size: 22px; font-weight: 700; line-height: 1.25; color: #e8ecf3; }
    .verdict-body { margin: 0; color: #d8cdb8; font-size: 15px; }

    .pill-fit {
        text-decoration: none; color: #e8ecf3; background: #0f2a1d; border: 1px solid #1d5a3a;
        border-radius: 12px; padding: 14px 16px; display: flex; align-items: center; gap: 12px;
        font-weight: 600; margin-bottom: 8px;
    }
    .pill-nofit {
        color: #c9d3e4; background: #171f31; border: 1px solid #2a3550; border-radius: 999px;
        padding: 8px 14px; font-size: 14px; display: inline-flex; align-items: center;
        margin: 0 8px 8px 0;
    }
    .pill-nofit-target {
        color: #e8ecf3; background: #3a1620; border: 1px solid #7a2a3c; border-radius: 999px;
        padding: 8px 14px; font-size: 14px; font-weight: 600; display: inline-flex; align-items: center;
        margin: 0 8px 8px 0;
    }
    .section-label {
        font-size: 13px; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def kpi_card(label: str, value: str, badge_text: str, badge_class: str,
             subtext: str, progress_pct: float | None = None) -> str:
    """Build one KPI card as raw HTML, styled to match the reference design."""
    progress_html = ""
    if progress_pct is not None:
        progress_html = (
            f'<div class="progress-track">'
            f'<div class="progress-fill" style="width:{progress_pct:.1f}%; '
            f'background:{_badge_color(badge_class)}"></div></div>'
        )
    # Built as ONE line with no embedded newlines, on purpose. Markdown
    # treats a blank line as the end of an HTML block — and when
    # progress_html is "" (no progress bar), a multi-line template leaves
    # a literal blank line in the middle of the card's HTML. Everything
    # after that blank line then gets parsed as a new, indented block and
    # rendered as visible code text instead of HTML (exactly the
    # "<p class=...>" bug). A single-line string can't have this problem.
    return (
        f'<div class="kpi-card">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-value-row">'
        f'<span class="kpi-value">{value}</span>'
        f'<span class="badge {badge_class}">{badge_text}</span>'
        f'</div>'
        f'{progress_html}'
        f'<p class="kpi-sub">{subtext}</p>'
        f'</div>'
    )


def _badge_color(badge_class: str) -> str:
    return {"badge-green": "#4ade80", "badge-amber": "#f5b455", "badge-red": "#ff8fa0"}.get(
        badge_class, "#9aa6bb"
    )


TIMELINE_BADGE = {
    "fresh_and_sustained": ("badge-green", "Active & sustained"),
    "aging_but_active": ("badge-amber", "No recent hit"),
    "unproven_spike": ("badge-amber", "Unproven breakout"),
    "stale": ("badge-red", "Stale catalog"),
    "recent_flop": ("badge-red", "Recent flop"),
    "unknown": ("badge-amber", "No data"),
}

TIMELINE_SUBTEXT = {
    "fresh_and_sustained": "Has a hit from the last ~2 years, backed up by other hits around it — looks like a real trend, not a one-off.",
    "aging_but_active": "Newest hit isn't brand new, but isn't ancient either — not a red flag on its own.",
    "unproven_spike": "Has a hit from the last ~2 years, but nothing else on the timeline backs it up yet — could be a trend or could be a fluke.",
    "stale": "Even the newest hit is years old — the catalog's numbers may reflect past relevance, not current momentum.",
    "recent_flop": "Dropped an album recently, but none of its tracks cracked their own top-tracks list — a release that didn't land, not just a quiet period.",
    "unknown": "Couldn't confidently match these tracks to Spotify release dates.",
}

CONFIDENCE_BADGE = {
    "low": ("badge-red", "Low confidence"),
    "moderate": ("badge-amber", "Moderate confidence"),
    "high": ("badge-green", "High confidence"),
}


# --- Sidebar inputs ------------------------------------------------------

st.sidebar.title("A&R Scouting")
st.sidebar.markdown("### Inputs")

# Pulled straight from risk_engine.LABEL_PROFILES (sorted alphabetically)
# so this dropdown can never drift out of sync with the actual profiles —
# add a label there and it shows up here automatically. Streamlit's
# selectbox lets you type to jump to a match, which doubles as a search
# now that there are ~35 options.
LABEL_OPTIONS = sorted(LABEL_PROFILES.keys())

st.sidebar.markdown("**1 · Artist**")
artist_name = st.sidebar.text_input("Artist name", value="Chris Patrick")
compare_mode = st.sidebar.checkbox(
    "Compare with a second artist", value=False,
    help="Evaluate two artists side by side against the same deal terms "
         "below — useful when choosing between two candidates for the "
         "same signing budget.",
)
second_artist_name = ""
if compare_mode:
    second_artist_name = st.sidebar.text_input("Second artist name", value="")

st.sidebar.markdown("**2 · The deal**")
advance_amount = st.sidebar.number_input(
    "Proposed advance ($)", min_value=10_000, max_value=1_000_000_000,
    value=1_000_000, step=10_000,
)
label_target = st.sidebar.selectbox(
    "Label to evaluate against",
    options=LABEL_OPTIONS,
    index=LABEL_OPTIONS.index("Interscope Geffen A&M"),
)
royalty_rate_pct = st.sidebar.slider(
    "Artist royalty rate (% of streaming revenue)",
    min_value=10, max_value=50, value=20, step=1, format="%d%%",
    help="What share of the blended per-stream rate actually flows to the "
         "artist (and so counts toward recouping the advance). A typical "
         "traditional deal runs roughly 15-20%; a more artist-favorable "
         "deal can run higher.",
)
royalty_rate = royalty_rate_pct / 100.0

st.sidebar.markdown("**3 · Revenue simulation**")
st.sidebar.caption(
    "No public API gives real current monthly stream counts, so this is "
    "either auto-estimated from each artist's Last.fm track data (rough, "
    "scales with artist size) or your own manual number."
)
if compare_mode:
    # A single manual stream count can't honestly apply to two different
    # artists, so compare mode always auto-estimates each artist's
    # starting point from their own Last.fm data instead of asking for
    # one shared manual number.
    auto_estimate_streams = True
    st.sidebar.caption(
        "Comparing two artists: current monthly streams are auto-estimated "
        "for each from their own track data (manual entry isn't available "
        "in compare mode)."
    )
    manual_streams = None
else:
    auto_estimate_streams = st.sidebar.checkbox(
        "Auto-estimate current monthly streams", value=False,
    )
    if not auto_estimate_streams:
        manual_streams = st.sidebar.number_input(
            "Current monthly streams", min_value=10_000, value=170_000, step=10_000,
        )
    else:
        manual_streams = None  # computed after fetching the artist's data below

organic_mu = st.sidebar.slider(
    "Organic monthly growth (without label investment)",
    min_value=-0.10, max_value=0.20, value=0.02, step=0.01, format="%.2f",
    help="Growth this artist would see on their own. The label's own "
         "spending adds an additional boost, modeled separately below.",
)
sigma = st.sidebar.slider(
    "Month-to-month volatility", min_value=0.01, max_value=0.50,
    value=0.15, step=0.01, format="%.2f",
)

run_button = st.sidebar.button("Run analysis", type="primary", use_container_width=True)

# --- Main view ------------------------------------------------------------

st.title("🎧 A&R Artist Investment & Risk Analytics")

if not run_button:
    st.info("Enter an artist and advance amount in the sidebar, then click **Run analysis**.")
    st.stop()


def evaluate_artist(
    artist_name: str,
    advance_amount: float,
    label_target: str,
    auto_estimate_streams: bool,
    manual_streams: float | None,
    organic_mu: float,
    sigma: float,
    royalty_rate: float,
) -> dict:
    """
    Runs the full data-fetch + risk-math pipeline for one artist and
    returns a bundle dict for render_report() to display. Never raises
    or calls st.stop() — any failure comes back as {"ok": False, "error":
    "..."} so a caller running two artists (compare mode) can show one
    artist's results even if the other one's lookup fails.
    """
    try:
        spotify_artist = search_artist(artist_name)
        lastfm_stats = get_artist_stats(artist_name)
    except ConnectionError as e:
        return {"ok": False, "error": f"Couldn't reach Last.fm: {e}"}

    if lastfm_stats is None:
        return {
            "ok": False,
            "error": (
                f"No artist found for '{artist_name}' on Last.fm. Check the "
                "spelling and try again — Last.fm is case-insensitive but "
                "needs the artist's actual name."
            ),
        }

    try:
        top_tracks = get_top_tracks(artist_name, limit=10)
    except ConnectionError as e:
        return {"ok": False, "error": f"Couldn't reach Last.fm: {e}"}

    if not top_tracks:
        return {
            "ok": False,
            "error": (
                f"'{artist_name}' was found but has no track data on "
                "Last.fm — can't compute Concentration Risk without at "
                "least one track."
            ),
        }

    track_few_warning = None
    if len(top_tracks) < 2:
        track_few_warning = (
            "Only 1 track found — Concentration Risk and some charts may "
            "not be meaningful with just a single track."
        )

    track_playcounts = [t["playcount"] for t in top_tracks]

    # Best-effort release-date lookup via Spotify's track search (not the
    # blocked artist-top-tracks endpoint — see spotify_client.py). This is
    # supplementary, not critical path: if it fails or can't match a
    # track, the rest of the analysis still works, just without the
    # timeline signal.
    try:
        release_years_by_name = get_track_release_years(
            [t["name"] for t in top_tracks], artist_name
        )
    except Exception:
        release_years_by_name = {}
    track_years_ago = [release_years_by_name.get(t["name"]) for t in top_tracks]

    artist = {
        "name": spotify_artist["name"] if spotify_artist else artist_name,
        "image_url": spotify_artist["image_url"] if spotify_artist else None,
        "listeners": lastfm_stats["listeners"],
        "playcount": lastfm_stats["playcount"],
        "genres": lastfm_stats["genres"],
    }

    # Also best-effort, also supplementary: when did this artist's most
    # recent album come out, and did it produce anything that actually
    # cracked their own top-tracks list?
    latest_album_years_ago = None
    if spotify_artist:
        try:
            latest_album_years_ago = get_latest_album_years_ago(spotify_artist["id"])
        except Exception:
            latest_album_years_ago = None

    # If auto-estimate is on, scale the simulation's starting point with
    # the artist's actual size instead of using a flat default — a
    # top-10-tracks playcount sum in the billions (a Drake) should produce
    # a very different estimate than one in the thousands (an unsigned
    # artist). Still a rough heuristic, not a real stream count: Last.fm's
    # total playcount accumulates over a track's whole lifetime, so
    # dividing by an assumed number of "active" months is a guess, not a
    # measurement.
    if auto_estimate_streams:
        starting_streams = max(
            sum(track_playcounts) / ASSUMED_ACCUMULATION_MONTHS, 10_000
        )
    else:
        starting_streams = manual_streams

    # --- Risk math ----------------------------------------------------
    cr = concentration_risk(track_playcounts)
    flr = fan_loyalty_ratio(listeners=artist["listeners"], playcount=artist["playcount"])
    catalog_recency_years = catalog_recency(track_playcounts, track_years_ago)
    hit_timeline = analyze_hit_timeline(
        track_years_ago, latest_album_years_ago=latest_album_years_ago
    )
    confidence = data_confidence(artist["listeners"])

    # Royalty split: DEFAULT_PRICE_PER_STREAM is the blended per-stream
    # rate paid to the RIGHTSHOLDER (roughly the label's side); only a
    # royalty_rate share of that actually flows to the artist and counts
    # toward recouping the advance. Modeling 100% of streaming revenue as
    # the artist's own (the old behavior) made recoupment look far easier
    # than a real contract would.
    effective_price_per_stream = DEFAULT_PRICE_PER_STREAM * royalty_rate
    current_monthly_revenue = starting_streams * effective_price_per_stream
    marketing_spend = advance_amount * MARKETING_SPEND_FRACTION
    investment_boost = compute_investment_boost(
        advance=advance_amount,
        current_monthly_revenue=current_monthly_revenue,
        listeners=artist["listeners"],
        months=SCENARIO_MONTHS,
        marketing_spend_fraction=MARKETING_SPEND_FRACTION,
    )

    half = SCENARIO_MONTHS // 2
    scenario_mu = {
        "No growth": 0.0,
        "Positive growth": organic_mu + investment_boost,
        "Positive, then negative": (
            [organic_mu + investment_boost] * half
            + [-investment_boost] * (SCENARIO_MONTHS - half)
        ),
        # Mirror image of "Positive growth": the deal doesn't land,
        # promotion doesn't move the needle, and the artist actually
        # loses ground at the same rate the optimistic case assumed it
        # would gain.
        "Negative growth": -(organic_mu + investment_boost),
        # Mirror image of "Positive, then negative": a slow/quiet start
        # (e.g. delayed rollout, no initial traction) followed by a real
        # comeback once something catches on — same magnitudes as the
        # "Positive, then negative" case, just reversed in order and sign.
        "Negative, then positive": (
            [-(organic_mu + investment_boost)] * half
            + [investment_boost] * (SCENARIO_MONTHS - half)
        ),
    }

    scenario_results = {
        name: run_monte_carlo_recoupment(
            advance=advance_amount,
            starting_monthly_streams=starting_streams,
            mu=mu_value,
            sigma=sigma,
            months=SCENARIO_MONTHS,
            simulations=SIMULATIONS_PER_SCENARIO,
            random_seed=SHARED_SEED,
            price_per_stream=effective_price_per_stream,
        )
        for name, mu_value in scenario_mu.items()
    }

    # The "Positive growth" scenario is treated as the primary/expected
    # case for the KPI cards, verdict banner, and label-fit check below —
    # it represents the deal doing what it's meant to do.
    mc_result = scenario_results["Positive growth"]
    prob_recoup = mc_result["probability_of_recoupment"]
    effective_mu = scenario_mu["Positive growth"]

    fit_results = label_benchmark_fit(
        cr=cr, flr=flr, mu=effective_mu,
        catalog_recency_years=catalog_recency_years,
        artist_genres=artist["genres"],
    )
    fitting_labels = [label for label, r in fit_results.items() if r["fits"]]
    nonfitting_labels = [label for label, r in fit_results.items() if not r["fits"]]
    target_fits = fit_results[label_target]["fits"]

    radar_scores = {}
    for label, result in fit_results.items():
        if result["fits"]:
            radar_scores[label] = 100
        else:
            num_failures = len(
                [r for r in result["reasons"] if "exceeds" in r or "below" in r]
            )
            radar_scores[label] = max(20, 100 - num_failures * 30)

    return {
        "ok": True,
        "error": None,
        "track_few_warning": track_few_warning,
        "artist": artist,
        "top_tracks": top_tracks,
        "track_years_ago": track_years_ago,
        "advance_amount": advance_amount,
        "label_target": label_target,
        "auto_estimate_streams": auto_estimate_streams,
        "starting_streams": starting_streams,
        "royalty_rate": royalty_rate,
        "effective_price_per_stream": effective_price_per_stream,
        "cr": cr,
        "flr": flr,
        "catalog_recency_years": catalog_recency_years,
        "hit_timeline": hit_timeline,
        "confidence": confidence,
        "current_monthly_revenue": current_monthly_revenue,
        "marketing_spend": marketing_spend,
        "investment_boost": investment_boost,
        "scenario_results": scenario_results,
        "prob_recoup": prob_recoup,
        "effective_mu": effective_mu,
        "fit_results": fit_results,
        "fitting_labels": fitting_labels,
        "nonfitting_labels": nonfitting_labels,
        "target_fits": target_fits,
        "n_fit": len(fitting_labels),
        "n_total": len(fit_results),
        "radar_scores": radar_scores,
    }


def _scenario_badge(prob: float) -> str:
    """
    Badge color driven by the scenario's actual recoupment probability —
    not by which scenario it is — so it stays consistent with how the
    main KPI cards derive their badge color, and keeps meaning something
    with 5 scenarios instead of 3.
    """
    if prob >= 70:
        return "badge-green"
    if prob >= 40:
        return "badge-amber"
    return "badge-red"


def render_report(bundle: dict) -> None:
    """Renders one artist's full dashboard from an evaluate_artist() bundle."""
    if not bundle["ok"]:
        st.error(bundle["error"])
        return

    artist = bundle["artist"]
    top_tracks = bundle["top_tracks"]
    track_years_ago = bundle["track_years_ago"]
    advance_amount = bundle["advance_amount"]
    label_target = bundle["label_target"]
    auto_estimate_streams = bundle["auto_estimate_streams"]
    starting_streams = bundle["starting_streams"]
    royalty_rate = bundle["royalty_rate"]
    effective_price_per_stream = bundle["effective_price_per_stream"]
    cr = bundle["cr"]
    flr = bundle["flr"]
    hit_timeline = bundle["hit_timeline"]
    confidence = bundle["confidence"]
    marketing_spend = bundle["marketing_spend"]
    investment_boost = bundle["investment_boost"]
    scenario_results = bundle["scenario_results"]
    prob_recoup = bundle["prob_recoup"]
    fit_results = bundle["fit_results"]
    fitting_labels = bundle["fitting_labels"]
    nonfitting_labels = bundle["nonfitting_labels"]
    target_fits = bundle["target_fits"]
    n_fit = bundle["n_fit"]
    n_total = bundle["n_total"]
    radar_scores = bundle["radar_scores"]

    if bundle["track_few_warning"]:
        st.warning(bundle["track_few_warning"])

    # --- Artist header ----------------------------------------------------
    col_img, col_info = st.columns([1, 5])
    with col_img:
        if artist["image_url"]:
            st.image(artist["image_url"], width=88)
    with col_info:
        st.subheader(artist["name"])
        genre_tags = " ".join(
            f'<span class="pill-nofit">{g}</span>' for g in artist["genres"][:4]
        )
        st.markdown(
            f'{genre_tags} <span style="color:#9aa6bb; font-size:14px;">'
            f'Evaluating a ${advance_amount:,.0f} advance for {label_target} · '
            f'{artist["listeners"]:,} listeners · {artist["playcount"]:,} total plays</span>',
            unsafe_allow_html=True,
        )

    if confidence["level"] == "low":
        st.warning(f"⚠️ Low data confidence: {confidence['message']}")

    streams_note = (
        f"Simulation uses an auto-estimated {starting_streams:,.0f} current monthly "
        f"streams (top-10 track playcounts ÷ {ASSUMED_ACCUMULATION_MONTHS} months — "
        "a rough heuristic, not a real stream count)."
        if auto_estimate_streams else
        f"Simulation uses your manually-set {starting_streams:,.0f} current monthly streams."
    )
    st.caption(
        f"{streams_note} Assumes a {royalty_rate:.0%} artist royalty rate "
        f"(${effective_price_per_stream:.5f} effective $/stream, out of a "
        f"${DEFAULT_PRICE_PER_STREAM:.4f} blended rightsholder rate)."
    )

    st.write("")

    # --- Verdict banner ---------------------------------------------------
    strong_case = prob_recoup >= 50 and target_fits
    weak_case = prob_recoup < 50 and not target_fits

    if strong_case:
        tone, icon, eyebrow_text = "good", "✓", "Verdict"
        title = f"Good fit for {label_target}"
    elif weak_case:
        tone, icon, eyebrow_text = "bad", "✕", "Verdict"
        title = f"High risk — unlikely to recoup and not a fit for {label_target}"
    else:
        tone, icon, eyebrow_text = "", "!", "Verdict"
        if target_fits:
            title = f"Fits {label_target}'s profile, but recoupment is uncertain"
        else:
            title = f"Likely to recoup, but not a fit for {label_target}"

    fit_list_str = ", ".join(fitting_labels) if fitting_labels else "none"
    verdict_body = (
        f"There is a {prob_recoup:.1f}% chance revenue covers the "
        f"${advance_amount:,.0f} advance. {n_fit} of {n_total} labels fit this "
        f"profile: {fit_list_str}."
    )

    st.markdown(
        f'<div class="verdict-banner {tone}">'
        f'<div class="verdict-icon {tone}">{icon}</div>'
        f'<div>'
        f'<div class="verdict-eyebrow {tone}">{eyebrow_text}</div>'
        f'<div class="verdict-title">{title}</div>'
        f'<p class="verdict-body">{verdict_body}</p>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.write("")

    # --- KPI cards ----------------------------------------------------------
    recoup_badge = (
        ("badge-green", "Strong") if prob_recoup >= 70 else
        ("badge-amber", "Moderate") if prob_recoup >= 40 else
        ("badge-red", "Weak")
    )
    cr_badge = (
        ("badge-green", "Healthy") if cr < 1.5 else
        ("badge-amber", "Watch") if cr <= 2.5 else
        ("badge-red", "High risk")
    )
    flr_badge = (
        ("badge-green", "Strong") if flr >= 15 else
        ("badge-amber", "Moderate") if flr >= 5 else
        ("badge-red", "Weak")
    )
    fit_badge = ("badge-green", "Fit") if target_fits else ("badge-red", "Pass")
    timeline_badge = TIMELINE_BADGE[hit_timeline["status"]]
    confidence_badge = CONFIDENCE_BADGE[confidence["level"]]

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    with k1:
        st.markdown(
            kpi_card(
                "Chance of recouping", f"{prob_recoup:.1f}%",
                recoup_badge[1], recoup_badge[0],
                f"In about {prob_recoup:.0f} of every 100 simulated 24-month "
                "outcomes, artist royalty revenue covers the advance.",
                progress_pct=prob_recoup,
            ),
            unsafe_allow_html=True,
        )
    with k2:
        cr_display = f"{cr:.2f}×" if cr != float("inf") else "∞"
        st.markdown(
            kpi_card(
                "Hit dependence", cr_display,
                cr_badge[1], cr_badge[0],
                "The top track's plays vs. the average of tracks 2–10. "
                "Higher means more reliance on one song. (Concentration risk)",
            ),
            unsafe_allow_html=True,
        )
    with k3:
        flr_display = f"{flr:.1f}" if flr != float("inf") else "∞"
        st.markdown(
            kpi_card(
                "Fan loyalty", flr_display,
                flr_badge[1], flr_badge[0],
                "Average plays per listener. Higher means the audience "
                "sticks around rather than listening once. (Fan Loyalty Ratio)",
            ),
            unsafe_allow_html=True,
        )
    with k4:
        st.markdown(
            kpi_card(
                f"Fit with {label_target}", "Fits" if target_fits else "Does not fit",
                fit_badge[1], fit_badge[0],
                "Signability against this label's benchmarks, including "
                "genre. See the ranked list below for labels that do fit.",
            ),
            unsafe_allow_html=True,
        )
    with k5:
        if hit_timeline["status"] == "unknown":
            timeline_value = "—"
        else:
            timeline_value = f"{hit_timeline['most_recent_hit_years_ago']:.1f}y"
        st.markdown(
            kpi_card(
                "Catalog timeline", timeline_value,
                timeline_badge[1], timeline_badge[0],
                TIMELINE_SUBTEXT[hit_timeline["status"]],
            ),
            unsafe_allow_html=True,
        )
    with k6:
        st.markdown(
            kpi_card(
                "Data confidence", confidence["level"].capitalize(),
                confidence_badge[1], confidence_badge[0],
                confidence["message"],
            ),
            unsafe_allow_html=True,
        )

    st.write("")

    # --- Growth scenarios: 5 scenarios, 3-then-2 grid -------------------------
    st.markdown(
        '<h3 style="margin-bottom:2px;">Growth Scenarios</h3>'
        f'<span style="font-size:13px; color:#9aa6bb;">Same advance, same '
        f'random draws — only the growth assumption changes. '
        f'{SIMULATIONS_PER_SCENARIO:,} simulations per scenario.</span>',
        unsafe_allow_html=True,
    )
    size_tier_label = (
        "under 1M listeners, so the boost is amplified" if artist["listeners"] < 1_000_000
        else "10M+ listeners, so the boost is sharply diminished" if artist["listeners"] >= 10_000_000
        else "1M-10M listeners (baseline boost)"
    )
    st.caption(
        f"Assumes {MARKETING_SPEND_FRACTION:.0%} of the advance "
        f"(${marketing_spend:,.0f}) goes to promotion, adding an estimated "
        f"+{investment_boost:.2%}/month to growth on top of your organic "
        f"growth slider, spread across {SCENARIO_MONTHS} months. This artist has "
        f"{size_tier_label} — the same advance moves a smaller artist's growth "
        "rate more, in relative terms, than it would a superstar's. This is "
        "this app's own modeling assumption, not an industry formula. The "
        "two \"negative\" scenarios apply that same magnitude in reverse — "
        "the deal's spend simply doesn't translate into growth."
    )
    st.write("")

    scenario_items = list(scenario_results.items())
    for row_start in range(0, len(scenario_items), 3):
        row_items = scenario_items[row_start:row_start + 3]
        row_cols = st.columns(3)
        for col, (name, result) in zip(row_cols, row_items):
            with col:
                prob = result["probability_of_recoupment"]
                st.markdown(
                    kpi_card(
                        name, f"{prob:.1f}%",
                        "Recoups" if prob >= 50 else "At risk",
                        _scenario_badge(prob),
                        f"Median 24-month revenue: ${result['median_revenue']:,.0f}",
                        progress_pct=prob,
                    ),
                    unsafe_allow_html=True,
                )
                st.plotly_chart(
                    plot_monte_carlo_distribution(result["cumulative_revenue"], advance_amount),
                    use_container_width=True,
                )

    st.write("")
    st.markdown(
        '<h4 style="margin-bottom:2px;">Scenario comparison</h4>'
        '<span style="font-size:13px; color:#9aa6bb;">Median projected '
        'monthly streams for each scenario, side by side.</span>',
        unsafe_allow_html=True,
    )
    st.plotly_chart(plot_scenario_paths(scenario_results), use_container_width=True)

    st.write("")

    # --- Remaining charts -----------------------------------------------------
    row1_col1, row1_col2 = st.columns(2)
    with row1_col1:
        st.plotly_chart(plot_top_tracks_bar(top_tracks), use_container_width=True)
    with row1_col2:
        st.plotly_chart(
            plot_fan_loyalty_scale(artist["listeners"], artist["playcount"], flr),
            use_container_width=True,
        )

    st.markdown(
        '<h4 style="margin-bottom:2px;">Hit Timeline</h4>'
        '<span style="font-size:13px; color:#9aa6bb;">Each top track plotted '
        'by playcount and years since release — catches a catalog propped up '
        'by an old hit, and a recent hit with nothing backing it up.</span>',
        unsafe_allow_html=True,
    )
    st.plotly_chart(plot_hit_timeline(top_tracks, track_years_ago), use_container_width=True)

    if hit_timeline["latest_album_years_ago"] is not None:
        st.caption(
            f"Most recent album: {hit_timeline['latest_album_years_ago']:.1f} years ago."
            + (
                " None of its tracks made this artist's own top-10-by-playcount "
                "list — a release that doesn't appear to have connected with listeners."
                if hit_timeline["recent_album_no_hit"] else ""
            )
        )
    st.caption(
        "Best-effort: release dates come from matching each Last.fm top "
        "track (and the latest album lookup) to Spotify's catalog search, "
        "which can occasionally miss or mismatch a generically-titled "
        "release. Thresholds (hit counts as \"recent\" under ~2 years, "
        "catalog reads as \"stale\" past ~6 years with no newer hit) are "
        "this app's own modeling assumptions, not an industry standard."
    )
    st.write("")

    # Radar is capped to the top 10 closest-fitting labels by score — with
    # ~35 label profiles now, plotting every one would make the chart
    # unreadable. The full fit/no-fit breakdown for every label is still
    # below this, unabridged.
    top_radar_labels = dict(
        sorted(radar_scores.items(), key=lambda kv: kv[1], reverse=True)[:10]
    )
    st.plotly_chart(plot_label_radar(top_radar_labels), use_container_width=True)
    st.caption("Showing the 10 closest-fitting labels. Full ranked list is below.")

    # --- Label fit -----------------------------------------------------
    st.markdown("---")
    st.markdown(
        f'<h3 style="margin-bottom:2px;">Where {artist["name"]} fits: '
        f'{n_fit} of {n_total} labels</h3>'
        f'<span style="font-size:13px; color:#9aa6bb;">Ranked against each '
        f'label\'s benchmarks (including genre). Expand a label below for '
        f'its detail.</span>',
        unsafe_allow_html=True,
    )
    st.write("")

    if fitting_labels:
        st.markdown(
            f'<div class="section-label" style="color:#4ade80;">Fits ({len(fitting_labels)})</div>',
            unsafe_allow_html=True,
        )
        fit_cols = st.columns(min(4, len(fitting_labels)) or 1)
        for i, label in enumerate(fitting_labels):
            with fit_cols[i % len(fit_cols)]:
                st.markdown(
                    f'<div class="pill-fit">✓ <span>{label}</span></div>',
                    unsafe_allow_html=True,
                )

    if nonfitting_labels:
        st.markdown(
            f'<div class="section-label" style="color:#ff8fa0; margin-top:12px;">'
            f'Does not fit ({len(nonfitting_labels)})</div>',
            unsafe_allow_html=True,
        )
        pills_html = ""
        for label in nonfitting_labels:
            css_class = "pill-nofit-target" if label == label_target else "pill-nofit"
            suffix = " · your target" if label == label_target else ""
            pills_html += f'<span class="{css_class}">{label}{suffix}</span>'
        st.markdown(pills_html, unsafe_allow_html=True)

    st.write("")
    st.markdown("---")
    st.subheader("Label Benchmark Detail")

    for label, result in fit_results.items():
        with st.expander(f"{label} — {'✅ Fits' if result['fits'] else '❌ Does not fit'}"):
            for reason in result["reasons"]:
                st.write(f"- {reason}")

    st.caption(
        "⚠️ This tool uses a simplified GBM-based simulation, a "
        f"${DEFAULT_PRICE_PER_STREAM:.4f}/stream blended rightsholder rate "
        f"at a {royalty_rate:.0%} assumed artist royalty share, and label "
        "thresholds that are educated guesses rather than published "
        "criteria. Treat outputs as directional, not as financial advice."
    )


# --- Run ---------------------------------------------------------------

if compare_mode and second_artist_name.strip():
    st.caption(
        f"Comparing **{artist_name}** against **{second_artist_name}** — "
        "same advance, label target, and growth assumptions for both, so "
        "the only thing that differs is each artist's own data."
    )

    with st.spinner(f"Evaluating {artist_name} and {second_artist_name}..."):
        bundle_a = evaluate_artist(
            artist_name, advance_amount, label_target,
            auto_estimate_streams, manual_streams, organic_mu, sigma, royalty_rate,
        )
        bundle_b = evaluate_artist(
            second_artist_name, advance_amount, label_target,
            auto_estimate_streams, manual_streams, organic_mu, sigma, royalty_rate,
        )

    if bundle_a["ok"] and bundle_b["ok"]:
        name_a = bundle_a["artist"]["name"]
        name_b = bundle_b["artist"]["name"]
        prob_a, prob_b = bundle_a["prob_recoup"], bundle_b["prob_recoup"]
        fit_a, fit_b = bundle_a["n_fit"], bundle_b["n_fit"]

        better_recoup = name_a if prob_a > prob_b else name_b if prob_b > prob_a else None
        better_fit = name_a if fit_a > fit_b else name_b if fit_b > fit_a else None

        head_to_head = (
            f"**Head-to-head:** "
            + (
                f"{better_recoup} has higher recoupment odds ({max(prob_a, prob_b):.1f}% vs "
                f"{min(prob_a, prob_b):.1f}%). "
                if better_recoup else
                f"Both have the same recoupment odds ({prob_a:.1f}%). "
            )
            + (
                f"{better_fit} fits more labels ({max(fit_a, fit_b)} vs {min(fit_a, fit_b)})."
                if better_fit else
                f"Both fit the same number of labels ({fit_a})."
            )
        )
        st.info(head_to_head)

    col_a, col_b = st.columns(2)
    with col_a:
        render_report(bundle_a)
    with col_b:
        render_report(bundle_b)

else:
    if compare_mode and not second_artist_name.strip():
        st.warning(
            "Compare mode is on, but no second artist name was entered — "
            f"showing just {artist_name}."
        )

    with st.spinner(f"Looking up '{artist_name}'..."):
        bundle = evaluate_artist(
            artist_name, advance_amount, label_target,
            auto_estimate_streams, manual_streams, organic_mu, sigma, royalty_rate,
        )

    if not bundle["ok"]:
        st.error(bundle["error"])
        st.stop()

    render_report(bundle)
