"""
Tests for WebSocket functionality in listening sessions.

Identity is carried by a session token in the query string (?token=), since
browsers can't set WebSocket headers. An empty/invalid token connects as guest.
"""
import time


def ws_url(code, token=""):
    return f"/api/sessions/{code}/ws?token={token}"


def _make_session(client, headers, **body):
    body.setdefault("name", "Room")
    return client.post("/api/sessions", json=body, headers=headers).json()["code"]


class TestWebSocketConnection:
    def test_websocket_connect_receives_sync(self, client, admin_headers, admin_token):
        code = _make_session(client, admin_headers, name="WS Test Room", album_id=1)
        with client.websocket_connect(ws_url(code, admin_token)) as ws:
            msg1 = ws.receive_json()
            assert msg1["type"] == "user_joined"
            assert msg1["user_name"] == "TestAdmin"
            msg2 = ws.receive_json()
            assert msg2["type"] == "sync"
            assert msg2["is_playing"] is False
            assert msg2["position"] == 0
            assert "listeners" in msg2

    def test_websocket_sync_includes_current_track(self, client, admin_headers, user_token):
        code = _make_session(client, admin_headers, name="WS Test Room", album_id=1)
        with client.websocket_connect(ws_url(code, user_token)) as ws:
            ws.receive_json()  # user_joined
            sync = ws.receive_json()
            assert sync["type"] == "sync"
            assert sync["track_id"] == 1

    def test_websocket_connect_as_guest(self, client, admin_headers):
        code = _make_session(client, admin_headers, name="Guest Test Room")
        with client.websocket_connect(ws_url(code)) as ws:
            joined = ws.receive_json()
            assert joined["type"] == "user_joined"
            assert joined["user_name"] == "Guest"
            assert str(joined["user_id"]).startswith("guest_")

    def test_websocket_connect_to_nonexistent_session(self, client):
        import pytest
        with pytest.raises(Exception):
            with client.websocket_connect(ws_url("NOTACODE")) as ws:
                ws.receive_json()


class TestWebSocketUserEvents:
    def test_user_joined_broadcast(self, client, admin_headers, admin_token, user_token):
        code = _make_session(client, admin_headers, name="Broadcast Test")
        with client.websocket_connect(ws_url(code, admin_token)) as ws1:
            ws1.receive_json(); ws1.receive_json()
            with client.websocket_connect(ws_url(code, user_token)) as ws2:
                joined = ws1.receive_json()
                assert joined["type"] == "user_joined"
                assert joined["user_id"] == 2
                assert joined["user_name"] == "TestUser"
                assert joined["active_count"] == 2
                assert ws2.receive_json()["type"] == "user_joined"

    def test_user_left_broadcast(self, client, admin_headers, admin_token, user_token):
        code = _make_session(client, admin_headers, name="Leave Test")
        with client.websocket_connect(ws_url(code, admin_token)) as ws1:
            ws1.receive_json(); ws1.receive_json()
            with client.websocket_connect(ws_url(code, user_token)) as ws2:
                ws1.receive_json()  # user 2 joined
                ws2.receive_json(); ws2.receive_json()
            left = ws1.receive_json()
            assert left["type"] == "user_left"
            assert left["user_id"] == 2
            assert left["active_count"] == 1

    def test_active_count_accuracy(self, client, admin_headers, admin_token, user_token):
        code = _make_session(client, admin_headers, name="Count Test")
        with client.websocket_connect(ws_url(code, admin_token)) as ws1:
            j1 = ws1.receive_json()
            assert j1["active_count"] == 1
            ws1.receive_json()
            with client.websocket_connect(ws_url(code, user_token)) as ws2:
                j2 = ws1.receive_json()
                assert j2["active_count"] == 2


class TestWebSocketPingPong:
    def test_ping_receives_pong(self, client, admin_headers, admin_token):
        code = _make_session(client, admin_headers, name="Ping Test")
        with client.websocket_connect(ws_url(code, admin_token)) as ws:
            ws.receive_json(); ws.receive_json()
            ws.send_json({"type": "ping"})
            pong = ws.receive_json()
            assert pong["type"] == "pong"
            assert pong["is_playing"] is False

    def test_pong_reflects_playback_state(self, client, admin_headers, admin_token):
        code = _make_session(client, admin_headers, name="Playback Test", album_id=1)
        client.post(f"/api/sessions/{code}/playback", params={"action": "play"}, headers=admin_headers)
        with client.websocket_connect(ws_url(code, admin_token)) as ws:
            ws.receive_json(); ws.receive_json()
            time.sleep(0.1)
            ws.send_json({"type": "ping"})
            pong = ws.receive_json()
            assert pong["is_playing"] is True
            assert pong["position"] >= 0


