"""
Lyrics routes — synced lyrics from LRCLIB with a local SQLite cache.
"""
import httpx
from fastapi import APIRouter, HTTPException, Query

from database import get_connection

router = APIRouter(prefix="/api/lyrics", tags=["lyrics"])

LRCLIB_BASE = "https://lrclib.net/api"
# LRCLIB recommends a descriptive User-Agent identifying the app
USER_AGENT = "AlbumRanker/1.0 (https://albums.garritsen.dev)"

# Search fallback accepts a match whose duration is within this window
DURATION_TOLERANCE_S = 10


async def fetch_from_lrclib(track_name: str, artist_name: str, album_name: str, duration_s: int):
    """Exact /get lookup first; fall back to /search picking the closest-duration hit."""
    async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": USER_AGENT}) as client:
        res = await client.get(f"{LRCLIB_BASE}/get", params={
            "track_name": track_name,
            "artist_name": artist_name,
            "album_name": album_name or "",
            "duration": duration_s,
        })
        if res.status_code == 200:
            return res.json()

        res = await client.get(f"{LRCLIB_BASE}/search", params={
            "track_name": track_name,
            "artist_name": artist_name,
        })
        if res.status_code != 200:
            return None
        candidates = [
            r for r in res.json()
            if not duration_s or abs((r.get("duration") or 0) - duration_s) <= DURATION_TOLERANCE_S
        ]
        if not candidates:
            return None
        # Prefer synced lyrics, then closest duration
        candidates.sort(key=lambda r: (
            not r.get("syncedLyrics"),
            abs((r.get("duration") or 0) - duration_s),
        ))
        return candidates[0]


@router.get("")
async def get_lyrics(
    spotify_track_id: str = Query(..., min_length=1),
    track_name: str = Query(..., min_length=1),
    artist_name: str = Query(..., min_length=1),
    album_name: str = "",
    duration_ms: int = 0,
):
    """Lyrics for a track, cached by Spotify track id (negative results cached too)."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM lyrics_cache WHERE spotify_track_id = ?",
            (spotify_track_id,),
        ).fetchone()
    if row:
        return {
            "found": bool(row["found"]),
            "instrumental": bool(row["instrumental"]),
            "synced_lyrics": row["synced_lyrics"],
            "plain_lyrics": row["plain_lyrics"],
        }

    duration_s = round(duration_ms / 1000) if duration_ms else 0
    try:
        data = await fetch_from_lrclib(track_name, artist_name, album_name, duration_s)
    except httpx.HTTPError:
        # Transient failure — do not negative-cache, let a later request retry
        raise HTTPException(status_code=502, detail="Lyrics service unavailable")

    found = data is not None
    synced = data.get("syncedLyrics") if data else None
    plain = data.get("plainLyrics") if data else None
    instrumental = bool(data.get("instrumental")) if data else False

    with get_connection() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO lyrics_cache
               (spotify_track_id, synced_lyrics, plain_lyrics, instrumental, found)
               VALUES (?, ?, ?, ?, ?)""",
            (spotify_track_id, synced, plain, int(instrumental), int(found)),
        )

    return {
        "found": found,
        "instrumental": instrumental,
        "synced_lyrics": synced,
        "plain_lyrics": plain,
    }
