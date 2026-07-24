"""
Listening session routes including WebSocket handling.
"""
from fastapi import APIRouter, HTTPException, Depends, Query, WebSocket
from typing import Optional
from datetime import datetime, timezone
import json
import random
import string
import time
import uuid
from urllib.parse import urlparse

from database import get_connection
from models import ListeningSession, SessionCreate, SessionJoin, SessionMediaSet
from state import active_sessions
from auth_deps import get_current_user, get_optional_user
from security import hash_password, verify_password, hash_token

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def generate_session_code():
    """Generate a random 6-character session code."""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


async def broadcast_to_session(code: str, message: dict):
    """Broadcast a message to all connected clients in a session.

    Connections are keyed by a per-socket id (never by user id): a reconnect
    or second tab must not overwrite — or later delete — another live socket's
    entry, which silently cut that client off from all broadcasts.
    """
    if code not in active_sessions:
        return
    connections = active_sessions[code]["connections"]
    failed = []
    for conn_id, entry in list(connections.items()):
        try:
            await entry["ws"].send_json(message)
        except Exception:
            failed.append(conn_id)
    for conn_id in failed:
        connections.pop(conn_id, None)


def session_listeners(state: dict) -> list[dict]:
    """Unique online users (a user with two tabs is listed once)."""
    seen = {}
    for entry in state["connections"].values():
        seen.setdefault(entry["user_key"], entry["user_name"])
    return [{"user_id": k, "user_name": v} for k, v in seen.items()]


def _is_giphy_url(url: str) -> bool:
    """Only Giphy-hosted media may be sent as a GIF message (no arbitrary
    image URLs through chat)."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (host == "giphy.com" or host.endswith(".giphy.com"))


def user_is_connected(state: dict, user_key) -> bool:
    return any(e["user_key"] == user_key for e in state["connections"].values())


# Net vote score orders the queue (most-wanted plays next); insertion id
# breaks ties so unvoted items stay FIFO.
QUEUE_ORDER_SQL = """
    SELECT q.id, q.type, q.spotify_id, q.name, q.artist, q.image,
           q.duration_ms, q.added_by, u.name as added_by_name,
           COALESCE(SUM(CASE WHEN v.vote = 1 THEN 1 END), 0) as likes,
           COALESCE(SUM(CASE WHEN v.vote = -1 THEN 1 END), 0) as dislikes
    FROM session_queue q
    JOIN users u ON q.added_by = u.id
    LEFT JOIN queue_votes v ON v.queue_item_id = q.id
    WHERE q.session_id = ?
    GROUP BY q.id
    ORDER BY (likes - dislikes) DESC, q.id
"""


def fetch_queue(conn, session_db_id: int) -> list[dict]:
    """Shared play queue with adder attribution and per-user votes attached."""
    rows = conn.execute(QUEUE_ORDER_SQL, (session_db_id,)).fetchall()
    items = [dict(r) for r in rows]
    for item in items:
        item["votes"] = []
    if items:
        by_id = {item["id"]: item for item in items}
        placeholders = ",".join("?" * len(by_id))
        votes = conn.execute(
            f"SELECT queue_item_id, user_id, vote FROM queue_votes WHERE queue_item_id IN ({placeholders})",
            list(by_id.keys())
        ).fetchall()
        for v in votes:
            by_id[v["queue_item_id"]]["votes"].append({"user_id": v["user_id"], "vote": v["vote"]})
    return items


@router.get("", response_model=list[ListeningSession])
def list_sessions():
    """List all active public rooms."""
    with get_connection() as conn:
        sessions = conn.execute("""
            SELECT ls.id, ls.code, ls.name, ls.album_id, ls.is_public, ls.password,
                   ls.current_track_id, ls.is_active, ls.created_by, ls.mode,
                   a.name as album_name, a.cover_url,
                   t.name as current_track_name,
                   u.name as created_by_name
            FROM listening_sessions ls
            LEFT JOIN albums a ON ls.album_id = a.id
            LEFT JOIN tracks t ON ls.current_track_id = t.id
            LEFT JOIN users u ON ls.created_by = u.id
            WHERE ls.is_active = 1 AND ls.is_public = 1
            ORDER BY ls.created_at DESC
        """).fetchall()

        result = []
        for s in sessions:
            conns = active_sessions.get(s["code"], {}).get("connections", {})
            active_count = len({e["user_key"] for e in conns.values()})
            result.append(ListeningSession(
                id=s["id"],
                code=s["code"],
                name=s["name"],
                album_id=s["album_id"],
                album_name=s["album_name"],
                cover_url=s["cover_url"],
                current_track_id=s["current_track_id"],
                current_track_name=s["current_track_name"],
                participant_count=active_count,
                is_public=bool(s["is_public"]),
                has_password=bool(s["password"]),
                created_by_name=s["created_by_name"],
                is_active=bool(s["is_active"]),
                mode=s["mode"] or "listening"
            ))
        return result


@router.post("")
def create_session(data: SessionCreate, user: dict = Depends(get_current_user)):
    """Create a new listening session."""
    x_user_id = user["id"]
    code = generate_session_code()
    # Hash the room password at rest (never store plaintext).
    password_hash = hash_password(data.password) if data.password else None

    album = None
    first_track = None

    with get_connection() as conn:
        if data.album_id:
            album = conn.execute("SELECT * FROM albums WHERE id = ?", (data.album_id,)).fetchone()
            if not album:
                raise HTTPException(404, "Album not found")

            first_track = conn.execute(
                "SELECT id FROM tracks WHERE album_id = ? ORDER BY disc_number, track_number LIMIT 1",
                (data.album_id,)
            ).fetchone()

        conn.execute("""
            INSERT INTO listening_sessions (code, name, album_id, current_track_id, created_by, is_public, password, mode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (code, data.name, data.album_id, first_track["id"] if first_track else None, x_user_id, 1 if data.is_public else 0, password_hash, data.mode))

        conn.execute("""
            INSERT OR IGNORE INTO session_participants (session_id, user_id)
            VALUES ((SELECT id FROM listening_sessions WHERE code = ?), ?)
        """, (code, x_user_id))

    active_sessions[code] = {
        "connections": {},
        "album_id": data.album_id,
        "current_track_id": first_track["id"] if first_track else None,
        "media": None,
        # Bumps on every now-playing change; queue advance requests carry the
        # seq they saw so a stale/duplicate advance is a no-op (no double-skip).
        "media_seq": 0,
        # Ephemeral like/dislike on the current song ({user_id: 1|-1}),
        # reset on every now-playing change.
        "media_votes": {},
        "is_playing": False,
        "playback_position": 0,
        "playback_started_at": None
    }

    return {"code": code, "name": data.name, "mode": data.mode, "album": dict(album) if album else None}


