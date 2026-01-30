from fastapi import FastAPI, HTTPException, Query, Header, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from typing import Optional
import json
import random
import string

from database import init_db, get_connection
from models import (
    UserCreate, User, PinVerify,
    AlbumAdd, Album, SpotifyAlbum, AlbumWithTracks,
    AlbumRankingCreate, TrackRankingCreate, UserRanking, TrackWithRankings,
    UserStats, HotTake, ComparisonItem, ListeningSession, SessionCreate, SessionJoin
)
from spotify import spotify_client, spotify_oauth, fetch_lyrics
from fastapi.responses import RedirectResponse
from datetime import datetime, timedelta

load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="Album Ranker API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8401",
        "http://127.0.0.1:8401",
        "https://albums.garritsen.online",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def verify_admin(user_id: Optional[int]) -> bool:
    if not user_id:
        return False
    with get_connection() as conn:
        row = conn.execute(
            "SELECT is_admin FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return row and row["is_admin"] == 1

# === Users ===
@app.get("/api/users", response_model=list[User])
def list_users():
    with get_connection() as conn:
        rows = conn.execute("SELECT id, name, is_admin, created_at FROM users ORDER BY name").fetchall()
        return [dict(row) for row in rows]

@app.post("/api/users", response_model=User)
def create_user(user: UserCreate):
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                "INSERT INTO users (name, is_admin) VALUES (?, 0) RETURNING id, name, is_admin, created_at",
                (user.name,)
            )
            return dict(cursor.fetchone())
        except Exception:
            raise HTTPException(400, "User already exists")

@app.post("/api/users/verify-pin")
def verify_pin(data: PinVerify):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT pin FROM users WHERE id = ? AND is_admin = 1",
            (data.user_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Admin user not found")
        if row["pin"] != data.pin:
            raise HTTPException(401, "Invalid PIN")
        return {"ok": True}

# === Spotify Search (Admin only) ===
@app.get("/api/spotify/search", response_model=list[SpotifyAlbum])
async def search_spotify(
    q: str = Query(..., min_length=1),
    x_user_id: Optional[int] = Header(None)
):
    if not verify_admin(x_user_id):
        raise HTTPException(403, "Admin access required")
    try:
        albums = await spotify_client.search_albums(q)
        return albums
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Spotify API error: {str(e)}")

@app.get("/api/spotify/new-releases", response_model=list[SpotifyAlbum])
async def get_new_releases():
    try:
        albums = await spotify_client.get_new_releases()
        return albums
    except Exception as e:
        raise HTTPException(500, f"Spotify API error: {str(e)}")

# === Spotify OAuth (for Web Playback SDK) ===
@app.get("/api/spotify/auth")
def spotify_auth(x_user_id: Optional[int] = Header(None)):
    """Redirect user to Spotify authorization"""
    if not x_user_id:
        raise HTTPException(401, "User required")

    # Use user_id as state for security
    state = str(x_user_id)
    auth_url = spotify_oauth.get_authorize_url(state)
    return {"auth_url": auth_url}

@app.get("/api/spotify/callback")
async def spotify_callback(code: str = Query(...), state: str = Query(...)):
    """Handle OAuth callback from Spotify"""
    import httpx

    try:
        user_id = int(state)
    except ValueError:
        raise HTTPException(400, "Invalid state parameter")

    try:
        tokens = await spotify_oauth.exchange_code(code)
        print(f"[Spotify OAuth] Got tokens for user {user_id}")
    except Exception as e:
        print(f"[Spotify OAuth] Token exchange failed for user {user_id}: {e}")
        # Redirect to frontend with error
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

    # Redirect back to frontend with success
    return RedirectResponse(url="/?spotify_connected=true")

@app.get("/api/spotify/token")
async def get_spotify_token(x_user_id: Optional[int] = Header(None)):
    """Get user's Spotify access token (refreshes if expired)"""
    if not x_user_id:
        raise HTTPException(401, "User required")

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

@app.get("/api/spotify/status")
def spotify_status(x_user_id: Optional[int] = Header(None)):
    """Check if user has Spotify connected"""
    if not x_user_id:
        return {"connected": False}

    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM spotify_tokens WHERE user_id = ?",
            (x_user_id,)
        ).fetchone()

        return {"connected": bool(row)}

@app.delete("/api/spotify/disconnect")
def spotify_disconnect(x_user_id: Optional[int] = Header(None)):
    """Disconnect user's Spotify account"""
    if not x_user_id:
        raise HTTPException(401, "User required")

    with get_connection() as conn:
        conn.execute("DELETE FROM spotify_tokens WHERE user_id = ?", (x_user_id,))

    return {"ok": True}

