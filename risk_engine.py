"""
risk_engine.py
--------------
Phase 2: Risk Algorithms & Math Core.

Turns raw Spotify data (from spotify_client.py) into the quantitative
metrics that drive the dashboard: Concentration Risk, Fan Loyalty Ratio,
a 24-month Monte Carlo recoupment simulation, and label benchmark fit.

None of these functions call the Spotify API directly — they only take
plain numbers/lists as input, which makes them easy to unit test.
"""

from __future__ import annotations

import numpy as np

EPSILON = 1e-6  # avoids division-by-zero when a catalog has few tracks
DEFAULT_PRICE_PER_STREAM = 0.0035  # rough blended industry royalty rate


def concentration_risk(track_popularities: list[int]) -> float:
    """
    Calculate Concentration Risk (CR): how dependent an artist is on a
    single viral hit versus having a deep, diversified catalog.

    CR = value(track #1) / (avg value(tracks 2-10) + epsilon)

    NOTE: the parameter is named track_popularities for historical
    reasons (this originally took Spotify's 0-100 popularity scores),
    but it now works the same way on Last.fm playcounts instead — CR is
    a ratio, so it doesn't matter what scale the underlying numbers are
    on, as long as all tracks use the same one. See lastfm_client.get_top_tracks().

    Interpretation
    --------------
    CR > 2.5 : high viral dependence ("one-hit wonder" risk)
    CR < 1.5 : strong catalog depth

    These thresholds were originally calibrated for Spotify's compressed
    0-100 scale. Real playcounts can be more skewed (a viral hit might
    have 50x the plays of a deep cut, not just 2-3x), so treat these as
    a starting point — worth re-checking once you've run a few real
    artists through and see what typical CR values actually look like.

    Parameters
    ----------
    track_popularities : list[int]
        Track-level values (playcounts from Last.fm), ideally the top 10
        tracks, already sorted descending (get_top_tracks() returns them
        this way).

    Returns
    -------
    float
        The concentration risk score. Returns float('inf') if there's
        only one track (no catalog to compare against).
    """
    if not track_popularities:
        raise ValueError("track_popularities cannot be empty")

    top_track = track_popularities[0]
    rest = track_popularities[1:10]  # tracks 2-10

    if not rest:
        return float("inf")

    avg_rest = np.mean(rest)
    return top_track / (avg_rest + EPSILON)


def fan_loyalty_ratio(listeners: int, playcount: int) -> float:
    """
    Calculate Fan Loyalty Ratio (FLR): average plays per listener.

    FLR = total playcount / listeners

    NOTE: this formula changed from the original Spotify-based design
    (followers / (popularity * 1000)) because Spotify's public API no
    longer returns followers/popularity/genres to standard apps (see
    spotify_client.py's docstring). We now source these numbers from
    Last.fm instead (lastfm_client.get_artist_stats()), which gives
    "listeners" (unique people who've played the artist) and "playcount"
    (total plays across everyone) rather than a 0-100 popularity score.

    This redefinition is arguably more honest than the original: it
    directly answers "on average, how many times does each listener play
    this artist?" — a real engagement signal, not a scaled-by-an-
    arbitrary-constant proxy. A high FLR means people who find the
    artist keep coming back (loyal); a low FLR means lots of one-off,
    passive listens (e.g. a single viral song on a playlist).

    Parameters
    ----------
    listeners : int
        Unique Last.fm listeners for the artist.
    playcount : int
        Total plays (scrobbles) across all listeners.

    Returns
    -------
    float
        Average plays per listener. Returns float('inf') if listeners
        is 0 (can't divide by zero).
    """
    if listeners <= 0:
        return float("inf")
    return playcount / listeners


