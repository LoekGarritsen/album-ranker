"""Mode gates and room access control added for hangout hardening.

Covers: listening-only endpoints rejecting hangout rooms (and vice versa),
vote/skip gating, empty-room play resurrection, and password-room privacy
(chat history, queue, WS-facing REST payloads).
"""


def _media(name="Song", sid="sp_gate_a"):
    return {
        "type": "track",
        "spotify_id": sid,
        "name": name,
        "artist": "Artist",
        "image": None,
        "duration_ms": 90000,
    }


def _room(client, headers, mode="hangout", **extra):
    res = client.post(
        "/api/sessions",
        json={"name": "Gate Room", "is_public": True, "mode": mode, **extra},
        headers=headers,
    )
    assert res.status_code == 200
    return res.json()["code"]


class TestModeGates:
    def test_track_rejected_in_hangout_room(self, client, admin_headers):
        code = _room(client, admin_headers, mode="hangout")
        res = client.post(f"/api/sessions/{code}/track?track_id=1", headers=admin_headers)
        assert res.status_code == 409

    def test_track_unknown_room_is_404(self, client, admin_headers):
        res = client.post("/api/sessions/ZZZZZZ/track?track_id=1", headers=admin_headers)
        assert res.status_code == 404

    def test_track_unknown_track_is_404_not_500(self, client, admin_headers):
        code = _room(client, admin_headers, mode="listening")
        res = client.post(f"/api/sessions/{code}/track?track_id=99999", headers=admin_headers)
        assert res.status_code == 404

    def test_album_rejected_in_hangout_room(self, client, admin_headers):
        code = _room(client, admin_headers, mode="hangout")
        res = client.post(f"/api/sessions/{code}/album?album_id=1", headers=admin_headers)
        assert res.status_code == 409

    def test_album_set_still_works_in_listening_room(self, client, admin_headers):
        code = _room(client, admin_headers, mode="listening")
        res = client.post(f"/api/sessions/{code}/album?album_id=1", headers=admin_headers)
        assert res.status_code == 200
        assert client.get(f"/api/sessions/{code}").json()["album_id"] == 1

    def test_media_vote_rejected_after_switch_to_listening(self, client, admin_headers):
        # Leftover hangout media must not accept votes (2 dislikes would
        # advance the queue and seize the listening room's clock).
        code = _room(client, admin_headers, mode="hangout")
        client.post(f"/api/sessions/{code}/queue", json=_media(), headers=admin_headers)
        client.post(f"/api/sessions/{code}/mode", params={"mode": "listening"}, headers=admin_headers)
        res = client.post(f"/api/sessions/{code}/media/vote?vote=down", headers=admin_headers)
        assert res.status_code == 409

    def test_play_on_empty_hangout_room_is_ignored(self, client, admin_headers):
        code = _room(client, admin_headers, mode="hangout")
        res = client.post(f"/api/sessions/{code}/playback?action=play", headers=admin_headers)
        assert res.status_code == 200
        assert res.json().get("ignored") is True
        assert client.get(f"/api/sessions/{code}").json()["playback"]["is_playing"] is False

    def test_play_with_media_on_still_works(self, client, admin_headers):
        code = _room(client, admin_headers, mode="hangout")
        client.post(f"/api/sessions/{code}/queue", json=_media(), headers=admin_headers)
        client.post(f"/api/sessions/{code}/playback?action=pause", headers=admin_headers)
        res = client.post(f"/api/sessions/{code}/playback?action=play", headers=admin_headers)
        assert res.status_code == 200
        assert client.get(f"/api/sessions/{code}").json()["playback"]["is_playing"] is True


class TestPasswordRoomAccess:
    def _password_room(self, client, headers):
        return _room(client, headers, mode="hangout", is_public=False, password="hunter2")

    def test_messages_hidden_from_non_members(self, client, admin_headers, user_headers):
        code = self._password_room(client, admin_headers)
        # Anonymous
        assert client.get(f"/api/sessions/{code}/messages").status_code == 403
        # Authed but never joined
        assert client.get(f"/api/sessions/{code}/messages", headers=user_headers).status_code == 403

    def test_messages_visible_after_join(self, client, admin_headers, user_headers):
        code = self._password_room(client, admin_headers)
        res = client.post(f"/api/sessions/{code}/join", json={"password": "hunter2"}, headers=user_headers)
        assert res.status_code == 200
        assert client.get(f"/api/sessions/{code}/messages", headers=user_headers).status_code == 200

    def test_queue_hidden_from_non_members(self, client, admin_headers):
        code = self._password_room(client, admin_headers)
        assert client.get(f"/api/sessions/{code}/queue").status_code == 403

    def test_session_details_strip_content_for_non_members(self, client, admin_headers):
        code = self._password_room(client, admin_headers)
        client.post(f"/api/sessions/{code}/queue", json=_media(), headers=admin_headers)
        client.post(f"/api/sessions/{code}/queue", json=_media("Queued", "sp_gate_b"), headers=admin_headers)

        # Metadata stays (join screen needs it), content stripped
        anon = client.get(f"/api/sessions/{code}").json()
        assert anon["has_password"] is True
        assert anon["media"] is None
        assert anon["queue"] == []

        # Creator (member) sees everything
        mine = client.get(f"/api/sessions/{code}", headers=admin_headers).json()
        assert mine["media"]["name"] == "Song"
        assert len(mine["queue"]) == 1

    def test_open_rooms_stay_open_to_guests(self, client, admin_headers):
        code = _room(client, admin_headers, mode="hangout")
        assert client.get(f"/api/sessions/{code}/messages").status_code == 200
        assert client.get(f"/api/sessions/{code}/queue").status_code == 200


class TestQueueAlbumName:
    def test_album_name_survives_queue_roundtrip(self, client, admin_headers):
        code = _room(client, admin_headers, mode="hangout")
        client.post(f"/api/sessions/{code}/queue", json=_media(), headers=admin_headers)
        queued = {**_media("Next Up", "sp_gate_c"), "album_name": "Source Album"}
        client.post(f"/api/sessions/{code}/queue", json=queued, headers=admin_headers)

        data = client.get(f"/api/sessions/{code}", headers=admin_headers).json()
        assert data["queue"][0]["album_name"] == "Source Album"

        # Advance pops it into now-playing with album_name intact
        res = client.post(f"/api/sessions/{code}/queue/next?seq={data['media_seq']}", headers=admin_headers)
        assert res.json()["advanced"] is True
        now = client.get(f"/api/sessions/{code}", headers=admin_headers).json()
        assert now["media"]["album_name"] == "Source Album"