@router.get("/{code}")
def get_session(code: str):
    """Get session details."""
    with get_connection() as conn:
        session = conn.execute("""
            SELECT ls.*, a.name as album_name, a.cover_url, t.name as current_track_name, t.duration_ms as current_track_duration,
                   u.name as created_by_name
            FROM listening_sessions ls
            LEFT JOIN albums a ON ls.album_id = a.id
            LEFT JOIN tracks t ON ls.current_track_id = t.id
            LEFT JOIN users u ON ls.created_by = u.id
            WHERE ls.code = ? AND ls.is_active = 1
        """, (code,)).fetchone()

        if not session:
            raise HTTPException(404, "Session not found")

        participants = conn.execute("""
            SELECT u.id, u.name FROM session_participants sp
            JOIN users u ON sp.user_id = u.id
            WHERE sp.session_id = ?
        """, (session["id"],)).fetchall()

        active_listener_ids = []
        if code in active_sessions:
            active_listener_ids = [
                e["user_key"] for e in active_sessions[code]["connections"].values()
            ]

        participant_list = []
        for p in participants:
            participant_list.append({
                "id": p["id"],
                "name": p["name"],
                "is_online": p["id"] in active_listener_ids
            })

        playback_state = {"is_playing": False, "position": 0}
        media_track = None
        if code in active_sessions:
            state = active_sessions[code]
            media_track = state.get("media_track")
            playback_state["is_playing"] = state["is_playing"]
            if state["is_playing"] and state["playback_started_at"]:
                elapsed = int((time.time() - state["playback_started_at"]) * 1000)
                playback_state["position"] = state["playback_position"] + elapsed
            else:
                playback_state["position"] = state["playback_position"]

        return {
            "id": session["id"],
            "code": code,
            "name": session["name"],
            "album_id": session["album_id"],
            "album_name": session["album_name"],
            "cover_url": session["cover_url"],
            "current_track_id": session["current_track_id"],
            "current_track_name": session["current_track_name"],
            "current_track_duration": session["current_track_duration"],
            "participants": participant_list,
            "active_listeners": len(active_listener_ids),
            "is_active": bool(session["is_active"]),
            "is_public": bool(session["is_public"]),
            "has_password": bool(session["password"]),
            "created_by": session["created_by"],
            "created_by_name": session["created_by_name"],
            "mode": session["mode"] or "listening",
            "media": json.loads(session["current_media"]) if session["current_media"] else None,
            "media_track": media_track,
            "queue": fetch_queue(conn, session["id"]),
            "playback": playback_state
        }


@router.post("/{code}/join")
def join_session(code: str, data: SessionJoin = None, user: dict = Depends(get_current_user)):
    """Join an existing session."""
    x_user_id = user["id"]

    with get_connection() as conn:
        session = conn.execute(
            "SELECT id, password FROM listening_sessions WHERE code = ? AND is_active = 1",
            (code,)
        ).fetchone()

        if not session:
            raise HTTPException(404, "Session not found")

        if session["password"]:
            provided_password = data.password if data else None
            if not provided_password or not verify_password(provided_password, session["password"]):
                raise HTTPException(403, "Invalid password")

        conn.execute("""
            INSERT OR IGNORE INTO session_participants (session_id, user_id)
            VALUES (?, ?)
        """, (session["id"], x_user_id))

    return {"ok": True}


