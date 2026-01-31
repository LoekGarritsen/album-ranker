"""
User management routes.
"""
from fastapi import APIRouter, HTTPException, Header
from typing import Optional

from database import get_connection
from models import UserCreate, User, PinVerify

router = APIRouter(prefix="/api/users", tags=["users"])


def verify_admin(user_id: Optional[int]) -> bool:
    """Check if a user is an admin."""
    if not user_id:
        return False
    with get_connection() as conn:
        row = conn.execute(
            "SELECT is_admin FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return row and row["is_admin"] == 1


@router.get("", response_model=list[User])
def list_users():
    """List all users."""
    with get_connection() as conn:
        rows = conn.execute("SELECT id, name, is_admin, created_at FROM users ORDER BY name").fetchall()
        return [dict(row) for row in rows]


@router.post("", response_model=User)
def create_user(user: UserCreate):
    """Create a new user."""
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                "INSERT INTO users (name, is_admin) VALUES (?, 0) RETURNING id, name, is_admin, created_at",
                (user.name,)
            )
            return dict(cursor.fetchone())
        except Exception:
            raise HTTPException(400, "User already exists")


@router.post("/verify-pin")
def verify_pin(data: PinVerify):
    """Verify admin PIN for elevated access."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT pin FROM users WHERE id = ? AND is_admin = 1",
            (data.user_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Admin user not found")
        if row["pin"] != data.pin:
            raise HTTPException(401, "Invalid PIN")
        return {"ok": True}
