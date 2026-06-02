"""
Spotify integration routes (OAuth, search, tokens).
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import RedirectResponse
from datetime import datetime, timedelta
import httpx

from database import get_connection
from models import SpotifyAlbum
from spotify import spotify_client, spotify_oauth
from auth_deps import get_current_user, require_admin
from security import generate_token
from state import spotify_oauth_states

router = APIRouter(prefix="/api/spotify", tags=["spotify"])

OAUTH_STATE_TTL_SEC = 600


def _purge_expired_states():
    now = datetime.now()
    for k in [k for k, v in spotify_oauth_states.items() if v["expires_at"] < now]:
        spotify_oauth_states.pop(k, None)


@router.get("/search", response_model=list[SpotifyAlbum])
async def search_spotify(
    q: str = Query(..., min_length=1),
    admin: dict = Depends(require_admin),
):
    """Search for albums on Spotify (admin only)."""
    try:
        albums = await spotify_client.search_albums(q)
        return albums
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Spotify API error: {str(e)}")


@router.get("/new-releases", response_model=list[SpotifyAlbum])
async def get_new_releases():
    """Get new album releases from Spotify."""
    try:
        albums = await spotify_client.get_new_releases()
        return albums
    except Exception as e:
        raise HTTPException(500, f"Spotify API error: {str(e)}")


@router.get("/auth")
def spotify_auth(user: dict = Depends(get_current_user)):
    """Get Spotify authorization URL for OAuth flow."""
    _purge_expired_states()
    state = generate_token(24)
    spotify_oauth_states[state] = {
        "user_id": user["id"],
        "expires_at": datetime.now() + timedelta(seconds=OAUTH_STATE_TTL_SEC),
    }
    auth_url = spotify_oauth.get_authorize_url(state)
    return {"auth_url": auth_url}


@router.get("/callback")
async def spotify_callback(code: str = Query(...), state: str = Query(...)):
    """Handle OAuth callback from Spotify.

    Identity comes from the random `state` nonce minted in /auth and bound to
    the authenticated user — never from a client-supplied id.
    """
    _purge_expired_states()
    entry = spotify_oauth_states.pop(state, None)
    if not entry or entry["expires_at"] < datetime.now():
        raise HTTPException(400, "Invalid or expired OAuth state")
    user_id = entry["user_id"]

    try:
        tokens = await spotify_oauth.exchange_code(code)
        print(f"[Spotify OAuth] Got tokens for user {user_id}")
    except Exception as e:
        print(f"[Spotify OAuth] Token exchange failed for user {user_id}: {e}")
        return RedirectResponse(url=f"/?spotify_error={str(e)}")

    # Verify the token works by checking the Spotify account
    async with httpx.AsyncClient() as client:
        try:
            me_res = await client.get(
                "https://api.spotify.com/v1/me",
                headers={"Authorization": f"Bearer {tokens['access_token']}"}
            )
            if me_res.status_code == 200:
                me_data = me_res.json()
                print(f"[Spotify OAuth] User {user_id} -> Spotify account: {me_data.get('display_name')} ({me_data.get('email')}), plan: {me_data.get('product')}")
            else:
                print(f"[Spotify OAuth] User {user_id} -> /me check failed: {me_res.status_code}")
        except Exception as e:
            print(f"[Spotify OAuth] User {user_id} -> /me check error: {e}")

    # Store tokens in database
    expires_at = datetime.now() + timedelta(seconds=tokens["expires_in"])

    with get_connection() as conn:
        conn.execute("""
            INSERT INTO spotify_tokens (user_id, access_token, refresh_token, expires_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                access_token = excluded.access_token,
                refresh_token = excluded.refresh_token,
                expires_at = excluded.expires_at,
                updated_at = CURRENT_TIMESTAMP
        """, (user_id, tokens["access_token"], tokens["refresh_token"], expires_at))

    return RedirectResponse(url="/?spotify_connected=true")


@router.get("/token")
async def get_spotify_token(user: dict = Depends(get_current_user)):
    """Get user's Spotify access token (refreshes if expired)."""
    x_user_id = user["id"]

    with get_connection() as conn:
        row = conn.execute(
            "SELECT access_token, refresh_token, expires_at FROM spotify_tokens WHERE user_id = ?",
            (x_user_id,)
        ).fetchone()

        if not row:
            raise HTTPException(404, "Spotify not connected")

        # Check if token is expired or about to expire (within 5 minutes)
        expires_at = datetime.fromisoformat(row["expires_at"])
        if datetime.now() >= expires_at - timedelta(minutes=5):
            # Refresh the token
            try:
                tokens = await spotify_oauth.refresh_token(row["refresh_token"])
                new_expires_at = datetime.now() + timedelta(seconds=tokens["expires_in"])

                conn.execute("""
                    UPDATE spotify_tokens
                    SET access_token = ?, refresh_token = ?, expires_at = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                """, (tokens["access_token"], tokens["refresh_token"], new_expires_at, x_user_id))

                return {"access_token": tokens["access_token"]}
            except Exception as e:
                # Token refresh failed, user needs to re-authenticate
                conn.execute("DELETE FROM spotify_tokens WHERE user_id = ?", (x_user_id,))
                raise HTTPException(401, "Token expired, please reconnect Spotify")

        return {"access_token": row["access_token"]}


@router.get("/status")
def spotify_status(user: dict = Depends(get_current_user)):
    """Check if user has Spotify connected."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM spotify_tokens WHERE user_id = ?",
            (user["id"],)
        ).fetchone()

        return {"connected": bool(row)}


@router.delete("/disconnect")
def spotify_disconnect(user: dict = Depends(get_current_user)):
    """Disconnect user's Spotify account."""
    with get_connection() as conn:
        conn.execute("DELETE FROM spotify_tokens WHERE user_id = ?", (user["id"],))

    return {"ok": True}
