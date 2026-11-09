# A&R Artist Investment & Risk Analytics

A quantitative scouting tool for evaluating whether to sign an artist. Type
an artist name, set a proposed advance and royalty rate, and get a
data-driven read on recoupment odds, hit-dependence risk, fan loyalty,
catalog freshness, and fit against 41 label profiles — backed by a Monte
Carlo revenue simulation. Supports side-by-side comparison of two artists.

**[Open the live app →](https://rlingard5-artist-risk-projection-app-rgqss2.streamlit.app/)**

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Streamlit](https://img.shields.io/badge/built%20with-Streamlit-FF4B4B)
![Status](https://img.shields.io/badge/status-active-brightgreen)

> **Disclaimer:** The formulas and label thresholds here are this project's
> own modeling assumptions, not industry-standard metrics. They're meant to
> give a consistent, explainable starting point for a conversation — not a
> replacement for A&R judgment.

---

## Contents

- [What it does](#what-it-does)
- [Screenshot](#screenshot)
- [How the metrics work](#how-the-metrics-work)
- [Label profiles](#label-profiles)
- [Recalibration methodology](#recalibration-methodology)
- [What each label looks for](#what-each-label-looks-for)
- [Run it locally](#run-it-locally)
- [Project structure](#project-structure)
- [Known limitations](#known-limitations)

---

## What it does

Enter an artist's name and a proposed advance, and the dashboard returns:

| | |
|---|---|
| 🎯 **Recoupment odds** | Monte Carlo simulation of 24 months of streaming revenue against the advance |
| 📈 **5 growth scenarios** | No growth · Positive · Positive-then-negative · Negative · Negative-then-positive, compared side by side |
| 💰 **Royalty-rate slider** | Set the artist's royalty rate (10–50% of streaming revenue) — only that share counts toward recoupment, not 100% of gross streaming revenue |
| 🎵 **Concentration Risk** | How dependent the artist's numbers are on one song vs. the rest of their catalog |
| ❤️ **Fan Loyalty Ratio** | Average plays per listener — a proxy for a sticky fanbase vs. one-and-done listening |
| 🕒 **Hit Timeline** | Flags a stale catalog, an unproven one-hit spike, or a **recent album that landed no hits** (a flop, not just a quiet period) |
| 📊 **Data confidence flag** | Warns when an artist's Last.fm listener count is too small for CR/FLR ratios to be statistically meaningful |
| 🎸 **Genre fit** | A label only gets credit for "fitting" an artist whose genre it actually signs — great numbers don't make a rap label sign an indie-pop band |
| 🏷️ **Label Benchmark Fit** | Ranks the artist against 41 label profiles — majors, artist-led hip-hop/R&B imprints, indie, country, jazz/blues, EDM, metal/punk |
| ⚖️ **Side-by-side compare** | Evaluate two artists against the same advance and label at once |
| 💵 **Deals up to $1B** | Advance input supports everything from a developing-artist deal to a superstar-scale signing |

All of it runs off just an artist name — no manual data entry required, since
Spotify (name/photo) and Last.fm (listener/playcount/track data) are queried
automatically.

## Screenshot

![Dashboard screenshot](docs/screenshot.png)

## How the metrics work

The underlying philosophy: real labels sign artists primarily when they've
already proven **market traction** (real listener numbers, not just hype),
**commercial potential** (room to grow, odds of recouping an advance), and a
**clear identity** (a genre/sound that fits what this specific label signs).
Every metric below maps to one of those three things — none of them
substitute for the others, which is why a label can fail to "fit" on genre
alone even with perfect numbers, or on numbers alone even in the right genre.

- **Concentration Risk (CR)** = top track's plays ÷ average of tracks 2–10.
  Higher means more dependent on one song. *(Traction)*
- **Fan Loyalty Ratio (FLR)** = total playcount ÷ unique listeners. Higher
  means fans replay the artist rather than listening once. *(Traction)*
- **Hit Timeline** classifies the catalog as: *(Traction)*
  - 🟢 **Fresh & sustained** — a hit from the last 2 years, backed up by
    an earlier hit or multiple recent hits together
  - 🟡 **Unproven spike** — a recent hit (within 2 years) with nothing else
    on the timeline supporting it (could be a trend, could be a fluke)
  - 🟡 **Aging but active** — nothing brand-new, nothing ancient either
  - 🔴 **Recent flop** — the artist put out a full album within the last 2
    years, but none of their top tracks are from it; a release that didn't
    land, not just a quiet period
  - 🔴 **Stale** — even the newest hit is older than 6 years
- **Data confidence** flags when an artist's Last.fm listener count is small
  enough that CR and FLR (both ratios) get noisy — a single very active fan
  can swing them. Below 1,000 listeners is flagged low confidence, below
  10,000 is moderate; results below high confidence should be read as
  directional, not precise. *(Traction)*
- **Royalty-rate slider** controls what share of gross streaming revenue
  actually flows to the artist and counts toward recouping the advance
  (10–50%, default 20%) — modeling 100% of streaming revenue as "the
  artist's money" overstates recoupment odds, since real deals only pay out
  a royalty percentage. *(Commercial potential)*
- **Genre fit** compares the artist's Last.fm genre tags against each
  label's accepted genres (substring matching, so "conscious hip hop"
  still matches a label that signs "hip hop"). A mismatch fails that
  label's fit check outright, regardless of how strong the numbers are —
  a rap label isn't a fit for an indie-pop band no matter its fan loyalty
  score. The big major-label generalists (Interscope, UMG, Republic,
  Columbia, Interscope Geffen A&M) have no genre restriction, since they
  sign across nearly every genre as a matter of business model. An artist
  with no genre tags at all skips this check rather than being penalized
  for missing data. *(Identity)*
- **Monte Carlo simulation** models monthly stream counts as a random walk
  (geometric Brownian motion), converts to revenue at an assumed
  price-per-stream, and reports what share of simulated outcomes clear the
  advance (now supports advances up to **$1 billion**, for deals that scale
  into superstar territory). *(Commercial potential)*
- **Size-scaled investment boost**: the growth-scenario math assumes a fixed
  fraction of the advance goes to promotion, but that spend doesn't move
  every artist equally. The same dollar amount buys proportionally more
  growth for a developing artist than for an established one — both
  because it's a bigger share of a smaller artist's existing revenue, and
  because of an explicit size-tier multiplier on top of that ratio:

  | Listener tier | Boost multiplier | Monthly growth cap |
  |---|---|---|
  | Under 1M listeners (emerging) | 2.0x | up to +15%/month |
  | 1M – 10M listeners (growing) | 1.0x (baseline) | up to +8%/month |
  | 10M+ listeners (established/superstar) | 0.4x | up to +3%/month |

  This is this app's own modeling assumption, not a real industry formula —
  the intent is to capture that a label's marketing dollars meaningfully
  move the needle for a developing artist, but barely register against a
  superstar's existing momentum. *(Commercial potential)*
- **Label Benchmark Fit** combines all of the above — genre, CR, FLR,
  growth rate, and catalog recency — against each label's thresholds in
  `risk_engine.py`'s `LABEL_PROFILES` dict. Most labels' thresholds are now
  calibrated against real signing history (see below), not pure guesswork.
- **Side-by-side compare** runs the whole pipeline twice (once per artist)
  against the same advance, royalty rate and target label, so you can put
  two prospects head to head. Because a single manually-entered stream
  count can't honestly represent two different artists, compare mode
  auto-estimates current streams for both from their own Last.fm data.

## Label profiles

41 labels across seven categories, each with its own CR/FLR/growth/recency/genre
thresholds reflecting a different risk appetite. Most of the hip-hop/R&B
imprints below were recalibrated using a real roster dataset — see
[Recalibration methodology](#recalibration-methodology):

| Category | Labels |
|---|---|
| Major / hip-hop & pop | Dreamville, TDE, Cactus Jack, OVO, Interscope Geffen A&M, Opium, UMG, Def Jam, Death Row, Cash Money, Young Money, Bad Boy, Aftermath, Collective Music Group, pgLang, Republic, Columbia |
| Artist-led hip-hop / R&B imprints | GOOD Music, 1017 Records, YSL Records, Maybach Music Group, Roc Nation, Starboy Entertainment |
| Indie / alternative | Sub Pop, Matador, Fueled by Ramen, Third Man, Astralwerks |
| Electronic / dance | Ultra, Anjunabeats/Anjunadeep, Ninja Tune |
| Country | Big Machine Label Group, MCA Nashville |
| Jazz / blues / folk | Motown, Rounder, Blue Note, Impulse!, Alligator |
| Metal / punk | Nuclear Blast, Epitaph, Metal Blade |

The in-app dropdown lets you type to jump straight to any label.

## Recalibration methodology

The CR/FLR/growth thresholds below can't be computed directly from real
streaming numbers inside this project's own data pipeline, because that
would require live Spotify/Last.fm API calls per historical artist (which
needs API credentials this repo doesn't ship with). Instead, many labels
were recalibrated against a real dataset of **actual signed artists per
label** — who each label signed, what they'd released *before* signing
(nothing yet vs. a mixtape vs. an already-charting album), and what genres
their rosters actually span.

That signing-stage evidence is a legitimate proxy for risk tolerance even
without streaming numbers: a label whose real roster is almost entirely
"signed off one mixtape with no album out yet" (e.g. TDE, Cactus Jack,
Opium, 1017 Records) has demonstrably low standards for proven traction —
so `min_flr` was lowered for several of these to reflect that. A label
whose roster mixes totally unproven acts with already-established stars
(e.g. Death Row, Maybach Music Group) keeps a wider-ranging profile.
Genre lists were also corrected and expanded against real signees — for
example Starboy Entertainment's roster (L.A.X., Terri) is Afrobeats, which
was missing from its genre list before this pass. A new label, **Young
Money Entertainment**, was added after its real signings (Drake, Nicki
Minaj, Tyga) turned up in the dataset with no existing profile.

Each recalibrated label's `description` in `risk_engine.py` now names the
real artists and signing stage behind its numbers, instead of saying
"Assumed profile." Labels with no signing data available (no roster rows
in the dataset — mostly the major generalists, country, jazz/blues, and
metal labels) are unchanged and still hand-estimated.

A follow-up pass added a **"Pre-Signing Platform & Context Metrics"**
column with approximate real numbers (e.g. "~50M streams on 'Mo Bamba'",
"500k+ mixtape downloads", or "Pre-Streaming" for artists signed before
streaming existed). That's still not the same thing this app's `min_flr`
measures (Fan Loyalty Ratio, a ratio of plays per listener) — raw
pre-signing reach doesn't convert into a ratio without the artist's actual
track-level data. But it's a real, concrete proxy for how much *growth
momentum* a label typically expects walking in, which maps cleanly to
`min_mu` (the minimum monthly growth rate used in the label-fit check).
Where a label's real roster showed consistently high pre-signing
momentum — Cactus Jack (5M–50M streams), Collective Music Group
(2M–25M) — `min_mu` was raised. Where it showed consistently modest or
zero momentum — Young Money (250k–500k), GOOD Music (0–100k, several
pre-streaming-era signees) — `min_mu` was lowered. pgLang's `min_mu` is
new but based on a single data point (Baby Keem, ~50M streams), so it's
flagged as provisional in the table above rather than treated as solid.
Every other label's `description` was enriched with the real figures even
where the number itself didn't move.

A third pass added real **post-signing outcomes** — RIAA certifications
(Gold/Platinum/Multi-Platinum/Diamond) and Billboard Hot 100 / Billboard
200 placements for each artist's first project after signing. This doesn't
feed any formula directly either (it's an outcome, not an input the
risk-fit math consumes), but it's the strongest evidence yet that these
labels' aggressive, low-traction-tolerant signing patterns actually work:
Bad Boy's Notorious B.I.G. bet (signed off one single) returned a 6x
Multi-Platinum album; Aftermath's zero-traction signings of Eminem, 50
Cent and The Game went 5x/9x/2x Multi-Platinum; Young Money's Drake and
Nicki Minaj (signed off a few hundred thousand mixtape downloads) both
debuted at #1 on the Billboard 200. Every recalibrated label's
`description` in `risk_engine.py` now names at least one concrete
real-world outcome alongside the signing-stage and pre-signing-reach
evidence, so a label's risk tolerance isn't just "this is what they took a
chance on" but "and here's how often that chance paid off."

## What each label looks for

Exact thresholds per label, straight from `risk_engine.py`'s `LABEL_PROFILES`
(so this table can't drift out of sync with the code). "—" means that check
is skipped for this label. "Any (genre-agnostic)" means the label signs
across genres and isn't genre-gated.

| Label | Max CR | Min FLR | Min growth/mo | Max hit age | Genres signed |
|---|---|---|---|---|---|
| 1017 Records | 5.5 | 2 | 3.5% | 2.0y | hip hop, rap, trap |
| Aftermath Entertainment | 2.2 | 14 | 2.0% | 4.0y | hip hop, rap, r&b, rnb |
| Alligator Records | 2.5 | 15 | — | 6.0y | blues |
| Anjunabeats / Anjunadeep | 3.0 | 10 | — | 3.5y | trance, deep house, progressive house, electronic, edm |
| Astralwerks | 3.5 | 8 | 2.0% | 3.0y | electronic, alternative, pop, indietronica, dance |
| Bad Boy Records | 4.8 | 4 | 2.5% | 4.0y | hip hop, rap, r&b, rnb |
| Big Machine Label Group | 4.0 | 7 | 2.0% | 3.0y | country, country pop |
| Blue Note Records | 2.5 | 18 | — | 6.0y | jazz |
| Cactus Jack | 5.0 | 0 | 3.5% | 2.5y | hip hop, rap, trap |
| Cash Money Records | 5.0 | 4 | 3.0% | 3.5y | hip hop, rap |
| Collective Music Group | 4.2 | 4 | 3.0% | 2.5y | hip hop, rap, drill, trap |
| Columbia Records | 4.0 | 6 | 2.0% | 3.0y | Any (genre-agnostic) |
| Death Row Records | 5.0 | 3 | 3.0% | 4.0y | hip hop, rap, gangsta rap, west coast rap |
| Def Jam Recordings | 4.5 | 5 | 2.0% | 3.0y | hip hop, rap |
| Dreamville | 2.7 | 10 | — | 3.0y | hip hop, rap, conscious hip hop, r&b, rnb |
| Epitaph Records | 3.2 | 10 | — | 4.0y | punk, pop punk, hardcore, rock |
| Fueled by Ramen | 3.5 | 8 | 1.5% | 3.0y | pop punk, emo, alternative, rock, alternative rock |
| GOOD Music | 4.0 | 6 | 1.5% | 3.5y | hip hop, rap, r&b, rnb |
| Impulse! Records | 2.5 | 18 | — | 6.0y | jazz |
| Interscope Geffen A&M | 4.5 | 5 | 2.0% | 3.0y | Any (genre-agnostic) |
| MCA Nashville | 3.5 | 8 | — | 4.0y | country |
| Matador Records | 3.0 | 12 | — | 4.0y | indie, alternative, rock, indie rock |
| Maybach Music Group | 4.5 | 4 | 3.0% | 3.5y | hip hop, rap, r&b, rnb |
| Metal Blade Records | 3.0 | 12 | — | 4.0y | metal, thrash metal, heavy metal |
| Motown | 3.0 | 10 | — | 5.0y | soul, r&b, rnb, motown, pop |
| Ninja Tune | 3.0 | 10 | — | 4.0y | electronic, trip hop, leftfield, experimental, hip hop, downtempo |
| Nuclear Blast | 3.0 | 12 | — | 4.0y | metal, heavy metal, death metal |
| OVO | 5.0 | 0 | 3.0% | 3.0y | hip hop, rap, r&b, rnb, dancehall |
| Opium | 6.0 | 2 | 4.0% | 2.0y | hip hop, rap, trap, underground rap |
| Republic Records | 4.0 | 6 | 2.0% | 3.0y | Any (genre-agnostic) |
| Roc Nation | 4.0 | 4 | 2.0% | 3.5y | hip hop, rap, r&b, rnb, pop |
| Rounder Records | 2.5 | 15 | — | 6.0y | folk, bluegrass, americana, roots |
| Starboy Entertainment | 3.0 | 10 | 1.5% | 4.0y | r&b, rnb, pop, alternative r&b, afrobeats |
| Sub Pop Records | 3.0 | 12 | — | 4.0y | indie, alternative, rock, indie rock, grunge |
| TDE | 2.7 | 10 | — | 3.0y | hip hop, rap, conscious hip hop, r&b, rnb |
| Third Man Records | 2.8 | 14 | — | 5.0y | rock, blues, garage rock, alternative, indie |
| UMG | 4.5 | 5 | 2.0% | 3.0y | Any (genre-agnostic) |
| Ultra Records | 5.0 | 3 | 3.0% | 2.5y | edm, house, dance, electronic, electro |
| YSL Records | 5.5 | 2 | 3.5% | 2.5y | hip hop, rap, trap |
| Young Money Entertainment | 4.5 | 4 | 2.0% | 3.0y | hip hop, rap |
| pgLang | 2.4 | 15 | 3.0%* | 3.0y | hip hop, rap, conscious hip hop |

<sub>*pgLang's growth-rate bar is based on a single roster data point (Baby Keem) — see methodology below.</sub>

## Run it locally

```bash
pip install -r requirements.txt
```

Get free API credentials:
- **Spotify** (name search + photo only): create an app at
  [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)
- **Last.fm** (listener/playcount/track data): get a key at
  [last.fm/api/account/create](https://www.last.fm/api/account/create)

Copy `.env.example` to `.env` and fill in your real values:

```
SPOTIFY_CLIENT_ID=your_spotify_client_id_here
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret_here
LASTFM_API_KEY=your_lastfm_api_key_here
```

Then run:

```bash
python -m streamlit run app.py
```

`.env` is gitignored — never commit it. Deploying your own copy on
[Streamlit Community Cloud](https://share.streamlit.io) instead uses its
**Secrets** settings (same three keys, pasted in as TOML) rather than a
`.env` file.

## Project structure

| File | Purpose |
|---|---|
| `app.py` | Streamlit UI — sidebar inputs, KPI cards, charts, label-fit panel |
| `spotify_client.py` | Spotify artist search (name/photo) + track release-date lookup |
| `lastfm_client.py` | Listener count, playcount, and top-track data |
| `risk_engine.py` | CR / FLR / hit-timeline formulas, Monte Carlo simulation, label profiles |
| `charts.py` | All Plotly chart definitions, dark-theme styled |
| `.streamlit/config.toml` | Dark theme configuration |
| `requirements.txt` | Python dependencies |
| `.env.example` | Template for required API keys |

## Known limitations

- Last.fm's `playcount` is a **lifetime total**, not a monthly figure — the
  "auto-estimate current monthly streams" option is a rough heuristic
  (total ÷ 12), not a real stream count. Manual entry is more reliable.
- Last.fm only counts **scrobbles** — plays from users who've connected a
  scrobbling app/plugin to their streaming service. That's a small,
  self-selected slice of an artist's real audience, and adoption varies a
  lot by fanbase: it's a decent proxy for artists whose fans skew toward
  more tech-savvy/indie-leaning listening habits, but can undercount a
  mainstream artist's real streaming volume by 10x or more, since most of
  their fans never set up scrobbling at all. The "Last.fm-to-real-streams
  multiplier" slider (shown when auto-estimate is on) is a manual way to
  correct for this when you know an artist's real numbers are higher —
  it's a fudge factor you set yourself, not derived from any data. When
  you have a real stream count (Spotify for Artists, Chartmetric,
  Soundcharts, etc.), manual entry is always more accurate than either.
- Track release dates are matched by name via Spotify search and can
  occasionally miss or mismatch a generically-titled track.
- Spotify's standard API access no longer exposes `followers`, `popularity`,
  or `genres` for most apps — that's why those fields are sourced from
  Last.fm instead.
- Label thresholds are a mix of hand estimates and the real-roster
  recalibration described above — none of it is validated against actual
  recoupment outcomes, so treat fit results as a starting point, not a
  verdict.
- The roster dataset behind the recalibration has no streaming numbers for
  historical signings (Spotify/Last.fm history for an artist from, say,
  1995 isn't a thing) — so CR/FLR/mu thresholds are still estimates, just
  ones grounded in real signing-stage evidence rather than pure guesswork.
- Genre fit uses substring matching against Last.fm's free-text community
  tags, not a fixed taxonomy — it can occasionally over- or under-match an
  oddly-tagged artist. An artist with no genre tags at all skips the check
  entirely rather than failing on missing data.
- The royalty-rate slider models a single blended rate for the whole deal;
  real contracts often have escalators, recoupable vs. non-recoupable
  costs, and different rates per revenue stream.
