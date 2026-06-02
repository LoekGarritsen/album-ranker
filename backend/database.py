import sqlite3
from pathlib import Path
from contextlib import contextmanager

import config

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
                disc_number INTEGER DEFAULT 1,
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

            -- Listening sessions (rooms) for real-time sync
            CREATE TABLE IF NOT EXISTS listening_sessions (
                id INTEGER PRIMARY KEY,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                album_id INTEGER REFERENCES albums(id) ON DELETE SET NULL,
                current_track_id INTEGER REFERENCES tracks(id) ON DELETE SET NULL,
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

            -- Spotify OAuth tokens for Web Playback SDK
            CREATE TABLE IF NOT EXISTS spotify_tokens (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                access_token TEXT NOT NULL,
                refresh_token TEXT NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Magic-link login tokens (single-use, short-lived, stored hashed)
            CREATE TABLE IF NOT EXISTS magic_links (
                id INTEGER PRIMARY KEY,
                email TEXT NOT NULL,
                token_hash TEXT UNIQUE NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                used INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_magic_links_hash ON magic_links(token_hash);

            -- Issued session tokens (replace client-trusted X-User-Id), stored hashed
            CREATE TABLE IF NOT EXISTS auth_sessions (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token_hash TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_auth_sessions_hash ON auth_sessions(token_hash);
        """)

        # Migrations for existing databases (must run before admin seeding so
        # the email column exists)
        _run_migrations(conn)

        # Insert admin user if none exist. The admin's email comes from the
        # ADMIN_EMAIL env var (never hardcoded); magic-link login is sent there.
        cursor = conn.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1")
        if cursor.fetchone()[0] == 0:
            conn.execute(
                "INSERT INTO users (name, is_admin, email) VALUES (?, 1, ?)",
                ("Loek", config.ADMIN_EMAIL or None),
            )
        elif config.ADMIN_EMAIL:
            # Backfill the admin email on an existing DB if it's missing.
            conn.execute(
                "UPDATE users SET email = ? WHERE is_admin = 1 AND (email IS NULL OR email = '')",
                (config.ADMIN_EMAIL,),
            )

def _run_migrations(conn):
    """Run database migrations for existing tables"""
    # Check if listening_sessions needs the new columns
    cursor = conn.execute("PRAGMA table_info(listening_sessions)")
    columns = {row[1] for row in cursor.fetchall()}

    if 'name' not in columns:
        # Add new columns for listening rooms feature
        conn.execute("ALTER TABLE listening_sessions ADD COLUMN name TEXT DEFAULT 'Listening Room'")
        conn.execute("ALTER TABLE listening_sessions ADD COLUMN is_public INTEGER DEFAULT 1")
        conn.execute("ALTER TABLE listening_sessions ADD COLUMN password TEXT")

        # Update existing sessions to have a name based on their album
        conn.execute("""
            UPDATE listening_sessions
            SET name = COALESCE(
                (SELECT albums.name FROM albums WHERE albums.id = listening_sessions.album_id),
                'Listening Room'
            )
            WHERE name = 'Listening Room' OR name IS NULL
        """)

    # Add disc_number to tracks table
    cursor = conn.execute("PRAGMA table_info(tracks)")
    track_columns = {row[1] for row in cursor.fetchall()}

    if 'disc_number' not in track_columns:
        conn.execute("ALTER TABLE tracks ADD COLUMN disc_number INTEGER DEFAULT 1")

    # Add email to users (magic-link login key). Unique among non-null values.
    cursor = conn.execute("PRAGMA table_info(users)")
    user_columns = {row[1] for row in cursor.fetchall()}

    if 'email' not in user_columns:
        conn.execute("ALTER TABLE users ADD COLUMN email TEXT")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email) WHERE email IS NOT NULL"
    )