@router.post("/{code}/track")
async def update_session_track(
    code: str,
    track_id: int = Query(...),
    keep_playing: bool = Query(False),
    play: bool = Query(False),
    user: dict = Depends(get_current_user),
):
    """Update the current track in a session.

    `play`: manual track pick that starts playback immediately — one atomic
    broadcast instead of a track/seek/play triplet (whose pause->play flip
    raced on remote Spotify clients). `keep_playing`: the room mirrors a
    native Spotify context advance; clients must NOT re-issue playback.
    Neither flag: track changes and the room is paused.
    """
    x_user_id = user["id"]
    user_name = None
    with get_connection() as conn:
        conn.execute("""
            UPDATE listening_sessions SET current_track_id = ?
            WHERE code = ? AND is_active = 1
        """, (track_id, code))

        track = conn.execute(
            "SELECT duration_ms FROM tracks WHERE id = ?", (track_id,)
        ).fetchone()

        if x_user_id:
            user = conn.execute("SELECT name FROM users WHERE id = ?", (x_user_id,)).fetchone()
            user_name = user["name"] if user else None

    if code in active_sessions:
        is_playing = keep_playing or play
        active_sessions[code]["current_track_id"] = track_id
        active_sessions[code]["playback_position"] = 0
        active_sessions[code]["is_playing"] = is_playing
        active_sessions[code]["playback_started_at"] = time.time() if is_playing else None

        await broadcast_to_session(code, {
            "type": "track_change",
            "track_id": track_id,
            "duration": track["duration_ms"] if track else 0,
            "position": 0,
            "is_playing": is_playing,
            "keep_playing": keep_playing,
            "changed_by": x_user_id,
            "changed_by_name": user_name
        })

    return {"ok": True}


@router.post("/{code}/mode")
async def set_session_mode(code: str, mode: str = Query(...), user: dict = Depends(get_current_user)):
    """Switch a room between listening and hangout mode (creator or admin only).

    Playback state is left untouched — switching to hangout keeps any album
    playing, and switching back restores the ranking UI around it.
    """
    if mode not in ("listening", "hangout"):
        raise HTTPException(400, "Invalid mode")

    with get_connection() as conn:
        session = conn.execute(
            "SELECT created_by, mode FROM listening_sessions WHERE code = ? AND is_active = 1",
            (code,)
        ).fetchone()
        if not session:
            raise HTTPException(404, "Session not found")
        if session["created_by"] != user["id"] and not user["is_admin"]:
            raise HTTPException(403, "Only the room creator can change the mode")
        if (session["mode"] or "listening") == mode:
            return {"ok": True, "mode": mode}

        conn.execute("UPDATE listening_sessions SET mode = ? WHERE code = ?", (mode, code))

    await broadcast_to_session(code, {
        "type": "mode_change",
        "mode": mode,
        "changed_by": user["id"],
        "changed_by_name": user["name"]
    })

    return {"ok": True, "mode": mode}


@router.post("/{code}/album")
async def set_session_album(code: str, album_id: int = Query(...), user: dict = Depends(get_current_user)):
    """Change the album for a session."""
    x_user_id = user["id"]
    user_name = None
    with get_connection() as conn:
        album = conn.execute("SELECT * FROM albums WHERE id = ?", (album_id,)).fetchone()
        if not album:
            raise HTTPException(404, "Album not found")

        first_track = conn.execute(
            "SELECT id, name, duration_ms FROM tracks WHERE album_id = ? ORDER BY disc_number, track_number LIMIT 1",
            (album_id,)
        ).fetchone()

        conn.execute("""
            UPDATE listening_sessions SET album_id = ?, current_track_id = ?
            WHERE code = ? AND is_active = 1
        """, (album_id, first_track["id"] if first_track else None, code))

        if x_user_id:
            user = conn.execute("SELECT name FROM users WHERE id = ?", (x_user_id,)).fetchone()
            user_name = user["name"] if user else None

    if code in active_sessions:
        active_sessions[code]["album_id"] = album_id
        active_sessions[code]["current_track_id"] = first_track["id"] if first_track else None
        active_sessions[code]["playback_position"] = 0
        active_sessions[code]["is_playing"] = False
        active_sessions[code]["playback_started_at"] = None

        await broadcast_to_session(code, {
            "type": "album_change",
            "album_id": album_id,
            "album_name": album["name"],
            "cover_url": album["cover_url"],
            "track_id": first_track["id"] if first_track else None,
            "track_name": first_track["name"] if first_track else None,
            "track_duration": first_track["duration_ms"] if first_track else None,
            "changed_by": x_user_id,
            "changed_by_name": user_name
        })

    return {"ok": True, "album": dict(album), "first_track": dict(first_track) if first_track else None}


