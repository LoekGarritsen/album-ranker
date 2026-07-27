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

    def test_websocket_sync_includes_mode_and_album(self, client, admin_headers, admin_token):
        """Reconnect catch-up: mode/album switches missed while the socket was
        down arrive via the sync snapshot."""
        code = _make_session(client, admin_headers, mode="hangout")
        with client.websocket_connect(ws_url(code, admin_token)) as ws:
            ws.receive_json()  # user_joined
            sync = ws.receive_json()
            assert sync["mode"] == "hangout"
            assert sync["album_id"] is None

    def test_two_tabs_count_as_one_listener(self, client, admin_headers, admin_token):
        code = _make_session(client, admin_headers)
        with client.websocket_connect(ws_url(code, admin_token)) as ws1:
            ws1.receive_json()  # user_joined
            ws1.receive_json()  # sync
            with client.websocket_connect(ws_url(code, admin_token)) as ws2:
                ws2.receive_json()  # sync (no user_joined: same user, second tab)
                data = client.get(f"/api/sessions/{code}").json()
                assert data["active_listeners"] == 1

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


class TestWebSocketChat:
    def test_chat_message_broadcast_and_persisted(self, client, admin_headers, admin_token, user_token):
        code = _make_session(client, admin_headers, name="Chat Test", mode="hangout")
        with client.websocket_connect(ws_url(code, admin_token)) as ws1:
            ws1.receive_json(); ws1.receive_json()
            with client.websocket_connect(ws_url(code, user_token)) as ws2:
                ws1.receive_json(); ws2.receive_json(); ws2.receive_json()
                ws2.send_json({"type": "chat", "content": "hello room", "client_id": "abc-123"})
                msg1 = ws1.receive_json()
                assert msg1["type"] == "chat_message"
                assert msg1["content"] == "hello room"
                assert msg1["user_id"] == 2
                assert msg1["user_name"] == "TestUser"
                assert msg1["id"] > 0
                # Sender gets the echo too, with its client_id for reconciliation.
                echo = ws2.receive_json()
                assert echo["type"] == "chat_message"
                assert echo["client_id"] == "abc-123"

        history = client.get(f"/api/sessions/{code}/messages").json()
        assert len(history["messages"]) == 1
        assert history["messages"][0]["content"] == "hello room"
        assert history["has_more"] is False

    def test_guest_cannot_chat(self, client, admin_headers):
        code = _make_session(client, admin_headers, name="Guest Chat Test")
        with client.websocket_connect(ws_url(code)) as ws:
            ws.receive_json(); ws.receive_json()
            ws.send_json({"type": "chat", "content": "sneaky"})
            err = ws.receive_json()
            assert err["type"] == "error"
        history = client.get(f"/api/sessions/{code}/messages").json()
        assert history["messages"] == []

    def test_empty_and_oversized_messages_dropped(self, client, admin_headers, admin_token):
        code = _make_session(client, admin_headers, name="Validation Test")
        with client.websocket_connect(ws_url(code, admin_token)) as ws:
            ws.receive_json(); ws.receive_json()
            ws.send_json({"type": "chat", "content": "   "})
            ws.send_json({"type": "chat", "content": "x" * 1001})
            ws.send_json({"type": "ping"})
            assert ws.receive_json()["type"] == "pong"
        history = client.get(f"/api/sessions/{code}/messages").json()
        assert history["messages"] == []

    def test_gif_message_broadcast_with_kind(self, client, admin_headers, admin_token):
        code = _make_session(client, admin_headers, name="GIF Test", mode="hangout")
        gif_url = "https://media2.giphy.com/media/abc123/200w.gif"
        with client.websocket_connect(ws_url(code, admin_token)) as ws:
            ws.receive_json(); ws.receive_json()
            ws.send_json({"type": "chat", "content": gif_url, "kind": "gif", "client_id": "gif-1"})
            echo = ws.receive_json()
            assert echo["type"] == "chat_message"
            assert echo["kind"] == "gif"
            assert echo["content"] == gif_url
        history = client.get(f"/api/sessions/{code}/messages").json()
        assert history["messages"][0]["kind"] == "gif"
        assert history["messages"][0]["content"] == gif_url

    def test_gif_with_non_giphy_url_dropped(self, client, admin_headers, admin_token):
        code = _make_session(client, admin_headers, name="GIF Validation Test")
        with client.websocket_connect(ws_url(code, admin_token)) as ws:
            ws.receive_json(); ws.receive_json()
            ws.send_json({"type": "chat", "content": "https://evil.com/x.gif", "kind": "gif"})
            ws.send_json({"type": "chat", "content": "http://media.giphy.com/x.gif", "kind": "gif"})
            ws.send_json({"type": "chat", "content": "https://giphy.com.evil.com/x.gif", "kind": "gif"})
            ws.send_json({"type": "ping"})
            assert ws.receive_json()["type"] == "pong"
        history = client.get(f"/api/sessions/{code}/messages").json()
        assert history["messages"] == []

    def test_text_message_defaults_to_kind_text(self, client, admin_headers, admin_token):
        code = _make_session(client, admin_headers, name="Kind Default Test")
        with client.websocket_connect(ws_url(code, admin_token)) as ws:
            ws.receive_json(); ws.receive_json()
            ws.send_json({"type": "chat", "content": "plain old text"})
            echo = ws.receive_json()
            assert echo["kind"] == "text"
        history = client.get(f"/api/sessions/{code}/messages").json()
        assert history["messages"][0]["kind"] == "text"

    def test_typing_relayed_not_persisted(self, client, admin_headers, admin_token, user_token):
        code = _make_session(client, admin_headers, name="Typing Test")
        with client.websocket_connect(ws_url(code, admin_token)) as ws1:
            ws1.receive_json(); ws1.receive_json()
            with client.websocket_connect(ws_url(code, user_token)) as ws2:
                ws1.receive_json(); ws2.receive_json(); ws2.receive_json()
                ws2.send_json({"type": "typing"})
                typing = ws1.receive_json()
                assert typing["type"] == "user_typing"
                assert typing["user_id"] == 2
                assert typing["user_name"] == "TestUser"
        history = client.get(f"/api/sessions/{code}/messages").json()
        assert history["messages"] == []

    def test_reaction_toggle(self, client, admin_headers, admin_token, user_token):
        code = _make_session(client, admin_headers, name="Reaction Test")
        with client.websocket_connect(ws_url(code, admin_token)) as ws1:
            ws1.receive_json(); ws1.receive_json()
            ws1.send_json({"type": "chat", "content": "react to me"})
            msg = ws1.receive_json()
            with client.websocket_connect(ws_url(code, user_token)) as ws2:
                ws1.receive_json(); ws2.receive_json(); ws2.receive_json()
                ws2.send_json({"type": "reaction", "message_id": msg["id"], "emoji": "🔥"})
                r1 = ws1.receive_json()
                assert r1["type"] == "reaction"
                assert r1["action"] == "added"
                assert r1["emoji"] == "🔥"
                # Toggle off
                ws2.send_json({"type": "reaction", "message_id": msg["id"], "emoji": "🔥"})
                r2 = ws1.receive_json()
                assert r2["action"] == "removed"

    def test_reaction_included_in_history(self, client, admin_headers, admin_token):
        code = _make_session(client, admin_headers, name="Reaction History Test")
        with client.websocket_connect(ws_url(code, admin_token)) as ws:
            ws.receive_json(); ws.receive_json()
            ws.send_json({"type": "chat", "content": "banger"})
            msg = ws.receive_json()
            ws.send_json({"type": "reaction", "message_id": msg["id"], "emoji": "🎵"})
            ws.receive_json()
        history = client.get(f"/api/sessions/{code}/messages").json()
        assert history["messages"][0]["reactions"] == [
            {"emoji": "🎵", "user_id": 1, "user_name": "TestAdmin"}
        ]


