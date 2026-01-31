"""
Tests for album and track rating functionality.
"""
import pytest


class TestAlbumRanking:
    """Tests for POST /api/rankings/album endpoint."""

    def test_submit_album_rating(self, client, user_headers):
        """Should create a new album rating."""
        response = client.post(
            "/api/rankings/album",
            json={
                "album_id": 1,
                "user_id": 2,
                "score": 8.5,
                "comment": "Great album!"
            }
        )

        assert response.status_code == 200
        assert response.json() == {"ok": True}

    def test_update_album_rating(self, client, user_headers):
        """Should update an existing rating (UPSERT behavior)."""
        # Submit initial rating
        client.post(
            "/api/rankings/album",
            json={"album_id": 1, "user_id": 2, "score": 7.0, "comment": "Good"}
        )

        # Update rating
        response = client.post(
            "/api/rankings/album",
            json={"album_id": 1, "user_id": 2, "score": 9.0, "comment": "Actually great!"}
        )

        assert response.status_code == 200

        # Verify update by checking albums endpoint
        albums_response = client.get("/api/albums")
        album = next(a for a in albums_response.json() if a["id"] == 1)
        user_ranking = next(
            r for r in album["album_rankings"] if r["user_id"] == 2
        )
        assert user_ranking["score"] == 9.0
        assert user_ranking["comment"] == "Actually great!"

    def test_album_rating_score_validation_min(self, client):
        """Should reject scores below 1."""
        response = client.post(
            "/api/rankings/album",
            json={"album_id": 1, "user_id": 2, "score": 0.5}
        )

        assert response.status_code == 422

    def test_album_rating_score_validation_max(self, client):
        """Should reject scores above 10."""
        response = client.post(
            "/api/rankings/album",
            json={"album_id": 1, "user_id": 2, "score": 11}
        )

        assert response.status_code == 422

    def test_album_rating_nonexistent_album(self, client):
        """Should return 404 for non-existent album."""
        response = client.post(
            "/api/rankings/album",
            json={"album_id": 999, "user_id": 2, "score": 8.0}
        )

        assert response.status_code == 404
        assert "Album not found" in response.json()["detail"]

    def test_album_rating_nonexistent_user(self, client):
        """Should return 404 for non-existent user."""
        response = client.post(
            "/api/rankings/album",
            json={"album_id": 1, "user_id": 999, "score": 8.0}
        )

        assert response.status_code == 404
        assert "User not found" in response.json()["detail"]

    def test_album_rating_optional_comment(self, client):
        """Comment should be optional."""
        response = client.post(
            "/api/rankings/album",
            json={"album_id": 1, "user_id": 2, "score": 7.5}
        )

        assert response.status_code == 200

    def test_album_rating_affects_average(self, client):
        """Album average should reflect all ratings."""
        # Admin rates album
        client.post(
            "/api/rankings/album",
            json={"album_id": 1, "user_id": 1, "score": 8.0}
        )
        # User rates album
        client.post(
            "/api/rankings/album",
            json={"album_id": 1, "user_id": 2, "score": 6.0}
        )

        # Check average
        albums_response = client.get("/api/albums")
        album = next(a for a in albums_response.json() if a["id"] == 1)

        assert album["average_album_score"] == 7.0


class TestTrackRanking:
    """Tests for POST /api/rankings/track endpoint."""

    def test_submit_track_rating(self, client):
        """Should create a new track rating."""
        response = client.post(
            "/api/rankings/track",
            json={
                "track_id": 1,
                "user_id": 2,
                "score": 9.0,
                "comment": "Best track!"
            }
        )

        assert response.status_code == 200
        assert response.json() == {"ok": True}

    def test_update_track_rating(self, client):
        """Should update an existing track rating."""
        # Submit initial rating
        client.post(
            "/api/rankings/track",
            json={"track_id": 1, "user_id": 2, "score": 7.0}
        )

        # Update rating
        response = client.post(
            "/api/rankings/track",
            json={"track_id": 1, "user_id": 2, "score": 8.5, "comment": "Grew on me"}
        )

        assert response.status_code == 200

    def test_track_rating_nonexistent_track(self, client):
        """Should return 404 for non-existent track."""
        response = client.post(
            "/api/rankings/track",
            json={"track_id": 999, "user_id": 2, "score": 8.0}
        )

        assert response.status_code == 404
        assert "Track not found" in response.json()["detail"]

    def test_track_rating_nonexistent_user(self, client):
        """Should return 404 for non-existent user."""
        response = client.post(
            "/api/rankings/track",
            json={"track_id": 1, "user_id": 999, "score": 8.0}
        )

        assert response.status_code == 404
        assert "User not found" in response.json()["detail"]

    def test_multiple_users_can_rate_same_track(self, client):
        """Multiple users should be able to rate the same track."""
        # User 1 rates
        client.post(
            "/api/rankings/track",
            json={"track_id": 1, "user_id": 1, "score": 8.0}
        )
        # User 2 rates
        response = client.post(
            "/api/rankings/track",
            json={"track_id": 1, "user_id": 2, "score": 9.0}
        )

        assert response.status_code == 200


