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


# Thresholds for data_confidence() below. CR, FLR, and growth are all
# ratios/rates — with only a handful of listeners, a single superfan
# replaying a track 50 times can swing FLR wildly, and the whole catalog
# can be a couple thousand plays. These are this app's own judgment calls
# about when a sample is "thin," not a statistical significance test.
LOW_CONFIDENCE_LISTENERS = 1_000
MODERATE_CONFIDENCE_LISTENERS = 10_000


def data_confidence(listeners: int) -> dict:
    """
    Flags how much weight to put on an artist's CR/FLR/Hit-Timeline
    numbers, based on how small the underlying Last.fm listener count is.

    A ratio computed from a handful of listeners is statistically noisy —
    a single very active fan can distort it — even though the formula
    itself is identical to one computed from millions of listeners. This
    doesn't change any of the other numbers; it's a flag for how much to
    trust them.

    Parameters
    ----------
    listeners : int
        Unique Last.fm listeners for the artist.

    Returns
    -------
    dict
        {
            "level": str,  # "low" | "moderate" | "high"
            "message": str,
        }
    """
    if listeners < LOW_CONFIDENCE_LISTENERS:
        return {
            "level": "low",
            "message": (
                f"Only {listeners:,} Last.fm listeners — ratios like CR and "
                "FLR are statistically noisy at this scale (a single active "
                "fan can swing them). Treat results as directional, not precise."
            ),
        }
    if listeners < MODERATE_CONFIDENCE_LISTENERS:
        return {
            "level": "moderate",
            "message": (
                f"{listeners:,} Last.fm listeners is a moderate sample — "
                "numbers are more stable than a brand-new artist's, but "
                "still worth a grain of salt."
            ),
        }
    return {
        "level": "high",
        "message": f"{listeners:,} Last.fm listeners is a solid sample size.",
    }


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
STALE_THRESHOLD_YEARS = 6.0   # a catalog whose newest hit is older than this reads as "stale"
RECENT_WINDOW_YEARS = 2.0     # how new a hit has to be to count as "recent"
SUPPORT_WINDOW_YEARS = 4.0    # how far back to look for a hit that "backs up" a recent one


