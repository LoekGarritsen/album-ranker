"""
Analytics routes (results, stats, hot takes, comparison, year review,
tier list, activity feed, rating history).
"""
from fastapi import APIRouter, Depends, Query
from typing import Optional
import json

from database import get_connection
from auth_deps import get_current_user
from blind import blind_album_ids

router = APIRouter(prefix="/api", tags=["analytics"])


@router.get("/results")
def get_results(user: dict = Depends(get_current_user)):
    """Get all albums with rankings sorted by average score."""
    with get_connection() as conn:
        albums = conn.execute("SELECT * FROM albums").fetchall()

        blind_ids = blind_album_ids(conn)
        my_rated = set()
        if blind_ids:
            rows = conn.execute(
                "SELECT album_id FROM album_rankings WHERE user_id = ? AND score IS NOT NULL",
                (user["id"],),
            ).fetchall()
            my_rated = {r["album_id"] for r in rows}

        results = []
        for album in albums:
            is_blind = album["id"] in blind_ids and album["id"] not in my_rated

            # Album rankings (with like tallies for the comment feed)
            album_rankings = conn.execute("""
                SELECT ar.id as ranking_id, ar.user_id, ar.score, ar.comment, u.name as user_name,
                       (SELECT COUNT(*) FROM ranking_likes rl
                        WHERE rl.kind = 'album' AND rl.ranking_id = ar.id) as likes,
                       (SELECT COUNT(*) FROM ranking_likes rl
                        WHERE rl.kind = 'album' AND rl.ranking_id = ar.id AND rl.user_id = ?) as liked_by_me
                FROM album_rankings ar
                JOIN users u ON ar.user_id = u.id
                WHERE ar.album_id = ?
            """, (user["id"], album["id"])).fetchall()

            if is_blind:
                # Hide others' album scores/comments while blind rating runs
                album_rankings = [
                    r if r["user_id"] == user["id"]
                    else {**dict(r), "score": None, "comment": None}
                    for r in album_rankings
                ]
            else:
                album_rankings = [dict(r) for r in album_rankings]

            album_scores = [r["score"] for r in album_rankings if r["score"]]
            album_avg = (
                None if is_blind
                else (sum(album_scores) / len(album_scores) if album_scores else None)
            )

            # Track rankings
            tracks = conn.execute("""
                SELECT t.id, t.name, t.track_number,
                       AVG(tr.score) as avg_score,
                       COUNT(tr.score) as rating_count
                FROM tracks t
                LEFT JOIN track_rankings tr ON t.id = tr.track_id
                WHERE t.album_id = ?
                GROUP BY t.id
                ORDER BY t.disc_number, t.track_number
            """, (album["id"],)).fetchall()

            track_results = []
            all_track_scores = []
            for t in tracks:
                rankings = conn.execute("""
                    SELECT tr.id as ranking_id, tr.user_id, tr.score, tr.comment, u.name as user_name,
                           (SELECT COUNT(*) FROM ranking_likes rl
                            WHERE rl.kind = 'track' AND rl.ranking_id = tr.id) as likes,
                           (SELECT COUNT(*) FROM ranking_likes rl
                            WHERE rl.kind = 'track' AND rl.ranking_id = tr.id AND rl.user_id = ?) as liked_by_me
                    FROM track_rankings tr
                    JOIN users u ON tr.user_id = u.id
                    WHERE tr.track_id = ?
                """, (user["id"], t["id"])).fetchall()

                # Collect individual ratings (not per-track averages) so this
                # matches the album-level average shown by /api/albums.
                all_track_scores.extend(r["score"] for r in rankings if r["score"])

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
                "album_rankings": album_rankings,
                "average_album_score": round(album_avg, 1) if album_avg else None,
                "tracks": track_results,
                "average_track_score": round(track_avg, 1) if track_avg else None,
                "blind": is_blind
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

        # Compatibility: 100% = identical scores on everything shared,
        # 0% = maximum possible disagreement (9 points apart on the 1-10 scale)
        shared_diffs = [
            c["difference"] for c in album_comparison + track_comparison
            if c["difference"] is not None
        ]
        agreements = sum(1 for d in shared_diffs if d <= 0.5)
        compatibility = None
        if shared_diffs:
            mean_diff = sum(shared_diffs) / len(shared_diffs)
            compatibility = {
                "score": round(100 * (1 - mean_diff / 9)),
                "mean_diff": round(mean_diff, 2),
                "shared_albums": sum(1 for c in album_comparison if c["difference"] is not None),
                "shared_tracks": sum(1 for c in track_comparison if c["difference"] is not None),
                "agreements": agreements,
            }

        # User names
        user1 = conn.execute("SELECT name FROM users WHERE id = ?", (user1_id,)).fetchone()
        user2 = conn.execute("SELECT name FROM users WHERE id = ?", (user2_id,)).fetchone()

        return {
            "user1": {"id": user1_id, "name": user1["name"] if user1 else "Unknown"},
            "user2": {"id": user2_id, "name": user2["name"] if user2 else "Unknown"},
            "albums": album_comparison,
            "tracks": track_comparison,
            "compatibility": compatibility
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
                # Worst = bottom 5 (ascending), never overlapping the top 10.
                "worst_tracks": [dict(r) for r in reversed(track_ratings[max(10, len(track_ratings) - 5):])],
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


@router.get("/feed")
def get_feed(limit: int = Query(30, ge=1, le=100), user: dict = Depends(get_current_user)):
    """Group activity feed: album ratings, track-rating bursts, albums added,
    lists created and club round changes, newest first."""
    with get_connection() as conn:
        blind_ids = blind_album_ids(conn)
        events = []

        album_ratings = conn.execute("""
            SELECT ar.id as ranking_id, ar.album_id, ar.score, ar.comment, ar.ranked_at,
                   u.id as user_id, u.name as user_name,
                   a.name as album_name, a.artist, a.cover_url,
                   (SELECT COUNT(*) FROM ranking_likes rl
                    WHERE rl.kind = 'album' AND rl.ranking_id = ar.id) as likes,
                   (SELECT COUNT(*) FROM ranking_likes rl
                    WHERE rl.kind = 'album' AND rl.ranking_id = ar.id AND rl.user_id = ?) as liked_by_me
            FROM album_rankings ar
            JOIN users u ON u.id = ar.user_id
            JOIN albums a ON a.id = ar.album_id
            WHERE ar.score IS NOT NULL
            ORDER BY ar.ranked_at DESC LIMIT ?
        """, (user["id"], limit)).fetchall()
        for r in album_ratings:
            if r["album_id"] in blind_ids and r["user_id"] != user["id"]:
                continue  # blind round: don't leak scores into the feed
            events.append({"kind": "album_rating", "at": r["ranked_at"], **dict(r)})

        # Track-rating bursts: one entry per user+album+day, not one per track
        track_bursts = conn.execute("""
            SELECT u.id as user_id, u.name as user_name, a.id as album_id,
                   a.name as album_name, a.artist, a.cover_url,
                   date(tr.ranked_at) as day, COUNT(*) as track_count,
                   ROUND(AVG(tr.score), 1) as avg_score, MAX(tr.ranked_at) as at
            FROM track_rankings tr
            JOIN users u ON u.id = tr.user_id
            JOIN tracks t ON t.id = tr.track_id
            JOIN albums a ON a.id = t.album_id
            WHERE tr.score IS NOT NULL
            GROUP BY tr.user_id, a.id, day
            ORDER BY at DESC LIMIT ?
        """, (limit,)).fetchall()
        for r in track_bursts:
            events.append({"kind": "track_burst", **dict(r)})

        added = conn.execute("""
            SELECT id as album_id, name as album_name, artist, cover_url, added_at as at
            FROM albums ORDER BY added_at DESC LIMIT ?
        """, (limit,)).fetchall()
        for r in added:
            events.append({"kind": "album_added", **dict(r)})

        new_lists = conn.execute("""
            SELECT l.id as list_id, l.title, l.created_at as at, u.name as user_name
            FROM lists l JOIN users u ON u.id = l.user_id
            ORDER BY l.created_at DESC LIMIT ?
        """, (limit,)).fetchall()
        for r in new_lists:
            events.append({"kind": "list_created", **dict(r)})

        club = conn.execute("""
            SELECT cr.id as round_id, cr.title, cr.status, cr.updated_at as at,
                   a.name as album_name, a.artist, a.cover_url
            FROM club_rounds cr
            LEFT JOIN albums a ON a.id = cr.album_id
            ORDER BY cr.updated_at DESC LIMIT ?
        """, (limit,)).fetchall()
        for r in club:
            events.append({"kind": "club_round", **dict(r)})

    events.sort(key=lambda e: str(e["at"] or ""), reverse=True)
    return {"feed": events[:limit]}


@router.get("/rating-history/growers")
def get_growers(user: dict = Depends(get_current_user)):
    """Re-rated items: biggest score climbs (growers) and drops (fell off)."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT h.kind, h.item_id, h.user_id, COUNT(*) as changes,
                   (SELECT score FROM ranking_history f
                    WHERE f.kind = h.kind AND f.item_id = h.item_id AND f.user_id = h.user_id
                    ORDER BY f.id ASC LIMIT 1) as first_score,
                   (SELECT score FROM ranking_history l
                    WHERE l.kind = h.kind AND l.item_id = h.item_id AND l.user_id = h.user_id
                    ORDER BY l.id DESC LIMIT 1) as last_score,
                   MAX(h.created_at) as last_change
            FROM ranking_history h
            GROUP BY h.kind, h.item_id, h.user_id
            HAVING COUNT(*) >= 2
        """).fetchall()

        blind_ids = blind_album_ids(conn)
        items = []
        for r in rows:
            if r["kind"] == "album":
                if r["item_id"] in blind_ids and r["user_id"] != user["id"]:
                    continue
                info = conn.execute(
                    "SELECT name, artist, cover_url FROM albums WHERE id = ?",
                    (r["item_id"],),
                ).fetchone()
            else:
                info = conn.execute("""
                    SELECT t.name, t.artist, a.cover_url FROM tracks t
                    JOIN albums a ON a.id = t.album_id WHERE t.id = ?
                """, (r["item_id"],)).fetchone()
            if not info:
                continue
            uname = conn.execute(
                "SELECT name FROM users WHERE id = ?", (r["user_id"],)
            ).fetchone()
            delta = round(r["last_score"] - r["first_score"], 1)
            if delta == 0:
                continue
            items.append({
                "kind": r["kind"],
                "item_id": r["item_id"],
                "name": info["name"],
                "artist": info["artist"],
                "cover_url": info["cover_url"],
                "user_name": uname["name"] if uname else "?",
                "first_score": r["first_score"],
                "last_score": r["last_score"],
                "delta": delta,
                "changes": r["changes"],
                "last_change": r["last_change"],
            })

    growers = sorted([i for i in items if i["delta"] > 0], key=lambda i: -i["delta"])[:10]
    fell_off = sorted([i for i in items if i["delta"] < 0], key=lambda i: i["delta"])[:10]
    return {"growers": growers, "fell_off": fell_off}
