"""In-app notification fan-out helper."""
import json

from database import get_connection


def notify(user_ids, type_: str, payload: dict, exclude_user_id: int | None = None):
    """Insert one notification per target user. Silent no-op on empty targets."""
    targets = [uid for uid in set(user_ids) if uid != exclude_user_id]
    if not targets:
        return
    blob = json.dumps(payload)
    with get_connection() as conn:
        conn.executemany(
            "INSERT INTO notifications (user_id, type, payload) VALUES (?, ?, ?)",
            [(uid, type_, blob) for uid in targets],
        )


def notify_all(type_: str, payload: dict, exclude_user_id: int | None = None):
    """Notify every registered user (small private group)."""
    with get_connection() as conn:
        rows = conn.execute("SELECT id FROM users").fetchall()
    notify([r["id"] for r in rows], type_, payload, exclude_user_id=exclude_user_id)
