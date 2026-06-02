"""
Listening session routes including WebSocket handling.
"""
from fastapi import APIRouter, HTTPException, Depends, Query, WebSocket
from typing import Optional
import random
import string
import time
import uuid

from database import get_connection
from models import ListeningSession, SessionCreate, SessionJoin
from state import active_sessions
from auth_deps import get_current_user
from security import hash_password, verify_password, hash_token

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def generate_session_code():
    """Generate a random 6-character session code."""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


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


def get_user_name(user_id) -> str:
    """Get user name by ID (handles int user IDs and guest_* strings)."""
    if not user_id:
        return "Guest"
    if isinstance(user_id, str) and user_id.startswith("guest_"):
        return "Guest"
    with get_connection() as conn:
        user = conn.execute("SELECT name FROM users WHERE id = ?", (user_id,)).fetchone()
        return user["name"] if user else "Guest"


@router.get("", response_model=list[ListeningSession])
def list_sessions():
    """List all active public rooms."""
    with get_connection() as conn:
        sessions = conn.execute("""
            SELECT ls.id, ls.code, ls.name, ls.album_id, ls.is_public, ls.password,
                   ls.current_track_id, ls.is_active, ls.created_by,
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
            active_count = len(active_sessions.get(s["code"], {}).get("connections", {}))
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
                is_active=bool(s["is_active"])
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
            INSERT INTO listening_sessions (code, name, album_id, current_track_id, created_by, is_public, password)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (code, data.name, data.album_id, first_track["id"] if first_track else None, x_user_id, 1 if data.is_public else 0, password_hash))

        conn.execute("""
            INSERT OR IGNORE INTO session_participants (session_id, user_id)
            VALUES ((SELECT id FROM listening_sessions WHERE code = ?), ?)
        """, (code, x_user_id))

    active_sessions[code] = {
        "connections": {},
        "album_id": data.album_id,
        "current_track_id": first_track["id"] if first_track else None,
        "is_playing": False,
        "playback_position": 0,
        "playback_started_at": None
    }

    return {"code": code, "name": data.name, "album": dict(album) if album else None}


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
            active_listener_ids = list(active_sessions[code]["connections"].keys())

        participant_list = []
        for p in participants:
            participant_list.append({
                "id": p["id"],
                "name": p["name"],
                "is_online": p["id"] in active_listener_ids
            })

        playback_state = {"is_playing": False, "position": 0}
        if code in active_sessions:
            state = active_sessions[code]
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
            "created_by_name": session["created_by_name"],
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
async def update_session_track(code: str, track_id: int = Query(...), user: dict = Depends(get_current_user)):
    """Update the current track in a session."""
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
        active_sessions[code]["current_track_id"] = track_id
        active_sessions[code]["playback_position"] = 0
        active_sessions[code]["is_playing"] = False
        active_sessions[code]["playback_started_at"] = None

        await broadcast_to_session(code, {
            "type": "track_change",
            "track_id": track_id,
            "duration": track["duration_ms"] if track else 0,
            "position": 0,
            "is_playing": False,
            "changed_by": x_user_id,
            "changed_by_name": user_name
        })

    return {"ok": True}


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


@router.post("/{code}/playback")
async def control_playback(code: str, action: str = Query(...), position: Optional[int] = Query(None), user: dict = Depends(get_current_user)):
    """Control playback (play/pause/seek)."""
    if code not in active_sessions:
        raise HTTPException(404, "Session not active")

    state = active_sessions[code]

    if action == "play":
        state["is_playing"] = True
        state["playback_started_at"] = time.time()
        await broadcast_to_session(code, {
            "type": "playback",
            "action": "play",
            "position": state["playback_position"]
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
            "position": state["playback_position"]
        })

    elif action == "seek" and position is not None:
        state["playback_position"] = position
        if state["is_playing"]:
            state["playback_started_at"] = time.time()
        await broadcast_to_session(code, {
            "type": "playback",
            "action": "seek",
            "position": position
        })

    return {"ok": True}


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
                "SELECT album_id, current_track_id, name FROM listening_sessions WHERE code = ? AND is_active = 1",
                (code,)
            ).fetchone()
            if session:
                active_sessions[code] = {
                    "connections": {},
                    "album_id": session["album_id"],
                    "current_track_id": session["current_track_id"],
                    "is_playing": False,
                    "playback_position": 0,
                    "playback_started_at": None
                }
            else:
                await websocket.close()
                return

    user_name = "Guest"
    if user_id:
        with get_connection() as conn:
            user = conn.execute("SELECT name FROM users WHERE id = ?", (user_id,)).fetchone()
            if user:
                user_name = user["name"]
            session = conn.execute("SELECT id FROM listening_sessions WHERE code = ? AND is_active = 1", (code,)).fetchone()
            if session:
                conn.execute("""
                    INSERT OR IGNORE INTO session_participants (session_id, user_id)
                    VALUES (?, ?)
                """, (session["id"], user_id))

    connection_id = user_id if user_id else f"guest_{uuid.uuid4().hex[:8]}"
    active_sessions[code]["connections"][connection_id] = websocket

    await broadcast_to_session(code, {
        "type": "user_joined",
        "user_id": connection_id,
        "user_name": user_name,
        "active_count": len(active_sessions[code]["connections"])
    })

    state = active_sessions[code]
    current_position = state["playback_position"]
    if state["is_playing"] and state["playback_started_at"]:
        elapsed = int((time.time() - state["playback_started_at"]) * 1000)
        current_position += elapsed

    await websocket.send_json({
        "type": "sync",
        "track_id": state["current_track_id"],
        "is_playing": state["is_playing"],
        "position": current_position,
        "listeners": [
            {"user_id": uid, "user_name": get_user_name(uid)}
            for uid in state["connections"].keys()
        ]
    })

    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                state = active_sessions.get(code, {})
                current_position = state.get("playback_position", 0)
                if state.get("is_playing") and state.get("playback_started_at"):
                    elapsed = int((time.time() - state["playback_started_at"]) * 1000)
                    current_position += elapsed
                await websocket.send_json({
                    "type": "pong",
                    "position": current_position,
                    "is_playing": state.get("is_playing", False)
                })
    except Exception:
        if code in active_sessions and connection_id in active_sessions[code]["connections"]:
            del active_sessions[code]["connections"][connection_id]

            await broadcast_to_session(code, {
                "type": "user_left",
                "user_id": connection_id,
                "user_name": user_name,
                "active_count": len(active_sessions[code]["connections"])
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
        for connection_id, ws in list(active_sessions[code]["connections"].items()):
            try:
                await ws.close()
            except Exception:
                pass
        del active_sessions[code]

    return {"ok": True}
