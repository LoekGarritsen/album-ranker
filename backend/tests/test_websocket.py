"""
Tests for WebSocket functionality in listening sessions.

Tests cover:
- Initial sync state on connection
- Broadcasting rating updates to all participants
- User join/leave notifications
- Ping/pong for connection keep-alive
- Cleanup on disconnect
"""
import pytest
import time
from unittest.mock import patch


class TestWebSocketConnection:
    """Tests for WebSocket connection and initial sync."""

    def test_websocket_connect_receives_sync(self, client, admin_headers):
        """Client should receive sync message immediately after connecting."""
        # Create a session first
        create_response = client.post(
            "/api/sessions",
            json={"name": "WS Test Room", "album_id": 1},
            headers=admin_headers
        )
        code = create_response.json()["code"]

        # Connect via WebSocket
        with client.websocket_connect(f"/api/sessions/{code}/ws?user_id=1") as ws:
            # First message should be user_joined (broadcast to all including self)
            msg1 = ws.receive_json()
            assert msg1["type"] == "user_joined"
            assert msg1["user_name"] == "TestAdmin"

            # Second message should be sync with initial state
            msg2 = ws.receive_json()
            assert msg2["type"] == "sync"
            assert "track_id" in msg2
            assert "is_playing" in msg2
            assert msg2["is_playing"] is False
            assert "position" in msg2
            assert msg2["position"] == 0
            assert "listeners" in msg2

    def test_websocket_sync_includes_current_track(self, client, admin_headers):
        """Sync message should include the current track from session."""
        # Create session with album (which sets first track)
        create_response = client.post(
            "/api/sessions",
            json={"name": "WS Test Room", "album_id": 1},
            headers=admin_headers
        )
        code = create_response.json()["code"]

        with client.websocket_connect(f"/api/sessions/{code}/ws?user_id=2") as ws:
            ws.receive_json()  # user_joined
            sync = ws.receive_json()

            assert sync["type"] == "sync"
            assert sync["track_id"] == 1  # First track of album

    def test_websocket_connect_without_user_id(self, client, admin_headers):
        """Guest users should be able to connect without user_id."""
        create_response = client.post(
            "/api/sessions",
            json={"name": "Guest Test Room"},
            headers=admin_headers
        )
        code = create_response.json()["code"]

        # Connect without user_id
        with client.websocket_connect(f"/api/sessions/{code}/ws") as ws:
            joined = ws.receive_json()
            assert joined["type"] == "user_joined"
            assert joined["user_name"] == "Guest"
            # Guest user_id should be a string like "guest_xxxxxxxx"
            assert str(joined["user_id"]).startswith("guest_")

    def test_websocket_connect_to_nonexistent_session(self, client):
        """Connecting to non-existent session should close immediately."""
        # This should close the WebSocket since session doesn't exist
        with pytest.raises(Exception):
            with client.websocket_connect("/api/sessions/NOTACODE/ws?user_id=1") as ws:
                # Should not reach here - connection should be closed
                ws.receive_json()


class TestWebSocketUserEvents:
    """Tests for user join/leave broadcasts."""

    def test_user_joined_broadcast(self, client, admin_headers, user_headers):
        """All clients should receive user_joined when someone connects."""
        # Create session
        create_response = client.post(
            "/api/sessions",
            json={"name": "Broadcast Test"},
            headers=admin_headers
        )
        code = create_response.json()["code"]

        # First user connects
        with client.websocket_connect(f"/api/sessions/{code}/ws?user_id=1") as ws1:
            ws1.receive_json()  # own user_joined
            ws1.receive_json()  # sync

            # Second user connects
            with client.websocket_connect(f"/api/sessions/{code}/ws?user_id=2") as ws2:
                # ws1 should receive user_joined for user 2
                joined_msg = ws1.receive_json()
                assert joined_msg["type"] == "user_joined"
                assert joined_msg["user_id"] == 2
                assert joined_msg["user_name"] == "TestUser"
                assert joined_msg["active_count"] == 2

                # ws2 should receive its own user_joined
                ws2_joined = ws2.receive_json()
                assert ws2_joined["type"] == "user_joined"

    def test_user_left_broadcast(self, client, admin_headers, user_headers):
        """All clients should receive user_left when someone disconnects."""
        create_response = client.post(
            "/api/sessions",
            json={"name": "Leave Test"},
            headers=admin_headers
        )
        code = create_response.json()["code"]

        with client.websocket_connect(f"/api/sessions/{code}/ws?user_id=1") as ws1:
            ws1.receive_json()  # own user_joined
            ws1.receive_json()  # sync

            # Second user connects then disconnects
            with client.websocket_connect(f"/api/sessions/{code}/ws?user_id=2") as ws2:
                ws1.receive_json()  # user_joined for user 2
                ws2.receive_json()  # user_joined
                ws2.receive_json()  # sync

            # After ws2 context exits (disconnect), ws1 should get user_left
            left_msg = ws1.receive_json()
            assert left_msg["type"] == "user_left"
            assert left_msg["user_id"] == 2
            assert left_msg["user_name"] == "TestUser"
            assert left_msg["active_count"] == 1

    def test_active_count_accuracy(self, client, admin_headers):
        """Active count should accurately reflect connected users."""
        create_response = client.post(
            "/api/sessions",
            json={"name": "Count Test"},
            headers=admin_headers
        )
        code = create_response.json()["code"]

        with client.websocket_connect(f"/api/sessions/{code}/ws?user_id=1") as ws1:
            joined1 = ws1.receive_json()
            assert joined1["type"] == "user_joined"
            assert joined1["active_count"] == 1
            ws1.receive_json()  # sync

            with client.websocket_connect(f"/api/sessions/{code}/ws?user_id=2") as ws2:
                # ws1 receives user_joined for user 2
                joined2 = ws1.receive_json()
                assert joined2["type"] == "user_joined"
                assert joined2["active_count"] == 2


