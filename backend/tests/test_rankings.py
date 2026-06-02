"""
Tests for album and track rating functionality.

Ratings are always attributed to the authenticated caller (any user_id in the
body is ignored), so multi-user tests use distinct auth headers.
"""
import sqlite3


class TestAlbumRanking:
    """POST /api/rankings/album."""

    def test_requires_auth(self, client):
        assert client.post("/api/rankings/album", json={"album_id": 1, "score": 8.5}).status_code == 401

    def test_submit_album_rating(self, client, user_headers):
        r = client.post("/api/rankings/album", json={"album_id": 1, "score": 8.5, "comment": "Great album!"}, headers=user_headers)
        assert r.status_code == 200
        assert r.json() == {"ok": True}

    def test_update_album_rating(self, client, user_headers):
        client.post("/api/rankings/album", json={"album_id": 1, "score": 7.0, "comment": "Good"}, headers=user_headers)
        r = client.post("/api/rankings/album", json={"album_id": 1, "score": 9.0, "comment": "Actually great!"}, headers=user_headers)
        assert r.status_code == 200

        album = next(a for a in client.get("/api/albums", headers=user_headers).json() if a["id"] == 1)
        ranking = next(rk for rk in album["album_rankings"] if rk["user_id"] == 2)
        assert ranking["score"] == 9.0
        assert ranking["comment"] == "Actually great!"

    def test_score_validation(self, client, user_headers):
        assert client.post("/api/rankings/album", json={"album_id": 1, "score": 0.5}, headers=user_headers).status_code == 422
        assert client.post("/api/rankings/album", json={"album_id": 1, "score": 11}, headers=user_headers).status_code == 422

    def test_nonexistent_album(self, client, user_headers):
        r = client.post("/api/rankings/album", json={"album_id": 999, "score": 8.0}, headers=user_headers)
        assert r.status_code == 404
        assert "Album not found" in r.json()["detail"]

    def test_comment_optional(self, client, user_headers):
        assert client.post("/api/rankings/album", json={"album_id": 1, "score": 7.5}, headers=user_headers).status_code == 200

    def test_body_user_id_is_ignored(self, client, user_headers):
        # Spoofing another user_id in the body must NOT attribute the rating to them.
        client.post("/api/rankings/album", json={"album_id": 1, "user_id": 1, "score": 3.0}, headers=user_headers)
        album = next(a for a in client.get("/api/albums", headers=user_headers).json() if a["id"] == 1)
        rankings = {rk["user_id"]: rk["score"] for rk in album["album_rankings"]}
        assert rankings.get(2) == 3.0   # attributed to the caller (user 2)
        assert rankings.get(1) is None  # NOT the spoofed admin

    def test_rating_affects_average(self, client, admin_headers, user_headers):
        client.post("/api/rankings/album", json={"album_id": 1, "score": 8.0}, headers=admin_headers)
        client.post("/api/rankings/album", json={"album_id": 1, "score": 6.0}, headers=user_headers)
        album = next(a for a in client.get("/api/albums", headers=user_headers).json() if a["id"] == 1)
        assert album["average_album_score"] == 7.0


class TestTrackRanking:
    """POST /api/rankings/track."""

    def test_submit_track_rating(self, client, user_headers):
        r = client.post("/api/rankings/track", json={"track_id": 1, "score": 9.0, "comment": "Best track!"}, headers=user_headers)
        assert r.status_code == 200

    def test_nonexistent_track(self, client, user_headers):
        r = client.post("/api/rankings/track", json={"track_id": 999, "score": 8.0}, headers=user_headers)
        assert r.status_code == 404
        assert "Track not found" in r.json()["detail"]

    def test_multiple_users_can_rate_same_track(self, client, admin_headers, user_headers):
        assert client.post("/api/rankings/track", json={"track_id": 1, "score": 8.0}, headers=admin_headers).status_code == 200
        assert client.post("/api/rankings/track", json={"track_id": 1, "score": 9.0}, headers=user_headers).status_code == 200


class TestTrackDetails:
    """GET /api/tracks/{track_id}."""

    def test_get_track_details(self, client, admin_headers, user_headers):
        client.post("/api/rankings/track", json={"track_id": 1, "score": 8.0, "comment": "Great!"}, headers=admin_headers)
        client.post("/api/rankings/track", json={"track_id": 1, "score": 7.0}, headers=user_headers)

        r = client.get("/api/tracks/1", headers=user_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == 1
        assert data["name"] == "Track 1"
        assert len(data["rankings"]) == 2
        assert data["average_score"] == 7.5

    def test_nonexistent(self, client, user_headers):
        assert client.get("/api/tracks/999", headers=user_headers).status_code == 404

    def test_no_ratings(self, client, user_headers):
        data = client.get("/api/tracks/2", headers=user_headers).json()
        assert data["rankings"] == []
        assert data["average_score"] is None


class TestAlbumsList:
    """GET /api/albums."""

    def test_requires_auth(self, client):
        assert client.get("/api/albums").status_code == 401

    def test_albums_include_track_rankings(self, client, user_headers):
        client.post("/api/rankings/track", json={"track_id": 1, "score": 8.5}, headers=user_headers)
        album = next(a for a in client.get("/api/albums", headers=user_headers).json() if a["id"] == 1)
        track = next(t for t in album["tracks"] if t["id"] == 1)
        ranking = next(r for r in track["rankings"] if r["user_id"] == 2)
        assert ranking["score"] == 8.5

    def test_average_track_score(self, client, user_headers):
        client.post("/api/rankings/track", json={"track_id": 1, "score": 9.0}, headers=user_headers)
        client.post("/api/rankings/track", json={"track_id": 2, "score": 8.0}, headers=user_headers)
        client.post("/api/rankings/track", json={"track_id": 3, "score": 7.0}, headers=user_headers)
        album = next(a for a in client.get("/api/albums", headers=user_headers).json() if a["id"] == 1)
        assert album["average_track_score"] == 8.0


class TestResultsEndpoint:
    """GET /api/results."""

    def test_results_sorted_by_average(self, client, user_headers, temp_db_path):
        conn = sqlite3.connect(temp_db_path)
        conn.execute(
            "INSERT INTO albums (id, spotify_id, name, artist) VALUES (2, 'spotify:album:second', 'Second Album', 'Another Artist')"
        )
        conn.commit()
        conn.close()

        client.post("/api/rankings/album", json={"album_id": 1, "score": 6.0}, headers=user_headers)
        client.post("/api/rankings/album", json={"album_id": 2, "score": 9.0}, headers=user_headers)

        results = client.get("/api/results", headers=user_headers).json()["results"]
        assert results[0]["album"]["name"] == "Second Album"
        assert results[1]["album"]["name"] == "Test Album"
