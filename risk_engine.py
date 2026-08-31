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

    CR = popularity(track #1) / (avg popularity(tracks 2-10) + epsilon)

    Interpretation
    --------------
    CR > 2.5 : high viral dependence ("one-hit wonder" risk)
    CR < 1.5 : strong catalog depth

    Parameters
    ----------
    track_popularities : list[int]
        Popularity scores (0-100), ideally the top 10 tracks, already
        sorted descending (get_top_tracks() returns them this way).

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


def fan_loyalty_ratio(followers: int, popularity: int) -> float:
    """
    Calculate Fan Loyalty Ratio (FLR): active committed fans (followers)
    relative to passive playlist-driven exposure (popularity score).

    FLR = followers / (popularity * 1,000)

    A higher FLR suggests a real, engaged fanbase rather than an artist
    who's popular purely because a playlist algorithm is pushing them.

    Parameters
    ----------
    followers : int
        Spotify follower count for the artist.
    popularity : int
        Spotify popularity score (0-100).

    Returns
    -------
    float
        The fan loyalty ratio. Returns float('inf') if popularity is 0
        (can't divide by zero, and zero popularity with any followers
        is maximally "loyal" by this formula's logic).
    """
    if popularity <= 0:
        return float("inf")
    return followers / (popularity * 1000)


def run_monte_carlo_recoupment(
    advance: float,
    starting_monthly_streams: float,
    mu: float,
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
        S_t = S_(t-1) * exp((mu - sigma^2 / 2) * dt + sigma * sqrt(dt) * Z)
        where Z ~ N(0, 1) and dt = 1 (one month per step)

    Parameters
    ----------
    advance : float
        Proposed advance amount in dollars, e.g. 250_000.
    starting_monthly_streams : float
        Estimated current monthly stream count to project forward from.
    mu : float
        Expected monthly stream growth rate (drift), e.g. 0.02 for 2%/mo.
    sigma : float
        Monthly volatility of streams, e.g. 0.15 for 15%/mo.
    months : int
        Contract horizon in months. Defaults to 24.
    simulations : int
        Number of Monte Carlo paths to simulate. Defaults to 1000.
    price_per_stream : float
        Blended royalty rate per stream in dollars.
    random_seed : int | None
        Optional seed for reproducible results (useful for testing/demos).

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

    # paths[:, 0] = starting point; we simulate `months` steps after that
    paths = np.zeros((simulations, months + 1))
    paths[:, 0] = starting_monthly_streams

    for t in range(1, months + 1):
        z = np.random.standard_normal(simulations)
        drift = (mu - (sigma ** 2) / 2) * dt
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
# These thresholds encode each label's stated risk appetite from the
# project brief. They're intentionally simple boolean/scored checks —
# easy to tune later once you have real signing outcomes to calibrate against.
#
# NOTE: Motown's specific thresholds weren't in the original brief, so
# these are a reasonable placeholder (similar spirit to Dreamville/TDE —
# steady catalog depth over hit-chasing). Adjust if you have a different
# read on their actual signing appetite.

LABEL_PROFILES = {
    "Dreamville": {
        "max_cr": 1.8,
        "min_flr": 0.5,
        "description": "Low concentration risk, high fan loyalty, steady catalog depth.",
    },
    "TDE": {
        "max_cr": 1.8,
        "min_flr": 0.5,
        "description": "Low concentration risk, high fan loyalty, steady catalog depth.",
    },
    "Cactus Jack": {
        "max_cr": 3.5,
        "min_flr": 0.0,
        "min_mu": 0.03,
        "description": "Tolerates hit-driven catalogs, prioritizes growth velocity.",
    },
    "OVO": {
        "max_cr": 3.5,
        "min_flr": 0.0,
        "min_mu": 0.03,
        "description": "Tolerates hit-driven catalogs, prioritizes growth velocity.",
    },
    "Motown": {
        "max_cr": 2.0,
        "min_flr": 0.4,
        "description": "Assumed profile — steady catalog depth, moderate fan loyalty floor.",
    },
    "Interscope": {
        "max_cr": 3.0,
        "min_flr": 0.2,
        "min_mu": 0.02,
        "description": "Assumed profile — major-label generalist: tolerates some hit-dependence, wants steady growth.",
    },
    "Opium": {
        "max_cr": 4.0,
        "min_flr": 0.15,
        "min_mu": 0.04,
        "description": "Assumed profile — Playboi Carti's imprint: tolerates high concentration risk (viral/aesthetic-driven singles), prioritizes fast growth over catalog depth or broad fan loyalty.",
    },
    "Def Jam Recordings": {
        "max_cr": 3.0,
        "min_flr": 0.2,
        "min_mu": 0.02,
        "description": "Assumed profile — legacy mainstream rap major: moderate risk tolerance, values crossover commercial potential.",
    },
    "Death Row Records": {
        "max_cr": 3.5,
        "min_flr": 0.1,
        "min_mu": 0.03,
        "description": "Assumed profile — historically star/hit-driven and aggressive; tolerates high concentration risk for a breakout artist.",
    },
    "Cash Money Records": {
        "max_cr": 3.5,
        "min_flr": 0.15,
        "min_mu": 0.03,
        "description": "Assumed profile — hit-driven commercial rap/pop crossover, built around star power over catalog depth.",
    },
    "Bad Boy Records": {
        "max_cr": 3.2,
        "min_flr": 0.15,
        "min_mu": 0.025,
        "description": "Assumed profile — image and star-driven, tolerant of hit concentration in service of crossover appeal.",
    },
    "Aftermath Entertainment": {
        "max_cr": 1.5,
        "min_flr": 0.5,
        "min_mu": 0.02,
        "description": "Assumed profile — famously selective/low-volume roster; wants deep catalog quality and loyalty, not just a viral single.",
    },
    "Collective Music Group": {
        "max_cr": 2.8,
        "min_flr": 0.2,
        "min_mu": 0.025,
        "description": "Assumed profile — contemporary trap/hip-hop imprint, moderate risk tolerance with an emphasis on growth.",
    },
    "pgLang": {
        "max_cr": 1.6,
        "min_flr": 0.4,
        "description": "Assumed profile — boutique, artist-development-focused: prioritizes catalog depth and creative reputation over rapid growth.",
    },
    "UMG": {
        "max_cr": 3.0,
        "min_flr": 0.2,
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
    sample_popularities = [88, 60, 55, 50, 48, 45, 40, 38, 35, 30]
    cr = concentration_risk(sample_popularities)
    flr = fan_loyalty_ratio(followers=1_200_000, popularity=75)

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