def catalog_recency(track_playcounts: list[int], track_years_ago: list[float | None]) -> float | None:
    """
    Weighted-average age (in years) of an artist's top tracks, weighted
    by each track's playcount — so a catalog carried by one old viral
    hit reads as "aging" even if a couple of newer, lower-played tracks
    are mixed in.

    This is meant to catch the case a pure streaming-volume number
    misses: an artist whose numbers look big only because of a song from
    4-5 years ago, versus one whose current output is what's driving
    those numbers. High catalog activity on old material is a real A&R
    red flag — it suggests the artist may be past their growth window
    rather than still building one.

    Parameters
    ----------
    track_playcounts : list[int]
        Playcount per top track (same order/length as track_years_ago).
    track_years_ago : list[float | None]
        Years since release per track, from
        spotify_client.get_track_release_years(). None for any track
        whose release date couldn't be found — those are excluded from
        the weighted average rather than guessed at.

    Returns
    -------
    float | None
        Playcount-weighted average age in years. None if no track had a
        known release date (can't compute anything in that case — the
        app should fall back to treating recency as "unknown", not
        "stale").
    """
    known = [
        (pc, years) for pc, years in zip(track_playcounts, track_years_ago)
        if years is not None
    ]
    if not known:
        return None

    total_weight = sum(pc for pc, _ in known)
    if total_weight <= 0:
        # All matched tracks have zero playcount (shouldn't normally
        # happen); fall back to a plain unweighted average.
        return float(np.mean([years for _, years in known]))

    weighted_sum = sum(pc * years for pc, years in known)
    return weighted_sum / total_weight


# Thresholds for analyze_hit_timeline() below — this app's own modeling
# assumptions, not an industry standard, and worth re-tuning per genre
# (a pop artist's hit cycle looks different from a rapper's mixtape cycle).
STALE_THRESHOLD_YEARS = 4.5   # a catalog whose newest hit is older than this reads as "stale"
RECENT_WINDOW_YEARS = 0.5     # ~6 months: how new a hit has to be to count as "recent"
SUPPORT_WINDOW_YEARS = 2.5    # how far back to look for a hit that "backs up" a recent one


def analyze_hit_timeline(track_years_ago: list[float | None]) -> dict:
    """
    Classifies an artist's hit pattern over time, to catch two different
    red flags a raw playcount or recency average can miss:

    1. "Stale" — the catalog's numbers are real, but nothing in it is
       recent; the artist may be past their growth window rather than
       still building one.
    2. "Unproven spike" — the artist has one hit from the last ~6 months,
       but nothing else on the timeline backs it up (no earlier hit
       building toward it, no second recent hit alongside it). That's a
       real signal, but on its own it could be a fluke rather than a
       trend — a label betting on this timeline is betting it repeats.

    An artist with a recent hit AND supporting hits around it (either an
    earlier one within SUPPORT_WINDOW_YEARS, or more than one hit inside
    RECENT_WINDOW_YEARS) reads as "fresh and sustained" — the strongest
    timeline pattern.

    Parameters
    ----------
    track_years_ago : list[float | None]
        Years since release per top track, same order as the track list,
        from spotify_client.get_track_release_years(). None entries
        (no confident Spotify match) are ignored rather than guessed at.

    Returns
    -------
    dict
        {
            "status": str,  # "fresh_and_sustained" | "aging_but_active"
                             # | "unproven_spike" | "stale" | "unknown"
            "most_recent_hit_years_ago": float | None,
            "oldest_hit_years_ago": float | None,
            "known_track_count": int,
        }
        "unknown" means no track had a usable release date at all —
        the app should treat that as "no data," not as a red flag.
    """
    known = sorted(y for y in track_years_ago if y is not None)

    if not known:
        return {
            "status": "unknown",
            "most_recent_hit_years_ago": None,
            "oldest_hit_years_ago": None,
            "known_track_count": 0,
        }

    most_recent = known[0]
    oldest = known[-1]
    has_recent_hit = most_recent <= RECENT_WINDOW_YEARS

    if not has_recent_hit:
        status = "stale" if most_recent > STALE_THRESHOLD_YEARS else "aging_but_active"
    else:
        recent_hit_count = sum(1 for y in known if y <= RECENT_WINDOW_YEARS)
        has_supporting_hit = any(
            RECENT_WINDOW_YEARS < y <= SUPPORT_WINDOW_YEARS for y in known
        )
        if recent_hit_count >= 2 or has_supporting_hit:
            status = "fresh_and_sustained"
        else:
            status = "unproven_spike"

    return {
        "status": status,
        "most_recent_hit_years_ago": most_recent,
        "oldest_hit_years_ago": oldest,
        "known_track_count": len(known),
    }


