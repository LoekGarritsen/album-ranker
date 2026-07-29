"""
Album club rounds: nominate -> vote -> blind rate -> reveal.

Lifecycle (status): 'nominating' -> 'voting' -> 'rating' -> 'revealed'.
On the voting->rating transition the winning nomination (most votes,
tie broken by earliest nomination) is imported into the library and
becomes the round's album. While 'rating', album-level scores of other
users are hidden (see blind.py). 'revealed' lifts the veil.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Literal, Optional

from database import get_connection
from auth_deps import get_current_user
from models import AlbumAdd
from notify import notify_all
from routers.albums import import_album_from_spotify

router = APIRouter(prefix="/api/club", tags=["club"])

STATUS_ORDER = ["nominating", "voting", "rating", "revealed"]


class RoundCreate(BaseModel):
    title: str = Field(min_length=1, max_length=100)


class Nomination(BaseModel):
    spotify_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=300)
    artist: str = Field(min_length=1, max_length=300)
    cover_url: Optional[str] = Field(default=None, max_length=500)
    release_date: Optional[str] = Field(default=None, max_length=20)


class VoteBody(BaseModel):
    nomination_id: int


class StatusBody(BaseModel):
    status: Literal["nominating", "voting", "rating", "revealed"]


def _can_manage(round_row, user: dict) -> bool:
    return user["is_admin"] or round_row["created_by"] == user["id"]


def _round_detail(conn, round_row, user_id: int) -> dict:
    """Full round payload: nominations with vote tallies + caller's own state."""
    nominations = conn.execute("""
        SELECT n.*, u.name as user_name,
               (SELECT COUNT(*) FROM club_votes v WHERE v.nomination_id = n.id) as votes
        FROM club_nominations n
        JOIN users u ON u.id = n.user_id
        WHERE n.round_id = ?
        ORDER BY votes DESC, n.id ASC
    """, (round_row["id"],)).fetchall()

    my_vote = conn.execute(
        "SELECT nomination_id FROM club_votes WHERE round_id = ? AND user_id = ?",
        (round_row["id"], user_id),
    ).fetchone()

    album = None
    my_rating = None
    rated_count = 0
    if round_row["album_id"]:
        album = conn.execute(
            "SELECT id, spotify_id, name, artist, cover_url, release_date FROM albums WHERE id = ?",
            (round_row["album_id"],),
        ).fetchone()
        album = dict(album) if album else None
        rated_count = conn.execute(
            "SELECT COUNT(*) FROM album_rankings WHERE album_id = ? AND score IS NOT NULL",
            (round_row["album_id"],),
        ).fetchone()[0]
        mine = conn.execute(
            "SELECT score FROM album_rankings WHERE album_id = ? AND user_id = ? AND score IS NOT NULL",
            (round_row["album_id"], user_id),
        ).fetchone()
        my_rating = mine["score"] if mine else None

    creator = conn.execute(
        "SELECT name FROM users WHERE id = ?", (round_row["created_by"],)
    ).fetchone()

    return {
        "id": round_row["id"],
        "title": round_row["title"],
        "status": round_row["status"],
        "album": album,
        "created_by": round_row["created_by"],
        "created_by_name": creator["name"] if creator else None,
        "created_at": round_row["created_at"],
        "nominations": [dict(n) for n in nominations],
        "my_vote": my_vote["nomination_id"] if my_vote else None,
        "my_rating": my_rating,
        "rated_count": rated_count,
    }