class TestWebSocketRatingBroadcast:
    def test_track_rating_broadcast(self, client, admin_headers, user_headers, admin_token, user_token):
        code = _make_session(client, admin_headers, name="Rating Test", album_id=1)
        with client.websocket_connect(ws_url(code, admin_token)) as ws1:
            ws1.receive_json(); ws1.receive_json()
            with client.websocket_connect(ws_url(code, user_token)) as ws2:
                ws1.receive_json(); ws2.receive_json(); ws2.receive_json()
                client.post(
                    "/api/rankings/track",
                    params={"session_code": code},
                    json={"track_id": 1, "score": 8.5, "comment": "Great track!"},
                    headers=user_headers,
                )
                rating1 = ws1.receive_json()
                assert rating1["type"] == "rating"
                assert rating1["track_id"] == 1
                assert rating1["user_id"] == 2
                assert rating1["user_name"] == "TestUser"
                assert rating1["score"] == 8.5
                assert ws2.receive_json()["type"] == "rating"

    def test_rating_without_session_code_no_broadcast(self, client, admin_headers, user_headers, admin_token):
        code = _make_session(client, admin_headers, name="No Broadcast Test", album_id=1)
        with client.websocket_connect(ws_url(code, admin_token)) as ws:
            ws.receive_json(); ws.receive_json()
            client.post("/api/rankings/track", json={"track_id": 1, "score": 7.0}, headers=user_headers)
            ws.send_json({"type": "ping"})
            assert ws.receive_json()["type"] == "pong"


class TestWebSocketPlaybackBroadcast:
    def test_track_change_broadcast(self, client, admin_headers, admin_token, user_token):
        code = _make_session(client, admin_headers, name="Track Change Test", album_id=1)
        with client.websocket_connect(ws_url(code, admin_token)) as ws1:
            ws1.receive_json(); ws1.receive_json()
            with client.websocket_connect(ws_url(code, user_token)) as ws2:
                ws1.receive_json(); ws2.receive_json(); ws2.receive_json()
                client.post(f"/api/sessions/{code}/track", params={"track_id": 2}, headers=admin_headers)
                change1 = ws1.receive_json()
                assert change1["type"] == "track_change"
                assert change1["track_id"] == 2
                # Default track change resets to paused (manual pick).
                assert change1["is_playing"] is False
                assert ws2.receive_json()["type"] == "track_change"

    def test_track_change_keep_playing(self, client, admin_headers, admin_token):
        """A native (gapless) advance keeps the room playing without a pause."""
        code = _make_session(client, admin_headers, name="Keep Playing Test", album_id=1)
        with client.websocket_connect(ws_url(code, admin_token)) as ws:
            ws.receive_json(); ws.receive_json()
            client.post(
                f"/api/sessions/{code}/track",
                params={"track_id": 2, "keep_playing": "true"},
                headers=admin_headers,
            )
            change = ws.receive_json()
            assert change["type"] == "track_change"
            assert change["track_id"] == 2
            assert change["is_playing"] is True

    def test_playback_control_broadcast(self, client, admin_headers, admin_token):
        code = _make_session(client, admin_headers, name="Playback Control Test", album_id=1)
        with client.websocket_connect(ws_url(code, admin_token)) as ws:
            ws.receive_json(); ws.receive_json()
            client.post(f"/api/sessions/{code}/playback", params={"action": "play"}, headers=admin_headers)
            play_msg = ws.receive_json()
            assert play_msg["type"] == "playback"
            assert play_msg["action"] == "play"
            client.post(f"/api/sessions/{code}/playback", params={"action": "pause"}, headers=admin_headers)
            pause_msg = ws.receive_json()
            assert pause_msg["action"] == "pause"


class TestWebSocketSessionEnd:
    def test_session_end_broadcast(self, client, admin_headers, admin_token):
        code = _make_session(client, admin_headers, name="End Test")
        with client.websocket_connect(ws_url(code, admin_token)) as ws:
            ws.receive_json(); ws.receive_json()
            client.delete(f"/api/sessions/{code}", headers=admin_headers)
            end_msg = ws.receive_json()
            assert end_msg["type"] == "session_ended"
            assert "message" in end_msg


class TestWebSocketCleanup:
    def test_disconnect_removes_from_active_sessions(self, client, admin_headers, user_token):
        code = _make_session(client, admin_headers, name="Cleanup Test")
        with client.websocket_connect(ws_url(code, user_token)) as ws:
            ws.receive_json(); ws.receive_json()
        data = client.get(f"/api/sessions/{code}").json()
        assert data["active_listeners"] == 0

    def test_reconnect_after_disconnect(self, client, admin_headers, admin_token):
        code = _make_session(client, admin_headers, name="Reconnect Test")
        with client.websocket_connect(ws_url(code, admin_token)) as ws:
            ws.receive_json(); ws.receive_json()
        with client.websocket_connect(ws_url(code, admin_token)) as ws:
            assert ws.receive_json()["type"] == "user_joined"
            assert ws.receive_json()["type"] == "sync"
