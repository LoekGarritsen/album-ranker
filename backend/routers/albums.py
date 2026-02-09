"""
Album management routes.
"""
from fastapi import APIRouter, HTTPException, Header
from typing import Optional
import json

from database import get_connection
from models import AlbumAdd, Album, AlbumWithTracks, UserRanking, TrackWithRankings
from spotify import spotify_client
from routers.users import verify_admin

router = APIRouter(prefix="/api/albums", tags=["albums"])


@router.get("", response_model=list[AlbumWithTracks])
def list_albums():
    """List all albums with tracks and rankings."""
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
            ORDER BY t.disc_number, t.track_number
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
                    "disc_number": t["disc_number"] or 1,
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
                    disc_number=track_data["disc_number"],
                    track_number=track_data["track_number"],
                    duration_ms=track_data["duration_ms"],
                    rankings=user_rankings,
                    average_score=round(track_avg, 1) if track_avg else None
                ))

            tracks_with_rankings.sort(key=lambda t: (t.disc_number, t.track_number))

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


@router.post("", response_model=Album)
async def add_album(album: AlbumAdd, x_user_id: Optional[int] = Header(None)):
    """Add a new album from Spotify (admin only)."""
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
                """INSERT INTO tracks (album_id, spotify_id, name, artist, disc_number, track_number, duration_ms)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (album_id, track["spotify_id"], track["name"], track["artist"],
                 track["disc_number"], track["track_number"], track["duration_ms"])
            )

    return album_row


@router.delete("/{album_id}")
def remove_album(album_id: int, x_user_id: Optional[int] = Header(None)):
    """Delete an album (admin only)."""
    if not verify_admin(x_user_id):
        raise HTTPException(403, "Admin access required")

    with get_connection() as conn:
        conn.execute("DELETE FROM albums WHERE id = ?", (album_id,))
        return {"ok": True}
