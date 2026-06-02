import httpx
import os
import base64
import urllib.parse
from datetime import datetime, timedelta
from typing import Optional

# OAuth scopes needed for Web Playback SDK
SPOTIFY_SCOPES = [
    "streaming",
    "user-read-email",
    "user-read-private",
    "user-read-playback-state",
    "user-modify-playback-state",
]

class SpotifyClient:
    def __init__(self):
        self.client_id = os.getenv("SPOTIFY_CLIENT_ID", "")
        self.client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "")
        self.token: Optional[str] = None
        self.token_expires: Optional[datetime] = None

    async def _get_token(self) -> str:
        if self.token and self.token_expires and datetime.now() < self.token_expires:
            return self.token

        if not self.client_id or not self.client_secret:
            raise ValueError("Spotify credentials not configured.")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://accounts.spotify.com/api/token",
                data={"grant_type": "client_credentials"},
                auth=(self.client_id, self.client_secret)
            )
            response.raise_for_status()
            data = response.json()

            self.token = data["access_token"]
            self.token_expires = datetime.now() + timedelta(seconds=data["expires_in"] - 60)
            return self.token

    async def search_albums(self, query: str, limit: int = 20) -> list[dict]:
        token = await self._get_token()

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.spotify.com/v1/search",
                params={"q": query, "type": "album", "limit": limit},
                headers={"Authorization": f"Bearer {token}"}
            )
            response.raise_for_status()
            data = response.json()

            albums = []
            for item in data.get("albums", {}).get("items", []):
                artists = ", ".join(a["name"] for a in item.get("artists", []))
                images = item.get("images", [])
                cover_url = images[0]["url"] if images else None

                albums.append({
                    "spotify_id": item["id"],
                    "name": item["name"],
                    "artist": artists,
                    "cover_url": cover_url,
                    "release_date": item.get("release_date")
                })

            return albums

    async def get_album_details(self, album_id: str) -> dict:
        """Fetch album details including genres"""
        token = await self._get_token()

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.spotify.com/v1/albums/{album_id}",
                headers={"Authorization": f"Bearer {token}"}
            )
            response.raise_for_status()
            data = response.json()

            # Get artist IDs to fetch their genres
            artist_ids = [a["id"] for a in data.get("artists", [])]
            genres = list(data.get("genres", []))

            # If album has no genres, fetch from artists
            if not genres and artist_ids:
                artist_response = await client.get(
                    "https://api.spotify.com/v1/artists",
                    params={"ids": ",".join(artist_ids[:50])},
                    headers={"Authorization": f"Bearer {token}"}
                )
                if artist_response.status_code == 200:
                    artist_data = artist_response.json()
                    for artist in artist_data.get("artists", []):
                        genres.extend(artist.get("genres", []))
                    genres = list(set(genres))[:5]  # Dedupe and limit

            return {"genres": genres}

    async def get_album_tracks(self, album_id: str) -> list[dict]:
        """Fetch all tracks from an album"""
        token = await self._get_token()

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.spotify.com/v1/albums/{album_id}/tracks",
                params={"limit": 50},
                headers={"Authorization": f"Bearer {token}"}
            )
            response.raise_for_status()
            data = response.json()

            tracks = []
            for item in data.get("items", []):
                artists = ", ".join(a["name"] for a in item.get("artists", []))
                tracks.append({
                    "spotify_id": item["id"],
                    "name": item["name"],
                    "artist": artists,
                    "disc_number": item.get("disc_number", 1),
                    "track_number": item.get("track_number", 0),
                    "duration_ms": item.get("duration_ms", 0)
                })

            return tracks

    async def get_new_releases(self, limit: int = 20) -> list[dict]:
        """Fetch new album releases from Spotify"""
        token = await self._get_token()

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.spotify.com/v1/browse/new-releases",
                params={"limit": limit, "country": "NL"},
                headers={"Authorization": f"Bearer {token}"}
            )
            response.raise_for_status()
            data = response.json()

            albums = []
            for item in data.get("albums", {}).get("items", []):
                artists = ", ".join(a["name"] for a in item.get("artists", []))
                images = item.get("images", [])
                cover_url = images[0]["url"] if images else None

                albums.append({
                    "spotify_id": item["id"],
                    "name": item["name"],
                    "artist": artists,
                    "cover_url": cover_url,
                    "release_date": item.get("release_date")
                })

            return albums

spotify_client = SpotifyClient()


class SpotifyOAuth:
    """Handle Spotify OAuth for user authentication (Web Playback SDK)"""

    def __init__(self):
        self.client_id = os.getenv("SPOTIFY_CLIENT_ID", "")
        self.client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "")
        self.redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI", "https://albums.garritsen.dev/api/spotify/callback")

    def get_authorize_url(self, state: str) -> str:
        """Generate OAuth authorization URL"""
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(SPOTIFY_SCOPES),
            "state": state,
        }
        return f"https://accounts.spotify.com/authorize?{urllib.parse.urlencode(params)}"

    async def exchange_code(self, code: str) -> dict:
        """Exchange authorization code for tokens"""
        auth_header = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://accounts.spotify.com/api/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                },
                headers={
                    "Authorization": f"Basic {auth_header}",
                    "Content-Type": "application/x-www-form-urlencoded",
                }
            )
            response.raise_for_status()
            data = response.json()

            return {
                "access_token": data["access_token"],
                "refresh_token": data["refresh_token"],
                "expires_in": data["expires_in"],
            }

    async def refresh_token(self, refresh_token: str) -> dict:
        """Refresh an expired access token"""
        auth_header = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://accounts.spotify.com/api/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
                headers={
                    "Authorization": f"Basic {auth_header}",
                    "Content-Type": "application/x-www-form-urlencoded",
                }
            )
            response.raise_for_status()
            data = response.json()

            return {
                "access_token": data["access_token"],
                "refresh_token": data.get("refresh_token", refresh_token),
                "expires_in": data["expires_in"],
            }


spotify_oauth = SpotifyOAuth()


async def fetch_lyrics(artist: str, title: str) -> str | None:
    """Fetch lyrics from lyrics.ovh API"""
    import urllib.parse
    artist_encoded = urllib.parse.quote(artist.split(',')[0].strip())
    title_encoded = urllib.parse.quote(title)

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"https://api.lyrics.ovh/v1/{artist_encoded}/{title_encoded}",
                timeout=10.0
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("lyrics")
        except Exception:
            pass
    return None