# === Albums ===
@app.get("/api/albums", response_model=list[AlbumWithTracks])
def list_albums():
    with get_connection() as conn:
        albums = conn.execute("SELECT * FROM albums ORDER BY added_at DESC").fetchall()

        users = conn.execute("SELECT id, name FROM users").fetchall()
        user_map = {u["id"]: u["name"] for u in users}

        # Get album rankings
        album_rankings_rows = conn.execute("""
            SELECT ar.album_id, ar.user_id, ar.score, ar.comment, u.name as user_name
            FROM album_rankings ar
            JOIN users u ON ar.user_id = u.id
        """).fetchall()

        album_rankings_map = {}
        for r in album_rankings_rows:
            if r["album_id"] not in album_rankings_map:
                album_rankings_map[r["album_id"]] = {}
            album_rankings_map[r["album_id"]][r["user_id"]] = {
                "score": r["score"],
                "comment": r["comment"],
                "user_name": r["user_name"]
            }

        # Get all tracks with their rankings
        all_tracks = conn.execute("""
            SELECT t.*, tr.user_id, tr.score, tr.comment, u.name as user_name
            FROM tracks t
            LEFT JOIN track_rankings tr ON t.id = tr.track_id
            LEFT JOIN users u ON tr.user_id = u.id
            ORDER BY t.track_number
        """).fetchall()

        # Group tracks by album
        album_tracks = {}
        for t in all_tracks:
            album_id = t["album_id"]
            track_id = t["id"]

            if album_id not in album_tracks:
                album_tracks[album_id] = {}

            if track_id not in album_tracks[album_id]:
                album_tracks[album_id][track_id] = {
                    "id": t["id"],
                    "spotify_id": t["spotify_id"],
                    "name": t["name"],
                    "artist": t["artist"],
                    "track_number": t["track_number"],
                    "duration_ms": t["duration_ms"],
                    "rankings": {}
                }

            if t["user_id"]:
                album_tracks[album_id][track_id]["rankings"][t["user_id"]] = {
                    "score": t["score"],
                    "comment": t["comment"],
                    "user_name": t["user_name"]
                }

        result = []
        for a in albums:
            album_dict = dict(a)
            tracks_dict = album_tracks.get(a["id"], {})
            album_rank_data = album_rankings_map.get(a["id"], {})

            # Build album rankings
            album_user_rankings = []
            album_scores = []
            for user_id, user_name in user_map.items():
                ranking = album_rank_data.get(user_id)
                album_user_rankings.append(UserRanking(
                    user_id=user_id,
                    user_name=user_name,
                    score=ranking["score"] if ranking else None,
                    comment=ranking["comment"] if ranking else None
                ))
                if ranking and ranking["score"]:
                    album_scores.append(ranking["score"])

            # Build tracks with rankings
            tracks_with_rankings = []
            all_track_scores = []

            for track_id, track_data in tracks_dict.items():
                user_rankings = []
                track_scores = []

                for user_id, user_name in user_map.items():
                    ranking = track_data["rankings"].get(user_id)
                    user_rankings.append(UserRanking(
                        user_id=user_id,
                        user_name=user_name,
                        score=ranking["score"] if ranking else None,
                        comment=ranking["comment"] if ranking else None
                    ))
                    if ranking and ranking["score"]:
                        track_scores.append(ranking["score"])
                        all_track_scores.append(ranking["score"])

                track_avg = sum(track_scores) / len(track_scores) if track_scores else None

                tracks_with_rankings.append(TrackWithRankings(
                    id=track_data["id"],
                    spotify_id=track_data["spotify_id"],
                    name=track_data["name"],
                    artist=track_data["artist"],
                    track_number=track_data["track_number"],
                    duration_ms=track_data["duration_ms"],
                    rankings=user_rankings,
                    average_score=round(track_avg, 1) if track_avg else None
                ))

            tracks_with_rankings.sort(key=lambda t: t.track_number)

            album_avg = sum(album_scores) / len(album_scores) if album_scores else None
            track_avg = sum(all_track_scores) / len(all_track_scores) if all_track_scores else None

            # Parse genres from JSON
            genres = None
            if album_dict.get("genres"):
                try:
                    genres = json.loads(album_dict["genres"])
                except:
                    pass
            album_dict["genres"] = genres

            result.append(AlbumWithTracks(
                **album_dict,
                tracks=tracks_with_rankings,
                album_rankings=album_user_rankings,
                average_album_score=round(album_avg, 1) if album_avg else None,
                average_track_score=round(track_avg, 1) if track_avg else None
            ))

        return result