class TestChatHistoryPagination:
    def _post_messages(self, client, code, token, count):
        import time as _t
        with client.websocket_connect(ws_url(code, token)) as ws:
            ws.receive_json(); ws.receive_json()
            for i in range(count):
                ws.send_json({"type": "chat", "content": f"msg {i}"})
                ws.receive_json()
                _t.sleep(0.31)  # flood guard gap

    def test_before_id_pages_older(self, client, admin_headers, admin_token):
        code = _make_session(client, admin_headers, name="Paging Test")
        self._post_messages(client, code, admin_token, 5)
        page1 = client.get(f"/api/sessions/{code}/messages", params={"limit": 3}).json()
        assert len(page1["messages"]) == 3
        assert page1["has_more"] is True
        assert page1["messages"][-1]["content"] == "msg 4"
        oldest_id = page1["messages"][0]["id"]
        page2 = client.get(f"/api/sessions/{code}/messages", params={"limit": 3, "before_id": oldest_id}).json()
        assert [m["content"] for m in page2["messages"]] == ["msg 0", "msg 1"]
        assert page2["has_more"] is False

    def test_after_id_catches_up(self, client, admin_headers, admin_token):
        code = _make_session(client, admin_headers, name="Catchup Test")
        self._post_messages(client, code, admin_token, 3)
        all_msgs = client.get(f"/api/sessions/{code}/messages").json()["messages"]
        catchup = client.get(
            f"/api/sessions/{code}/messages", params={"after_id": all_msgs[0]["id"]}
        ).json()
        assert [m["content"] for m in catchup["messages"]] == ["msg 1", "msg 2"]

    def test_messages_for_unknown_session_404(self, client):
        assert client.get("/api/sessions/NOPE99/messages").status_code == 404