def analyze_hit_timeline(
    track_years_ago: list[float | None],
    latest_album_years_ago: float | None = None,
) -> dict:
    """
    Classifies an artist's hit pattern over time, to catch red flags a raw
    playcount or recency average can miss:

    1. "Stale" — the catalog's numbers are real, but nothing in it is
       recent; the artist may be past their growth window rather than
       still building one.
    2. "Unproven spike" — the artist has one hit from the last ~2 years,
       but nothing else on the timeline backs it up (no earlier hit
       building toward it, no second recent hit alongside it). That's a
       real signal, but on its own it could be a fluke rather than a
       trend — a label betting on this timeline is betting it repeats.
    3. "Recent flop" — the artist released a full album within the last
       RECENT_WINDOW_YEARS, but none of their top tracks by playcount are
       from that recent window at all. That's a stronger, more specific
       negative than plain staleness: this isn't an artist who's been
       quiet, it's one who tried something recently and it didn't catch
       on with listeners.

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
    latest_album_years_ago : float | None
        Years since the artist's most recent album, from
        spotify_client.get_latest_album_years_ago(). None (no album found,
        or the lookup failed) skips the "recent flop" check entirely
        rather than treating missing data as a red flag.

    Returns
    -------
    dict
        {
            "status": str,  # "fresh_and_sustained" | "aging_but_active"
                             # | "unproven_spike" | "stale"
                             # | "recent_flop" | "unknown"
            "most_recent_hit_years_ago": float | None,
            "oldest_hit_years_ago": float | None,
            "known_track_count": int,
            "latest_album_years_ago": float | None,
            "recent_album_no_hit": bool,
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
            "latest_album_years_ago": latest_album_years_ago,
            "recent_album_no_hit": False,
        }

    most_recent = known[0]
    oldest = known[-1]
    has_recent_hit = most_recent <= RECENT_WINDOW_YEARS

    # A recent album that produced nothing in the top-tracks-by-playcount
    # list at all is a stronger signal than plain staleness — the artist
    # clearly tried, and it didn't land with listeners.
    recent_album_no_hit = (
        latest_album_years_ago is not None
        and latest_album_years_ago <= RECENT_WINDOW_YEARS
        and not has_recent_hit
    )

    if not has_recent_hit:
        if recent_album_no_hit:
            status = "recent_flop"
        else:
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
        "latest_album_years_ago": latest_album_years_ago,
        "recent_album_no_hit": recent_album_no_hit,
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
        "min_flr": 10,
        "max_hit_age_years": 3.0,
        "genres": ["hip hop", "rap", "conscious hip hop", "r&b", "rnb"],
        "description": "Calibrated from real signing history — 6 of 7 roster artists (Bas, Omen, Cozz, Lute, JID, EarthGang) were signed off a mixtape or EP with no prior album, with pre-signing reach from ~500k mixtape downloads (Bas) to ~5M indie streams (EarthGang); Ari Lennox brought the roster into R&B. The bet paid off commercially too — JID's debut single went RIAA Gold and charted on the Billboard 200. Low entry bar for traction, but low concentration risk and deep catalog loyalty once developed.",
    },
    "TDE": {
        "max_cr": 2.7,
        "min_flr": 10,
        "max_hit_age_years": 3.0,
        "genres": ["hip hop", "rap", "conscious hip hop", "r&b", "rnb"],
        "description": "Calibrated from real signing history — Jay Rock, Kendrick Lamar, Ab-Soul and Schoolboy Q were all signed in the pre-streaming era with essentially zero digital footprint (street mixtapes/CD handouts); later signees like Doechii arrived with real viral numbers (~15M streams). SZA's debut EP went on to a Gold-certified track and charted on the Billboard 200, confirming the label's bets on unproven talent do convert. Near-zero entry bar for traction historically, but famously low-volume and loyalty-driven once an artist is in.",
    },
    "Cactus Jack": {
        "max_cr": 5.0,
        "min_flr": 0,
        "min_mu": 0.035,
        "max_hit_age_years": 2.5,
        "genres": ["hip hop", "rap", "trap"],
        "description": "Calibrated from real signing history — Sheck Wes (~50M streams on 'Mo Bamba'), Don Toliver (~5M pre-Astroworld) and SoFaygo (~30M on 'Knock Knock') were all already-viral on SoundCloud/Spotify before signing with no album out. Both Sheck Wes's MUDBOY and Don Toliver's Heaven or Hell went RIAA Platinum, backing up the high growth-rate bar (min_mu) this viral-first profile sets.",
    },
    "OVO": {
        "max_cr": 5.0,
        "min_flr": 0,
        "min_mu": 0.03,
        "max_hit_age_years": 3.0,
        "genres": ["hip hop", "rap", "r&b", "rnb", "dancehall"],
        "description": "Calibrated from real signing history — pre-signing reach ranged from near-zero (PARTYNEXTDOOR, Myspace-era demos) to Popcaan's ~20M Caribbean/YouTube streams; most of the roster (Majid Jordan, Roy Woods, DVSN, Smiley) sat in the 1-5M range with no album yet. PARTYNEXTDOOR's zero-traction bet still converted to a Gold-certified lead single. Popcaan's signing adds dancehall to the genre mix alongside hip-hop/R&B.",
    },
    "Motown": {
        "max_cr": 3.0,
        "min_flr": 10,
        "max_hit_age_years": 5.0,
        "genres": ["soul", "r&b", "rnb", "motown", "pop"],
        "description": "Assumed profile — steady catalog depth, moderate fan loyalty floor.",
    },
    "Opium": {
        "max_cr": 6.0,
        "min_flr": 2,
        "min_mu": 0.04,
        "max_hit_age_years": 2.0,
        "genres": ["hip hop", "rap", "trap", "underground rap"],
        "description": "Calibrated from real signing history — Ken Carson (~5M), Destroy Lonely (~10M) and Homixide Gang (~2M) were all signed off SoundCloud/TikTok streams on an early EP, no album yet. Confirms Playboi Carti's imprint takes already-viral, aesthetic-driven acts and prioritizes fast growth over catalog depth or broad fan loyalty.",
    },
    "Def Jam Recordings": {
        "max_cr": 4.5,
        "min_flr": 5,
        "min_mu": 0.02,
        "max_hit_age_years": 3.0,
        "genres": ["hip hop", "rap"],
        "description": "Assumed profile — legacy mainstream rap major: moderate risk tolerance, values crossover commercial potential.",
    },
    "Death Row Records": {
        "max_cr": 5.0,
        "min_flr": 3,
        "min_mu": 0.03,
        "max_hit_age_years": 4.0,
        "genres": ["hip hop", "rap", "gangsta rap", "west coast rap"],
        "description": "Calibrated from real signing history — Snoop Dogg and Tha Dogg Pound were signed off little more than guest features, while 2Pac was already a two-album star when he joined. Confirms a star/hit-driven, aggressive profile willing to bet on raw talent or buy an established name.",
    },
    "Cash Money Records": {
        "max_cr": 5.0,
        "min_flr": 4,
        "min_mu": 0.03,
        "max_hit_age_years": 3.5,
        "genres": ["hip hop", "rap"],
        "description": "Calibrated from real signing history — Lil Wayne (1995) was signed with literally no digital footprint (regional cassette/CD sales only, years before streaming existed), well before he broke commercially. His first post-signing album, Tha Block Is Hot, went RIAA Platinum and hit #3 on the Billboard 200 — the bet on zero traction paid off. Confirms a hit-driven, star-power-over-catalog-depth profile.",
    },
    "Bad Boy Records": {
        "max_cr": 4.8,
        "min_flr": 4,
        "min_mu": 0.025,
        "max_hit_age_years": 4.0,
        "genres": ["hip hop", "rap", "r&b", "rnb"],
        "description": "Calibrated from real signing history — The Notorious B.I.G. (1993, pre-streaming demo tapes) was signed off a single, no album, and went on to Ready to Die: 6x Multi-Platinum, two top-10 Hot 100 hits — one of the highest-conviction bets in this dataset paying off at the highest level. Machine Gun Kelly (~5M early YouTube/DatPiff views) followed the same unproven-to-signed pattern decades later. Confirms an image- and star-driven profile tolerant of hit concentration, with a traction bar that scales to whatever proof of buzz looked like in that era.",
    },
    "Young Money Entertainment": {
        "max_cr": 4.5,
        "min_flr": 4,
        "min_mu": 0.02,
        "max_hit_age_years": 3.0,
        "genres": ["hip hop", "rap"],
        "description": "Calibrated from real signing history — Drake (~500k mixtape downloads on So Far Gone) and Nicki Minaj (~250k mixtape downloads) were both signed at modest pre-signing scale; Tyga had a debut album but no measurable streaming footprint listed. Both bets converted at the highest level — Drake's Thank Me Later and Nicki's Pink Friday both went 4x/3x Multi-Platinum and debuted at #1 on the Billboard 200. That modest entry bar lowered the growth-rate requirement (min_mu) from the original estimate; the hit rate on that low bar has been exceptional.",
    },
    "Aftermath Entertainment": {
        "max_cr": 2.2,
        "min_flr": 14,
        "min_mu": 0.02,
        "max_hit_age_years": 4.0,
        "genres": ["hip hop", "rap", "r&b", "rnb"],
        "description": "Calibrated from real signing history — Eminem, 50 Cent and The Game were all signed with zero digital footprint (pre-streaming cassette/mixtape-CD era), while later signees Kendrick Lamar (~10M) and Anderson .Paak (~15M) arrived with real streaming numbers. The hit rate on those zero-traction bets is extraordinary: Eminem (5x Multi-Platinum), 50 Cent (9x Multi-Platinum, #1 debut) and The Game (2x Multi-Platinum, #1 debut) all broke at the highest commercial tier. Dre signs raw, largely unproven talent despite the label's famously small, low-volume roster, but still wants depth and versatility over a single viral moment, hence the low concentration-risk ceiling.",
    },
    "Collective Music Group": {
        "max_cr": 4.2,
        "min_flr": 4,
        "min_mu": 0.03,
        "max_hit_age_years": 2.5,
        "genres": ["hip hop", "rap", "drill", "trap"],
        "description": "Calibrated from real signing history — Moneybagg Yo (~2M), 42 Dugg (~10M regional Detroit streams) and GloRilla (~25M viral TikTok/Spotify streams) were all signed straight off a mixtape or EP, but with consistently strong pre-signing momentum. Both 42 Dugg and GloRilla's first post-signing projects went RIAA Gold with top-10 Hot 100 hits, confirming that momentum reliably converts here. Low entry bar on catalog depth, but the growth-rate bar (min_mu) was raised to match that real momentum.",
    },
    "pgLang": {
        "max_cr": 2.4,
        "min_flr": 15,
        "min_mu": 0.03,
        "max_hit_age_years": 3.0,
        "genres": ["hip hop", "rap", "conscious hip hop"],
        "description": "Calibrated from real signing history — the one roster data point available, Baby Keem, had ~50M streams on 'ORANGE SODA' before signing (explosive, not just developing, momentum); Tanna Leone was signed off singles only. That bet converted into a Gold-certified, Grammy-winning album (The Melodic Blue, #5 Billboard 200). Still boutique and creative-reputation-focused, but the single clear data point argues for a real growth-rate bar rather than none — treat min_mu here as provisional given the small sample.",
    },
    "UMG": {
        "max_cr": 4.5,
        "min_flr": 5,
        "min_mu": 0.02,
        "max_hit_age_years": 3.0,
        # No "genres" key — same reasoning as Interscope (a UMG imprint).
        "description": "Assumed profile — major-label generalist, similar risk appetite to Interscope (a UMG imprint).",
    },

    # --- Additional majors / imprints -----------------------------------
    "Republic Records": {
        "max_cr": 4.0,
        "min_flr": 6,
        "min_mu": 0.02,
        "max_hit_age_years": 3.0,
        # No "genres" key: major generalist across pop/hip-hop/rock/etc.
        "description": "Assumed profile — major pop/hip-hop powerhouse (Drake, Ariana Grande, Metro Boomin): expects big streaming scale and steady growth, moderate hit-dependence tolerance.",
    },
    "Columbia Records": {
        "max_cr": 4.0,
        "min_flr": 6,
        "min_mu": 0.02,
        "max_hit_age_years": 3.0,
        # No "genres" key — major generalist, same reasoning as Republic.
        "description": "Assumed profile — major-label generalist across genres, similar risk appetite to Republic/Interscope.",
    },
    "Interscope Geffen A&M": {
        "max_cr": 4.5,
        "min_flr": 5,
        "min_mu": 0.02,
        "max_hit_age_years": 3.0,
        # No "genres" key: IGA signs across nearly every genre as a
        # major-label generalist, so it isn't genre-gated like a boutique
        # or identity-driven imprint elsewhere in this dict.
        "description": "Assumed profile — the combined Interscope Geffen A&M umbrella (IGA): major-label generalist, tolerates some hit-dependence, wants steady growth.",
    },

    # --- Indie / alternative ---------------------------------------------
    "Sub Pop Records": {
        "max_cr": 3.0,
        "min_flr": 12,
        "max_hit_age_years": 4.0,
        "genres": ["indie", "alternative", "rock", "indie rock", "grunge"],
        "description": "Assumed profile — storied indie/alt label (Nirvana's old home): values a loyal cult following and catalog depth over chart velocity.",
    },
    "Matador Records": {
        "max_cr": 3.0,
        "min_flr": 12,
        "max_hit_age_years": 4.0,
        "genres": ["indie", "alternative", "rock", "indie rock"],
        "description": "Assumed profile — critically-driven indie label: prioritizes a devoted listener base over hit concentration.",
    },
    "Fueled by Ramen": {
        "max_cr": 3.5,
        "min_flr": 8,
        "min_mu": 0.015,
        "max_hit_age_years": 3.0,
        "genres": ["pop punk", "emo", "alternative", "rock", "alternative rock"],
        "description": "Assumed profile — pop-punk/emo home (Paramore, Twenty One Pilots): built on loyal fanbases, with room for growth-stage acts.",
    },
    "Third Man Records": {
        "max_cr": 2.8,
        "min_flr": 14,
        "max_hit_age_years": 5.0,
        "genres": ["rock", "blues", "garage rock", "alternative", "indie"],
        "description": "Calibrated from real signing history — Margo Price and The Black Belles were both signed with no album out yet. Confirms Jack White's boutique label takes unproven acts into a very niche/collector-driven, deep-fan-loyalty-over-scale profile.",
    },
    "Astralwerks": {
        "max_cr": 3.5,
        "min_flr": 8,
        "min_mu": 0.02,
        "max_hit_age_years": 3.0,
        "genres": ["electronic", "alternative", "pop", "indietronica", "dance"],
        "description": "Assumed profile — electronic/alt crossover imprint (Halsey, Flume): moderate risk tolerance, values growth trajectory.",
    },

    # --- Electronic / dance ------------------------------------------------
    "Ultra Records": {
        "max_cr": 5.0,
        "min_flr": 3,
        "min_mu": 0.03,
        "max_hit_age_years": 2.5,
        "genres": ["edm", "house", "dance", "electronic", "electro"],
        "description": "Assumed profile — big-room EDM label: tolerates high hit concentration and lower per-listener loyalty, hype/velocity-driven.",
    },
    "Anjunabeats / Anjunadeep": {
        "max_cr": 3.0,
        "min_flr": 10,
        "max_hit_age_years": 3.5,
        "genres": ["trance", "deep house", "progressive house", "electronic", "edm"],
        "description": "Calibrated from real signing history — Mat Zo, Ilan Bluestone and Lane 8 were all signed off a single with no album yet. Confirms Above & Beyond's imprints take developing talent but hold them to unusually dedicated fan communities and value loyalty over viral scale.",
    },
    "Ninja Tune": {
        "max_cr": 3.0,
        "min_flr": 10,
        "max_hit_age_years": 4.0,
        "genres": ["electronic", "trip hop", "leftfield", "experimental", "hip hop", "downtempo"],
        "description": "Calibrated from real signing history — Cinematic Orchestra was signed off a single, while Bonobo already had a debut album; both fit a boutique leftfield electronic profile valuing catalog depth and listener loyalty over mainstream velocity.",
    },

    # --- Country -----------------------------------------------------------
    "Big Machine Label Group": {
        "max_cr": 4.0,
        "min_flr": 7,
        "min_mu": 0.02,
        "max_hit_age_years": 3.0,
        "genres": ["country", "country pop"],
        "description": "Assumed profile — mainstream country-pop major (Taylor Swift's former home): expects commercial scale and steady growth.",
    },
    "MCA Nashville": {
        "max_cr": 3.5,
        "min_flr": 8,
        "max_hit_age_years": 4.0,
        "genres": ["country"],
        "description": "Assumed profile — traditional/mainstream country imprint: values a loyal audience over rapid velocity.",
    },

    # --- Jazz / blues / folk (legacy catalog labels) -----------------------
    "Rounder Records": {
        "max_cr": 2.5,
        "min_flr": 15,
        "max_hit_age_years": 6.0,
        "genres": ["folk", "bluegrass", "americana", "roots"],
        "description": "Assumed profile — roots/folk/bluegrass label: low-volume, catalog-and-loyalty-driven, tolerant of an older-skewing catalog.",
    },
    "Blue Note Records": {
        "max_cr": 2.5,
        "min_flr": 18,
        "max_hit_age_years": 6.0,
        "genres": ["jazz"],
        "description": "Assumed profile — legendary jazz imprint: deep listener loyalty expected, not a hits-driven or velocity-driven signing.",
    },
    "Impulse! Records": {
        "max_cr": 2.5,
        "min_flr": 18,
        "max_hit_age_years": 6.0,
        "genres": ["jazz"],
        "description": "Assumed profile — jazz label in the same mold as Blue Note: catalog depth and loyalty over scale or recency.",
    },
    "Alligator Records": {
        "max_cr": 2.5,
        "min_flr": 15,
        "max_hit_age_years": 6.0,
        "genres": ["blues"],
        "description": "Assumed profile — blues specialty label: small, devoted audience expected; an aging catalog isn't disqualifying here.",
    },

    # --- Metal / punk --------------------------------------------------------
    "Nuclear Blast": {
        "max_cr": 3.0,
        "min_flr": 12,
        "max_hit_age_years": 4.0,
        "genres": ["metal", "heavy metal", "death metal"],
        "description": "Assumed profile — major metal label: fanbase loyalty (touring, merch, album sales) matters more than streaming hit concentration.",
    },
    "Epitaph Records": {
        "max_cr": 3.2,
        "min_flr": 10,
        "max_hit_age_years": 4.0,
        "genres": ["punk", "pop punk", "hardcore", "rock"],
        "description": "Calibrated from real signing history — Rancid was signed off just an EP, while The Offspring already had a debut album when they joined. Confirms this punk institution (Bad Religion, NOFX) values cult loyalty over mainstream streaming velocity, whether the artist is developing or already established.",
    },
    "Metal Blade Records": {
        "max_cr": 3.0,
        "min_flr": 12,
        "max_hit_age_years": 4.0,
        "genres": ["metal", "thrash metal", "heavy metal"],
        "description": "Assumed profile — metal label in the Nuclear Blast mold: loyalty-driven, tolerant of a slower-moving catalog.",
    },

    # --- Additional hip-hop / R&B imprints ---------------------------------
    "GOOD Music": {
        "max_cr": 4.0,
        "min_flr": 6,
        "min_mu": 0.015,
        "max_hit_age_years": 3.5,
        "genres": ["hip hop", "rap", "r&b", "rnb"],
        "description": "Calibrated from real signing history — John Legend and Pusha T (via Clipse) were signed with literally no streaming footprint (pre-streaming demo/live-show era), and Big Sean's ~100k mixtape downloads were modest too. Both low-traction bets converted big: John Legend's Get Lifted went 2x Multi-Platinum and Big Sean's Finally Famous went Platinum. That low pre-signing scale lowered the growth-rate bar (min_mu) from the original estimate — Kanye's imprint bets on creative reputation and crossover potential over proven momentum.",
    },
    "1017 Records": {
        "max_cr": 5.5,
        "min_flr": 2,
        "min_mu": 0.035,
        "max_hit_age_years": 2.0,
        "genres": ["hip hop", "rap", "trap"],
        "description": "Calibrated from real signing history — Waka Flocka Flame (~200k downloads), Young Thug (~1M views) and Pooh Shiesty (~15M streams) were all signed off a mixtape or single, none with an album yet, spanning modest regional buzz to real viral reach. Waka Flocka's Flockaveli and Pooh Shiesty's Shiesty Season both went Gold, each carrying a 3x-Platinum single. Confirms Gucci Mane's prolific mixtape-culture label tolerates very high hit concentration and prioritizes release velocity over catalog depth.",
    },
    "YSL Records": {
        "max_cr": 5.5,
        "min_flr": 2,
        "min_mu": 0.035,
        "max_hit_age_years": 2.5,
        "genres": ["hip hop", "rap", "trap"],
        "description": "Calibrated from real signing history — Gunna (~500k mixtape plays) and Lil Keed (~3M streams) were both signed as unproven mixtape-stage artists with no major label track record. Confirms an aggressive, hit-driven trap collective built around viral singles and star power.",
    },
    "Maybach Music Group": {
        "max_cr": 4.5,
        "min_flr": 4,
        "min_mu": 0.03,
        "max_hit_age_years": 3.5,
        "genres": ["hip hop", "rap", "r&b", "rnb"],
        "description": "Calibrated from real signing history — Meek Mill was signed off ~1M mixtape downloads, while Wale was already an established, charting act (Billboard 200 sales via Interscope) joining for a crossover relaunch; Wale's Ambition went Gold and hit #2 on the Billboard 200. Confirms a star-power, crossover-appeal profile open to both developing and already-established talent.",
    },
    "Roc Nation": {
        "max_cr": 4.0,
        "min_flr": 4,
        "min_mu": 0.02,
        "max_hit_age_years": 3.5,
        "genres": ["hip hop", "rap", "r&b", "rnb", "pop"],
        "description": "Calibrated from real signing history — J. Cole (~250k downloads, blog era) and Rihanna (demo CD audition tapes, no music released at all) were both signed with essentially zero traction. Both bets converted: J. Cole's pre-studio mixtape The Warm Up went 2x Platinum on DatPiff (700k+ downloads), and Rihanna's debut Music of the Sun went Gold, hitting #10 on the Billboard 200 with a #2 Hot 100 single. Confirms Jay-Z's company bets on undiscovered talent across hip-hop/R&B/pop, then expects commercial scale and steady growth like a major.",
    },
    "Starboy Entertainment": {
        "max_cr": 3.0,
        "min_flr": 10,
        "min_mu": 0.015,
        "max_hit_age_years": 4.0,
        "genres": ["r&b", "rnb", "pop", "alternative r&b", "afrobeats"],
        "description": "Calibrated from real signing history — L.A.X. and Terri were both signed off a single with no album. Confirms The Weeknd's imprint prioritizes artistic identity and atmosphere over raw hit concentration; roster evidence (both Afrobeats artists) adds that genre to the label's profile.",
    },
}



def _genre_match(artist_genres: list[str], label_genres: list[str]) -> bool:
    """
    True if any of the artist's genre tags overlaps any of a label's
    accepted genres, using substring containment in both directions
    (case-insensitive) rather than exact string equality.

    Last.fm genre tags are free-text community tags, not a fixed taxonomy
    — the same artist might be tagged "rap," "Hip-Hop," or "conscious hip
    hop" depending on who tagged them. Substring matching (e.g. the label
    keyword "hip hop" matching the artist tag "conscious hip hop") catches
    far more of these than exact matching would, at the cost of being a
    little permissive at the edges.
    """
    artist_lower = [g.lower() for g in artist_genres]
    label_lower = [g.lower() for g in label_genres]
    for a in artist_lower:
        for l in label_lower:
            if l in a or a in l:
                return True
    return False


def label_benchmark_fit(
    cr: float,
    flr: float,
    mu: float,
    catalog_recency_years: float | None = None,
    artist_genres: list[str] | None = None,
) -> dict:
    """
    Score an artist's metrics against each predefined label profile.

    Real A&R decisions aren't only about an artist's numbers — genre and
    identity rule labels in or out before the numbers even get discussed
    (a rap label doesn't sign an indie-pop band, no matter how strong its
    fan-loyalty score is). This function checks genre fit first, then the
    same quantitative thresholds (CR, FLR, growth, catalog recency) as
    before, so a label can fail on either identity or traction/commercial
    potential.

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
    artist_genres : list[str] | None
        The artist's Last.fm genre/community tags. Checked against each
        profile's "genres" list when both are present and non-empty. A
        label profile with no "genres" key (the big major-label
        generalists, which sign across nearly every genre) skips this
        check entirely, as does an artist with no genre tags at all —
        missing genre data isn't treated as a mismatch.

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

        if (
            "genres" in rules
            and artist_genres
            and not _genre_match(artist_genres, rules["genres"])
        ):
            fits = False
            reasons.append(
                f"Genre mismatch: artist tagged {', '.join(artist_genres[:3])}; "
                f"this label signs {', '.join(rules['genres'][:3])}"
            )

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