@router.get("/rounds")
def list_rounds(user: dict = Depends(get_current_user)):
    """All rounds newest first; the latest non-revealed one is 'current'."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM club_rounds ORDER BY id DESC LIMIT 50"
        ).fetchall()
        rounds = [_round_detail(conn, r, user["id"]) for r in rows]
    current = next((r for r in rounds if r["status"] != "revealed"), None)
    return {"rounds": rounds, "current": current}


@router.post("/rounds")
def create_round(body: RoundCreate, user: dict = Depends(get_current_user)):
    """Start a new round. Only one open round at a time."""
    with get_connection() as conn:
        open_round = conn.execute(
            "SELECT 1 FROM club_rounds WHERE status != 'revealed'"
        ).fetchone()
        if open_round:
            raise HTTPException(400, "There is already an open round")
        row = conn.execute(
            "INSERT INTO club_rounds (title, created_by) VALUES (?, ?) RETURNING *",
            (body.title, user["id"]),
        ).fetchone()
        detail = _round_detail(conn, row, user["id"])
    notify_all("club_round", {
        "round_id": detail["id"], "title": detail["title"], "status": "nominating",
    }, exclude_user_id=user["id"])
    return detail


@router.post("/rounds/{round_id}/nominate")
def nominate(round_id: int, body: Nomination, user: dict = Depends(get_current_user)):
    """Nominate an album (replaces your previous nomination this round)."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM club_rounds WHERE id = ?", (round_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Round not found")
        if row["status"] != "nominating":
            raise HTTPException(400, "Nominations are closed for this round")
        conn.execute("""
            INSERT INTO club_nominations (round_id, user_id, spotify_id, name, artist, cover_url, release_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(round_id, user_id) DO UPDATE SET
                spotify_id = excluded.spotify_id, name = excluded.name,
                artist = excluded.artist, cover_url = excluded.cover_url,
                release_date = excluded.release_date, created_at = CURRENT_TIMESTAMP
        """, (round_id, user["id"], body.spotify_id, body.name, body.artist,
              body.cover_url, body.release_date))
        detail = _round_detail(conn, row, user["id"])
    return detail


@router.post("/rounds/{round_id}/vote")
def vote(round_id: int, body: VoteBody, user: dict = Depends(get_current_user)):
    """Vote for a nomination (re-vote replaces, same pick toggles off)."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM club_rounds WHERE id = ?", (round_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Round not found")
        if row["status"] != "voting":
            raise HTTPException(400, "Voting is not open for this round")
        nom = conn.execute(
            "SELECT 1 FROM club_nominations WHERE id = ? AND round_id = ?",
            (body.nomination_id, round_id),
        ).fetchone()
        if not nom:
            raise HTTPException(404, "Nomination not found")
        existing = conn.execute(
            "SELECT nomination_id FROM club_votes WHERE round_id = ? AND user_id = ?",
            (round_id, user["id"]),
        ).fetchone()
        if existing and existing["nomination_id"] == body.nomination_id:
            conn.execute(
                "DELETE FROM club_votes WHERE round_id = ? AND user_id = ?",
                (round_id, user["id"]),
            )
        else:
            conn.execute("""
                INSERT INTO club_votes (round_id, nomination_id, user_id)
                VALUES (?, ?, ?)
                ON CONFLICT(round_id, user_id) DO UPDATE SET
                    nomination_id = excluded.nomination_id, created_at = CURRENT_TIMESTAMP
            """, (round_id, body.nomination_id, user["id"]))
        detail = _round_detail(conn, row, user["id"])
    return detail


@router.post("/rounds/{round_id}/status")
async def set_status(round_id: int, body: StatusBody, user: dict = Depends(get_current_user)):
    """Advance the round (creator or admin). Voting -> rating picks the winner."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM club_rounds WHERE id = ?", (round_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Round not found")
        if not _can_manage(row, user):
            raise HTTPException(403, "Only the round creator or an admin can do this")
        if STATUS_ORDER.index(body.status) != STATUS_ORDER.index(row["status"]) + 1:
            raise HTTPException(400, f"Cannot go from {row['status']} to {body.status}")
        if body.status == "voting":
            has_noms = conn.execute(
                "SELECT 1 FROM club_nominations WHERE round_id = ?", (round_id,)
            ).fetchone()
            if not has_noms:
                raise HTTPException(400, "No nominations yet")
        winner = None
        if body.status == "rating":
            winner = conn.execute("""
                SELECT n.*, (SELECT COUNT(*) FROM club_votes v WHERE v.nomination_id = n.id) as votes
                FROM club_nominations n
                WHERE n.round_id = ?
                ORDER BY votes DESC, n.id ASC
                LIMIT 1
            """, (round_id,)).fetchone()
            if not winner:
                raise HTTPException(400, "No nominations to pick a winner from")

    # Import outside the connection: import_album_from_spotify opens its own.
    album_id = row["album_id"]
    if winner is not None:
        album_row = await import_album_from_spotify(AlbumAdd(
            spotify_id=winner["spotify_id"], name=winner["name"],
            artist=winner["artist"], cover_url=winner["cover_url"],
            release_date=winner["release_date"],
        ))
        album_id = album_row["id"]

    with get_connection() as conn:
        conn.execute(
            "UPDATE club_rounds SET status = ?, album_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (body.status, album_id, round_id),
        )
        row = conn.execute("SELECT * FROM club_rounds WHERE id = ?", (round_id,)).fetchone()
        detail = _round_detail(conn, row, user["id"])

    notify_all("club_round", {
        "round_id": round_id, "title": row["title"], "status": body.status,
        "album": detail["album"],
    }, exclude_user_id=user["id"])
    return detail


@router.delete("/rounds/{round_id}")
def delete_round(round_id: int, user: dict = Depends(get_current_user)):
    """Delete a round (creator or admin). Library album stays."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM club_rounds WHERE id = ?", (round_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Round not found")
        if not _can_manage(row, user):
            raise HTTPException(403, "Only the round creator or an admin can do this")
        conn.execute("DELETE FROM club_rounds WHERE id = ?", (round_id,))
    return {"ok": True}
