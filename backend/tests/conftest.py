"""
Pytest fixtures for Album Ranker backend tests.

Schema comes from the real ``init_db`` (no drift). Auth is exercised with real
session tokens issued straight into ``auth_sessions`` (the magic-link flow
itself is covered separately in ``test_auth.py``).
"""
import sqlite3
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def temp_db_path(tmp_path):
    return tmp_path / "test_album_ranker.db"


def _seed(db_path):
    """Initialise schema via init_db, then reset to a known fixture dataset."""
    from database import init_db
    init_db()
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(
        """
        DELETE FROM users;
        INSERT INTO users (id, name, is_admin, email) VALUES (1, 'TestAdmin', 1, 'admin@test.dev');
        INSERT INTO users (id, name, is_admin, email) VALUES (2, 'TestUser', 0, 'user@test.dev');
        INSERT INTO albums (id, spotify_id, name, artist, cover_url, release_date, genres)
            VALUES (1, 'spotify:album:test123', 'Test Album', 'Test Artist',
                    'https://example.com/cover.jpg', '2024-01-01', '["rock", "indie"]');
        """
    )
    for i in range(1, 4):
        conn.execute(
            "INSERT INTO tracks (id, album_id, spotify_id, name, artist, disc_number, track_number, duration_ms)"
            " VALUES (?, 1, ?, ?, 'Test Artist', 1, ?, 180000)",
            (i, f"spotify:track:test{i}", f"Track {i}", i),
        )
    conn.commit()
    conn.close()


@pytest.fixture
def client(temp_db_path):
    """FastAPI test client backed by a temp DB, with rate limiting disabled."""
    with patch("database.DB_PATH", temp_db_path), \
         patch("database.get_db_path", return_value=temp_db_path):
        _seed(temp_db_path)
        from main import app
        from state import active_sessions
        from ratelimit import limiter
        active_sessions.clear()
        limiter.enabled = False  # avoid 429s from repeated auth calls in tests
        with TestClient(app) as test_client:
            yield test_client


def _issue_raw(db_path, user_id):
    """Insert a valid session token for a user; return the raw token string."""
    from security import generate_token, hash_token
    raw = generate_token()
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO auth_sessions (user_id, token_hash, expires_at) VALUES (?, ?, ?)",
        (user_id, hash_token(raw), (datetime.utcnow() + timedelta(days=1)).isoformat()),
    )
    conn.commit()
    conn.close()
    return raw


@pytest.fixture
def admin_token(temp_db_path, client):
    """Raw session token for the admin (for WebSocket ?token= query)."""
    return _issue_raw(temp_db_path, 1)


@pytest.fixture
def user_token(temp_db_path, client):
    """Raw session token for a regular user."""
    return _issue_raw(temp_db_path, 2)


@pytest.fixture
def admin_headers(admin_token):
    """Authenticated admin (user id 1)."""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def user_headers(user_token):
    """Authenticated regular user (user id 2)."""
    return {"Authorization": f"Bearer {user_token}"}


# --- Spotify mocks ---

@pytest.fixture
def mock_spotify_search():
    results = [
        {"spotify_id": "spotify:album:newalbum1", "name": "New Album 1", "artist": "Artist 1",
         "cover_url": "https://i.scdn.co/image/1", "release_date": "2024-06-01"},
        {"spotify_id": "spotify:album:newalbum2", "name": "New Album 2", "artist": "Artist 2",
         "cover_url": "https://i.scdn.co/image/2", "release_date": "2024-05-15"},
    ]
    with patch("routers.spotify_routes.spotify_client.search_albums", new_callable=AsyncMock) as mock:
        mock.return_value = results
        yield mock


@pytest.fixture
def mock_spotify_album_details():
    with patch("routers.albums.spotify_client.get_album_details", new_callable=AsyncMock) as mock:
        mock.return_value = {"genres": ["rock", "alternative"]}
        yield mock


@pytest.fixture
def mock_spotify_tracks():
    tracks = [
        {"spotify_id": "spotify:track:new1", "name": "New Track 1", "artist": "Artist 1",
         "track_number": 1, "duration_ms": 200000},
        {"spotify_id": "spotify:track:new2", "name": "New Track 2", "artist": "Artist 1",
         "track_number": 2, "duration_ms": 180000},
    ]
    with patch("routers.albums.spotify_client.get_album_tracks", new_callable=AsyncMock) as mock:
        mock.return_value = tracks
        yield mock


@pytest.fixture
def mock_spotify_all(mock_spotify_search, mock_spotify_album_details, mock_spotify_tracks):
    return {"search": mock_spotify_search, "details": mock_spotify_album_details, "tracks": mock_spotify_tracks}