class TestWebSocketPingPong:
    """Tests for ping/pong keep-alive mechanism."""

    def test_ping_receives_pong(self, client, admin_headers):
        """Client ping should receive pong with current state."""
        create_response = client.post(
            "/api/sessions",
            json={"name": "Ping Test"},
            headers=admin_headers
        )
        code = create_response.json()["code"]

        with client.websocket_connect(f"/api/sessions/{code}/ws?user_id=1") as ws:
            ws.receive_json()  # user_joined
            ws.receive_json()  # sync

            # Send ping
            ws.send_json({"type": "ping"})

            # Should receive pong
            pong = ws.receive_json()
            assert pong["type"] == "pong"
            assert "position" in pong
            assert "is_playing" in pong
            assert pong["is_playing"] is False

    def test_pong_reflects_playback_state(self, client, admin_headers):
        """Pong should reflect current playback position."""
        create_response = client.post(
            "/api/sessions",
            json={"name": "Playback Test", "album_id": 1},
            headers=admin_headers
        )
        code = create_response.json()["code"]

        # Start playback via API
        client.post(
            f"/api/sessions/{code}/playback",
            params={"action": "play"},
            headers=admin_headers
        )

        with client.websocket_connect(f"/api/sessions/{code}/ws?user_id=1") as ws:
            ws.receive_json()  # user_joined
            ws.receive_json()  # sync

            # Small delay to accumulate position
            time.sleep(0.1)

            ws.send_json({"type": "ping"})
            pong = ws.receive_json()

            assert pong["is_playing"] is True
            # Position should have advanced (at least slightly)
            assert pong["position"] >= 0


class TestWebSocketRatingBroadcast:
    """Tests for rating broadcasts through WebSocket."""

    def test_track_rating_broadcast(self, client, admin_headers, user_headers):
        """Rating a track should broadcast to all session participants."""
        # Create session
        create_response = client.post(
            "/api/sessions",
            json={"name": "Rating Test", "album_id": 1},
            headers=admin_headers
        )
        code = create_response.json()["code"]

        # Two users connect
        with client.websocket_connect(f"/api/sessions/{code}/ws?user_id=1") as ws1:
            ws1.receive_json()  # user_joined
            ws1.receive_json()  # sync

            with client.websocket_connect(f"/api/sessions/{code}/ws?user_id=2") as ws2:
                ws1.receive_json()  # user_joined for user 2
                ws2.receive_json()  # user_joined
                ws2.receive_json()  # sync

                # User 2 submits a rating with session_code
                client.post(
                    "/api/rankings/track",
                    params={"session_code": code},
                    json={
                        "track_id": 1,
                        "user_id": 2,
                        "score": 8.5,
                        "comment": "Great track!"
                    }
                )

                # Both users should receive rating broadcast
                rating1 = ws1.receive_json()
                assert rating1["type"] == "rating"
                assert rating1["track_id"] == 1
                assert rating1["user_id"] == 2
                assert rating1["user_name"] == "TestUser"
                assert rating1["score"] == 8.5
                assert rating1["comment"] == "Great track!"

                rating2 = ws2.receive_json()
                assert rating2["type"] == "rating"

    def test_rating_without_session_code_no_broadcast(self, client, admin_headers):
        """Rating without session_code should not broadcast."""
        create_response = client.post(
            "/api/sessions",
            json={"name": "No Broadcast Test", "album_id": 1},
            headers=admin_headers
        )
        code = create_response.json()["code"]

        with client.websocket_connect(f"/api/sessions/{code}/ws?user_id=1") as ws:
            ws.receive_json()  # user_joined
            ws.receive_json()  # sync

            # Rate without session_code parameter
            client.post(
                "/api/rankings/track",
                json={"track_id": 1, "user_id": 2, "score": 7.0}
            )

            # Send ping to check - we should only get pong, not rating
            ws.send_json({"type": "ping"})
            msg = ws.receive_json()
            assert msg["type"] == "pong"  # Not "rating"


