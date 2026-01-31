"""
Tests for user management and admin PIN verification.
"""
import pytest


class TestListUsers:
    """Tests for GET /api/users endpoint."""

    def test_list_users_returns_seeded_users(self, client):
        """Should return all users in database."""
        response = client.get("/api/users")

        assert response.status_code == 200
        users = response.json()
        assert len(users) == 2

        names = {u["name"] for u in users}
        assert "TestAdmin" in names
        assert "TestUser" in names

    def test_list_users_includes_admin_flag(self, client):
        """Should indicate which users are admins."""
        response = client.get("/api/users")
        users = response.json()

        admin = next(u for u in users if u["name"] == "TestAdmin")
        regular = next(u for u in users if u["name"] == "TestUser")

        assert admin["is_admin"] is True
        assert regular["is_admin"] is False


class TestCreateUser:
    """Tests for POST /api/users endpoint."""

    def test_create_user_success(self, client):
        """Should create a new user and return user data."""
        response = client.post("/api/users", json={"name": "NewUser"})

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "NewUser"
        assert data["is_admin"] is False
        assert "id" in data
        assert "created_at" in data

    def test_create_user_duplicate_name_fails(self, client):
        """Should reject duplicate user names."""
        response = client.post("/api/users", json={"name": "TestAdmin"})

        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    def test_create_user_empty_name_fails(self, client):
        """Should reject empty user names."""
        response = client.post("/api/users", json={"name": ""})

        assert response.status_code == 422  # Pydantic validation

    def test_create_user_long_name_fails(self, client):
        """Should reject names exceeding max length."""
        long_name = "A" * 51  # Max is 50
        response = client.post("/api/users", json={"name": long_name})

        assert response.status_code == 422


class TestPinVerification:
    """Tests for POST /api/users/verify-pin endpoint."""

    def test_verify_pin_correct(self, client):
        """Should succeed with correct PIN for admin user."""
        response = client.post(
            "/api/users/verify-pin",
            json={"user_id": 1, "pin": "1234"}
        )

        assert response.status_code == 200
        assert response.json() == {"ok": True}

    def test_verify_pin_incorrect(self, client):
        """Should fail with incorrect PIN."""
        response = client.post(
            "/api/users/verify-pin",
            json={"user_id": 1, "pin": "0000"}
        )

        assert response.status_code == 401
        assert "Invalid PIN" in response.json()["detail"]

    def test_verify_pin_non_admin_user(self, client):
        """Should fail for non-admin users (they don't have PINs)."""
        response = client.post(
            "/api/users/verify-pin",
            json={"user_id": 2, "pin": "1234"}
        )

        assert response.status_code == 404
        assert "Admin user not found" in response.json()["detail"]

    def test_verify_pin_nonexistent_user(self, client):
        """Should fail for users that don't exist."""
        response = client.post(
            "/api/users/verify-pin",
            json={"user_id": 999, "pin": "1234"}
        )

        assert response.status_code == 404

    def test_verify_pin_invalid_format(self, client):
        """Should reject PINs that aren't 4 digits."""
        # Too short
        response = client.post(
            "/api/users/verify-pin",
            json={"user_id": 1, "pin": "123"}
        )
        assert response.status_code == 422

        # Too long
        response = client.post(
            "/api/users/verify-pin",
            json={"user_id": 1, "pin": "12345"}
        )
        assert response.status_code == 422

        # Non-numeric
        response = client.post(
            "/api/users/verify-pin",
            json={"user_id": 1, "pin": "abcd"}
        )
        assert response.status_code == 422


class TestAdminAccess:
    """Tests for admin-only endpoint access control."""

    def test_spotify_search_requires_admin(self, client, user_headers, mock_spotify_search):
        """Non-admin should be denied access to Spotify search."""
        response = client.get(
            "/api/spotify/search",
            params={"q": "test"},
            headers=user_headers
        )

        assert response.status_code == 403
        assert "Admin access required" in response.json()["detail"]

    def test_spotify_search_allowed_for_admin(self, client, admin_headers, mock_spotify_search):
        """Admin should be able to search Spotify."""
        response = client.get(
            "/api/spotify/search",
            params={"q": "test"},
            headers=admin_headers
        )

        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_spotify_search_no_user_id_header(self, client, mock_spotify_search):
        """Should deny access when no X-User-Id header provided."""
        response = client.get("/api/spotify/search", params={"q": "test"})

        assert response.status_code == 403
