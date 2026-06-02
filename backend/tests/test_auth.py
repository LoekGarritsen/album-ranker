"""
Tests for magic-link authentication.
"""
from unittest.mock import AsyncMock, patch


def _request_and_capture(client, email):
    """POST /auth/request and return the magic-link token sent by email."""
    captured = {}

    async def fake_send(to, link):
        captured["link"] = link
        return True

    with patch("routers.auth.send_magic_link", new=AsyncMock(side_effect=fake_send)):
        r = client.post("/api/auth/request", json={"email": email})
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    return captured["link"].split("token=")[1]


class TestMagicLink:
    def test_request_always_ok_even_unknown_email(self, client):
        # No account enumeration: unknown emails still return ok.
        with patch("routers.auth.send_magic_link", new=AsyncMock(return_value=True)):
            r = client.post("/api/auth/request", json={"email": "stranger@example.com"})
        assert r.status_code == 200

    def test_invalid_email_rejected(self, client):
        assert client.post("/api/auth/request", json={"email": "not-an-email"}).status_code == 422

    def test_verify_issues_session_and_grants_access(self, client):
        token = _request_and_capture(client, "admin@test.dev")
        r = client.post("/api/auth/verify", json={"token": token})
        assert r.status_code == 200
        data = r.json()
        assert data["user"]["email"] == "admin@test.dev"
        assert data["user"]["is_admin"] is True
        # Session token works on a protected route.
        h = {"Authorization": f"Bearer {data['token']}"}
        assert client.get("/api/auth/me", headers=h).status_code == 200
        assert client.get("/api/albums", headers=h).status_code == 200

    def test_link_is_single_use(self, client):
        token = _request_and_capture(client, "user@test.dev")
        assert client.post("/api/auth/verify", json={"token": token}).status_code == 200
        # Second use is rejected.
        assert client.post("/api/auth/verify", json={"token": token}).status_code == 400

    def test_unknown_token_rejected(self, client):
        assert client.post("/api/auth/verify", json={"token": "nope"}).status_code == 400

    def test_new_email_creates_account(self, client):
        token = _request_and_capture(client, "newcomer@example.com")
        r = client.post("/api/auth/verify", json={"token": token})
        assert r.status_code == 200
        assert r.json()["user"]["is_admin"] is False

    def test_logout_revokes_session(self, client):
        token = _request_and_capture(client, "admin@test.dev")
        sess = client.post("/api/auth/verify", json={"token": token}).json()["token"]
        h = {"Authorization": f"Bearer {sess}"}
        assert client.post("/api/auth/logout", headers=h).status_code == 200
        # Token no longer valid.
        assert client.get("/api/auth/me", headers=h).status_code == 401

    def test_me_requires_auth(self, client):
        assert client.get("/api/auth/me").status_code == 401
