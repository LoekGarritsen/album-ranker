"""
Tests for the user directory and admin access control.

(Account creation and login are covered in test_auth.py — magic-link based.)
"""


class TestListUsers:
    """GET /api/users (auth required)."""

    def test_list_requires_auth(self, client):
        assert client.get("/api/users").status_code == 401

    def test_list_users_returns_seeded_users(self, client, user_headers):
        response = client.get("/api/users", headers=user_headers)
        assert response.status_code == 200
        names = {u["name"] for u in response.json()}
        assert {"TestAdmin", "TestUser"} <= names

    def test_list_users_includes_admin_flag(self, client, user_headers):
        users = client.get("/api/users", headers=user_headers).json()
        admin = next(u for u in users if u["name"] == "TestAdmin")
        regular = next(u for u in users if u["name"] == "TestUser")
        assert admin["is_admin"] is True
        assert regular["is_admin"] is False


class TestAdminAccess:
    """Admin-only endpoints are gated by the authenticated session, not a header claim."""

    def test_spotify_search_requires_admin(self, client, user_headers, mock_spotify_search):
        response = client.get("/api/spotify/search", params={"q": "test"}, headers=user_headers)
        assert response.status_code == 403
        assert "Admin access required" in response.json()["detail"]

    def test_spotify_search_allowed_for_admin(self, client, admin_headers, mock_spotify_search):
        response = client.get("/api/spotify/search", params={"q": "test"}, headers=admin_headers)
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_spotify_search_unauthenticated(self, client, mock_spotify_search):
        # No token at all -> 401 (cannot be reached by spoofing a header).
        assert client.get("/api/spotify/search", params={"q": "test"}).status_code == 401
