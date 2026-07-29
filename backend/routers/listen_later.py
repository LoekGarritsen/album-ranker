"""
Listen-later backlog: Spotify albums bookmarked per user.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import Optional

from database import get_connection
from auth_deps import get_current_user

router = APIRouter(prefix="/api/listen-later", tags=["listen-later"])


class BacklogItem(BaseModel):
    spotify_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=300)
    artist: str = Field(min_length=1, max_length=300)
    image: Optional[str] = Field(default=None, max_length=500)
    release_date: Optional[str] = Field(default=None, max_length=20)


@router.get("")
def list_backlog(user: dict = Depends(get_current_user)):
    """The caller's backlog, newest first, flagged if already in the library."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT ll.*, a.id as library_album_id
            FROM listen_later ll
            LEFT JOIN albums a ON a.spotify_id = ll.spotify_id
            WHERE ll.user_id = ?
            ORDER BY ll.id DESC
        """, (user["id"],)).fetchall()
    return {"items": [dict(r) for r in rows]}


@router.post("")
def toggle_backlog(item: BacklogItem, user: dict = Depends(get_current_user)):
    """Toggle an album in the caller's backlog."""
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM listen_later WHERE user_id = ? AND spotify_id = ?",
            (user["id"], item.spotify_id),
        ).fetchone()
        if existing:
            conn.execute("DELETE FROM listen_later WHERE id = ?", (existing["id"],))
            saved = False
        else:
            conn.execute("""
                INSERT INTO listen_later (user_id, spotify_id, name, artist, image, release_date)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user["id"], item.spotify_id, item.name, item.artist,
                  item.image, item.release_date))
            saved = True
    return {"ok": True, "saved": saved}
