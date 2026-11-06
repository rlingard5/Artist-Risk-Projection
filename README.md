A&R Artist Investment & Risk Analytics

A quantitative scouting tool for evaluating whether to sign an artist. Type an artist name, set a proposed advance, and get a data-driven read on recoupment odds, hit-dependence risk, fan loyalty, catalog freshness, and fit against 35 label profiles — backed by a Monte Carlo revenue simulation.

Disclaimer: The formulas and label thresholds here are this project's own modeling assumptions, not industry-standard metrics. They're meant to give a consistent, explainable starting point for a conversation — not a replacement for A&R judgment.

Features
Auto-fetched data — just type an artist name. Pulls listener/playcount stats from Last.fm and a name/photo from Spotify.
Monte Carlo recoupment simulation — runs thousands of simulated 24-month revenue paths (geometric Brownian motion) against the proposed advance.
5 growth scenarios compared side by side: No growth, Positive growth, Positive-then-negative, Negative growth, and Negative-then-positive — plus a chart overlaying all five median trajectories.
Concentration Risk (CR) — how dependent the artist's numbers are on one song vs. the rest of their catalog.
Fan Loyalty Ratio (FLR) — average plays per listener, as a proxy for how sticky the fanbase is vs. one-and-done listening.
Hit Timeline — flags whether an artist's hits are stale (nothing recent) or an unproven one-off spike (one recent hit with nothing before or after it to back it up), using Spotify release dates.
Label Benchmark Fit — checks the artist against 35 label profiles (major, indie, country, jazz/blues, EDM, metal/punk) and ranks which ones they'd actually be signable to.
Setup
Install dependencies
bash
   pip install -r requirements.txt
Get API credentials
Spotify (name search + photo only): create an app at developer.spotify.com/dashboard and copy its Client ID / Client Secret.
Last.fm (listener/playcount/top-track data — free, no approval needed): get a key at last.fm/api/account/create.
Configure environment variables Copy .env.example to .env and fill in your real values:
bash
   cp .env.example .env
   SPOTIFY_CLIENT_ID=your_spotify_client_id_here
   SPOTIFY_CLIENT_SECRET=your_spotify_client_secret_here
   LASTFM_API_KEY=your_lastfm_api_key_here

Never commit your real .env file — only .env.example should be tracked in git.

Run the app
bash
   python -m streamlit run app.py

(Use python -m streamlit instead of a bare streamlit command if your system's PATH doesn't have it set up.)

Project structure
File	Purpose
app.py	Streamlit UI — sidebar inputs, KPI cards, charts, label-fit panel
spotify_client.py	Spotify artist search (name/photo) + track release-date lookup
lastfm_client.py	Listener count, playcount, and top-track data
risk_engine.py	CR / FLR / hit-timeline formulas, Monte Carlo simulation, label profiles
charts.py	All Plotly chart definitions, dark-theme styled
.streamlit/config.toml	Dark theme configuration
requirements.txt	Python dependencies
.env.example	Template for required API keys
How the numbers work
Concentration Risk = top track's plays ÷ average of tracks 2–10. Higher = more dependent on one song.
Fan Loyalty Ratio = total playcount ÷ unique listeners. Higher = fans replay the artist rather than listening once.
Hit Timeline classifies the catalog as stale (nothing newer than ~4.5 years), an unproven spike (a hit within ~6 months with nothing backing it up), or fresh & sustained (a recent hit supported by an earlier one or multiple recent hits together).
Monte Carlo simulation models monthly stream counts as a random walk, converts to revenue at an assumed price-per-stream, and reports what share of simulated outcomes clear the advance. The "growth scenario" assumes a fixed fraction of the advance goes to promotion and translates into a capped monthly growth boost — this app's own assumption, not a real industry formula.
Label Benchmark Fit checks CR, FLR, growth rate, and catalog recency against each label's thresholds in risk_engine.py's LABEL_PROFILES dict. These thresholds are rough, manually-set estimates and should be recalibrated against real outcomes over time.
Known limitations
Last.fm's playcount is a lifetime total, not a monthly figure — the "auto-estimate current monthly streams" option is a rough heuristic (total ÷ 12), not a real stream count. Manual entry is more reliable.
Track release dates are matched by name via Spotify search and can occasionally miss or mismatch a generically-titled track.
Spotify's standard API access no longer exposes followers, popularity, or genres for most apps — that's why those fields are sourced from Last.fm instead.
