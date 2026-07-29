"""Blind-rating helpers for club rounds.

While a club round is in 'rating', other users' ALBUM-level scores and
comments for that album are hidden from anyone who hasn't submitted their
own album rating yet (prevents anchoring). Track ratings stay live so
listening sessions keep their realtime feel. Reveal lifts the veil.
"""
from database import get_connection


def blind_album_ids(conn) -> set[int]:
    """Album ids currently under blind rating."""
    rows = conn.execute(
        "SELECT album_id FROM club_rounds WHERE status = 'rating' AND album_id IS NOT NULL"
    ).fetchall()
    return {r["album_id"] for r in rows}


def is_blind_for_user(conn, album_id: int, user_id: int | None) -> bool:
    """True if this album's other ratings must be hidden from this user."""
    if album_id not in blind_album_ids(conn):
        return False
    if user_id is None:
        return True
    rated = conn.execute(
        "SELECT 1 FROM album_rankings WHERE album_id = ? AND user_id = ? AND score IS NOT NULL",
        (album_id, user_id),
    ).fetchone()
    return not rated
