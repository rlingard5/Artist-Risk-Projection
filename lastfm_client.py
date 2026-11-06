"""
lastfm_client.py
-----------------
Fetches the quantitative artist data Spotify's public API no longer
provides to standard apps (listeners, playcount, top-track playcounts).

Last.fm's API is free, requires only an API key (no app-review process
or "Extended Quota Mode" approval like Spotify), and is read-only here —
we never touch a user's personal Last.fm account, just public artist
stats. Get a free key at https://www.last.fm/api/account/create

This is the module that makes the dashboard "just type an artist name" —
spotify_client.py still handles the name search + photo (that part of
Spotify's API works fine), and this module supplies the actual numbers
the risk formulas run on.
"""

from __future__ import annotations

import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

# https, not http: plain HTTP gets silently blocked/hung by some networks
# (corporate firewalls, certain ISPs/VPNs), which shows up as a read
# timeout rather than a clear connection-refused error.
BASE_URL = "https://ws.audioscrobbler.com/2.0/"

REQUEST_TIMEOUT = 15  # seconds; Last.fm can be slow under load
MAX_RETRIES = 2


def _get_api_key() -> str:
    api_key = os.getenv("LASTFM_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "Missing LASTFM_API_KEY. Get a free key at "
            "https://www.last.fm/api/account/create and add it to your .env file."
        )
    return api_key


def _request(method: str, params: dict) -> dict:
    """
    Make a Last.fm API call and raise a clear error if it failed.

    Last.fm returns HTTP 200 even on errors — the error is embedded in
    the JSON body as {"error": <code>, "message": <str>} — so we check
    for that explicitly instead of relying on raise_for_status().

    Retries on timeouts/connection errors (transient network hiccups),
    but not on a real Last.fm API error (e.g. "artist not found") — that
    would just fail the same way every time, so retrying wastes time.
    """
    query = {
        "method": method,
        "api_key": _get_api_key(),
        "format": "json",
        **params,
    }

    last_exception = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(BASE_URL, params=query, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()  # catches HTTP-level failures
            data = response.json()

            if "error" in data:
                raise ValueError(
                    f"Last.fm API error {data['error']}: "
                    f"{data.get('message', 'Unknown error')}"
                )
            return data

        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last_exception = e
            if attempt < MAX_RETRIES:
                time.sleep(1)  # brief pause before retrying
                continue
            raise ConnectionError(
                f"Couldn't reach Last.fm after {MAX_RETRIES} attempts "
                f"(method={method}). This is usually a network issue — "
                "check your internet connection, or a firewall/VPN may be "
                f"blocking the request. Original error: {e}"
            ) from last_exception


def get_artist_stats(artist_name: str) -> dict | None:
    """
    Fetch an artist's listener count and total playcount from Last.fm.

    Parameters
    ----------
    artist_name : str
        Artist name, e.g. "Central Cee".

    Returns
    -------
    dict | None
        {
            "listeners": int,   # unique Last.fm users who've played them
            "playcount": int,   # total scrobbles (plays) across all users
            "genres": list[str],  # Last.fm community tags, used as a genre proxy
        }
        Returns None if the artist isn't found on Last.fm.
    """
    try:
        data = _request("artist.getinfo", {"artist": artist_name})
    except ValueError:
        # Last.fm's "artist not found" case raises ValueError from _request;
        # treat it the same as spotify_client.search_artist()'s None return.
        return None

    artist = data.get("artist")
    if not artist:
        return None

    stats = artist.get("stats", {})
    tags = artist.get("tags", {}).get("tag", [])

    return {
        "listeners": int(stats.get("listeners", 0)),
        "playcount": int(stats.get("playcount", 0)),
        "genres": [t["name"] for t in tags] if isinstance(tags, list) else [],
    }


def get_top_tracks(artist_name: str, limit: int = 10) -> list[dict]:
    """
    Fetch an artist's top tracks by playcount from Last.fm.

    Parameters
    ----------
    artist_name : str
        Artist name, e.g. "Central Cee".
    limit : int
        Max number of tracks to fetch (default 10, matching the
        Concentration Risk formula's "top 10" design).

    Returns
    -------
    list[dict]
        Up to `limit` tracks, each:
        {"name": str, "playcount": int}
        Sorted by playcount descending (Last.fm already returns them
        this way, but we sort defensively).
    """
    data = _request(
        "artist.gettoptracks", {"artist": artist_name, "limit": limit}
    )
    tracks = data.get("toptracks", {}).get("track", [])

    # Last.fm returns a single dict (not a list) if there's only one track
    if isinstance(tracks, dict):
        tracks = [tracks]

    parsed = [
        {"name": t["name"], "playcount": int(t["playcount"])}
        for t in tracks
    ]
    parsed.sort(key=lambda t: t["playcount"], reverse=True)
    return parsed


if __name__ == "__main__":
    # Quick manual smoke test: run `python lastfm_client.py` to confirm
    # your Last.fm API key works and see real data printed.
    test_name = "Central Cee"
    stats = get_artist_stats(test_name)
    if stats is None:
        print(f"No artist found for '{test_name}' on Last.fm")
    else:
        print("Artist stats:", stats)
        tracks = get_top_tracks(test_name)
        print(f"\nTop {len(tracks)} tracks:")
        for i, t in enumerate(tracks, start=1):
            print(f"  {i}. {t['name']} (playcount: {t['playcount']:,})")