class TestWebSocketPlaybackBroadcast:
    """Tests for playback control broadcasts."""

    def test_track_change_broadcast(self, client, admin_headers):
        """Changing track should broadcast to all clients."""
        create_response = client.post(
            "/api/sessions",
            json={"name": "Track Change Test", "album_id": 1},
            headers=admin_headers
        )
        code = create_response.json()["code"]

        with client.websocket_connect(f"/api/sessions/{code}/ws?user_id=1") as ws1:
            ws1.receive_json()  # user_joined
            ws1.receive_json()  # sync

            with client.websocket_connect(f"/api/sessions/{code}/ws?user_id=2") as ws2:
                ws1.receive_json()  # user 2 joined
                ws2.receive_json()  # user_joined
                ws2.receive_json()  # sync

                # Change track via API
                client.post(
                    f"/api/sessions/{code}/track",
                    params={"track_id": 2},
                    headers=admin_headers
                )

                # Both should receive track_change
                change1 = ws1.receive_json()
                assert change1["type"] == "track_change"
                assert change1["track_id"] == 2

                change2 = ws2.receive_json()
                assert change2["type"] == "track_change"

    def test_playback_control_broadcast(self, client, admin_headers):
        """Play/pause should broadcast to all clients."""
        create_response = client.post(
            "/api/sessions",
            json={"name": "Playback Control Test", "album_id": 1},
            headers=admin_headers
        )
        code = create_response.json()["code"]

        with client.websocket_connect(f"/api/sessions/{code}/ws?user_id=1") as ws:
            ws.receive_json()  # user_joined
            ws.receive_json()  # sync

            # Start playback
            client.post(
                f"/api/sessions/{code}/playback",
                params={"action": "play"},
                headers=admin_headers
            )

            play_msg = ws.receive_json()
            assert play_msg["type"] == "playback"
            assert play_msg["action"] == "play"

            # Pause
            client.post(
                f"/api/sessions/{code}/playback",
                params={"action": "pause"},
                headers=admin_headers
            )

            pause_msg = ws.receive_json()
            assert pause_msg["type"] == "playback"
            assert pause_msg["action"] == "pause"


class TestWebSocketSessionEnd:
    """Tests for session termination."""

    def test_session_end_broadcast(self, client, admin_headers):
        """Ending session should broadcast session_ended to all clients."""
        create_response = client.post(
            "/api/sessions",
            json={"name": "End Test"},
            headers=admin_headers
        )
        code = create_response.json()["code"]

        with client.websocket_connect(f"/api/sessions/{code}/ws?user_id=1") as ws:
            ws.receive_json()  # user_joined
            ws.receive_json()  # sync

            # End session
            client.delete(f"/api/sessions/{code}", headers=admin_headers)

            # Should receive session_ended
            end_msg = ws.receive_json()
            assert end_msg["type"] == "session_ended"
            assert "message" in end_msg


class TestWebSocketCleanup:
    """Tests for connection cleanup and state management."""

    def test_disconnect_removes_from_active_sessions(self, client, admin_headers):
        """Disconnecting should remove user from active connections."""
        create_response = client.post(
            "/api/sessions",
            json={"name": "Cleanup Test"},
            headers=admin_headers
        )
        code = create_response.json()["code"]

        # Connect and disconnect
        with client.websocket_connect(f"/api/sessions/{code}/ws?user_id=2") as ws:
            ws.receive_json()  # user_joined
            ws.receive_json()  # sync

        # After disconnect, check session state
        session_response = client.get(f"/api/sessions/{code}")
        data = session_response.json()

        # User 2 should not be in active listeners
        # (They're still a participant in DB, just not connected)
        assert data["active_listeners"] == 0

    def test_reconnect_after_disconnect(self, client, admin_headers):
        """User should be able to reconnect after disconnecting."""
        create_response = client.post(
            "/api/sessions",
            json={"name": "Reconnect Test"},
            headers=admin_headers
        )
        code = create_response.json()["code"]

        # First connection
        with client.websocket_connect(f"/api/sessions/{code}/ws?user_id=1") as ws:
            ws.receive_json()
            ws.receive_json()

        # Reconnect
        with client.websocket_connect(f"/api/sessions/{code}/ws?user_id=1") as ws:
            joined = ws.receive_json()
            assert joined["type"] == "user_joined"
            sync = ws.receive_json()
            assert sync["type"] == "sync"
