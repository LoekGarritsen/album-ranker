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
                mode TEXT DEFAULT 'listening',
                current_media TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS session_participants (
                session_id INTEGER REFERENCES listening_sessions(id) ON DELETE CASCADE,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (session_id, user_id)
            );

            -- Chat messages in rooms (hangout mode + listening chat)
            CREATE TABLE IF NOT EXISTS session_messages (
                id INTEGER PRIMARY KEY,
                session_id INTEGER NOT NULL REFERENCES listening_sessions(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                content TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'text',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_session_messages_session
                ON session_messages(session_id, id);

            -- Shared play queue (hangout mode): anyone can add and reorder.
            -- position is the manual base order; votes sort above it.
            CREATE TABLE IF NOT EXISTS session_queue (
                id INTEGER PRIMARY KEY,
                session_id INTEGER NOT NULL REFERENCES listening_sessions(id) ON DELETE CASCADE,
                added_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                type TEXT NOT NULL,
                spotify_id TEXT NOT NULL,
                name TEXT NOT NULL,
                artist TEXT DEFAULT '',
                image TEXT,
                duration_ms INTEGER DEFAULT 0,
                position INTEGER DEFAULT 0,
                album_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_session_queue_session
                ON session_queue(session_id, id);

            -- Like/dislike on queue items: net score reorders the queue
            -- (most-wanted plays next). One vote per user, toggle semantics.
            CREATE TABLE IF NOT EXISTS queue_votes (
                queue_item_id INTEGER NOT NULL REFERENCES session_queue(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                vote INTEGER NOT NULL CHECK(vote IN (1, -1)),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (queue_item_id, user_id)
            );

            -- Personal favorites: saved Spotify tracks/albums for quick re-queue
            CREATE TABLE IF NOT EXISTS user_favorites (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                type TEXT NOT NULL,
                spotify_id TEXT NOT NULL,
                name TEXT NOT NULL,
                artist TEXT DEFAULT '',
                image TEXT,
                duration_ms INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, spotify_id)
            );

            -- Emoji reactions on chat messages (toggle semantics)
            CREATE TABLE IF NOT EXISTS message_reactions (
                message_id INTEGER NOT NULL REFERENCES session_messages(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                emoji TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (message_id, user_id, emoji)
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

            -- LRCLIB lyrics cache (negative lookups cached with found=0)
            CREATE TABLE IF NOT EXISTS lyrics_cache (
                spotify_track_id TEXT PRIMARY KEY,
                synced_lyrics TEXT,
                plain_lyrics TEXT,
                instrumental INTEGER DEFAULT 0,
                found INTEGER DEFAULT 0,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Club rounds: nominate -> vote -> blind rate -> reveal
            CREATE TABLE IF NOT EXISTS club_rounds (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'nominating'
                    CHECK(status IN ('nominating', 'voting', 'rating', 'revealed')),
                album_id INTEGER REFERENCES albums(id) ON DELETE SET NULL,
                created_by INTEGER REFERENCES users(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- One nomination per user per round (replaced while nominating)
            CREATE TABLE IF NOT EXISTS club_nominations (
                id INTEGER PRIMARY KEY,
                round_id INTEGER NOT NULL REFERENCES club_rounds(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                spotify_id TEXT NOT NULL,
                name TEXT NOT NULL,
                artist TEXT NOT NULL,
                cover_url TEXT,
                release_date TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(round_id, user_id)
            );

            -- One vote per user per round (re-vote replaces)
            CREATE TABLE IF NOT EXISTS club_votes (
                round_id INTEGER NOT NULL REFERENCES club_rounds(id) ON DELETE CASCADE,
                nomination_id INTEGER NOT NULL REFERENCES club_nominations(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (round_id, user_id)
            );

            -- Listen-later backlog: Spotify albums bookmarked per user
            CREATE TABLE IF NOT EXISTS listen_later (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                spotify_id TEXT NOT NULL,
                name TEXT NOT NULL,
                artist TEXT NOT NULL,
                image TEXT,
                release_date TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, spotify_id)
            );

            -- Custom user-made album lists
            CREATE TABLE IF NOT EXISTS lists (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS list_items (
                id INTEGER PRIMARY KEY,
                list_id INTEGER NOT NULL REFERENCES lists(id) ON DELETE CASCADE,
                album_id INTEGER NOT NULL REFERENCES albums(id) ON DELETE CASCADE,
                position INTEGER NOT NULL DEFAULT 0,
                note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(list_id, album_id)
            );

            -- Likes on rating comments (kind: 'album' or 'track')
            CREATE TABLE IF NOT EXISTS ranking_likes (
                id INTEGER PRIMARY KEY,
                kind TEXT NOT NULL CHECK(kind IN ('album', 'track')),
                ranking_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(kind, ranking_id, user_id)
            );

            -- In-app notifications (payload is a JSON blob per type)
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                type TEXT NOT NULL,
                payload TEXT NOT NULL DEFAULT '{}',
                read INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_notifications_user
                ON notifications(user_id, id);

            -- Followed Spotify artists for the new-release watch
            CREATE TABLE IF NOT EXISTS artist_follows (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                spotify_artist_id TEXT NOT NULL,
                name TEXT NOT NULL,
                image TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, spotify_artist_id)
            );

            -- Cache of an artist's recent releases (Spotify), refreshed every 6h
            CREATE TABLE IF NOT EXISTS release_cache (
                spotify_artist_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Append-only score history: one row per rating change (re-rates)
            CREATE TABLE IF NOT EXISTS ranking_history (
                id INTEGER PRIMARY KEY,
                kind TEXT NOT NULL CHECK(kind IN ('album', 'track')),
                item_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                score REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_ranking_history_item
                ON ranking_history(kind, item_id, user_id, id);
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

    # Room mode: 'listening' (album sync) or 'hangout' (chat-first, music optional)
    if 'mode' not in columns:
        conn.execute("ALTER TABLE listening_sessions ADD COLUMN mode TEXT DEFAULT 'listening'")

    # Hangout now-playing (JSON: type/spotify_id/name/artist/image/duration_ms)
    if 'current_media' not in columns:
        conn.execute("ALTER TABLE listening_sessions ADD COLUMN current_media TEXT")

    # Message kind: 'text' or 'gif' (content = GIF URL)
    cursor = conn.execute("PRAGMA table_info(session_messages)")
    message_columns = {row[1] for row in cursor.fetchall()}
    if 'kind' not in message_columns:
        conn.execute("ALTER TABLE session_messages ADD COLUMN kind TEXT NOT NULL DEFAULT 'text'")

    # Manual queue order (drag to reorder); backfill keeps insertion order
    cursor = conn.execute("PRAGMA table_info(session_queue)")
    queue_columns = {row[1] for row in cursor.fetchall()}
    if 'position' not in queue_columns:
        conn.execute("ALTER TABLE session_queue ADD COLUMN position INTEGER DEFAULT 0")
        conn.execute("UPDATE session_queue SET position = id")

    # Source album of a queued track — improves LRCLIB lyrics matching
    if 'album_name' not in queue_columns:
        conn.execute("ALTER TABLE session_queue ADD COLUMN album_name TEXT")

    if 'email' not in user_columns:
        conn.execute("ALTER TABLE users ADD COLUMN email TEXT")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email) WHERE email IS NOT NULL"
    )
