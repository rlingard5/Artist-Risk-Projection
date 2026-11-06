"""
spotify_client.py
-----------------
Phase 1: Environment & Data Ingestion.

Handles all direct communication with the Spotify Web API via spotipy.
Every other module (risk_engine, charts, app) should get its raw data
through the functions defined here — nothing else should call spotipy
directly. That keeps API changes contained to this one file.
"""

from __future__ import annotations

import os
from datetime import date
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# Load SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET from a local .env file
load_dotenv()


def get_spotify_client():
    """
    Authenticate with Spotify using the Client Credentials flow.

    This flow is read-only and doesn't require a logged-in user — it's
    the right choice here because we're only reading public artist/track
    data, not touching anyone's personal Spotify account.

    Returns
    -------
    spotipy.Spotify
        An authenticated client ready to make API calls.

    Raises
    ------
    EnvironmentError
        If credentials are missing from the environment.
    """
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise EnvironmentError(
            "Missing Spotify credentials. Copy .env.example to .env and "
            "fill in SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET."
        )

    auth_manager = SpotifyClientCredentials(
        client_id=client_id,
        client_secret=client_secret,
    )
    return spotipy.Spotify(auth_manager=auth_manager)


def search_artist(name: str) -> dict | None:
    """
    Search Spotify for an artist by name and return their basic profile.

    NOTE: As of late 2024, Spotify restricts several artist fields
    (followers, popularity, genres) and the top-tracks endpoint to apps
    approved for Extended Quota Mode. A standard/development-mode app
    (like this one) only reliably gets id/name/images back. Because of
    that, this function only returns what's actually available — the
    rest (followers, popularity, genres, top track scores) is entered
    manually in the Streamlit sidebar instead. See app.py.

    Parameters
    ----------
    name : str
        Artist name to search for, e.g. "Central Cee".

    Returns
    -------
    dict | None
        {
            "id": str,
            "name": str,
            "image_url": str | None,
        }
        Returns None if no artist is found.
    """
    sp = get_spotify_client()
    results = sp.search(q=name, type="artist", limit=1)
    items = results.get("artists", {}).get("items", [])

    if not items:
        return None

    artist = items[0]
    return {
        "id": artist["id"],
        "name": artist["name"],
        "image_url": artist["images"][0]["url"] if artist.get("images") else None,
    }


def get_track_release_years(track_names: list[str], artist_name: str) -> dict[str, float | None]:
    """
    Look up each track's release year via Spotify's track search, so the
    app can tell a catalog carried by a 4-5-year-old hit from one carried
    by something current.

    NOTE: Spotify's Nov-2024 API restrictions blocked the artist
    top-tracks endpoint (see search_artist's docstring), but the plain
    /v1/search endpoint (what this uses) and track/album lookups are NOT
    on that restricted list — they still work for a standard app. This
    is a best-effort text match (search for "track:<name> artist:<artist>"
    and take the top result), not a guaranteed exact match: a very
    generic track title could occasionally match the wrong recording.

    Parameters
    ----------
    track_names : list[str]
        Track names, e.g. from lastfm_client.get_top_tracks().
    artist_name : str
        The artist's name, used to narrow the search.

    Returns
    -------
    dict[str, float | None]
        Maps track name -> years since release (float, can be fractional),
        or None if no confident match was found on Spotify.
    """
    sp = get_spotify_client()
    today = date.today()
    results: dict[str, float | None] = {}

    for track_name in track_names:
        query = f'track:{track_name} artist:{artist_name}'
        try:
            search_result = sp.search(q=query, type="track", limit=1)
            items = search_result.get("tracks", {}).get("items", [])
        except Exception:
            items = []

        if not items:
            results[track_name] = None
            continue

        release_date = items[0].get("album", {}).get("release_date")
        if not release_date:
            results[track_name] = None
            continue

        # Spotify release_date precision varies: "YYYY", "YYYY-MM", or
        # "YYYY-MM-DD" (precision is given in release_date_precision).
        # A plain year is close enough for this purpose.
        try:
            year = int(release_date[:4])
            # Rough day-of-year estimate when we only have a year/month,
            # so "years ago" isn't always a suspiciously round number.
            month = int(release_date[5:7]) if len(release_date) >= 7 else 7
            day = int(release_date[8:10]) if len(release_date) >= 10 else 1
            release = date(year, month, day)
            years_ago = (today - release).days / 365.25
            results[track_name] = max(years_ago, 0.0)
        except (ValueError, IndexError):
            results[track_name] = None

    return results


if __name__ == "__main__":
    # Quick manual smoke test: run `python spotify_client.py` to confirm
    # your credentials work and see real data printed to the console.
    test_name = "Central Cee"
    artist = search_artist(test_name)
    if artist is None:
        print(f"No artist found for '{test_name}'")
    else:
        print("Artist found:", artist)
