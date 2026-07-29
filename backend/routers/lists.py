"""
Custom user-made album lists (library albums, ordered, with notes).
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from database import get_connection
from auth_deps import get_current_user

router = APIRouter(prefix="/api/lists", tags=["lists"])


class ListCreate(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)


class ListItemAdd(BaseModel):
    album_id: int
    note: Optional[str] = Field(default=None, max_length=300)


class ListReorder(BaseModel):
    item_ids: list[int]


def _owned_list(conn, list_id: int, user: dict):
    row = conn.execute("SELECT * FROM lists WHERE id = ?", (list_id,)).fetchone()
    if not row:
        raise HTTPException(404, "List not found")
    if row["user_id"] != user["id"] and not user["is_admin"]:
        raise HTTPException(403, "Not your list")
    return row


@router.get("")
def list_lists():
    """All lists with owner, item count and up to 4 preview covers."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT l.*, u.name as user_name,
                   (SELECT COUNT(*) FROM list_items li WHERE li.list_id = l.id) as item_count
            FROM lists l
            JOIN users u ON u.id = l.user_id
            ORDER BY l.updated_at DESC
        """).fetchall()
        result = []
        for r in rows:
            covers = conn.execute("""
                SELECT a.cover_url FROM list_items li
                JOIN albums a ON a.id = li.album_id
                WHERE li.list_id = ? ORDER BY li.position, li.id LIMIT 4
            """, (r["id"],)).fetchall()
            entry = dict(r)
            entry["covers"] = [c["cover_url"] for c in covers if c["cover_url"]]
            result.append(entry)
    return {"lists": result}


@router.post("")
def create_list(body: ListCreate, user: dict = Depends(get_current_user)):
    with get_connection() as conn:
        row = conn.execute(
            "INSERT INTO lists (user_id, title, description) VALUES (?, ?, ?) RETURNING *",
            (user["id"], body.title, body.description),
        ).fetchone()
    return dict(row)


@router.get("/{list_id}")
def get_list(list_id: int):
    """List detail: items in order with album info and average score."""
    with get_connection() as conn:
        row = conn.execute("""
            SELECT l.*, u.name as user_name FROM lists l
            JOIN users u ON u.id = l.user_id WHERE l.id = ?
        """, (list_id,)).fetchone()
        if not row:
            raise HTTPException(404, "List not found")
        items = conn.execute("""
            SELECT li.id, li.album_id, li.position, li.note,
                   a.name, a.artist, a.cover_url, a.release_date,
                   (SELECT ROUND(AVG(ar.score), 1) FROM album_rankings ar
                    WHERE ar.album_id = a.id AND ar.score IS NOT NULL) as average_score
            FROM list_items li
            JOIN albums a ON a.id = li.album_id
            WHERE li.list_id = ?
            ORDER BY li.position, li.id
        """, (list_id,)).fetchall()
    detail = dict(row)
    detail["items"] = [dict(i) for i in items]
    return detail


@router.put("/{list_id}")
def update_list(list_id: int, body: ListCreate, user: dict = Depends(get_current_user)):
    with get_connection() as conn:
        _owned_list(conn, list_id, user)
        conn.execute(
            "UPDATE lists SET title = ?, description = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (body.title, body.description, list_id),
        )
    return {"ok": True}


@router.delete("/{list_id}")
def delete_list(list_id: int, user: dict = Depends(get_current_user)):
    with get_connection() as conn:
        _owned_list(conn, list_id, user)
        conn.execute("DELETE FROM lists WHERE id = ?", (list_id,))
    return {"ok": True}


@router.post("/{list_id}/items")
def add_item(list_id: int, body: ListItemAdd, user: dict = Depends(get_current_user)):
    with get_connection() as conn:
        _owned_list(conn, list_id, user)
        if not conn.execute("SELECT 1 FROM albums WHERE id = ?", (body.album_id,)).fetchone():
            raise HTTPException(404, "Album not found")
        max_pos = conn.execute(
            "SELECT COALESCE(MAX(position), 0) FROM list_items WHERE list_id = ?",
            (list_id,),
        ).fetchone()[0]
        try:
            conn.execute(
                "INSERT INTO list_items (list_id, album_id, position, note) VALUES (?, ?, ?, ?)",
                (list_id, body.album_id, max_pos + 1, body.note),
            )
        except Exception:
            raise HTTPException(400, "Album already in this list")
        conn.execute(
            "UPDATE lists SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (list_id,)
        )
    return {"ok": True}


@router.delete("/{list_id}/items/{item_id}")
def remove_item(list_id: int, item_id: int, user: dict = Depends(get_current_user)):
    with get_connection() as conn:
        _owned_list(conn, list_id, user)
        conn.execute(
            "DELETE FROM list_items WHERE id = ? AND list_id = ?", (item_id, list_id)
        )
        conn.execute(
            "UPDATE lists SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (list_id,)
        )
    return {"ok": True}


@router.put("/{list_id}/reorder")
def reorder_items(list_id: int, body: ListReorder, user: dict = Depends(get_current_user)):
    """Set item order to the given id sequence (ids not listed keep tail order)."""
    with get_connection() as conn:
        _owned_list(conn, list_id, user)
        for pos, item_id in enumerate(body.item_ids, start=1):
            conn.execute(
                "UPDATE list_items SET position = ? WHERE id = ? AND list_id = ?",
                (pos, item_id, list_id),
            )
        conn.execute(
            "UPDATE lists SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (list_id,)
        )
    return {"ok": True}
