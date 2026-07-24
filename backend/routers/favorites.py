"""
Personal favorites: saved Spotify tracks/albums for quick re-queue in rooms.
"""
from fastapi import APIRouter, Depends, HTTPException

from database import get_connection
from models import SessionMediaSet
from auth_deps import get_current_user

router = APIRouter(prefix="/api/favorites", tags=["favorites"])


@router.get("")
def list_favorites(user: dict = Depends(get_current_user)):
    """The caller's favorites, newest first."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT id, type, spotify_id, name, artist, image, duration_ms, created_at
            FROM user_favorites
            WHERE user_id = ?
            ORDER BY id DESC
        """, (user["id"],)).fetchall()
    return {"favorites": [dict(r) for r in rows]}


@router.post("")
def toggle_favorite(item: SessionMediaSet, user: dict = Depends(get_current_user)):
    """Toggle a favorite: saves it, or removes it if already saved."""
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM user_favorites WHERE user_id = ? AND spotify_id = ?",
            (user["id"], item.spotify_id)
        ).fetchone()
        if existing:
            conn.execute("DELETE FROM user_favorites WHERE id = ?", (existing["id"],))
            favorited = False
        else:
            conn.execute("""
                INSERT INTO user_favorites (user_id, type, spotify_id, name, artist, image, duration_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (user["id"], item.type, item.spotify_id, item.name,
                  item.artist, item.image, item.duration_ms))
            favorited = True
    return {"ok": True, "favorited": favorited}
