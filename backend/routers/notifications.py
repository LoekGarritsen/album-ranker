"""
In-app notification center: list, unread count, mark read.
"""
import json

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from typing import Optional

from database import get_connection
from auth_deps import get_current_user

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class MarkRead(BaseModel):
    ids: Optional[list[int]] = None  # None = mark all read


@router.get("")
def list_notifications(
    before_id: Optional[int] = Query(None),
    limit: int = Query(30, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    """The caller's notifications, newest first, keyset-paginated."""
    with get_connection() as conn:
        params = [user["id"]]
        where = "user_id = ?"
        if before_id:
            where += " AND id < ?"
            params.append(before_id)
        rows = conn.execute(
            f"""SELECT id, type, payload, read, created_at
                FROM notifications WHERE {where}
                ORDER BY id DESC LIMIT ?""",
            (*params, limit),
        ).fetchall()
        unread = conn.execute(
            "SELECT COUNT(*) FROM notifications WHERE user_id = ? AND read = 0",
            (user["id"],),
        ).fetchone()[0]

    items = []
    for r in rows:
        item = dict(r)
        try:
            item["payload"] = json.loads(item["payload"])
        except (TypeError, ValueError):
            item["payload"] = {}
        items.append(item)
    return {"notifications": items, "unread": unread}


@router.post("/read")
def mark_read(body: MarkRead, user: dict = Depends(get_current_user)):
    """Mark specific notifications (or all) as read."""
    with get_connection() as conn:
        if body.ids:
            qs = ",".join("?" * len(body.ids))
            conn.execute(
                f"UPDATE notifications SET read = 1 WHERE user_id = ? AND id IN ({qs})",
                (user["id"], *body.ids),
            )
        else:
            conn.execute(
                "UPDATE notifications SET read = 1 WHERE user_id = ?", (user["id"],)
            )
    return {"ok": True}
