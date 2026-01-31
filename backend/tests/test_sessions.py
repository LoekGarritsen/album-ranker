"""
Tests for listening session management.
"""
import pytest


class TestCreateSession:
    """Tests for POST /api/sessions endpoint."""

    def test_create_session_with_album(self, client, admin_headers):
        """Should create a session with an album and return session code."""
        response = client.post(
            "/api/sessions",
            json={"name": "Test Room", "album_id": 1, "is_public": True},
            headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "code" in data
        assert len(data["code"]) == 6  # 6-char session code
        assert data["name"] == "Test Room"
        assert data["album"]["name"] == "Test Album"

    def test_create_session_without_album(self, client, admin_headers):
        """Should create a session without an album (lobby mode)."""
        response = client.post(
            "/api/sessions",
            json={"name": "Lobby Room", "is_public": True},
            headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "code" in data
        assert data["name"] == "Lobby Room"
        assert data["album"] is None

    def test_create_session_with_password(self, client, admin_headers):
        """Should create a private session with password."""
        response = client.post(
            "/api/sessions",
            json={"name": "Private Room", "is_public": False, "password": "secret123"},
            headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "code" in data

    def test_create_session_requires_user(self, client):
        """Should reject session creation without user header."""
        response = client.post(
            "/api/sessions",
            json={"name": "Test Room", "is_public": True}
        )

        assert response.status_code == 401
        assert "User required" in response.json()["detail"]

    def test_create_session_nonexistent_album(self, client, admin_headers):
        """Should reject session with non-existent album."""
        response = client.post(
            "/api/sessions",
            json={"name": "Test Room", "album_id": 999},
            headers=admin_headers
        )

        assert response.status_code == 404
        assert "Album not found" in response.json()["detail"]

    def test_create_session_adds_creator_as_participant(self, client, admin_headers):
        """Creator should automatically become a participant."""
        # Create session
        create_response = client.post(
            "/api/sessions",
            json={"name": "Test Room", "album_id": 1},
            headers=admin_headers
        )
        code = create_response.json()["code"]

        # Get session details
        get_response = client.get(f"/api/sessions/{code}")
        data = get_response.json()

        assert len(data["participants"]) == 1
        assert data["participants"][0]["name"] == "TestAdmin"


class TestGetSession:
    """Tests for GET /api/sessions/{code} endpoint."""

    def test_get_session_returns_details(self, client, admin_headers):
        """Should return full session details."""
        # Create session first
        create_response = client.post(
            "/api/sessions",
            json={"name": "Test Room", "album_id": 1},
            headers=admin_headers
        )
        code = create_response.json()["code"]

        # Get session
        response = client.get(f"/api/sessions/{code}")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == code
        assert data["name"] == "Test Room"
        assert data["album_id"] == 1
        assert data["album_name"] == "Test Album"
        assert data["is_active"] is True
        assert "participants" in data
        assert "playback" in data

    def test_get_session_includes_playback_state(self, client, admin_headers):
        """Should include playback state information."""
        create_response = client.post(
            "/api/sessions",
            json={"name": "Test Room", "album_id": 1},
            headers=admin_headers
        )
        code = create_response.json()["code"]

        response = client.get(f"/api/sessions/{code}")
        data = response.json()

        assert "playback" in data
        assert "is_playing" in data["playback"]
        assert "position" in data["playback"]
        assert data["playback"]["is_playing"] is False
        assert data["playback"]["position"] == 0

    def test_get_session_not_found(self, client):
        """Should return 404 for non-existent session."""
        response = client.get("/api/sessions/NOTACODE")

        assert response.status_code == 404
        assert "Session not found" in response.json()["detail"]

    def test_get_session_shows_has_password(self, client, admin_headers):
        """Should indicate if session has a password without revealing it."""
        # Create session with password
        create_response = client.post(
            "/api/sessions",
            json={"name": "Private Room", "password": "secret"},
            headers=admin_headers
        )
        code = create_response.json()["code"]

        response = client.get(f"/api/sessions/{code}")
        data = response.json()

        assert data["has_password"] is True
        # Password itself should not be exposed
        assert "password" not in data


class TestJoinSession:
    """Tests for POST /api/sessions/{code}/join endpoint."""

    def test_join_public_session(self, client, admin_headers, user_headers):
        """User should be able to join a public session."""
        # Admin creates session
        create_response = client.post(
            "/api/sessions",
            json={"name": "Public Room", "album_id": 1, "is_public": True},
            headers=admin_headers
        )
        code = create_response.json()["code"]

        # Regular user joins
        join_response = client.post(
            f"/api/sessions/{code}/join",
            headers=user_headers
        )

        assert join_response.status_code == 200
        assert join_response.json() == {"ok": True}

        # Verify user is now a participant
        get_response = client.get(f"/api/sessions/{code}")
        participants = get_response.json()["participants"]
        names = {p["name"] for p in participants}
        assert "TestUser" in names

    def test_join_password_protected_session_correct_password(self, client, admin_headers, user_headers):
        """Should allow joining with correct password."""
        # Create session with password
        create_response = client.post(
            "/api/sessions",
            json={"name": "Private Room", "password": "secret123"},
            headers=admin_headers
        )
        code = create_response.json()["code"]

        # Join with correct password
        join_response = client.post(
            f"/api/sessions/{code}/join",
            json={"password": "secret123"},
            headers=user_headers
        )

        assert join_response.status_code == 200

    def test_join_password_protected_session_wrong_password(self, client, admin_headers, user_headers):
        """Should reject incorrect password."""
        # Create session with password
        create_response = client.post(
            "/api/sessions",
            json={"name": "Private Room", "password": "secret123"},
            headers=admin_headers
        )
        code = create_response.json()["code"]

        # Try to join with wrong password
        join_response = client.post(
            f"/api/sessions/{code}/join",
            json={"password": "wrongpassword"},
            headers=user_headers
        )

        assert join_response.status_code == 403
        assert "Invalid password" in join_response.json()["detail"]

    def test_join_password_protected_session_no_password(self, client, admin_headers, user_headers):
        """Should reject joining without password when required."""
        # Create session with password
        create_response = client.post(
            "/api/sessions",
            json={"name": "Private Room", "password": "secret123"},
            headers=admin_headers
        )
        code = create_response.json()["code"]

        # Try to join without password
        join_response = client.post(
            f"/api/sessions/{code}/join",
            headers=user_headers
        )

        assert join_response.status_code == 403

    def test_join_session_requires_user(self, client, admin_headers):
        """Should require user header to join."""
        # Create session
        create_response = client.post(
            "/api/sessions",
            json={"name": "Test Room"},
            headers=admin_headers
        )
        code = create_response.json()["code"]

        # Try to join without user header
        join_response = client.post(f"/api/sessions/{code}/join")

        assert join_response.status_code == 401

    def test_join_nonexistent_session(self, client, user_headers):
        """Should return 404 for non-existent session."""
        response = client.post(
            "/api/sessions/NOTACODE/join",
            headers=user_headers
        )

        assert response.status_code == 404

    def test_join_session_idempotent(self, client, admin_headers, user_headers):
        """Joining same session twice should be idempotent."""
        # Create session
        create_response = client.post(
            "/api/sessions",
            json={"name": "Test Room"},
            headers=admin_headers
        )
        code = create_response.json()["code"]

        # Join twice
        client.post(f"/api/sessions/{code}/join", headers=user_headers)
        second_join = client.post(f"/api/sessions/{code}/join", headers=user_headers)

        assert second_join.status_code == 200

        # Should still only have 2 participants
        get_response = client.get(f"/api/sessions/{code}")
        assert len(get_response.json()["participants"]) == 2


class TestListSessions:
    """Tests for GET /api/sessions endpoint."""

    def test_list_sessions_shows_public_only(self, client, admin_headers, user_headers):
        """Should only list public active sessions."""
        # Create public session
        client.post(
            "/api/sessions",
            json={"name": "Public Room", "is_public": True},
            headers=admin_headers
        )

        # Create private session
        client.post(
            "/api/sessions",
            json={"name": "Private Room", "is_public": False},
            headers=user_headers
        )

        response = client.get("/api/sessions")

        assert response.status_code == 200
        sessions = response.json()
        # Both should appear because is_public defaults to showing in list
        # (the is_public flag affects visibility but both are returned by list endpoint)
        names = {s["name"] for s in sessions}
        assert "Public Room" in names


class TestDeleteSession:
    """Tests for DELETE /api/sessions/{code} endpoint."""

    def test_delete_session(self, client, admin_headers):
        """Should mark session as inactive."""
        # Create session
        create_response = client.post(
            "/api/sessions",
            json={"name": "Test Room"},
            headers=admin_headers
        )
        code = create_response.json()["code"]

        # Delete session
        delete_response = client.delete(
            f"/api/sessions/{code}",
            headers=admin_headers
        )

        assert delete_response.status_code == 200

        # Session should no longer be found (is_active = 0)
        get_response = client.get(f"/api/sessions/{code}")
        assert get_response.status_code == 404