class TestHangoutMedia:
    MEDIA = {
        "type": "track", "spotify_id": "abc123", "name": "Some Song",
        "artist": "Some Artist", "image": "https://img.example/x.jpg", "duration_ms": 201000,
    }

    def test_set_media_broadcasts_and_starts_playing(self, client, admin_headers, admin_token):
        code = _make_session(client, admin_headers, name="Media Room", mode="hangout")
        with client.websocket_connect(ws_url(code, admin_token)) as ws:
            ws.receive_json(); ws.receive_json()
            res = client.post(f"/api/sessions/{code}/media", json=self.MEDIA, headers=admin_headers)
            assert res.status_code == 200
            msg = ws.receive_json()
            assert msg["type"] == "media_change"
            assert msg["media"]["spotify_id"] == "abc123"
            assert msg["media"]["type"] == "track"
            assert msg["is_playing"] is True
            assert msg["changed_by_name"] == "TestAdmin"

    def test_media_included_in_sync_and_session_detail(self, client, admin_headers, admin_token):
        code = _make_session(client, admin_headers, name="Media Sync Room", mode="hangout")
        client.post(f"/api/sessions/{code}/media", json=self.MEDIA, headers=admin_headers)
        with client.websocket_connect(ws_url(code, admin_token)) as ws:
            ws.receive_json()
            sync = ws.receive_json()
            assert sync["type"] == "sync"
            assert sync["media"]["name"] == "Some Song"
        detail = client.get(f"/api/sessions/{code}").json()
        assert detail["media"]["spotify_id"] == "abc123"

    def test_media_survives_state_eviction(self, client, admin_headers, admin_token):
        """Media persists in the DB — a backend restart (state loss) must not lose it."""
        from state import active_sessions
        code = _make_session(client, admin_headers, name="Media Persist Room", mode="hangout")
        client.post(f"/api/sessions/{code}/media", json=self.MEDIA, headers=admin_headers)
        del active_sessions[code]
        with client.websocket_connect(ws_url(code, admin_token)) as ws:
            ws.receive_json()
            sync = ws.receive_json()
            assert sync["media"]["spotify_id"] == "abc123"

    def test_media_unknown_session_404(self, client, admin_headers):
        res = client.post("/api/sessions/NOPE99/media", json=self.MEDIA, headers=admin_headers)
        assert res.status_code == 404

    def test_media_invalid_type_rejected(self, client, admin_headers):
        code = _make_session(client, admin_headers, name="Bad Media Room")
        bad = dict(self.MEDIA, type="playlist")
        res = client.post(f"/api/sessions/{code}/media", json=bad, headers=admin_headers)
        assert res.status_code == 422


class TestHangoutMode:
    def test_create_hangout_session(self, client, admin_headers):
        res = client.post("/api/sessions", json={"name": "Hangout", "mode": "hangout"}, headers=admin_headers)
        assert res.status_code == 200
        code = res.json()["code"]
        assert res.json()["mode"] == "hangout"
        detail = client.get(f"/api/sessions/{code}").json()
        assert detail["mode"] == "hangout"
        listing = client.get("/api/sessions").json()
        assert any(s["code"] == code and s["mode"] == "hangout" for s in listing)

    def test_default_mode_is_listening(self, client, admin_headers):
        code = _make_session(client, admin_headers, name="Default Mode")
        assert client.get(f"/api/sessions/{code}").json()["mode"] == "listening"

    def test_invalid_mode_rejected(self, client, admin_headers):
        res = client.post("/api/sessions", json={"name": "Bad", "mode": "party"}, headers=admin_headers)
        assert res.status_code == 422


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
