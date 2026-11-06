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

LABEL_PROFILES = {
    "Dreamville": {
        "max_cr": 2.7,
        "min_flr": 15,
        "description": "Low concentration risk, high fan loyalty, steady catalog depth.",
    },
    "TDE": {
        "max_cr": 2.7,
        "min_flr": 15,
        "description": "Low concentration risk, high fan loyalty, steady catalog depth.",
    },
    "Cactus Jack": {
        "max_cr": 5.0,
        "min_flr": 0,
        "min_mu": 0.03,
        "description": "Tolerates hit-driven catalogs, prioritizes growth velocity.",
    },
    "OVO": {
        "max_cr": 5.0,
        "min_flr": 0,
        "min_mu": 0.03,
        "description": "Tolerates hit-driven catalogs, prioritizes growth velocity.",
    },
    "Motown": {
        "max_cr": 3.0,
        "min_flr": 10,
        "description": "Assumed profile — steady catalog depth, moderate fan loyalty floor.",
    },
    "Interscope": {
        "max_cr": 4.5,
        "min_flr": 5,
        "min_mu": 0.02,
        "description": "Assumed profile — major-label generalist: tolerates some hit-dependence, wants steady growth.",
    },
    "Opium": {
        "max_cr": 6.0,
        "min_flr": 2,
        "min_mu": 0.04,
        "description": "Assumed profile — Playboi Carti's imprint: tolerates high concentration risk (viral/aesthetic-driven singles), prioritizes fast growth over catalog depth or broad fan loyalty.",
    },
    "Def Jam Recordings": {
        "max_cr": 4.5,
        "min_flr": 5,
        "min_mu": 0.02,
        "description": "Assumed profile — legacy mainstream rap major: moderate risk tolerance, values crossover commercial potential.",
    },
    "Death Row Records": {
        "max_cr": 5.0,
        "min_flr": 3,
        "min_mu": 0.03,
        "description": "Assumed profile — historically star/hit-driven and aggressive; tolerates high concentration risk for a breakout artist.",
    },
    "Cash Money Records": {
        "max_cr": 5.0,
        "min_flr": 4,
        "min_mu": 0.03,
        "description": "Assumed profile — hit-driven commercial rap/pop crossover, built around star power over catalog depth.",
    },
    "Bad Boy Records": {
        "max_cr": 4.8,
        "min_flr": 4,
        "min_mu": 0.025,
        "description": "Assumed profile — image and star-driven, tolerant of hit concentration in service of crossover appeal.",
    },
    "Aftermath Entertainment": {
        "max_cr": 2.2,
        "min_flr": 18,
        "min_mu": 0.02,
        "description": "Assumed profile — famously selective/low-volume roster; wants deep catalog quality and loyalty, not just a viral single.",
    },
    "Collective Music Group": {
        "max_cr": 4.2,
        "min_flr": 6,
        "min_mu": 0.025,
        "description": "Assumed profile — contemporary trap/hip-hop imprint, moderate risk tolerance with an emphasis on growth.",
    },
    "pgLang": {
        "max_cr": 2.4,
        "min_flr": 15,
        "description": "Assumed profile — boutique, artist-development-focused: prioritizes catalog depth and creative reputation over rapid growth.",
    },
    "UMG": {
        "max_cr": 4.5,
        "min_flr": 5,
        "min_mu": 0.02,
        "description": "Assumed profile — major-label generalist, similar risk appetite to Interscope (a UMG imprint).",
    },
}



def label_benchmark_fit(cr: float, flr: float, mu: float) -> dict:
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