def run_monte_carlo_recoupment(
    advance: float,
    starting_monthly_streams: float,
    mu: float | list[float],
    sigma: float,
    months: int = 24,
    simulations: int = 1000,
    price_per_stream: float = DEFAULT_PRICE_PER_STREAM,
    random_seed: int | None = None,
) -> dict:
    """
    Simulate monthly streaming volume using Geometric Brownian Motion
    (GBM) to estimate the probability an advance gets recouped within
    the contract horizon.

    GBM formula (applied each month):
        S_t = S_(t-1) * exp((mu_t - sigma^2 / 2) * dt + sigma * sqrt(dt) * Z)
        where Z ~ N(0, 1) and dt = 1 (one month per step)

    Parameters
    ----------
    advance : float
        Proposed advance amount in dollars, e.g. 250_000.
    starting_monthly_streams : float
        Estimated current monthly stream count to project forward from.
    mu : float | list[float]
        Expected monthly stream growth rate (drift). Either a single
        number applied to every month (e.g. 0.02 for 2%/mo, constant
        growth), or a list of per-month values of length `months` for a
        growth rate that changes over the horizon — e.g. a marketing-
        driven spike in the first year that fades in the second. A list
        shorter/longer than `months` raises ValueError.
    sigma : float
        Monthly volatility of streams, e.g. 0.15 for 15%/mo.
    months : int
        Contract horizon in months. Defaults to 24.
    simulations : int
        Number of Monte Carlo paths to simulate. Defaults to 1000.
    price_per_stream : float
        Blended royalty rate per stream in dollars.
    random_seed : int | None
        Optional seed for reproducible results (useful for testing/demos,
        or for running several scenarios on the same random draws so the
        only difference between them is the growth assumption).

    Returns
    -------
    dict
        {
            "paths": np.ndarray,           # shape (simulations, months+1) stream paths
            "cumulative_revenue": np.ndarray,  # shape (simulations,) total $ per sim
            "probability_of_recoupment": float,  # 0-100
            "median_revenue": float,
            "advance": float,
        }
    """
    if random_seed is not None:
        np.random.seed(random_seed)

    dt = 1  # one time-step = one month

    if np.isscalar(mu):
        mu_schedule = np.full(months, float(mu))
    else:
        mu_schedule = np.asarray(mu, dtype=float)
        if len(mu_schedule) != months:
            raise ValueError(
                f"mu schedule must have length {months} (one value per "
                f"month), got {len(mu_schedule)}"
            )

    # paths[:, 0] = starting point; we simulate `months` steps after that
    paths = np.zeros((simulations, months + 1))
    paths[:, 0] = starting_monthly_streams

    for t in range(1, months + 1):
        z = np.random.standard_normal(simulations)
        drift = (mu_schedule[t - 1] - (sigma ** 2) / 2) * dt
        shock = sigma * np.sqrt(dt) * z
        paths[:, t] = paths[:, t - 1] * np.exp(drift + shock)

    # Total streams over the horizon (excluding the starting month-0 value,
    # since that's a snapshot, not a month of accumulated streams)
    total_streams_per_sim = paths[:, 1:].sum(axis=1)
    cumulative_revenue = total_streams_per_sim * price_per_stream

    recouped = np.sum(cumulative_revenue >= advance)
    probability_of_recoupment = (recouped / simulations) * 100

    return {
        "paths": paths,
        "cumulative_revenue": cumulative_revenue,
        "probability_of_recoupment": float(probability_of_recoupment),
        "median_revenue": float(np.median(cumulative_revenue)),
        "advance": float(advance),
    }


# --- Label benchmark profiles -------------------------------------------
#
# These thresholds encode each label's stated/assumed risk appetite.
# They're intentionally simple boolean/scored checks — easy to tune
# later once you have real signing outcomes to calibrate against.
#
# NOTE ON UNITS (important): these thresholds were re-tuned for the
# Last.fm-based metrics (see concentration_risk() and fan_loyalty_ratio()
# docstrings above) —
#   - max_cr: loosened roughly 1.5x from the original Spotify-era values,
#     since raw playcounts tend to be more skewed than Spotify's
#     compressed 0-100 popularity scale (a viral hit can have 10-50x the
#     plays of a deep cut, not just 2-3x).
#   - min_flr: now in "average plays per listener" units instead of the
#     old followers/(popularity*1000) formula. These are rough estimates,
#     not derived from real data — I don't have a solid reference for
#     what's "typical" here. Treat every number in this dict as a
#     starting point: run a few real artists through and adjust based on
#     whether the fit/no-fit calls feel right to you.
#   - max_hit_age_years: how old (playcount-weighted average, see
#     catalog_recency()) a catalog's dominant hits can be before this
#     label profile considers it a "past the growth window" catalog
#     rather than a current one. Faster-moving, trend/virality-driven
#     imprints get a tighter number; legacy/catalog-oriented labels get
#     more slack. These are judgment calls, not researched figures —
#     retune freely.