class TestTrackDetails:
    """Tests for GET /api/tracks/{track_id} endpoint."""

    def test_get_track_details(self, client):
        """Should return track with rankings."""
        # Submit some ratings first
        client.post(
            "/api/rankings/track",
            json={"track_id": 1, "user_id": 1, "score": 8.0, "comment": "Great!"}
        )
        client.post(
            "/api/rankings/track",
            json={"track_id": 1, "user_id": 2, "score": 7.0}
        )

        response = client.get("/api/tracks/1")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["name"] == "Track 1"
        assert len(data["rankings"]) == 2
        assert data["average_score"] == 7.5

    def test_get_track_details_nonexistent(self, client):
        """Should return 404 for non-existent track."""
        response = client.get("/api/tracks/999")

        assert response.status_code == 404

    def test_get_track_details_no_ratings(self, client):
        """Should return track with empty rankings if not rated."""
        response = client.get("/api/tracks/2")  # Track 2 has no ratings

        assert response.status_code == 200
        data = response.json()
        assert data["rankings"] == []
        assert data["average_score"] is None


class TestAlbumsList:
    """Tests for GET /api/albums endpoint with rankings."""

    def test_albums_include_track_rankings(self, client):
        """Albums endpoint should include track rankings."""
        # Rate a track
        client.post(
            "/api/rankings/track",
            json={"track_id": 1, "user_id": 2, "score": 8.5}
        )

        response = client.get("/api/albums")

        assert response.status_code == 200
        albums = response.json()
        album = next(a for a in albums if a["id"] == 1)

        # Find Track 1 in the album's tracks
        track = next(t for t in album["tracks"] if t["id"] == 1)
        # Albums endpoint returns all users' rankings (including null for unrated)
        # Find the rating from user 2
        user2_ranking = next(r for r in track["rankings"] if r["user_id"] == 2)
        assert user2_ranking["score"] == 8.5

    def test_albums_calculate_average_track_score(self, client):
        """Should calculate average track score across all tracks."""
        # Rate all tracks
        client.post("/api/rankings/track", json={"track_id": 1, "user_id": 2, "score": 9.0})
        client.post("/api/rankings/track", json={"track_id": 2, "user_id": 2, "score": 8.0})
        client.post("/api/rankings/track", json={"track_id": 3, "user_id": 2, "score": 7.0})

        response = client.get("/api/albums")
        album = next(a for a in response.json() if a["id"] == 1)

        # Average of 9, 8, 7 = 8.0
        assert album["average_track_score"] == 8.0


class TestResultsEndpoint:
    """Tests for GET /api/results endpoint."""

    def test_results_sorted_by_average(self, client, seeded_db):
        """Results should be sorted by average score descending."""
        # Add another album directly to DB for sorting test
        with seeded_db() as conn:
            conn.execute("""
                INSERT INTO albums (id, spotify_id, name, artist)
                VALUES (2, 'spotify:album:second', 'Second Album', 'Another Artist')
            """)

        # Rate first album lower
        client.post("/api/rankings/album", json={"album_id": 1, "user_id": 2, "score": 6.0})
        # Rate second album higher
        client.post("/api/rankings/album", json={"album_id": 2, "user_id": 2, "score": 9.0})

        response = client.get("/api/results")

        assert response.status_code == 200
        data = response.json()

        # Results endpoint returns {"results": [...]}
        results = data["results"]

        # Higher rated album should come first
        assert results[0]["album"]["name"] == "Second Album"
        assert results[1]["album"]["name"] == "Test Album"
