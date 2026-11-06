# A&R Artist Investment & Risk Analytics

A quantitative scouting tool for evaluating whether to sign an artist. Type
an artist name, set a proposed advance, and get a data-driven read on
recoupment odds, hit-dependence risk, fan loyalty, catalog freshness, and
fit against 35 label profiles — backed by a Monte Carlo revenue simulation.

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
| 🎵 **Concentration Risk** | How dependent the artist's numbers are on one song vs. the rest of their catalog |
| ❤️ **Fan Loyalty Ratio** | Average plays per listener — a proxy for a sticky fanbase vs. one-and-done listening |
| 🕒 **Hit Timeline** | Flags a stale catalog (nothing recent) or an unproven one-hit spike (a recent hit with nothing backing it up) |
| 🏷️ **Label Benchmark Fit** | Ranks the artist against 35 label profiles — majors, indie, country, jazz/blues, EDM, metal/punk |

All of it runs off just an artist name — no manual data entry required, since
Spotify (name/photo) and Last.fm (listener/playcount/track data) are queried
automatically.

## Screenshot

*(Add a screenshot or short GIF of the dashboard here — drag an image into
this spot in GitHub's README editor, or run the app, take a screenshot, and
drop it in as `docs/screenshot.png`, then reference it like:)*

```markdown
![Dashboard screenshot](docs/screenshot.png)
```

## How the metrics work

- **Concentration Risk (CR)** = top track's plays ÷ average of tracks 2–10.
  Higher means more dependent on one song.
- **Fan Loyalty Ratio (FLR)** = total playcount ÷ unique listeners. Higher
  means fans replay the artist rather than listening once.
- **Hit Timeline** classifies the catalog as:
  - 🟢 **Fresh & sustained** — a hit from the last ~6 months, backed up by
    an earlier hit or multiple recent hits together
  - 🟡 **Unproven spike** — a recent hit with nothing else on the timeline
    supporting it (could be a trend, could be a fluke)
  - 🟡 **Aging but active** — nothing brand-new, nothing ancient either
  - 🔴 **Stale** — even the newest hit is older than ~4.5 years
- **Monte Carlo simulation** models monthly stream counts as a random walk
  (geometric Brownian motion), converts to revenue at an assumed
  price-per-stream, and reports what share of simulated outcomes clear the
  advance. The growth-scenario math assumes a fixed fraction of the advance
  goes to promotion and translates into a capped monthly growth boost —
  this app's own modeling assumption, not a real industry formula.
- **Label Benchmark Fit** checks CR, FLR, growth rate, and catalog recency
  against each label's thresholds in `risk_engine.py`'s `LABEL_PROFILES`
  dict — rough, manually-set estimates worth recalibrating against real
  outcomes over time.

## Label profiles

35 labels across six categories, each with its own CR/FLR/growth/recency
thresholds reflecting a different risk appetite:

| Category | Labels |
|---|---|
| Major / hip-hop & pop | Dreamville, TDE, Cactus Jack, OVO, Interscope, Interscope Geffen A&M, Opium, UMG, Def Jam, Death Row, Cash Money, Bad Boy, Aftermath, Collective Music Group, pgLang, Republic, Columbia |
| Indie / alternative | Sub Pop, Matador, Fueled by Ramen, Third Man, Astralwerks |
| Electronic / dance | Ultra, Anjunabeats/Anjunadeep, Ninja Tune |
| Country | Big Machine Label Group, MCA Nashville |
| Jazz / blues / folk | Motown, Rounder, Blue Note, Impulse!, Alligator |
| Metal / punk | Nuclear Blast, Epitaph, Metal Blade |

The in-app dropdown lets you type to jump straight to any label.

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
- Track release dates are matched by name via Spotify search and can
  occasionally miss or mismatch a generically-titled track.
- Spotify's standard API access no longer exposes `followers`, `popularity`,
  or `genres` for most apps — that's why those fields are sourced from
  Last.fm instead.
- Label thresholds are rough estimates calibrated by hand, not against
  historical outcomes — treat fit results as a starting point, not a verdict.
