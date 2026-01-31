"""
Analytics routes (results, stats, hot takes, comparison, year review, tier list).
"""
from fastapi import APIRouter, Query
from typing import Optional
import json

from database import get_connection

router = APIRouter(prefix="/api", tags=["analytics"])


@router.get("/results")
def get_results():
    """Get all albums with rankings sorted by average score."""
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


@router.get("/stats")
def get_stats():
    """Get statistics dashboard with user stats, global stats, and top tracks."""
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


@router.get("/hot-takes")
def get_hot_takes():
    """Get ratings that differ significantly from the average."""
    with get_connection() as conn:
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
                if diff >= 1.5:
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


@router.get("/comparison")
def get_comparison(user1_id: int = Query(...), user2_id: int = Query(...)):
    """Compare ratings between two users."""
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


@router.get("/year-review/{year}")
def get_year_review(year: int, user_id: Optional[int] = Query(None)):
    """Get year-in-review statistics."""
    with get_connection() as conn:
        year_start = f"{year}-01-01"
        year_end = f"{year}-12-31"

        # Albums added this year
        albums_added = conn.execute("""
            SELECT COUNT(*) FROM albums
            WHERE date(added_at) BETWEEN ? AND ?
        """, (year_start, year_end)).fetchone()[0]

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


@router.get("/tier-list")
def get_tier_list(user_id: Optional[int] = Query(None)):
    """Get albums organized into tiers (S/A/B/C/D/F)."""
    with get_connection() as conn:
        if user_id:
            albums = conn.execute("""
                SELECT a.id, a.name, a.artist, a.cover_url, ar.score
                FROM albums a
                LEFT JOIN album_rankings ar ON a.id = ar.album_id AND ar.user_id = ?
            """, (user_id,)).fetchall()
        else:
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