LABEL_PROFILES = {
    "Dreamville": {
        "max_cr": 2.7,
        "min_flr": 15,
        "max_hit_age_years": 3.0,
        "description": "Low concentration risk, high fan loyalty, steady catalog depth.",
    },
    "TDE": {
        "max_cr": 2.7,
        "min_flr": 15,
        "max_hit_age_years": 3.0,
        "description": "Low concentration risk, high fan loyalty, steady catalog depth.",
    },
    "Cactus Jack": {
        "max_cr": 5.0,
        "min_flr": 0,
        "min_mu": 0.03,
        "max_hit_age_years": 2.5,
        "description": "Tolerates hit-driven catalogs, prioritizes growth velocity.",
    },
    "OVO": {
        "max_cr": 5.0,
        "min_flr": 0,
        "min_mu": 0.03,
        "max_hit_age_years": 3.0,
        "description": "Tolerates hit-driven catalogs, prioritizes growth velocity.",
    },
    "Motown": {
        "max_cr": 3.0,
        "min_flr": 10,
        "max_hit_age_years": 5.0,
        "description": "Assumed profile — steady catalog depth, moderate fan loyalty floor.",
    },
    "Interscope": {
        "max_cr": 4.5,
        "min_flr": 5,
        "min_mu": 0.02,
        "max_hit_age_years": 3.0,
        "description": "Assumed profile — major-label generalist: tolerates some hit-dependence, wants steady growth.",
    },
    "Opium": {
        "max_cr": 6.0,
        "min_flr": 2,
        "min_mu": 0.04,
        "max_hit_age_years": 2.0,
        "description": "Assumed profile — Playboi Carti's imprint: tolerates high concentration risk (viral/aesthetic-driven singles), prioritizes fast growth over catalog depth or broad fan loyalty.",
    },
    "Def Jam Recordings": {
        "max_cr": 4.5,
        "min_flr": 5,
        "min_mu": 0.02,
        "max_hit_age_years": 3.0,
        "description": "Assumed profile — legacy mainstream rap major: moderate risk tolerance, values crossover commercial potential.",
    },
    "Death Row Records": {
        "max_cr": 5.0,
        "min_flr": 3,
        "min_mu": 0.03,
        "max_hit_age_years": 4.0,
        "description": "Assumed profile — historically star/hit-driven and aggressive; tolerates high concentration risk for a breakout artist.",
    },
    "Cash Money Records": {
        "max_cr": 5.0,
        "min_flr": 4,
        "min_mu": 0.03,
        "max_hit_age_years": 3.5,
        "description": "Assumed profile — hit-driven commercial rap/pop crossover, built around star power over catalog depth.",
    },
    "Bad Boy Records": {
        "max_cr": 4.8,
        "min_flr": 4,
        "min_mu": 0.025,
        "max_hit_age_years": 4.0,
        "description": "Assumed profile — image and star-driven, tolerant of hit concentration in service of crossover appeal.",
    },
    "Aftermath Entertainment": {
        "max_cr": 2.2,
        "min_flr": 18,
        "min_mu": 0.02,
        "max_hit_age_years": 4.0,
        "description": "Assumed profile — famously selective/low-volume roster; wants deep catalog quality and loyalty, not just a viral single.",
    },
    "Collective Music Group": {
        "max_cr": 4.2,
        "min_flr": 6,
        "min_mu": 0.025,
        "max_hit_age_years": 2.5,
        "description": "Assumed profile — contemporary trap/hip-hop imprint, moderate risk tolerance with an emphasis on growth.",
    },
    "pgLang": {
        "max_cr": 2.4,
        "min_flr": 15,
        "max_hit_age_years": 3.0,
        "description": "Assumed profile — boutique, artist-development-focused: prioritizes catalog depth and creative reputation over rapid growth.",
    },
    "UMG": {
        "max_cr": 4.5,
        "min_flr": 5,
        "min_mu": 0.02,
        "max_hit_age_years": 3.0,
        "description": "Assumed profile — major-label generalist, similar risk appetite to Interscope (a UMG imprint).",
    },

    # --- Additional majors / imprints -----------------------------------
    "Republic Records": {
        "max_cr": 4.0,
        "min_flr": 6,
        "min_mu": 0.02,
        "max_hit_age_years": 3.0,
        "description": "Assumed profile — major pop/hip-hop powerhouse (Drake, Ariana Grande, Metro Boomin): expects big streaming scale and steady growth, moderate hit-dependence tolerance.",
    },
    "Columbia Records": {
        "max_cr": 4.0,
        "min_flr": 6,
        "min_mu": 0.02,
        "max_hit_age_years": 3.0,
        "description": "Assumed profile — major-label generalist across genres, similar risk appetite to Republic/Interscope.",
    },
    "Interscope Geffen A&M": {
        "max_cr": 4.5,
        "min_flr": 5,
        "min_mu": 0.02,
        "max_hit_age_years": 3.0,
        "description": "Assumed profile — the combined Interscope umbrella (IGA): same risk appetite as the standalone Interscope profile above.",
    },

    # --- Indie / alternative ---------------------------------------------
    "Sub Pop Records": {
        "max_cr": 3.0,
        "min_flr": 12,
        "max_hit_age_years": 4.0,
        "description": "Assumed profile — storied indie/alt label (Nirvana's old home): values a loyal cult following and catalog depth over chart velocity.",
    },
    "Matador Records": {
        "max_cr": 3.0,
        "min_flr": 12,
        "max_hit_age_years": 4.0,
        "description": "Assumed profile — critically-driven indie label: prioritizes a devoted listener base over hit concentration.",
    },
    "Fueled by Ramen": {
        "max_cr": 3.5,
        "min_flr": 8,
        "min_mu": 0.015,
        "max_hit_age_years": 3.0,
        "description": "Assumed profile — pop-punk/emo home (Paramore, Twenty One Pilots): built on loyal fanbases, with room for growth-stage acts.",
    },
    "Third Man Records": {
        "max_cr": 2.8,
        "min_flr": 14,
        "max_hit_age_years": 5.0,
        "description": "Assumed profile — Jack White's boutique label: very niche/collector-driven, prioritizes deep fan loyalty over scale.",
    },
    "Astralwerks": {
        "max_cr": 3.5,
        "min_flr": 8,
        "min_mu": 0.02,
        "max_hit_age_years": 3.0,
        "description": "Assumed profile — electronic/alt crossover imprint (Halsey, Flume): moderate risk tolerance, values growth trajectory.",
    },

    # --- Electronic / dance ------------------------------------------------
    "Ultra Records": {
        "max_cr": 5.0,
        "min_flr": 3,
        "min_mu": 0.03,
        "max_hit_age_years": 2.5,
        "description": "Assumed profile — big-room EDM label: tolerates high hit concentration and lower per-listener loyalty, hype/velocity-driven.",
    },
    "Anjunabeats / Anjunadeep": {
        "max_cr": 3.0,
        "min_flr": 10,
        "max_hit_age_years": 3.5,
        "description": "Assumed profile — trance/deep house imprints known for unusually dedicated fan communities: values loyalty over viral scale.",
    },
    "Ninja Tune": {
        "max_cr": 3.0,
        "min_flr": 10,
        "max_hit_age_years": 4.0,
        "description": "Assumed profile — boutique leftfield electronic/hip-hop label: catalog depth and listener loyalty over mainstream velocity.",
    },

    # --- Country -----------------------------------------------------------
    "Big Machine Label Group": {
        "max_cr": 4.0,
        "min_flr": 7,
        "min_mu": 0.02,
        "max_hit_age_years": 3.0,
        "description": "Assumed profile — mainstream country-pop major (Taylor Swift's former home): expects commercial scale and steady growth.",
    },
    "MCA Nashville": {
        "max_cr": 3.5,
        "min_flr": 8,
        "max_hit_age_years": 4.0,
        "description": "Assumed profile — traditional/mainstream country imprint: values a loyal audience over rapid velocity.",
    },

    # --- Jazz / blues / folk (legacy catalog labels) -----------------------
    "Rounder Records": {
        "max_cr": 2.5,
        "min_flr": 15,
        "max_hit_age_years": 6.0,
        "description": "Assumed profile — roots/folk/bluegrass label: low-volume, catalog-and-loyalty-driven, tolerant of an older-skewing catalog.",
    },
    "Blue Note Records": {
        "max_cr": 2.5,
        "min_flr": 18,
        "max_hit_age_years": 6.0,
        "description": "Assumed profile — legendary jazz imprint: deep listener loyalty expected, not a hits-driven or velocity-driven signing.",
    },
    "Impulse! Records": {
        "max_cr": 2.5,
        "min_flr": 18,
        "max_hit_age_years": 6.0,
        "description": "Assumed profile — jazz label in the same mold as Blue Note: catalog depth and loyalty over scale or recency.",
    },
    "Alligator Records": {
        "max_cr": 2.5,
        "min_flr": 15,
        "max_hit_age_years": 6.0,
        "description": "Assumed profile — blues specialty label: small, devoted audience expected; an aging catalog isn't disqualifying here.",
    },

    # --- Metal / punk --------------------------------------------------------
    "Nuclear Blast": {
        "max_cr": 3.0,
        "min_flr": 12,
        "max_hit_age_years": 4.0,
        "description": "Assumed profile — major metal label: fanbase loyalty (touring, merch, album sales) matters more than streaming hit concentration.",
    },
    "Epitaph Records": {
        "max_cr": 3.2,
        "min_flr": 10,
        "max_hit_age_years": 4.0,
        "description": "Assumed profile — punk institution (Bad Religion, NOFX): cult loyalty valued over mainstream streaming velocity.",
    },
    "Metal Blade Records": {
        "max_cr": 3.0,
        "min_flr": 12,
        "max_hit_age_years": 4.0,
        "description": "Assumed profile — metal label in the Nuclear Blast mold: loyalty-driven, tolerant of a slower-moving catalog.",
    },
}