@app.post("/api/albums", response_model=Album)
async def add_album(album: AlbumAdd, x_user_id: Optional[int] = Header(None)):
    if not verify_admin(x_user_id):
        raise HTTPException(403, "Admin access required")

    # Fetch genres from Spotify
    genres = []
    try:
        details = await spotify_client.get_album_details(album.spotify_id)
        genres = details.get("genres", [])
    except:
        pass

    with get_connection() as conn:
        existing = conn.execute(
            "SELECT * FROM albums WHERE spotify_id = ?", (album.spotify_id,)
        ).fetchone()

        if existing:
            raise HTTPException(400, "Album already added")

        cursor = conn.execute(
            """INSERT INTO albums (spotify_id, name, artist, cover_url, release_date, genres)
               VALUES (?, ?, ?, ?, ?, ?) RETURNING *""",
            (album.spotify_id, album.name, album.artist, album.cover_url, album.release_date, json.dumps(genres))
        )
        album_row = dict(cursor.fetchone())
        album_id = album_row["id"]

    # Fetch tracks from Spotify
    try:
        tracks = await spotify_client.get_album_tracks(album.spotify_id)
    except Exception as e:
        with get_connection() as conn:
            conn.execute("DELETE FROM albums WHERE id = ?", (album_id,))
        raise HTTPException(500, f"Failed to fetch tracks: {str(e)}")

    with get_connection() as conn:
        for track in tracks:
            conn.execute(
                """INSERT INTO tracks (album_id, spotify_id, name, artist, track_number, duration_ms)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (album_id, track["spotify_id"], track["name"], track["artist"],
                 track["track_number"], track["duration_ms"])
            )

    return album_row

@app.delete("/api/albums/{album_id}")
def remove_album(album_id: int, x_user_id: Optional[int] = Header(None)):
    if not verify_admin(x_user_id):
        raise HTTPException(403, "Admin access required")

    with get_connection() as conn:
        conn.execute("DELETE FROM albums WHERE id = ?", (album_id,))
        return {"ok": True}

# === Rankings ===
@app.post("/api/rankings/album")
def submit_album_ranking(ranking: AlbumRankingCreate):
    with get_connection() as conn:
        if not conn.execute("SELECT 1 FROM albums WHERE id = ?", (ranking.album_id,)).fetchone():
            raise HTTPException(404, "Album not found")
        if not conn.execute("SELECT 1 FROM users WHERE id = ?", (ranking.user_id,)).fetchone():
            raise HTTPException(404, "User not found")

        conn.execute("""
            INSERT INTO album_rankings (album_id, user_id, score, comment)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(album_id, user_id)
            DO UPDATE SET score = excluded.score, comment = excluded.comment, ranked_at = CURRENT_TIMESTAMP
        """, (ranking.album_id, ranking.user_id, ranking.score, ranking.comment))

        return {"ok": True}

@app.post("/api/rankings/track")
async def submit_track_ranking(ranking: TrackRankingCreate, session_code: Optional[str] = Query(None)):
    with get_connection() as conn:
        if not conn.execute("SELECT 1 FROM tracks WHERE id = ?", (ranking.track_id,)).fetchone():
            raise HTTPException(404, "Track not found")
        user = conn.execute("SELECT id, name FROM users WHERE id = ?", (ranking.user_id,)).fetchone()
        if not user:
            raise HTTPException(404, "User not found")

        conn.execute("""
            INSERT INTO track_rankings (track_id, user_id, score, comment)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(track_id, user_id)
            DO UPDATE SET score = excluded.score, comment = excluded.comment, ranked_at = CURRENT_TIMESTAMP
        """, (ranking.track_id, ranking.user_id, ranking.score, ranking.comment))

    # Broadcast rating to session if provided
    if session_code and session_code in active_sessions:
        await broadcast_to_session(session_code, {
            "type": "rating",
            "track_id": ranking.track_id,
            "user_id": ranking.user_id,
            "user_name": user["name"],
            "score": ranking.score,
            "comment": ranking.comment
        })

    return {"ok": True}

@app.get("/api/tracks/{track_id}")
async def get_track_details(track_id: int):
    with get_connection() as conn:
        track = conn.execute("""
            SELECT t.*, a.name as album_name, a.artist as album_artist, a.cover_url
            FROM tracks t
            JOIN albums a ON t.album_id = a.id
            WHERE t.id = ?
        """, (track_id,)).fetchone()

        if not track:
            raise HTTPException(404, "Track not found")

        rankings = conn.execute("""
            SELECT tr.score, tr.comment, u.id as user_id, u.name as user_name
            FROM track_rankings tr
            JOIN users u ON tr.user_id = u.id
            WHERE tr.track_id = ?
        """, (track_id,)).fetchall()

        scores = [r["score"] for r in rankings if r["score"]]
        avg = sum(scores) / len(scores) if scores else None

    # Fetch lyrics
    lyrics = await fetch_lyrics(track["artist"], track["name"])

    return {
        "id": track["id"],
        "name": track["name"],
        "artist": track["artist"],
        "track_number": track["track_number"],
        "duration_ms": track["duration_ms"],
        "album_name": track["album_name"],
        "album_artist": track["album_artist"],
        "cover_url": track["cover_url"],
        "lyrics": lyrics,
        "rankings": [dict(r) for r in rankings],
        "average_score": round(avg, 1) if avg else None
    }

@app.get("/api/results")
def get_results():
    with get_connection() as conn:
        albums = conn.execute("SELECT * FROM albums").fetchall()

        results = []
        for album in albums:
            # Album rankings
            album_rankings = conn.execute("""
                SELECT ar.score, ar.comment, u.name as user_name
                FROM album_rankings ar
                JOIN users u ON ar.user_id = u.id
                WHERE ar.album_id = ?
            """, (album["id"],)).fetchall()

            album_scores = [r["score"] for r in album_rankings if r["score"]]
            album_avg = sum(album_scores) / len(album_scores) if album_scores else None

            # Track rankings
            tracks = conn.execute("""
                SELECT t.id, t.name, t.track_number,
                       AVG(tr.score) as avg_score,
                       COUNT(tr.score) as rating_count
                FROM tracks t
                LEFT JOIN track_rankings tr ON t.id = tr.track_id
                WHERE t.album_id = ?
                GROUP BY t.id
                ORDER BY t.track_number
            """, (album["id"],)).fetchall()

            track_results = []
            all_track_scores = []
            for t in tracks:
                rankings = conn.execute("""
                    SELECT tr.score, tr.comment, u.name as user_name
                    FROM track_rankings tr
                    JOIN users u ON tr.user_id = u.id
                    WHERE tr.track_id = ?
                """, (t["id"],)).fetchall()

                if t["avg_score"]:
                    all_track_scores.append(t["avg_score"])

                track_results.append({
                    "id": t["id"],
                    "name": t["name"],
                    "track_number": t["track_number"],
                    "average_score": round(t["avg_score"], 1) if t["avg_score"] else None,
                    "rating_count": t["rating_count"],
                    "rankings": [dict(r) for r in rankings]
                })

            track_avg = sum(all_track_scores) / len(all_track_scores) if all_track_scores else None

            results.append({
                "album": dict(album),
                "album_rankings": [dict(r) for r in album_rankings],
                "average_album_score": round(album_avg, 1) if album_avg else None,
                "tracks": track_results,
                "average_track_score": round(track_avg, 1) if track_avg else None
            })

        results.sort(key=lambda x: x["average_album_score"] or 0, reverse=True)
        return {"results": results}

# === Stats Dashboard ===
@app.get("/api/stats")
def get_stats():
    with get_connection() as conn:
        users = conn.execute("SELECT id, name FROM users").fetchall()

        user_stats = []
        for user in users:
            # Album stats
            album_ratings = conn.execute("""
                SELECT ar.score, a.name as album_name
                FROM album_rankings ar
                JOIN albums a ON ar.album_id = a.id
                WHERE ar.user_id = ? AND ar.score IS NOT NULL
                ORDER BY ar.score DESC
            """, (user["id"],)).fetchall()

            # Track stats
            track_count = conn.execute("""
                SELECT COUNT(*) as count FROM track_rankings
                WHERE user_id = ? AND score IS NOT NULL
            """, (user["id"],)).fetchone()["count"]

            track_avg = conn.execute("""
                SELECT AVG(score) as avg FROM track_rankings
                WHERE user_id = ? AND score IS NOT NULL
            """, (user["id"],)).fetchone()["avg"]

            album_scores = [r["score"] for r in album_ratings]
            album_avg = sum(album_scores) / len(album_scores) if album_scores else None

            user_stats.append({
                "user_id": user["id"],
                "user_name": user["name"],
                "albums_rated": len(album_ratings),
                "tracks_rated": track_count,
                "average_album_score": round(album_avg, 2) if album_avg else None,
                "average_track_score": round(track_avg, 2) if track_avg else None,
                "highest_rated_album": album_ratings[0]["album_name"] if album_ratings else None,
                "lowest_rated_album": album_ratings[-1]["album_name"] if album_ratings else None
            })

        # Global stats
        total_albums = conn.execute("SELECT COUNT(*) FROM albums").fetchone()[0]
        total_tracks = conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
        total_album_ratings = conn.execute("SELECT COUNT(*) FROM album_rankings WHERE score IS NOT NULL").fetchone()[0]
        total_track_ratings = conn.execute("SELECT COUNT(*) FROM track_rankings WHERE score IS NOT NULL").fetchone()[0]

        # Top rated tracks
        top_tracks = conn.execute("""
            SELECT t.name, t.artist, a.name as album_name, a.cover_url,
                   AVG(tr.score) as avg_score, COUNT(tr.score) as rating_count
            FROM tracks t
            JOIN albums a ON t.album_id = a.id
            JOIN track_rankings tr ON t.id = tr.track_id
            WHERE tr.score IS NOT NULL
            GROUP BY t.id
            HAVING rating_count >= 1
            ORDER BY avg_score DESC
            LIMIT 10
        """).fetchall()

        # Genre breakdown
        genres_count = {}
        albums_with_genres = conn.execute("SELECT genres FROM albums WHERE genres IS NOT NULL").fetchall()
        for row in albums_with_genres:
            try:
                album_genres = json.loads(row["genres"]) if row["genres"] else []
                for genre in album_genres:
                    genres_count[genre] = genres_count.get(genre, 0) + 1
            except:
                pass

        return {
            "user_stats": user_stats,
            "total_albums": total_albums,
            "total_tracks": total_tracks,
            "total_album_ratings": total_album_ratings,
            "total_track_ratings": total_track_ratings,
            "top_tracks": [dict(t) for t in top_tracks],
            "genres": dict(sorted(genres_count.items(), key=lambda x: x[1], reverse=True)[:15])
        }

# === Hot Takes ===
@app.get("/api/hot-takes")
def get_hot_takes():
    with get_connection() as conn:
        # Find tracks where individual ratings differ most from average
        hot_takes = conn.execute("""
            SELECT t.name as track_name, a.name as album_name, a.cover_url,
                   u.name as user_name, tr.score as user_score,
                   (SELECT AVG(tr2.score) FROM track_rankings tr2 WHERE tr2.track_id = t.id) as avg_score
            FROM track_rankings tr
            JOIN tracks t ON tr.track_id = t.id
            JOIN albums a ON t.album_id = a.id
            JOIN users u ON tr.user_id = u.id
            WHERE tr.score IS NOT NULL
        """).fetchall()

        results = []
        for take in hot_takes:
            if take["avg_score"]:
                diff = abs(take["user_score"] - take["avg_score"])
                if diff >= 1.5:  # Only show significant differences
                    results.append({
                        "track_name": take["track_name"],
                        "album_name": take["album_name"],
                        "cover_url": take["cover_url"],
                        "user_name": take["user_name"],
                        "user_score": take["user_score"],
                        "average_score": round(take["avg_score"], 1),
                        "difference": round(diff, 1)
                    })

        results.sort(key=lambda x: x["difference"], reverse=True)
        return {"hot_takes": results[:20]}

# === Score Comparison ===
@app.get("/api/comparison")
def get_comparison(user1_id: int = Query(...), user2_id: int = Query(...)):
    with get_connection() as conn:
        # Album comparison
        albums = conn.execute("""
            SELECT a.id, a.name, a.cover_url,
                   ar1.score as user1_score, ar2.score as user2_score
            FROM albums a
            LEFT JOIN album_rankings ar1 ON a.id = ar1.album_id AND ar1.user_id = ?
            LEFT JOIN album_rankings ar2 ON a.id = ar2.album_id AND ar2.user_id = ?
            WHERE ar1.score IS NOT NULL OR ar2.score IS NOT NULL
        """, (user1_id, user2_id)).fetchall()

        album_comparison = []
        for a in albums:
            diff = None
            if a["user1_score"] and a["user2_score"]:
                diff = round(abs(a["user1_score"] - a["user2_score"]), 1)
            album_comparison.append({
                "id": a["id"],
                "name": a["name"],
                "cover_url": a["cover_url"],
                "user1_score": a["user1_score"],
                "user2_score": a["user2_score"],
                "difference": diff
            })

        # Track comparison
        tracks = conn.execute("""
            SELECT t.id, t.name, a.name as album_name, a.cover_url,
                   tr1.score as user1_score, tr2.score as user2_score
            FROM tracks t
            JOIN albums a ON t.album_id = a.id
            LEFT JOIN track_rankings tr1 ON t.id = tr1.track_id AND tr1.user_id = ?
            LEFT JOIN track_rankings tr2 ON t.id = tr2.track_id AND tr2.user_id = ?
            WHERE tr1.score IS NOT NULL OR tr2.score IS NOT NULL
        """, (user1_id, user2_id)).fetchall()

        track_comparison = []
        for t in tracks:
            diff = None
            if t["user1_score"] and t["user2_score"]:
                diff = round(abs(t["user1_score"] - t["user2_score"]), 1)
            track_comparison.append({
                "id": t["id"],
                "name": t["name"],
                "album_name": t["album_name"],
                "cover_url": t["cover_url"],
                "user1_score": t["user1_score"],
                "user2_score": t["user2_score"],
                "difference": diff
            })

        # Sort by biggest disagreement
        album_comparison.sort(key=lambda x: x["difference"] or 0, reverse=True)
        track_comparison.sort(key=lambda x: x["difference"] or 0, reverse=True)

        # User names
        user1 = conn.execute("SELECT name FROM users WHERE id = ?", (user1_id,)).fetchone()
        user2 = conn.execute("SELECT name FROM users WHERE id = ?", (user2_id,)).fetchone()

        return {
            "user1": {"id": user1_id, "name": user1["name"] if user1 else "Unknown"},
            "user2": {"id": user2_id, "name": user2["name"] if user2 else "Unknown"},
            "albums": album_comparison,
            "tracks": track_comparison
        }

# === Year in Review ===
@app.get("/api/year-review/{year}")
def get_year_review(year: int, user_id: Optional[int] = Query(None)):
    with get_connection() as conn:
        year_start = f"{year}-01-01"
        year_end = f"{year}-12-31"

        # Albums added this year
        albums_added = conn.execute("""
            SELECT COUNT(*) FROM albums
            WHERE date(added_at) BETWEEN ? AND ?
        """, (year_start, year_end)).fetchone()[0]

        # Ratings made this year
        if user_id:
            album_ratings = conn.execute("""
                SELECT ar.score, a.name, a.artist, a.cover_url, ar.ranked_at
                FROM album_rankings ar
                JOIN albums a ON ar.album_id = a.id
                WHERE ar.user_id = ? AND date(ar.ranked_at) BETWEEN ? AND ?
                ORDER BY ar.score DESC
            """, (user_id, year_start, year_end)).fetchall()

            track_ratings = conn.execute("""
                SELECT tr.score, t.name, a.name as album_name, a.cover_url, tr.ranked_at
                FROM track_rankings tr
                JOIN tracks t ON tr.track_id = t.id
                JOIN albums a ON t.album_id = a.id
                WHERE tr.user_id = ? AND date(tr.ranked_at) BETWEEN ? AND ?
                ORDER BY tr.score DESC
            """, (user_id, year_start, year_end)).fetchall()

            album_scores = [r["score"] for r in album_ratings if r["score"]]
            track_scores = [r["score"] for r in track_ratings if r["score"]]

            # Monthly breakdown
            monthly_counts = conn.execute("""
                SELECT strftime('%m', ranked_at) as month, COUNT(*) as count
                FROM track_rankings
                WHERE user_id = ? AND date(ranked_at) BETWEEN ? AND ?
                GROUP BY month
            """, (user_id, year_start, year_end)).fetchall()

            return {
                "year": year,
                "user_id": user_id,
                "albums_added": albums_added,
                "albums_rated": len(album_ratings),
                "tracks_rated": len(track_ratings),
                "average_album_score": round(sum(album_scores) / len(album_scores), 1) if album_scores else None,
                "average_track_score": round(sum(track_scores) / len(track_scores), 1) if track_scores else None,
                "top_albums": [dict(r) for r in album_ratings[:5]],
                "top_tracks": [dict(r) for r in track_ratings[:10]],
                "worst_tracks": [dict(r) for r in track_ratings[-5:]] if len(track_ratings) >= 5 else [],
                "monthly_activity": {r["month"]: r["count"] for r in monthly_counts}
            }
        else:
            return {"year": year, "albums_added": albums_added}

# === Listening Sessions ===
# Active session state: code -> {connections: {user_id: websocket}, album_id, current_track_id, is_playing, playback_position, playback_started_at}
active_sessions = {}
import time

def generate_session_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

@app.post("/api/sessions")
def create_session(data: SessionCreate, x_user_id: Optional[int] = Header(None)):
    if not x_user_id:
        raise HTTPException(401, "User required")

    code = generate_session_code()

    with get_connection() as conn:
        album = conn.execute("SELECT * FROM albums WHERE id = ?", (data.album_id,)).fetchone()
        if not album:
            raise HTTPException(404, "Album not found")

        first_track = conn.execute(
            "SELECT id FROM tracks WHERE album_id = ? ORDER BY track_number LIMIT 1",
            (data.album_id,)
        ).fetchone()

        conn.execute("""
            INSERT INTO listening_sessions (code, album_id, current_track_id, created_by)
            VALUES (?, ?, ?, ?)
        """, (code, data.album_id, first_track["id"] if first_track else None, x_user_id))

        conn.execute("""
            INSERT INTO session_participants (session_id, user_id)
            VALUES ((SELECT id FROM listening_sessions WHERE code = ?), ?)
        """, (code, x_user_id))

    active_sessions[code] = {
        "connections": {},  # user_id -> websocket
        "album_id": data.album_id,
        "current_track_id": first_track["id"] if first_track else None,
        "is_playing": False,
        "playback_position": 0,
        "playback_started_at": None
    }

    return {"code": code, "album": dict(album)}

@app.get("/api/sessions/{code}")
def get_session(code: str):
    with get_connection() as conn:
        session = conn.execute("""
            SELECT ls.*, a.name as album_name, a.cover_url, t.name as current_track_name, t.duration_ms as current_track_duration
            FROM listening_sessions ls
            JOIN albums a ON ls.album_id = a.id
            LEFT JOIN tracks t ON ls.current_track_id = t.id
            WHERE ls.code = ? AND ls.is_active = 1
        """, (code,)).fetchone()

        if not session:
            raise HTTPException(404, "Session not found")

        participants = conn.execute("""
            SELECT u.id, u.name FROM session_participants sp
            JOIN users u ON sp.user_id = u.id
            WHERE sp.session_id = ?
        """, (session["id"],)).fetchall()

        # Get active listeners from memory
        active_listener_ids = []
        if code in active_sessions:
            active_listener_ids = list(active_sessions[code]["connections"].keys())

        # Build participant list with online status
        participant_list = []
        for p in participants:
            participant_list.append({
                "id": p["id"],
                "name": p["name"],
                "is_online": p["id"] in active_listener_ids
            })

        # Get playback state
        playback_state = {
            "is_playing": False,
            "position": 0
        }
        if code in active_sessions:
            state = active_sessions[code]
            playback_state["is_playing"] = state["is_playing"]
            if state["is_playing"] and state["playback_started_at"]:
                # Calculate current position based on when playback started
                elapsed = int((time.time() - state["playback_started_at"]) * 1000)
                playback_state["position"] = state["playback_position"] + elapsed
            else:
                playback_state["position"] = state["playback_position"]

        return {
            "id": session["id"],
            "code": code,
            "album_id": session["album_id"],
            "album_name": session["album_name"],
            "cover_url": session["cover_url"],
            "current_track_id": session["current_track_id"],
            "current_track_name": session["current_track_name"],
            "current_track_duration": session["current_track_duration"],
            "participants": participant_list,
            "active_listeners": len(active_listener_ids),
            "is_active": bool(session["is_active"]),
            "playback": playback_state
        }

@app.post("/api/sessions/{code}/join")
def join_session(code: str, x_user_id: Optional[int] = Header(None)):
    if not x_user_id:
        raise HTTPException(401, "User required")

    with get_connection() as conn:
        session = conn.execute(
            "SELECT id FROM listening_sessions WHERE code = ? AND is_active = 1",
            (code,)
        ).fetchone()

        if not session:
            raise HTTPException(404, "Session not found")

        conn.execute("""
            INSERT OR IGNORE INTO session_participants (session_id, user_id)
            VALUES (?, ?)
        """, (session["id"], x_user_id))

    return {"ok": True}

@app.post("/api/sessions/{code}/track")
async def update_session_track(code: str, track_id: int = Query(...), x_user_id: Optional[int] = Header(None)):
    with get_connection() as conn:
        conn.execute("""
            UPDATE listening_sessions SET current_track_id = ?
            WHERE code = ? AND is_active = 1
        """, (track_id, code))

        # Get track duration
        track = conn.execute("SELECT duration_ms FROM tracks WHERE id = ?", (track_id,)).fetchone()
        duration = track["duration_ms"] if track else 0

    # Notify all websocket clients and reset playback
    if code in active_sessions:
        active_sessions[code]["current_track_id"] = track_id
        active_sessions[code]["playback_position"] = 0
        active_sessions[code]["is_playing"] = False
        active_sessions[code]["playback_started_at"] = None

        await broadcast_to_session(code, {
            "type": "track_change",
            "track_id": track_id,
            "duration": duration,
            "position": 0,
            "is_playing": False
        })

    return {"ok": True}

@app.post("/api/sessions/{code}/playback")
async def update_playback(
    code: str,
    action: str = Query(...),  # play, pause, seek
    position: Optional[int] = Query(None),  # position in ms for seek
    x_user_id: Optional[int] = Header(None)
):
    if code not in active_sessions:
        raise HTTPException(404, "Session not found")

    state = active_sessions[code]

    if action == "play":
        state["is_playing"] = True
        state["playback_started_at"] = time.time()
        await broadcast_to_session(code, {
            "type": "playback",
            "action": "play",
            "position": state["playback_position"]
        })
    elif action == "pause":
        if state["is_playing"] and state["playback_started_at"]:
            elapsed = int((time.time() - state["playback_started_at"]) * 1000)
            state["playback_position"] += elapsed
        state["is_playing"] = False
        state["playback_started_at"] = None
        await broadcast_to_session(code, {
            "type": "playback",
            "action": "pause",
            "position": state["playback_position"]
        })
    elif action == "seek" and position is not None:
        state["playback_position"] = position
        if state["is_playing"]:
            state["playback_started_at"] = time.time()
        await broadcast_to_session(code, {
            "type": "playback",
            "action": "seek",
            "position": position
        })

    return {"ok": True}

async def broadcast_to_session(code: str, message: dict):
    """Broadcast a message to all connected clients in a session"""
    if code not in active_sessions:
        return
    for user_id, ws in list(active_sessions[code]["connections"].items()):
        try:
            await ws.send_json(message)
        except:
            pass

@app.websocket("/api/sessions/{code}/ws")
async def session_websocket(websocket: WebSocket, code: str, user_id: Optional[int] = Query(None)):
    await websocket.accept()

    if code not in active_sessions:
        # Initialize session if it exists in DB but not in memory
        with get_connection() as conn:
            session = conn.execute(
                "SELECT album_id, current_track_id FROM listening_sessions WHERE code = ? AND is_active = 1",
                (code,)
            ).fetchone()
            if session:
                active_sessions[code] = {
                    "connections": {},
                    "album_id": session["album_id"],
                    "current_track_id": session["current_track_id"],
                    "is_playing": False,
                    "playback_position": 0,
                    "playback_started_at": None
                }
            else:
                await websocket.close()
                return

    # Get user name
    user_name = "Guest"
    if user_id:
        with get_connection() as conn:
            user = conn.execute("SELECT name FROM users WHERE id = ?", (user_id,)).fetchone()
            if user:
                user_name = user["name"]

    # Add user to connections
    active_sessions[code]["connections"][user_id] = websocket

    # Broadcast user joined
    await broadcast_to_session(code, {
        "type": "user_joined",
        "user_id": user_id,
        "user_name": user_name,
        "active_count": len(active_sessions[code]["connections"])
    })

    # Send current state to the new connection
    state = active_sessions[code]
    current_position = state["playback_position"]
    if state["is_playing"] and state["playback_started_at"]:
        elapsed = int((time.time() - state["playback_started_at"]) * 1000)
        current_position += elapsed

    await websocket.send_json({
        "type": "sync",
        "track_id": state["current_track_id"],
        "is_playing": state["is_playing"],
        "position": current_position,
        "listeners": [
            {"user_id": uid, "user_name": get_user_name(uid)}
            for uid in state["connections"].keys()
        ]
    })

    try:
        while True:
            data = await websocket.receive_json()
            # Handle incoming messages from client
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        # Remove user from connections
        if code in active_sessions and user_id in active_sessions[code]["connections"]:
            del active_sessions[code]["connections"][user_id]

            # Broadcast user left
            await broadcast_to_session(code, {
                "type": "user_left",
                "user_id": user_id,
                "user_name": user_name,
                "active_count": len(active_sessions[code]["connections"])
            })

def get_user_name(user_id: int) -> str:
    """Helper to get user name by ID"""
    if not user_id:
        return "Guest"
    with get_connection() as conn:
        user = conn.execute("SELECT name FROM users WHERE id = ?", (user_id,)).fetchone()
        return user["name"] if user else "Guest"

@app.delete("/api/sessions/{code}")
def end_session(code: str, x_user_id: Optional[int] = Header(None)):
    with get_connection() as conn:
        conn.execute("""
            UPDATE listening_sessions SET is_active = 0
            WHERE code = ?
        """, (code,))

    if code in active_sessions:
        del active_sessions[code]

    return {"ok": True}

# === Tier List ===
@app.get("/api/tier-list")
def get_tier_list(user_id: Optional[int] = Query(None)):
    with get_connection() as conn:
        if user_id:
            # User-specific tier list
            albums = conn.execute("""
                SELECT a.id, a.name, a.artist, a.cover_url, ar.score
                FROM albums a
                LEFT JOIN album_rankings ar ON a.id = ar.album_id AND ar.user_id = ?
            """, (user_id,)).fetchall()
        else:
            # Average tier list
            albums = conn.execute("""
                SELECT a.id, a.name, a.artist, a.cover_url, AVG(ar.score) as score
                FROM albums a
                LEFT JOIN album_rankings ar ON a.id = ar.album_id
                GROUP BY a.id
            """).fetchall()

        tiers = {"S": [], "A": [], "B": [], "C": [], "D": [], "F": [], "Unrated": []}

        for album in albums:
            score = album["score"]
            album_data = {
                "id": album["id"],
                "name": album["name"],
                "artist": album["artist"],
                "cover_url": album["cover_url"],
                "score": round(score, 1) if score else None
            }

            if score is None:
                tiers["Unrated"].append(album_data)
            elif score >= 9:
                tiers["S"].append(album_data)
            elif score >= 8:
                tiers["A"].append(album_data)
            elif score >= 6.5:
                tiers["B"].append(album_data)
            elif score >= 5:
                tiers["C"].append(album_data)
            elif score >= 3.5:
                tiers["D"].append(album_data)
            else:
                tiers["F"].append(album_data)

        # Sort each tier by score
        for tier in tiers:
            if tier != "Unrated":
                tiers[tier].sort(key=lambda x: x["score"] or 0, reverse=True)

        return {"tiers": tiers}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8400)
