import sqlite3
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).parent / "data" / "album_ranker.db"

def get_db_path() -> Path:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return DB_PATH

@contextmanager
def get_connection():
    conn = sqlite3.connect(get_db_path(), check_same_thread=False)
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

def init_db():
    with get_connection() as conn:
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

            -- Album ratings
            CREATE TABLE IF NOT EXISTS album_rankings (
                id INTEGER PRIMARY KEY,
                album_id INTEGER REFERENCES albums(id) ON DELETE CASCADE,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                score REAL CHECK(score >= 1 AND score <= 10),
                comment TEXT,
                ranked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(album_id, user_id)
            );

            -- Track ratings
            CREATE TABLE IF NOT EXISTS track_rankings (
                id INTEGER PRIMARY KEY,
                track_id INTEGER REFERENCES tracks(id) ON DELETE CASCADE,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                score REAL CHECK(score >= 1 AND score <= 10),
                comment TEXT,
                ranked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(track_id, user_id)
            );

            -- Listening sessions for real-time sync
            CREATE TABLE IF NOT EXISTS listening_sessions (
                id INTEGER PRIMARY KEY,
                code TEXT UNIQUE NOT NULL,
                album_id INTEGER REFERENCES albums(id) ON DELETE CASCADE,
                current_track_id INTEGER REFERENCES tracks(id),
                created_by INTEGER REFERENCES users(id),
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS session_participants (
                session_id INTEGER REFERENCES listening_sessions(id) ON DELETE CASCADE,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (session_id, user_id)
            );

            -- Spotify OAuth tokens for Web Playback SDK
            CREATE TABLE IF NOT EXISTS spotify_tokens (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                access_token TEXT NOT NULL,
                refresh_token TEXT NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Insert admin user if none exist
        cursor = conn.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1")
        if cursor.fetchone()[0] == 0:
            conn.execute(
                "INSERT INTO users (name, is_admin, pin) VALUES (?, 1, ?)",
                ("Loek", "0406")
            )