# --- Size-scaled investment boost -----------------------------------------
# A label's marketing spend doesn't move every artist the same amount. The
# same $100k promo budget is a rounding error for an artist already pulling
# tens of millions of monthly streams, but can meaningfully accelerate an
# artist who's still under a million listeners. These tiers are this app's
# own modeling assumption — not a published industry formula — encoding
# "signing helps a small artist more, in relative terms, than a big one."
SIZE_TIERS = [
    # (listener ceiling, multiplier on the computed boost, cap on mu/month)
    (1_000_000, 2.0, 0.15),      # emerging: marketing spend goes furthest here
    (10_000_000, 1.0, 0.08),     # growing: the original baseline behavior
    (float("inf"), 0.4, 0.03),   # established/superstar: diminishing returns
]


def compute_investment_boost(
    advance: float,
    current_monthly_revenue: float,
    listeners: int,
    months: int,
    marketing_spend_fraction: float = 0.10,
) -> float:
    """
    Models how much of a monthly growth-rate boost a label's advance buys,
    on top of an artist's organic growth — this app's own assumption, not
    an industry formula.

    Base idea: the label spends a fixed fraction of the advance on
    promotion, and that spend matters more, proportionally, to an artist
    with less existing monthly revenue (the same dollar amount is a bigger
    relative push). On top of that base ratio, SIZE_TIERS applies an
    explicit multiplier and cap by audience size: an artist under 1M
    listeners gets amplified further (up to 15%/month), a "growing" artist
    (1M-10M listeners) gets the original baseline (up to 8%/month), and an
    established/superstar artist (10M+ listeners) sees sharply diminishing
    returns (up to 3%/month) — a label's marketing dollars just don't move
    the needle much for an artist already at that scale.

    Parameters
    ----------
    advance : float
        Proposed advance amount, in dollars.
    current_monthly_revenue : float
        Artist's current monthly streaming revenue, in dollars.
    listeners : int
        Artist's unique listener count (from Last.fm), used to pick the
        size tier.
    months : int
        Number of months the boost is spread across (the simulation
        horizon).
    marketing_spend_fraction : float
        Share of the advance assumed to go to promotion.

    Returns
    -------
    float
        Monthly growth-rate boost (e.g. 0.08 = +8%/month), already capped
        for the artist's size tier.
    """
    if current_monthly_revenue <= 0 or months <= 0:
        return 0.0

    marketing_spend = advance * marketing_spend_fraction
    raw_boost = marketing_spend / current_monthly_revenue / months

    multiplier, cap = 1.0, 0.08
    for ceiling, tier_multiplier, tier_cap in SIZE_TIERS:
        if listeners < ceiling:
            multiplier, cap = tier_multiplier, tier_cap
            break

    return min(raw_boost * multiplier, cap)


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
