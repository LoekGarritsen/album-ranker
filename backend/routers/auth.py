"""Passwordless (magic-link) authentication.

Flow:
  POST /api/auth/request  {email}        -> emails a single-use sign-in link
  POST /api/auth/verify   {token}        -> exchanges link token for a session token
  GET  /api/auth/me                      -> current user (requires Bearer token)
  POST /api/auth/logout                  -> revokes the current session
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr

import config
from auth_deps import get_current_user
from database import get_connection
from email_service import send_magic_link
from ratelimit import limiter
from security import generate_token, hash_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


class MagicLinkRequest(BaseModel):
    email: EmailStr


class MagicLinkVerify(BaseModel):
    token: str


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _unique_name(conn, base: str) -> str:
    """Derive a unique display name from an email local-part."""
    base = (base or "user").strip()[:50] or "user"
    name, n = base, 1
    while conn.execute("SELECT 1 FROM users WHERE name = ?", (name,)).fetchone():
        n += 1
        name = f"{base}{n}"
    return name


@router.post("/request")
@limiter.limit("5/minute")
async def request_magic_link(data: MagicLinkRequest, request: Request):
    """Send a magic sign-in link. Always returns ok (no account enumeration)."""
    email = data.email.lower().strip()

    with get_connection() as conn:
        user = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if not user:
            # First sign-in creates the account.
            name = _unique_name(conn, email.split("@", 1)[0])
            conn.execute(
                "INSERT INTO users (name, email, is_admin) VALUES (?, ?, 0)",
                (name, email),
            )

        raw = generate_token()
        expires = _now() + timedelta(minutes=config.MAGIC_LINK_TTL_MIN)
        conn.execute(
            "INSERT INTO magic_links (email, token_hash, expires_at) VALUES (?, ?, ?)",
            (email, hash_token(raw), expires.isoformat()),
        )

    link = f"{config.FRONTEND_URL}/auth/verify?token={raw}"
    await send_magic_link(email, link)
    return {"ok": True}


@router.post("/verify")
@limiter.limit("10/minute")
async def verify_magic_link(data: MagicLinkVerify, request: Request):
    """Exchange a magic-link token for a session token."""
    th = hash_token(data.token)
    with get_connection() as conn:
        link = conn.execute(
            "SELECT id, email, expires_at, used FROM magic_links WHERE token_hash = ?",
            (th,),
        ).fetchone()
        if not link or link["used"]:
            raise HTTPException(400, "Invalid or already-used link")
        try:
            exp = datetime.fromisoformat(str(link["expires_at"]))
        except ValueError:
            raise HTTPException(400, "Invalid link")
        if exp < _now():
            raise HTTPException(400, "Link expired")

        # Single-use: burn it immediately.
        conn.execute("UPDATE magic_links SET used = 1 WHERE id = ?", (link["id"],))

        user = conn.execute(
            "SELECT id, name, is_admin, email FROM users WHERE email = ?",
            (link["email"],),
        ).fetchone()
        if not user:
            raise HTTPException(400, "Account not found")

        session_token = generate_token()
        sess_exp = _now() + timedelta(days=config.SESSION_TTL_DAYS)
        conn.execute(
            "INSERT INTO auth_sessions (user_id, token_hash, expires_at) VALUES (?, ?, ?)",
            (user["id"], hash_token(session_token), sess_exp.isoformat()),
        )

    return {
        "token": session_token,
        "user": {
            "id": user["id"],
            "name": user["name"],
            "is_admin": bool(user["is_admin"]),
            "email": user["email"],
        },
    }


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return user


@router.post("/logout")
def logout(request: Request, user: dict = Depends(get_current_user)):
    """Revoke the presenting session token."""
    auth = request.headers.get("authorization", "")
    parts = auth.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        with get_connection() as conn:
            conn.execute(
                "DELETE FROM auth_sessions WHERE token_hash = ?",
                (hash_token(parts[1].strip()),),
            )
    return {"ok": True}