@router.post("/{code}/media")
async def set_session_media(code: str, media: SessionMediaSet, user: dict = Depends(get_current_user)):
    """Set the hangout now-playing: an individual Spotify track or album.

    Distinct from /album (listening mode, library albums for ranking) —
    hangout media is any Spotify catalog item, no DB album rows involved.
    """
    media_dict = media.model_dump()
    with get_connection() as conn:
        updated = conn.execute("""
            UPDATE listening_sessions SET current_media = ?
            WHERE code = ? AND is_active = 1
        """, (json.dumps(media_dict), code))
        if updated.rowcount == 0:
            raise HTTPException(404, "Session not found")
        row = conn.execute("SELECT name FROM users WHERE id = ?", (user["id"],)).fetchone()
        user_name = row["name"] if row else None

    if code in active_sessions:
        state = active_sessions[code]
        state["media"] = media_dict
        state["media_seq"] = state.get("media_seq", 0) + 1
        state["media_track"] = None
        state["media_votes"] = {}
        state["playback_position"] = 0
        state["is_playing"] = True
        state["playback_started_at"] = time.time()

        await broadcast_to_session(code, {
            "type": "media_change",
            "media": media_dict,
            "media_seq": state["media_seq"],
            "is_playing": True,
            "position": 0,
            "changed_by": user["id"],
            "changed_by_name": user_name
        })

    return {"ok": True}


@router.get("/{code}/queue")
def get_queue(code: str):
    """The room's shared play queue."""
    with get_connection() as conn:
        session = conn.execute(
            "SELECT id FROM listening_sessions WHERE code = ? AND is_active = 1", (code,)
        ).fetchone()
        if not session:
            raise HTTPException(404, "Session not found")
        return {"queue": fetch_queue(conn, session["id"])}