def label_benchmark_fit(
    cr: float, flr: float, mu: float, catalog_recency_years: float | None = None
) -> dict:
    """
    Score an artist's metrics against each predefined label profile.

    Parameters
    ----------
    cr : float
        Concentration Risk score (from concentration_risk()).
    flr : float
        Fan Loyalty Ratio (from fan_loyalty_ratio()).
    mu : float
        Expected monthly growth rate used in the Monte Carlo sim.
    catalog_recency_years : float | None
        Playcount-weighted average age of the artist's top tracks, from
        catalog_recency(). Checked against each profile's
        "max_hit_age_years" when both are available. None (no Spotify
        release-date match for any track) skips this check entirely
        rather than treating missing data as a failure.

    Returns
    -------
    dict
        {label_name: {"fits": bool, "reasons": list[str]}}
        for every profile in LABEL_PROFILES.
    """
    results = {}

    for label, rules in LABEL_PROFILES.items():
        reasons = []
        fits = True

        if "max_cr" in rules and cr > rules["max_cr"]:
            fits = False
            reasons.append(f"CR {cr:.2f} exceeds max {rules['max_cr']}")

        if "min_flr" in rules and flr < rules["min_flr"]:
            fits = False
            reasons.append(f"FLR {flr:.2f} below min {rules['min_flr']}")

        if "min_mu" in rules and mu < rules["min_mu"]:
            fits = False
            reasons.append(f"Growth mu {mu:.2%} below min {rules['min_mu']:.2%}")

        if (
            "max_hit_age_years" in rules
            and catalog_recency_years is not None
            and catalog_recency_years > rules["max_hit_age_years"]
        ):
            fits = False
            reasons.append(
                f"Catalog recency {catalog_recency_years:.1f}y exceeds max "
                f"{rules['max_hit_age_years']}y — hits skew too old for this profile"
            )

        if fits:
            reasons.append("Meets all thresholds for this profile.")

        results[label] = {"fits": fits, "reasons": reasons}

    return results


