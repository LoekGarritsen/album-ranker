"""Authentication dependencies.

Identity is established from an opaque session token presented as
`Authorization: Bearer <token>` — NOT from a client-supplied user id.
Tokens are looked up by their SHA-256 hash (stored at rest).
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, Header, HTTPException

from database import get_connection
from security import hash_token


def _user_from_token(token: Optional[str]) -> Optional[dict]:
    if not token:
        return None
    th = hash_token(token)
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT u.id, u.name, u.is_admin, u.email, u.created_at, s.expires_at
            FROM auth_sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = ?
            """,
            (th,),
        ).fetchone()
        if not row:
            return None
        # Expiry check (stored as ISO/SQLite timestamp).
        try:
            exp = datetime.fromisoformat(str(row["expires_at"]))
        except ValueError:
            return None
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if exp < now:
            conn.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (th,))
            return None
        conn.execute(
            "UPDATE auth_sessions SET last_used_at = CURRENT_TIMESTAMP WHERE token_hash = ?",
            (th,),
        )
        return {
            "id": row["id"],
            "name": row["name"],
            "is_admin": bool(row["is_admin"]),
            "email": row["email"],
        }


def _extract_bearer(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None


def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """Require a valid session. Raises 401 otherwise."""
    user = _user_from_token(_extract_bearer(authorization))
    if not user:
        raise HTTPException(401, "Not authenticated")
    return user


def get_optional_user(authorization: Optional[str] = Header(None)) -> Optional[dict]:
    """Return the user if authenticated, else None (no error)."""
    return _user_from_token(_extract_bearer(authorization))


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Require an authenticated admin."""
    if not user["is_admin"]:
        raise HTTPException(403, "Admin access required")
    return user
