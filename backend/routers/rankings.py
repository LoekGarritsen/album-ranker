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

router = APIRouter(prefix="/api", tags=["rankings"])


async def broadcast_to_session(code: str, message: dict):
    """Broadcast a message to all connected clients in a session."""
    if code not in active_sessions:
        return
    failed_connections = []
    for user_id, ws in list(active_sessions[code]["connections"].items()):
        try:
            await ws.send_json(message)
        except Exception:
            failed_connections.append(user_id)
    for user_id in failed_connections:
        if code in active_sessions and user_id in active_sessions[code]["connections"]:
            del active_sessions[code]["connections"][user_id]


@router.post("/rankings/album")
def submit_album_ranking(ranking: AlbumRankingCreate, user: dict = Depends(get_current_user)):
    """Submit or update an album rating (always attributed to the caller)."""
    user_id = user["id"]
    with get_connection() as conn:
        if not conn.execute("SELECT 1 FROM albums WHERE id = ?", (ranking.album_id,)).fetchone():
            raise HTTPException(404, "Album not found")

        conn.execute("""
            INSERT INTO album_rankings (album_id, user_id, score, comment)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(album_id, user_id)
            DO UPDATE SET score = excluded.score, comment = excluded.comment, ranked_at = CURRENT_TIMESTAMP
        """, (ranking.album_id, user_id, ranking.score, ranking.comment))

        return {"ok": True}


@router.post("/rankings/track")
async def submit_track_ranking(ranking: TrackRankingCreate, session_code: Optional[str] = Query(None), user: dict = Depends(get_current_user)):
    """Submit or update a track rating (always attributed to the caller)."""
    user_id = user["id"]
    with get_connection() as conn:
        if not conn.execute("SELECT 1 FROM tracks WHERE id = ?", (ranking.track_id,)).fetchone():
            raise HTTPException(404, "Track not found")

        conn.execute("""
            INSERT INTO track_rankings (track_id, user_id, score, comment)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(track_id, user_id)
            DO UPDATE SET score = excluded.score, comment = excluded.comment, ranked_at = CURRENT_TIMESTAMP
        """, (ranking.track_id, user_id, ranking.score, ranking.comment))

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
