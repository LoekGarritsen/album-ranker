"""
Likes on rating comments (album or track rankings). Toggle semantics;
the rating's owner gets a notification on like.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Literal

from database import get_connection
from auth_deps import get_current_user
from notify import notify

router = APIRouter(prefix="/api/likes", tags=["likes"])

_TABLES = {"album": "album_rankings", "track": "track_rankings"}


class LikeToggle(BaseModel):
    kind: Literal["album", "track"]
    ranking_id: int


@router.post("/toggle")
def toggle_like(body: LikeToggle, user: dict = Depends(get_current_user)):
    table = _TABLES[body.kind]
    with get_connection() as conn:
        ranking = conn.execute(
            f"SELECT * FROM {table} WHERE id = ?", (body.ranking_id,)
        ).fetchone()
        if not ranking:
            raise HTTPException(404, "Rating not found")

        existing = conn.execute(
            "SELECT id FROM ranking_likes WHERE kind = ? AND ranking_id = ? AND user_id = ?",
            (body.kind, body.ranking_id, user["id"]),
        ).fetchone()
        if existing:
            conn.execute("DELETE FROM ranking_likes WHERE id = ?", (existing["id"],))
            liked = False
        else:
            conn.execute(
                "INSERT INTO ranking_likes (kind, ranking_id, user_id) VALUES (?, ?, ?)",
                (body.kind, body.ranking_id, user["id"]),
            )
            liked = True
        count = conn.execute(
            "SELECT COUNT(*) FROM ranking_likes WHERE kind = ? AND ranking_id = ?",
            (body.kind, body.ranking_id),
        ).fetchone()[0]

        # Context for the owner's notification
        if body.kind == "album":
            item = conn.execute(
                "SELECT a.name FROM albums a WHERE a.id = ?", (ranking["album_id"],)
            ).fetchone()
        else:
            item = conn.execute(
                "SELECT t.name FROM tracks t WHERE t.id = ?", (ranking["track_id"],)
            ).fetchone()

    if liked and ranking["user_id"] != user["id"]:
        notify([ranking["user_id"]], "rating_like", {
            "kind": body.kind,
            "ranking_id": body.ranking_id,
            "item_name": item["name"] if item else None,
            "by_name": user["name"],
            "score": ranking["score"],
        })
    return {"ok": True, "liked": liked, "count": count}
