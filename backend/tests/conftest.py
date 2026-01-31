"""
Pytest fixtures for Album Ranker backend tests.

Provides:
- Temporary SQLite database with schema
- FastAPI test client
- Mock Spotify API responses
"""
import pytest
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch, AsyncMock
from contextlib import contextmanager

from fastapi.testclient import TestClient
import httpx


# --- Database Fixtures ---

@pytest.fixture
def temp_db_path(tmp_path):
    """Create a temporary database file path."""
    return tmp_path / "test_album_ranker.db"


@pytest.fixture
def db_connection(temp_db_path):
    """
    Create a temporary SQLite database with schema initialized.
    Yields a connection factory for tests that need direct DB access.
    """
    @contextmanager
    def get_test_connection():
        conn = sqlite3.connect(temp_db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # Initialize schema
    with get_test_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                is_admin INTEGER DEFAULT 0,
                pin TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS albums (
                id INTEGER PRIMARY KEY,
                spotify_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                artist TEXT NOT NULL,
                cover_url TEXT,
                release_date TEXT,
                genres TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS tracks (
                id INTEGER PRIMARY KEY,
                album_id INTEGER REFERENCES albums(id) ON DELETE CASCADE,
                spotify_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                artist TEXT NOT NULL,
                track_number INTEGER,
                duration_ms INTEGER,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS album_rankings (
                id INTEGER PRIMARY KEY,
                album_id INTEGER REFERENCES albums(id) ON DELETE CASCADE,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                score REAL CHECK(score >= 1 AND score <= 10),
                comment TEXT,
                ranked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(album_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS track_rankings (
                id INTEGER PRIMARY KEY,
                track_id INTEGER REFERENCES tracks(id) ON DELETE CASCADE,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                score REAL CHECK(score >= 1 AND score <= 10),
                comment TEXT,
                ranked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(track_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS listening_sessions (
                id INTEGER PRIMARY KEY,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                album_id INTEGER REFERENCES albums(id) ON DELETE SET NULL,
                current_track_id INTEGER REFERENCES tracks(id),
                created_by INTEGER REFERENCES users(id),
                is_active INTEGER DEFAULT 1,
                is_public INTEGER DEFAULT 1,
                password TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS session_participants (
                session_id INTEGER REFERENCES listening_sessions(id) ON DELETE CASCADE,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (session_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS spotify_tokens (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                access_token TEXT NOT NULL,
                refresh_token TEXT NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

    yield get_test_connection


@pytest.fixture
def seeded_db(db_connection):
    """
    Database with test data pre-seeded:
    - Admin user (id=1, name="TestAdmin", pin="1234")
    - Regular user (id=2, name="TestUser")
    - Album with 3 tracks
    """
    with db_connection() as conn:
        # Create admin user
        conn.execute(
            "INSERT INTO users (id, name, is_admin, pin) VALUES (1, 'TestAdmin', 1, '1234')"
        )
        # Create regular user
        conn.execute(
            "INSERT INTO users (id, name, is_admin) VALUES (2, 'TestUser', 0)"
        )
        # Create album
        conn.execute("""
            INSERT INTO albums (id, spotify_id, name, artist, cover_url, release_date, genres)
            VALUES (1, 'spotify:album:test123', 'Test Album', 'Test Artist',
                    'https://example.com/cover.jpg', '2024-01-01', '["rock", "indie"]')
        """)
        # Create tracks
        for i in range(1, 4):
            conn.execute("""
                INSERT INTO tracks (id, album_id, spotify_id, name, artist, track_number, duration_ms)
                VALUES (?, 1, ?, ?, 'Test Artist', ?, 180000)
            """, (i, f'spotify:track:test{i}', f'Track {i}', i))

    return db_connection


# --- FastAPI Test Client Fixture ---

@pytest.fixture
def client(temp_db_path, seeded_db):
    """
    FastAPI test client with mocked database path.
    Uses seeded_db to ensure test data is available.
    """
    # Patch the database module to use our temp path
    with patch('database.DB_PATH', temp_db_path):
        # Also patch get_db_path to return our temp path
        with patch('database.get_db_path', return_value=temp_db_path):
            # Import app after patching to ensure patches take effect
            from main import app

            # Clear any cached active_sessions state
            from state import active_sessions
            active_sessions.clear()

            with TestClient(app) as test_client:
                yield test_client


@pytest.fixture
def admin_headers():
    """Headers for admin user requests."""
    return {"X-User-Id": "1"}


@pytest.fixture
def user_headers():
    """Headers for regular user requests."""
    return {"X-User-Id": "2"}


# --- Spotify Mock Fixtures ---

@pytest.fixture
def mock_spotify_search():
    """Mock Spotify album search responses."""
    mock_results = [
        {
            "spotify_id": "spotify:album:newalbum1",
            "name": "New Album 1",
            "artist": "Artist 1",
            "cover_url": "https://i.scdn.co/image/1",
            "release_date": "2024-06-01"
        },
        {
            "spotify_id": "spotify:album:newalbum2",
            "name": "New Album 2",
            "artist": "Artist 2",
            "cover_url": "https://i.scdn.co/image/2",
            "release_date": "2024-05-15"
        }
    ]

    with patch('routers.spotify_routes.spotify_client.search_albums', new_callable=AsyncMock) as mock:
        mock.return_value = mock_results
        yield mock


@pytest.fixture
def mock_spotify_album_details():
    """Mock Spotify album details (genres) response."""
    with patch('routers.albums.spotify_client.get_album_details', new_callable=AsyncMock) as mock:
        mock.return_value = {"genres": ["rock", "alternative"]}
        yield mock


@pytest.fixture
def mock_spotify_tracks():
    """Mock Spotify album tracks response."""
    mock_tracks = [
        {
            "spotify_id": "spotify:track:new1",
            "name": "New Track 1",
            "artist": "Artist 1",
            "track_number": 1,
            "duration_ms": 200000
        },
        {
            "spotify_id": "spotify:track:new2",
            "name": "New Track 2",
            "artist": "Artist 1",
            "track_number": 2,
            "duration_ms": 180000
        }
    ]

    with patch('routers.albums.spotify_client.get_album_tracks', new_callable=AsyncMock) as mock:
        mock.return_value = mock_tracks
        yield mock


@pytest.fixture
def mock_spotify_all(mock_spotify_search, mock_spotify_album_details, mock_spotify_tracks):
    """Convenience fixture combining all Spotify mocks."""
    return {
        "search": mock_spotify_search,
        "details": mock_spotify_album_details,
        "tracks": mock_spotify_tracks
    }
