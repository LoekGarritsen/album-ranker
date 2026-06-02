"""Runtime configuration, read from environment."""
import os

# Resend transactional email
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
MAIL_FROM = os.getenv("MAIL_FROM", "Album Ranker <no-reply@garritsen.dev>")

# Public URL of the frontend (magic links point here)
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8401").rstrip("/")

# Seed/admin bootstrap — the email that owns the admin account.
# Set in backend/.env (never committed). If unset, no admin email is seeded.
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "").strip().lower()

# Token lifetimes
MAGIC_LINK_TTL_MIN = int(os.getenv("MAGIC_LINK_TTL_MIN", "15"))
SESSION_TTL_DAYS = int(os.getenv("SESSION_TTL_DAYS", "30"))

# Sign-up allow-list. Comma-separated emails permitted to request a magic link.
# Empty => open signup. Set this for a private (friends-only) deployment to
# prevent quota-exhaustion / user-table-pollution via the public endpoint.
ALLOWED_EMAILS = {
    e.strip().lower() for e in os.getenv("ALLOWED_EMAILS", "").split(",") if e.strip()
}


def email_allowed(email: str) -> bool:
    """True if signup/login is permitted for this email (open when list empty)."""
    return not ALLOWED_EMAILS or email.strip().lower() in ALLOWED_EMAILS

# CORS allow-list (comma-separated). Defaults cover local dev + prod.
CORS_ORIGINS = [
    o.strip() for o in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:8401,http://127.0.0.1:8401,https://albums.garritsen.dev",
    ).split(",") if o.strip()
]