@router.post("/{code}/queue")
async def add_to_queue(code: str, item: SessionMediaSet, user: dict = Depends(get_current_user)):
    """Add a Spotify track/album to the shared queue (any signed-in member).

    If nothing is on yet, the item skips the queue and starts playing —
    the first pick in an idle room shouldn't sit waiting behind nothing.
    """
    media_dict = item.model_dump()
    with get_connection() as conn:
        session = conn.execute(
            "SELECT id, current_media FROM listening_sessions WHERE code = ? AND is_active = 1",
            (code,)
        ).fetchone()
        if not session:
            raise HTTPException(404, "Session not found")

        state = active_sessions.get(code)
        current = state["media"] if state else (
            json.loads(session["current_media"]) if session["current_media"] else None
        )

        started = current is None
        if started:
            conn.execute(
                "UPDATE listening_sessions SET current_media = ? WHERE id = ?",
                (json.dumps(media_dict), session["id"])
            )
        else:
            conn.execute("""
                INSERT INTO session_queue (session_id, added_by, type, spotify_id, name, artist, image, duration_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (session["id"], user["id"], item.type, item.spotify_id, item.name,
                  item.artist, item.image, item.duration_ms))
        queue = fetch_queue(conn, session["id"])

    if started and state is not None:
        state["media"] = media_dict
        state["media_seq"] = state.get("media_seq", 0) + 1
        state["media_track"] = None
        state["media_votes"] = {}
        state["playback_position"] = 0
        state["is_playing"] = True
        state["playback_started_at"] = time.time()
        await broadcast_to_session(code, {
            "type": "media_change",
            "media": media_dict,
            "media_seq": state["media_seq"],
            "is_playing": True,
            "position": 0,
            "changed_by": user["id"],
            "changed_by_name": user["name"]
        })
    elif not started:
        await broadcast_to_session(code, {
            "type": "queue_update",
            "action": "added",
            "item": {**media_dict, "added_by": user["id"], "added_by_name": user["name"]},
            "by": user["id"],
            "by_name": user["name"],
            "queue": queue
        })

    return {"ok": True, "started": started, "queue": queue}


@router.delete("/{code}/queue/{item_id}")
async def remove_from_queue(code: str, item_id: int, user: dict = Depends(get_current_user)):
    """Remove a queue item (whoever added it, the room creator, or an admin)."""
    with get_connection() as conn:
        session = conn.execute(
            "SELECT id, created_by FROM listening_sessions WHERE code = ? AND is_active = 1",
            (code,)
        ).fetchone()
        if not session:
            raise HTTPException(404, "Session not found")

        row = conn.execute(
            "SELECT added_by, name FROM session_queue WHERE id = ? AND session_id = ?",
            (item_id, session["id"])
        ).fetchone()
        if not row:
            raise HTTPException(404, "Queue item not found")
        if row["added_by"] != user["id"] and session["created_by"] != user["id"] and not user["is_admin"]:
            raise HTTPException(403, "You can only remove your own queue items")

        conn.execute("DELETE FROM session_queue WHERE id = ?", (item_id,))
        queue = fetch_queue(conn, session["id"])

    await broadcast_to_session(code, {
        "type": "queue_update",
        "action": "removed",
        "item": {"id": item_id, "name": row["name"]},
        "by": user["id"],
        "by_name": user["name"],
        "queue": queue
    })
    return {"ok": True, "queue": queue}


@router.post("/{code}/queue/{item_id}/vote")
async def vote_queue_item(code: str, item_id: int, vote: str = Query(...), user: dict = Depends(get_current_user)):
    """Like/dislike a queue item — net score reorders the queue.

    Toggle semantics like reactions: voting the same way again removes the
    vote; voting the other way switches it. One vote per user per item.
    """
    if vote not in ("up", "down"):
        raise HTTPException(400, "Vote must be 'up' or 'down'")
    value = 1 if vote == "up" else -1

    with get_connection() as conn:
        session = conn.execute(
            "SELECT id FROM listening_sessions WHERE code = ? AND is_active = 1", (code,)
        ).fetchone()
        if not session:
            raise HTTPException(404, "Session not found")

        row = conn.execute(
            "SELECT id FROM session_queue WHERE id = ? AND session_id = ?",
            (item_id, session["id"])
        ).fetchone()
        if not row:
            raise HTTPException(404, "Queue item not found")

        existing = conn.execute(
            "SELECT vote FROM queue_votes WHERE queue_item_id = ? AND user_id = ?",
            (item_id, user["id"])
        ).fetchone()
        if existing and existing["vote"] == value:
            conn.execute(
                "DELETE FROM queue_votes WHERE queue_item_id = ? AND user_id = ?",
                (item_id, user["id"])
            )
        else:
            conn.execute("""
                INSERT INTO queue_votes (queue_item_id, user_id, vote) VALUES (?, ?, ?)
                ON CONFLICT(queue_item_id, user_id) DO UPDATE SET vote = excluded.vote
            """, (item_id, user["id"], value))
        queue = fetch_queue(conn, session["id"])

    await broadcast_to_session(code, {
        "type": "queue_update",
        "action": "voted",
        "item": {"id": item_id},
        "by": user["id"],
        "by_name": user["name"],
        "queue": queue
    })
    return {"ok": True, "queue": queue}


async def _advance_now_playing(code: str, state: dict, skip_reason: str = None) -> dict:
    """Pop the highest-voted queue item into now-playing; clear it if empty.

    All DB work and state mutation happen before the first await, so callers
    that guard on media_seq synchronously can't be interleaved by a concurrent
    advance on the single event loop.
    """
    with get_connection() as conn:
        session = conn.execute(
            "SELECT id FROM listening_sessions WHERE code = ? AND is_active = 1", (code,)
        ).fetchone()
        if not session:
            raise HTTPException(404, "Session not found")

        # Highest net vote score plays next (same ordering the queue shows).
        head = conn.execute(QUEUE_ORDER_SQL + " LIMIT 1", (session["id"],)).fetchone()

        media_dict = None
        if head:
            conn.execute("DELETE FROM session_queue WHERE id = ?", (head["id"],))
            media_dict = {
                "type": head["type"], "spotify_id": head["spotify_id"],
                "name": head["name"], "artist": head["artist"],
                "image": head["image"], "duration_ms": head["duration_ms"]
            }
        # Empty queue clears now-playing: the room reads "nothing on" again
        # and the next added item starts immediately instead of queueing
        # behind a song that already finished.
        conn.execute(
            "UPDATE listening_sessions SET current_media = ? WHERE id = ?",
            (json.dumps(media_dict) if media_dict else None, session["id"])
        )
        queue = fetch_queue(conn, session["id"])

    if head:
        state["media"] = media_dict
        state["media_seq"] = state.get("media_seq", 0) + 1
        state["media_track"] = None
        state["media_votes"] = {}
        state["playback_position"] = 0
        state["is_playing"] = True
        state["playback_started_at"] = time.time()
        await broadcast_to_session(code, {
            "type": "media_change",
            "media": media_dict,
            "media_seq": state["media_seq"],
            "is_playing": True,
            "position": 0,
            "auto": True,
            "skip_reason": skip_reason,
            "changed_by": None,
            "changed_by_name": head["added_by_name"]
        })
        await broadcast_to_session(code, {
            "type": "queue_update",
            "action": "advanced",
            "item": None,
            "by": None,
            "by_name": None,
            "queue": queue
        })
        return {"ok": True, "advanced": True, "queue": queue}

    # Queue drained — clear now-playing and stop the server clock so pong
    # doesn't resurrect playback.
    state["media"] = None
    state["media_seq"] = state.get("media_seq", 0) + 1
    state["media_track"] = None
    state["media_votes"] = {}
    state["is_playing"] = False
    state["playback_position"] = 0
    state["playback_started_at"] = None
    await broadcast_to_session(code, {
        "type": "media_change",
        "media": None,
        "media_seq": state["media_seq"],
        "is_playing": False,
        "position": 0,
        "auto": True,
        "skip_reason": skip_reason,
        "changed_by": None,
        "changed_by_name": None
    })
    return {"ok": True, "advanced": False, "queue": queue}


@router.post("/{code}/queue/next")
async def advance_queue(
    code: str,
    seq: Optional[int] = Query(None),
    user: Optional[dict] = Depends(get_optional_user),
):
    """Pop the queue head into now-playing (auto-advance on track end, or skip).

    Every connected client may report a track end, so advances are guarded by
    `seq`: the media_seq the client last saw. A request carrying a stale seq
    means someone already advanced — it's a no-op instead of a double-skip.

    Anonymous guests may advance too: a guest-only room must not stall when a
    track ends, attribution comes from the queue item (not the caller), and the
    seq guard already de-dupes concurrent reports.
    """
    state = active_sessions.get(code)
    if state is None:
        raise HTTPException(404, "Session not active")

    if seq is not None and seq != state.get("media_seq", 0):
        with get_connection() as conn:
            session = conn.execute(
                "SELECT id FROM listening_sessions WHERE code = ? AND is_active = 1", (code,)
            ).fetchone()
            queue = fetch_queue(conn, session["id"]) if session else []
        return {"ok": True, "advanced": False, "queue": queue}

    return await _advance_now_playing(code, state)


def _media_vote_counts(state: dict) -> dict:
    votes = state.get("media_votes", {})
    return {
        "likes": sum(1 for v in votes.values() if v == 1),
        "dislikes": sum(1 for v in votes.values() if v == -1),
        "voters": [{"user_id": uid, "vote": v} for uid, v in votes.items()]
    }


@router.post("/{code}/media/vote")
async def vote_current_media(code: str, vote: str = Query(...), user: dict = Depends(get_current_user)):
    """Like/dislike the song currently playing (toggle, one vote per user).

    Votes are ephemeral per play — kept in memory and reset whenever the
    now-playing changes. When a majority of the people online dislike the
    song (at least 2), it's skipped: the queue advances automatically.
    """
    if vote not in ("up", "down"):
        raise HTTPException(400, "Vote must be 'up' or 'down'")

    state = active_sessions.get(code)
    if state is None or not state.get("media"):
        raise HTTPException(404, "Nothing is playing")

    value = 1 if vote == "up" else -1
    votes = state.setdefault("media_votes", {})
    if votes.get(user["id"]) == value:
        votes.pop(user["id"])
    else:
        votes[user["id"]] = value

    counts = _media_vote_counts(state)

    # Vote-to-skip decision + seq snapshot happen before any await, so a
    # concurrent vote can't sneak in between decision and advance.
    online = len(session_listeners(state))
    threshold = max(2, -(-online // 2))  # ceil(online / 2), never below 2
    should_skip = counts["dislikes"] >= threshold
    seq_at_vote = state.get("media_seq", 0)

    await broadcast_to_session(code, {
        "type": "media_vote",
        **counts,
        "by": user["id"],
        "by_name": user["name"]
    })

    skipped = False
    if should_skip and state.get("media_seq", 0) == seq_at_vote:
        await _advance_now_playing(code, state, skip_reason="votes")
        skipped = True

    return {"ok": True, **counts, "skipped": skipped}


@router.post("/{code}/playback")
async def control_playback(code: str, action: str = Query(...), position: Optional[int] = Query(None), user: dict = Depends(get_current_user)):
    """Control playback (play/pause/seek)."""
    if code not in active_sessions:
        raise HTTPException(404, "Session not active")

    state = active_sessions[code]

    # "by" lets clients that already applied the action optimistically
    # (e.g. the seeking user) skip re-applying their own echo.
    if action == "play":
        state["is_playing"] = True
        state["playback_started_at"] = time.time()
        await broadcast_to_session(code, {
            "type": "playback",
            "action": "play",
            "position": state["playback_position"],
            "by": user["id"]
        })

    elif action == "pause":
        if state["is_playing"] and state["playback_started_at"]:
            elapsed = int((time.time() - state["playback_started_at"]) * 1000)
            state["playback_position"] += elapsed
        state["is_playing"] = False
        state["playback_started_at"] = None
        await broadcast_to_session(code, {
            "type": "playback",
            "action": "pause",
            "position": state["playback_position"],
            "by": user["id"]
        })

    elif action == "seek" and position is not None:
        state["playback_position"] = position
        if state["is_playing"]:
            state["playback_started_at"] = time.time()
        await broadcast_to_session(code, {
            "type": "playback",
            "action": "seek",
            "position": position,
            "by": user["id"]
        })

    return {"ok": True}


@router.get("/{code}/messages")
def get_session_messages(
    code: str,
    before_id: Optional[int] = Query(None),
    after_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=100),
):
    """Chat history, keyset-paginated by message id (offset shifts under live
    inserts). `before_id` pages older (scroll-up); `after_id` is reconnect
    catch-up. Always returned ascending."""
    with get_connection() as conn:
        session = conn.execute(
            "SELECT id FROM listening_sessions WHERE code = ?", (code,)
        ).fetchone()
        if not session:
            raise HTTPException(404, "Session not found")

        where = "m.session_id = ?"
        params = [session["id"]]
        if after_id is not None:
            where += " AND m.id > ?"
            params.append(after_id)
            order = "ASC"
        else:
            if before_id is not None:
                where += " AND m.id < ?"
                params.append(before_id)
            order = "DESC"

        rows = conn.execute(f"""
            SELECT m.id, m.user_id, u.name as user_name, m.content, m.kind, m.created_at
            FROM session_messages m
            JOIN users u ON m.user_id = u.id
            WHERE {where}
            ORDER BY m.id {order}
            LIMIT ?
        """, (*params, limit)).fetchall()

        messages = [dict(r) for r in rows]
        if order == "DESC":
            messages.reverse()

        for m in messages:
            m["reactions"] = []
        if messages:
            by_id = {m["id"]: m for m in messages}
            placeholders = ",".join("?" * len(by_id))
            reactions = conn.execute(f"""
                SELECT r.message_id, r.emoji, r.user_id, u.name as user_name
                FROM message_reactions r
                JOIN users u ON r.user_id = u.id
                WHERE r.message_id IN ({placeholders})
                ORDER BY r.created_at
            """, list(by_id.keys())).fetchall()
            for r in reactions:
                by_id[r["message_id"]]["reactions"].append({
                    "emoji": r["emoji"],
                    "user_id": r["user_id"],
                    "user_name": r["user_name"]
                })

    return {"messages": messages, "has_more": len(rows) == limit}


@router.websocket("/{code}/ws")
async def session_websocket(websocket: WebSocket, code: str, token: Optional[str] = Query(None)):
    """WebSocket endpoint for real-time session updates.

    Identity comes from a session token in the query string (browsers can't
    set WS headers). An invalid/absent token connects as an anonymous guest,
    which is fine for listening in public rooms.
    """
    await websocket.accept()

    # Resolve identity from the session token (never a client-supplied id).
    from auth_deps import _user_from_token
    authed = _user_from_token(token)
    user_id = authed["id"] if authed else None

    if code not in active_sessions:
        with get_connection() as conn:
            session = conn.execute(
                "SELECT album_id, current_track_id, current_media, name FROM listening_sessions WHERE code = ? AND is_active = 1",
                (code,)
            ).fetchone()
            if session:
                active_sessions[code] = {
                    "connections": {},
                    "album_id": session["album_id"],
                    "current_track_id": session["current_track_id"],
                    "media": json.loads(session["current_media"]) if session["current_media"] else None,
                    "media_seq": 0,
                    "media_votes": {},
                    "is_playing": False,
                    "playback_position": 0,
                    "playback_started_at": None
                }
            else:
                await websocket.close()
                return

    user_name = "Guest"
    session_db_id = None
    with get_connection() as conn:
        session = conn.execute("SELECT id FROM listening_sessions WHERE code = ? AND is_active = 1", (code,)).fetchone()
        if session:
            session_db_id = session["id"]
        if user_id:
            user = conn.execute("SELECT name FROM users WHERE id = ?", (user_id,)).fetchone()
            if user:
                user_name = user["name"]
            if session_db_id:
                conn.execute("""
                    INSERT OR IGNORE INTO session_participants (session_id, user_id)
                    VALUES (?, ?)
                """, (session_db_id, user_id))

    # Key by a per-socket id: a reconnect or second tab from the same user
    # must never overwrite (or later delete) another live socket's entry.
    state = active_sessions[code]
    user_key = user_id if user_id else f"guest_{uuid.uuid4().hex[:8]}"
    conn_id = uuid.uuid4().hex
    first_connection = not user_is_connected(state, user_key)
    state["connections"][conn_id] = {
        "ws": websocket,
        "user_key": user_key,
        "user_name": user_name,
    }

    if first_connection:
        await broadcast_to_session(code, {
            "type": "user_joined",
            "user_id": user_key,
            "user_name": user_name,
            "active_count": len(session_listeners(state))
        })

    current_position = state["playback_position"]
    if state["is_playing"] and state["playback_started_at"]:
        elapsed = int((time.time() - state["playback_started_at"]) * 1000)
        current_position += elapsed

    queue = []
    if session_db_id:
        with get_connection() as conn:
            queue = fetch_queue(conn, session_db_id)

    await websocket.send_json({
        "type": "sync",
        "track_id": state["current_track_id"],
        "media": state.get("media"),
        "media_seq": state.get("media_seq", 0),
        "media_track": state.get("media_track"),
        "media_votes": _media_vote_counts(state),
        "is_playing": state["is_playing"],
        "position": current_position,
        "listeners": session_listeners(state),
        "queue": queue
    })

    try:
        last_chat_at = 0.0
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "ping":
                state = active_sessions.get(code, {})
                # Hangout clients mirror their Spotify clock in (track within
                # album context + position) so a rejoin resumes mid-album
                # instead of restarting at track 1. Latest report wins.
                prog = data.get("progress")
                if (
                    isinstance(prog, dict) and state.get("media") and state.get("is_playing")
                    and prog.get("media_seq") == state.get("media_seq", 0)
                    and isinstance(prog.get("track_spotify_id"), str)
                    and isinstance(prog.get("position"), (int, float))
                ):
                    state["media_track"] = {
                        "spotify_id": prog["track_spotify_id"],
                        "name": str(prog.get("track_name") or ""),
                        "duration_ms": prog.get("duration_ms") if isinstance(prog.get("duration_ms"), (int, float)) else 0
                    }
                    state["playback_position"] = max(0, int(prog["position"]))
                    state["playback_started_at"] = time.time()
                current_position = state.get("playback_position", 0)
                if state.get("is_playing") and state.get("playback_started_at"):
                    elapsed = int((time.time() - state["playback_started_at"]) * 1000)
                    current_position += elapsed
                # Autoplay fallback: a track overran its duration and no
                # client reported the end — advance the queue server-side.
                m = state.get("media")
                if (state.get("is_playing") and m and m.get("type") == "track"
                        and m.get("duration_ms")
                        and current_position >= m["duration_ms"] + 2000):
                    try:
                        await _advance_now_playing(code, state)
                    except HTTPException:
                        pass
                    current_position = state.get("playback_position", 0)
                    if state.get("is_playing") and state.get("playback_started_at"):
                        current_position += int((time.time() - state["playback_started_at"]) * 1000)
                await websocket.send_json({
                    "type": "pong",
                    "position": current_position,
                    "is_playing": state.get("is_playing", False),
                    "media_track": state.get("media_track")
                })

            elif msg_type == "chat":
                # Authed users only — guests are read-only in chat.
                if not user_id or not session_db_id:
                    await websocket.send_json({"type": "error", "message": "Sign in to chat"})
                    continue
                content = str(data.get("content") or "").strip()
                if not content or len(content) > 1000:
                    continue
                # 'gif' messages carry a Giphy media URL as content; anything
                # else falls back to plain text so old clients keep working.
                kind = "gif" if data.get("kind") == "gif" else "text"
                if kind == "gif" and not _is_giphy_url(content):
                    continue
                # Light flood guard per connection.
                now = time.time()
                if now - last_chat_at < 0.3:
                    continue
                last_chat_at = now
                # ISO UTC so browsers parse it unambiguously (SQLite's
                # CURRENT_TIMESTAMP format is treated as local time by JS).
                created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                # Persist before broadcasting: the PK is the authoritative
                # ordering and a crash must not deliver an unpersisted message.
                with get_connection() as conn:
                    cur = conn.execute(
                        "INSERT INTO session_messages (session_id, user_id, content, kind, created_at) VALUES (?, ?, ?, ?, ?)",
                        (session_db_id, user_id, content, kind, created_at)
                    )
                    msg_id = cur.lastrowid
                await broadcast_to_session(code, {
                    "type": "chat_message",
                    "id": msg_id,
                    # Echoed back so the sender reconciles its optimistic bubble.
                    "client_id": data.get("client_id"),
                    "user_id": user_id,
                    "user_name": user_name,
                    "content": content,
                    "kind": kind,
                    "created_at": created_at
                })

            elif msg_type == "typing":
                # Ephemeral — relayed, never persisted. Clients filter self.
                await broadcast_to_session(code, {
                    "type": "user_typing",
                    "user_id": user_key,
                    "user_name": user_name
                })

            elif msg_type == "reaction":
                if not user_id or not session_db_id:
                    continue
                message_id = data.get("message_id")
                emoji = str(data.get("emoji") or "")
                if not isinstance(message_id, int) or not emoji or len(emoji) > 16:
                    continue
                with get_connection() as conn:
                    msg = conn.execute(
                        "SELECT id FROM session_messages WHERE id = ? AND session_id = ?",
                        (message_id, session_db_id)
                    ).fetchone()
                    if not msg:
                        continue
                    existing = conn.execute(
                        "SELECT 1 FROM message_reactions WHERE message_id = ? AND user_id = ? AND emoji = ?",
                        (message_id, user_id, emoji)
                    ).fetchone()
                    if existing:
                        conn.execute(
                            "DELETE FROM message_reactions WHERE message_id = ? AND user_id = ? AND emoji = ?",
                            (message_id, user_id, emoji)
                        )
                        action = "removed"
                    else:
                        conn.execute(
                            "INSERT INTO message_reactions (message_id, user_id, emoji) VALUES (?, ?, ?)",
                            (message_id, user_id, emoji)
                        )
                        action = "added"
                await broadcast_to_session(code, {
                    "type": "reaction",
                    "message_id": message_id,
                    "emoji": emoji,
                    "user_id": user_id,
                    "user_name": user_name,
                    "action": action
                })
    except Exception:
        state = active_sessions.get(code)
        # Identity check: only remove OUR entry, never a newer socket's.
        if state and state["connections"].get(conn_id, {}).get("ws") is websocket:
            del state["connections"][conn_id]
            if not user_is_connected(state, user_key):
                await broadcast_to_session(code, {
                    "type": "user_left",
                    "user_id": user_key,
                    "user_name": user_name,
                    "active_count": len(session_listeners(state))
                })


@router.delete("/{code}")
async def end_session(code: str, user: dict = Depends(get_current_user)):
    """End a listening session (creator or admin only)."""
    with get_connection() as conn:
        session = conn.execute(
            "SELECT created_by FROM listening_sessions WHERE code = ? AND is_active = 1",
            (code,)
        ).fetchone()
        if not session:
            raise HTTPException(404, "Session not found")
        if session["created_by"] != user["id"] and not user["is_admin"]:
            raise HTTPException(403, "Only the room creator can close it")

        conn.execute("""
            UPDATE listening_sessions SET is_active = 0
            WHERE code = ?
        """, (code,))

    if code in active_sessions:
        await broadcast_to_session(code, {
            "type": "session_ended",
            "message": "This room has been closed"
        })
        for entry in list(active_sessions[code]["connections"].values()):
            try:
                await entry["ws"].close()
            except Exception:
                pass
        del active_sessions[code]

    return {"ok": True}
