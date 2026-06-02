"""Security helpers: token generation and password hashing.

No third-party crypto deps — uses the standard library only.
Passwords are hashed with PBKDF2-HMAC-SHA256 and verified in constant time.
"""
import hashlib
import hmac
import secrets


def generate_token(nbytes: int = 32) -> str:
    """Return a URL-safe, cryptographically-random opaque token."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """SHA-256 of an opaque token, for storage at rest.

    Magic-link and session tokens are stored hashed so a database leak
    cannot be replayed. Lookups hash the incoming token and match the digest.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def hash_password(password: str) -> str:
    """Hash a room password. Returns 'salt$hash' (both hex)."""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return f"{salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time verify a password against a 'salt$hash' value."""
    if not stored or "$" not in stored:
        return False
    salt_hex, hash_hex = stored.split("$", 1)
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return hmac.compare_digest(dk.hex(), hash_hex)
