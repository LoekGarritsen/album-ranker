"""
User directory routes.

User accounts are created and authenticated via magic-link login (see
routers/auth.py). This module only exposes the roster used by comparison and
stats views. Identity/authorisation is handled by auth_deps, not here.
"""
from fastapi import APIRouter

from database import get_connection
from models import User

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=list[User])
def list_users():
    """List all users (names + admin flag) for comparison/stats UIs."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, name, is_admin, created_at FROM users ORDER BY name"
        ).fetchall()
        return [dict(row) for row in rows]