if __name__ == "__main__":
    # Quick manual smoke test with made-up numbers (no API calls needed).
    # These are now playcount-scale numbers, matching what lastfm_client
    # would actually return (millions of plays, not 0-100 scores).
    sample_popularities = [8_800_000, 6_000_000, 5_500_000, 5_000_000,
                            4_800_000, 4_500_000, 4_000_000, 3_800_000,
                            3_500_000, 3_000_000]
    cr = concentration_risk(sample_popularities)
    flr = fan_loyalty_ratio(listeners=1_200_000, playcount=18_000_000)

    print(f"Concentration Risk: {cr:.2f}")
    print(f"Fan Loyalty Ratio: {flr:.2f}")

    mc = run_monte_carlo_recoupment(
        advance=250_000,
        starting_monthly_streams=3_000_000,
        mu=0.02,
        sigma=0.15,
        random_seed=42,
    )
    print(f"Probability of Recoupment: {mc['probability_of_recoupment']:.1f}%")
    print(f"Median 24-month Revenue: ${mc['median_revenue']:,.0f}")

    fit = label_benchmark_fit(cr, flr, mu=0.02)
    for label, result in fit.items():
        print(f"\n{label}: {'FITS' if result['fits'] else 'does not fit'}")
        for reason in result["reasons"]:
            print(f"  - {reason}")
