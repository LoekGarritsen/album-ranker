"""
Tests for the Spotify connect/token path.

Focus is the OAuth token lifecycle on GET /api/spotify/token: returning a still
-valid token, refreshing an expiring one, and — the regression that motivated
these tests — deleting a dead token row when the refresh fails (previously the
delete was rolled back because it ran inside the raising transaction).
"""
import sqlite3
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock


def _insert_token(db_path, user_id, access, refresh, expires_at):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO spotify_tokens (user_id, access_token, refresh_token, expires_at)"
        " VALUES (?, ?, ?, ?)",
        (user_id, access, refresh, expires_at.isoformat()),
    )
    conn.commit()
    conn.close()


def _token_row(db_path, user_id):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM spotify_tokens WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    return row


class TestSpotifyStatus:
    def test_status_false_when_not_connected(self, client, user_headers):
        res = client.get("/api/spotify/status", headers=user_headers)
        assert res.status_code == 200
        assert res.json()["connected"] is False

    def test_status_true_when_connected(self, client, user_headers, temp_db_path):
        _insert_token(temp_db_path, 2, "acc", "ref", datetime.now() + timedelta(hours=1))
        res = client.get("/api/spotify/status", headers=user_headers)
        assert res.json()["connected"] is True


class TestSpotifyToken:
    def test_token_404_when_not_connected(self, client, user_headers):
        res = client.get("/api/spotify/token", headers=user_headers)
        assert res.status_code == 404

    def test_valid_token_returned_without_refresh(self, client, user_headers, temp_db_path):
        _insert_token(temp_db_path, 2, "still_good", "ref", datetime.now() + timedelta(hours=1))
        with patch(
            "routers.spotify_routes.spotify_oauth.refresh_token", new_callable=AsyncMock
        ) as mock_refresh:
            res = client.get("/api/spotify/token", headers=user_headers)
            assert res.status_code == 200
            assert res.json()["access_token"] == "still_good"
            mock_refresh.assert_not_called()

    def test_expiring_token_is_refreshed_and_stored(self, client, user_headers, temp_db_path):
        # Within the 5-minute pre-expiry window -> must refresh.
        _insert_token(temp_db_path, 2, "old_access", "old_refresh", datetime.now() + timedelta(minutes=2))
        with patch(
            "routers.spotify_routes.spotify_oauth.refresh_token", new_callable=AsyncMock
        ) as mock_refresh:
            mock_refresh.return_value = {
                "access_token": "new_access",
                "refresh_token": "new_refresh",
                "expires_in": 3600,
            }
            res = client.get("/api/spotify/token", headers=user_headers)

        assert res.status_code == 200
        assert res.json()["access_token"] == "new_access"
        row = _token_row(temp_db_path, 2)
        assert row["access_token"] == "new_access"
        assert row["refresh_token"] == "new_refresh"

    def test_refresh_failure_deletes_dead_token(self, client, user_headers, temp_db_path):
        """Regression: a failed refresh must actually remove the row.

        The delete previously ran inside the get_connection() context, so the
        raised HTTPException rolled it back and the broken token survived,
        looping the user through endless failing refreshes.
        """
        _insert_token(temp_db_path, 2, "dead_access", "dead_refresh", datetime.now() - timedelta(minutes=1))
        with patch(
            "routers.spotify_routes.spotify_oauth.refresh_token", new_callable=AsyncMock
        ) as mock_refresh:
            mock_refresh.side_effect = Exception("invalid_grant")
            res = client.get("/api/spotify/token", headers=user_headers)

        assert res.status_code == 401
        assert _token_row(temp_db_path, 2) is None  # row must be gone


class TestSpotifyDisconnect:
    def test_disconnect_removes_token(self, client, user_headers, temp_db_path):
        _insert_token(temp_db_path, 2, "acc", "ref", datetime.now() + timedelta(hours=1))
        res = client.delete("/api/spotify/disconnect", headers=user_headers)
        assert res.status_code == 200
        assert _token_row(temp_db_path, 2) is None
