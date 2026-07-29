"""
Rating/ranking routes for albums and tracks.
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional

from database import get_connection
from models import AlbumRankingCreate, TrackRankingCreate
from spotify import fetch_lyrics
from state import active_sessions
from auth_deps import get_current_user
from blind import blind_album_ids
# Single broadcast implementation — a stale duplicate here once assumed the
# old connections shape and silently dropped every client it touched.
from routers.sessions import broadcast_to_session

router = APIRouter(prefix="/api", tags=["rankings"])


@router.post("/rankings/album")
async def submit_album_ranking(ranking: AlbumRankingCreate, session_code: Optional[str] = Query(None), user: dict = Depends(get_current_user)):
    """Submit or update an album rating (always attributed to the caller)."""
    user_id = user["id"]
    with get_connection() as conn:
        if not conn.execute("SELECT 1 FROM albums WHERE id = ?", (ranking.album_id,)).fetchone():
            raise HTTPException(404, "Album not found")

        old = conn.execute(
            "SELECT score FROM album_rankings WHERE album_id = ? AND user_id = ?",
            (ranking.album_id, user_id),
        ).fetchone()

        conn.execute("""
            INSERT INTO album_rankings (album_id, user_id, score, comment)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(album_id, user_id)
            DO UPDATE SET score = excluded.score, comment = excluded.comment, ranked_at = CURRENT_TIMESTAMP
        """, (ranking.album_id, user_id, ranking.score, ranking.comment))

        if old is None or old["score"] != ranking.score:
            conn.execute(
                "INSERT INTO ranking_history (kind, item_id, user_id, score) VALUES ('album', ?, ?, ?)",
                (ranking.album_id, user_id, ranking.score),
            )

        # While a club round holds this album in blind rating, scores must
        # not leak to others via the session broadcast.
        is_blind = ranking.album_id in blind_album_ids(conn)

    # Broadcast rating to session if provided
    if is_blind:
        return {"ok": True, "blind": True}
    if session_code and session_code in active_sessions:
        await broadcast_to_session(session_code, {
            "type": "album_rating",
            "album_id": ranking.album_id,
            "user_id": user_id,
            "user_name": user["name"],
            "score": ranking.score,
            "comment": ranking.comment
        })

    return {"ok": True}


@router.post("/rankings/track")
async def submit_track_ranking(ranking: TrackRankingCreate, session_code: Optional[str] = Query(None), user: dict = Depends(get_current_user)):
    """Submit or update a track rating (always attributed to the caller)."""
    user_id = user["id"]
    with get_connection() as conn:
        if not conn.execute("SELECT 1 FROM tracks WHERE id = ?", (ranking.track_id,)).fetchone():
            raise HTTPException(404, "Track not found")

        old = conn.execute(
            "SELECT score FROM track_rankings WHERE track_id = ? AND user_id = ?",
            (ranking.track_id, user_id),
        ).fetchone()

        conn.execute("""
            INSERT INTO track_rankings (track_id, user_id, score, comment)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(track_id, user_id)
            DO UPDATE SET score = excluded.score, comment = excluded.comment, ranked_at = CURRENT_TIMESTAMP
        """, (ranking.track_id, user_id, ranking.score, ranking.comment))

        if old is None or old["score"] != ranking.score:
            conn.execute(
                "INSERT INTO ranking_history (kind, item_id, user_id, score) VALUES ('track', ?, ?, ?)",
                (ranking.track_id, user_id, ranking.score),
            )

    # Broadcast rating to session if provided
    if session_code and session_code in active_sessions:
        await broadcast_to_session(session_code, {
            "type": "rating",
            "track_id": ranking.track_id,
            "user_id": user_id,
            "user_name": user["name"],
            "score": ranking.score,
            "comment": ranking.comment
        })

    return {"ok": True}


@router.get("/tracks/{track_id}")
async def get_track_details(track_id: int):
    """Get track details with rankings and lyrics."""
    with get_connection() as conn:
        track = conn.execute("""
            SELECT t.*, a.name as album_name, a.artist as album_artist, a.cover_url
            FROM tracks t
            JOIN albums a ON t.album_id = a.id
            WHERE t.id = ?
        """, (track_id,)).fetchone()

        if not track:
            raise HTTPException(404, "Track not found")

        rankings = conn.execute("""
            SELECT tr.score, tr.comment, u.id as user_id, u.name as user_name
            FROM track_rankings tr
            JOIN users u ON tr.user_id = u.id
            WHERE tr.track_id = ?
        """, (track_id,)).fetchall()

        scores = [r["score"] for r in rankings if r["score"]]
        avg = sum(scores) / len(scores) if scores else None

    # Fetch lyrics
    lyrics = await fetch_lyrics(track["artist"], track["name"])

    return {
        "id": track["id"],
        "name": track["name"],
        "artist": track["artist"],
        "track_number": track["track_number"],
        "duration_ms": track["duration_ms"],
        "album_name": track["album_name"],
        "album_artist": track["album_artist"],
        "cover_url": track["cover_url"],
        "lyrics": lyrics,
        "rankings": [dict(r) for r in rankings],
        "average_score": round(avg, 1) if avg else None
    }
