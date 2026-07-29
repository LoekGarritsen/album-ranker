"""
Artist follows + new-release watch. Releases come from Spotify per followed
artist, cached in release_cache for 6 hours, filtered to the last 120 days.
"""
import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional

from database import get_connection
from auth_deps import get_current_user
from spotify import spotify_client

router = APIRouter(prefix="/api/artists", tags=["artists"])

CACHE_TTL = timedelta(hours=6)
RELEASE_WINDOW_DAYS = 120


class FollowToggle(BaseModel):
    spotify_artist_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=300)
    image: Optional[str] = Field(default=None, max_length=500)


@router.get("/follows")
def list_follows(user: dict = Depends(get_current_user)):
    """Everyone's follows; the caller's own are flagged (shared watchlist)."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT spotify_artist_id, name, image,
                   COUNT(*) as followers,
                   MAX(CASE WHEN user_id = ? THEN 1 ELSE 0 END) as followed_by_me
            FROM artist_follows
            GROUP BY spotify_artist_id
            ORDER BY name COLLATE NOCASE
        """, (user["id"],)).fetchall()
    return {"artists": [dict(r) for r in rows]}


@router.post("/follows")
def toggle_follow(body: FollowToggle, user: dict = Depends(get_current_user)):
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM artist_follows WHERE user_id = ? AND spotify_artist_id = ?",
            (user["id"], body.spotify_artist_id),
        ).fetchone()
        if existing:
            conn.execute("DELETE FROM artist_follows WHERE id = ?", (existing["id"],))
            followed = False
        else:
            conn.execute(
                "INSERT INTO artist_follows (user_id, spotify_artist_id, name, image) VALUES (?, ?, ?, ?)",
                (user["id"], body.spotify_artist_id, body.name, body.image),
            )
            followed = True
    return {"ok": True, "followed": followed}


@router.get("/search")
async def search_artists(q: str = Query(..., min_length=1)):
    try:
        return {"artists": await spotify_client.search_artists(q)}
    except Exception as e:
        raise HTTPException(502, f"Spotify search failed: {e}")


async def _artist_releases(artist_id: str) -> list[dict]:
    """Cached recent releases for one artist."""
    now = datetime.utcnow()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT payload, fetched_at FROM release_cache WHERE spotify_artist_id = ?",
            (artist_id,),
        ).fetchone()
    if row:
        try:
            fetched = datetime.fromisoformat(str(row["fetched_at"]))
            if now - fetched < CACHE_TTL:
                return json.loads(row["payload"])
        except (ValueError, TypeError):
            pass
    try:
        releases = await spotify_client.get_artist_albums(artist_id)
    except Exception:
        return json.loads(row["payload"]) if row else []
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO release_cache (spotify_artist_id, payload, fetched_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(spotify_artist_id) DO UPDATE SET
                payload = excluded.payload, fetched_at = CURRENT_TIMESTAMP
        """, (artist_id, json.dumps(releases)))
    return releases


@router.get("/releases")
async def new_releases(user: dict = Depends(get_current_user)):
    """Recent releases (last 120 days) across all followed artists."""
    with get_connection() as conn:
        artists = conn.execute(
            "SELECT DISTINCT spotify_artist_id, name FROM artist_follows"
        ).fetchall()
        library = {
            r["spotify_id"] for r in conn.execute("SELECT spotify_id FROM albums").fetchall()
        }
        backlog = {
            r["spotify_id"] for r in conn.execute(
                "SELECT spotify_id FROM listen_later WHERE user_id = ?", (user["id"],)
            ).fetchall()
        }

    cutoff = (datetime.utcnow() - timedelta(days=RELEASE_WINDOW_DAYS)).strftime("%Y-%m-%d")
    seen = set()
    releases = []
    for artist in artists:
        for rel in await _artist_releases(artist["spotify_artist_id"]):
            date = rel.get("release_date") or ""
            # Spotify dates can be YYYY or YYYY-MM; only full dates compare cleanly
            if len(date) == 4:
                date = f"{date}-01-01"
            elif len(date) == 7:
                date = f"{date}-01"
            if date < cutoff or rel["spotify_id"] in seen:
                continue
            seen.add(rel["spotify_id"])
            rel["followed_artist"] = artist["name"]
            rel["in_library"] = rel["spotify_id"] in library
            rel["in_backlog"] = rel["spotify_id"] in backlog
            releases.append(rel)

    releases.sort(key=lambda r: r["release_date"] or "", reverse=True)
    return {"releases": releases}
