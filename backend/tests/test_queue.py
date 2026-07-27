"""
Shared play queue (hangout mode): add, vote-reorder, remove, guarded advance.
Plus personal favorites.
"""


def _create_hangout(client, headers, name="Hangout"):
    res = client.post("/api/sessions", json={"name": name, "mode": "hangout"}, headers=headers)
    assert res.status_code == 200
    return res.json()["code"]


def _media(name="Song A", spotify_id="sp_a", media_type="track"):
    return {
        "type": media_type,
        "spotify_id": spotify_id,
        "name": name,
        "artist": "Artist",
        "image": None,
        "duration_ms": 200000,
    }


class TestModeGating:
    """Hangout automation must not fire while a room is in listening mode."""

    def test_add_in_listening_room_queues_instead_of_starting(self, client, admin_headers):
        res = client.post("/api/sessions", json={"name": "Rank", "mode": "listening"}, headers=admin_headers)
        code = res.json()["code"]
        res = client.post(f"/api/sessions/{code}/queue", json=_media(), headers=admin_headers)
        assert res.status_code == 200
        assert res.json()["started"] is False
        assert len(res.json()["queue"]) == 1
        assert client.get(f"/api/sessions/{code}").json()["media"] is None

    def test_advance_is_noop_in_listening_mode(self, client, admin_headers):
        code = _create_hangout(client, admin_headers)
        client.post(f"/api/sessions/{code}/queue", json=_media("Now"), headers=admin_headers)
        client.post(f"/api/sessions/{code}/queue", json=_media("Queued", "sp_b"), headers=admin_headers)
        client.post(f"/api/sessions/{code}/mode", params={"mode": "listening"}, headers=admin_headers)

        res = client.post(f"/api/sessions/{code}/queue/next?seq=1", headers=admin_headers)
        assert res.status_code == 200
        assert res.json()["advanced"] is False
        data = client.get(f"/api/sessions/{code}").json()
        assert data["media"]["name"] == "Now"
        assert len(data["queue"]) == 1

        # Switching back re-enables the queue with everything intact.
        client.post(f"/api/sessions/{code}/mode", params={"mode": "hangout"}, headers=admin_headers)
        res = client.post(f"/api/sessions/{code}/queue/next?seq=1", headers=admin_headers)
        assert res.json()["advanced"] is True
        assert client.get(f"/api/sessions/{code}").json()["media"]["name"] == "Queued"


class TestQueueAdd:
    def test_first_add_in_idle_room_starts_playing(self, client, admin_headers):
        code = _create_hangout(client, admin_headers)
        res = client.post(f"/api/sessions/{code}/queue", json=_media(), headers=admin_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["started"] is True
        assert data["queue"] == []
        # Now-playing was set, not queued
        session = client.get(f"/api/sessions/{code}").json()
        assert session["media"]["spotify_id"] == "sp_a"

    def test_add_while_playing_queues(self, client, admin_headers, user_headers):
        code = _create_hangout(client, admin_headers)
        client.post(f"/api/sessions/{code}/media", json=_media(), headers=admin_headers)
        res = client.post(
            f"/api/sessions/{code}/queue",
            json=_media("Song B", "sp_b"), headers=user_headers
        )
        data = res.json()
        assert data["started"] is False
        assert len(data["queue"]) == 1
        item = data["queue"][0]
        assert item["spotify_id"] == "sp_b"
        assert item["added_by_name"] == "TestUser"

    def test_add_requires_auth(self, client, admin_headers):
        code = _create_hangout(client, admin_headers)
        res = client.post(f"/api/sessions/{code}/queue", json=_media())
        assert res.status_code == 401

    def test_add_unknown_session_404(self, client, admin_headers):
        res = client.post("/api/sessions/NOPE99/queue", json=_media(), headers=admin_headers)
        assert res.status_code == 404


class TestQueueVotes:
    def _setup_two_items(self, client, admin_headers, user_headers):
        code = _create_hangout(client, admin_headers)
        client.post(f"/api/sessions/{code}/media", json=_media(), headers=admin_headers)
        client.post(f"/api/sessions/{code}/queue", json=_media("Song B", "sp_b"), headers=admin_headers)
        res = client.post(f"/api/sessions/{code}/queue", json=_media("Song C", "sp_c"), headers=user_headers)
        return code, res.json()["queue"]

    def test_upvote_reorders_queue(self, client, admin_headers, user_headers):
        code, queue = self._setup_two_items(client, admin_headers, user_headers)
        assert [q["spotify_id"] for q in queue] == ["sp_b", "sp_c"]
        last_id = queue[1]["id"]
        res = client.post(f"/api/sessions/{code}/queue/{last_id}/vote?vote=up", headers=user_headers)
        new_queue = res.json()["queue"]
        assert [q["spotify_id"] for q in new_queue] == ["sp_c", "sp_b"]
        assert new_queue[0]["likes"] == 1
        assert new_queue[0]["votes"] == [{"user_id": 2, "vote": 1}]

    def test_same_vote_toggles_off(self, client, admin_headers, user_headers):
        code, queue = self._setup_two_items(client, admin_headers, user_headers)
        item_id = queue[0]["id"]
        client.post(f"/api/sessions/{code}/queue/{item_id}/vote?vote=up", headers=user_headers)
        res = client.post(f"/api/sessions/{code}/queue/{item_id}/vote?vote=up", headers=user_headers)
        item = next(q for q in res.json()["queue"] if q["id"] == item_id)
        assert item["likes"] == 0 and item["votes"] == []

    def test_opposite_vote_switches(self, client, admin_headers, user_headers):
        code, queue = self._setup_two_items(client, admin_headers, user_headers)
        item_id = queue[0]["id"]
        client.post(f"/api/sessions/{code}/queue/{item_id}/vote?vote=up", headers=user_headers)
        res = client.post(f"/api/sessions/{code}/queue/{item_id}/vote?vote=down", headers=user_headers)
        item = next(q for q in res.json()["queue"] if q["id"] == item_id)
        assert item["likes"] == 0 and item["dislikes"] == 1

    def test_invalid_vote_rejected(self, client, admin_headers, user_headers):
        code, queue = self._setup_two_items(client, admin_headers, user_headers)
        res = client.post(f"/api/sessions/{code}/queue/{queue[0]['id']}/vote?vote=sideways", headers=user_headers)
        assert res.status_code == 400


class TestQueueMove:
    def _room_with_three(self, client, admin_headers):
        code = _create_hangout(client, admin_headers)
        client.post(f"/api/sessions/{code}/media", json=_media(), headers=admin_headers)
        for name, sid in (("B", "sp_b"), ("C", "sp_c"), ("D", "sp_d")):
            res = client.post(f"/api/sessions/{code}/queue", json=_media(name, sid), headers=admin_headers)
        return code, res.json()["queue"]

    def test_move_to_front(self, client, admin_headers):
        code, queue = self._room_with_three(client, admin_headers)
        last_id = queue[2]["id"]
        res = client.post(f"/api/sessions/{code}/queue/{last_id}/move?index=0", headers=admin_headers)
        assert [q["spotify_id"] for q in res.json()["queue"]] == ["sp_d", "sp_b", "sp_c"]

    def test_move_down(self, client, admin_headers):
        code, queue = self._room_with_three(client, admin_headers)
        first_id = queue[0]["id"]
        res = client.post(f"/api/sessions/{code}/queue/{first_id}/move?index=1", headers=admin_headers)
        assert [q["spotify_id"] for q in res.json()["queue"]] == ["sp_c", "sp_b", "sp_d"]

    def test_move_index_clamped(self, client, admin_headers):
        code, queue = self._room_with_three(client, admin_headers)
        first_id = queue[0]["id"]
        res = client.post(f"/api/sessions/{code}/queue/{first_id}/move?index=99", headers=admin_headers)
        assert [q["spotify_id"] for q in res.json()["queue"]] == ["sp_c", "sp_d", "sp_b"]

    def test_moved_order_drives_advance(self, client, admin_headers):
        code, queue = self._room_with_three(client, admin_headers)
        last_id = queue[2]["id"]
        client.post(f"/api/sessions/{code}/queue/{last_id}/move?index=0", headers=admin_headers)
        client.post(f"/api/sessions/{code}/queue/next?seq=1", headers=admin_headers)
        session = client.get(f"/api/sessions/{code}").json()
        assert session["media"]["spotify_id"] == "sp_d"

    def test_votes_sort_above_manual_order(self, client, admin_headers, user_headers):
        code, queue = self._room_with_three(client, admin_headers)
        last_id = queue[2]["id"]
        client.post(f"/api/sessions/{code}/queue/{last_id}/vote?vote=up", headers=user_headers)
        first_id = queue[0]["id"]
        res = client.post(f"/api/sessions/{code}/queue/{first_id}/move?index=0", headers=admin_headers)
        # Voted item keeps the top spot despite the manual move
        assert res.json()["queue"][0]["spotify_id"] == "sp_d"

    def test_move_unknown_item_404(self, client, admin_headers):
        code, _ = self._room_with_three(client, admin_headers)
        res = client.post(f"/api/sessions/{code}/queue/99999/move?index=0", headers=admin_headers)
        assert res.status_code == 404


class TestQueueRemove:
    def test_adder_can_remove_own_item(self, client, admin_headers, user_headers):
        code = _create_hangout(client, admin_headers)
        client.post(f"/api/sessions/{code}/media", json=_media(), headers=admin_headers)
        added = client.post(f"/api/sessions/{code}/queue", json=_media("B", "sp_b"), headers=user_headers).json()
        item_id = added["queue"][0]["id"]
        res = client.delete(f"/api/sessions/{code}/queue/{item_id}", headers=user_headers)
        assert res.status_code == 200
        assert res.json()["queue"] == []

    def test_non_adder_cannot_remove(self, client, admin_headers, user_headers):
        # Room owned by admin; admin queues an item; a regular non-creator
        # (not the adder, not creator, not admin) may not remove it.
        code = _create_hangout(client, admin_headers)
        client.post(f"/api/sessions/{code}/media", json=_media(), headers=admin_headers)
        added = client.post(f"/api/sessions/{code}/queue", json=_media("C", "sp_c"), headers=admin_headers).json()
        res = client.delete(f"/api/sessions/{code}/queue/{added['queue'][0]['id']}", headers=user_headers)
        assert res.status_code == 403

    def test_creator_can_remove_any_item(self, client, admin_headers, user_headers):
        code = _create_hangout(client, admin_headers)
        client.post(f"/api/sessions/{code}/media", json=_media(), headers=admin_headers)
        added = client.post(f"/api/sessions/{code}/queue", json=_media("B", "sp_b"), headers=user_headers).json()
        item_id = added["queue"][0]["id"]
        res = client.delete(f"/api/sessions/{code}/queue/{item_id}", headers=admin_headers)
        assert res.status_code == 200


class TestQueueAdvance:
    def test_advance_pops_highest_voted(self, client, admin_headers, user_headers):
        code = _create_hangout(client, admin_headers)
        client.post(f"/api/sessions/{code}/media", json=_media(), headers=admin_headers)  # seq -> 1
        client.post(f"/api/sessions/{code}/queue", json=_media("B", "sp_b"), headers=admin_headers)
        added = client.post(f"/api/sessions/{code}/queue", json=_media("C", "sp_c"), headers=user_headers).json()
        c_id = added["queue"][1]["id"]
        client.post(f"/api/sessions/{code}/queue/{c_id}/vote?vote=up", headers=user_headers)

        res = client.post(f"/api/sessions/{code}/queue/next?seq=1", headers=user_headers)
        data = res.json()
        assert data["advanced"] is True
        assert [q["spotify_id"] for q in data["queue"]] == ["sp_b"]
        session = client.get(f"/api/sessions/{code}").json()
        assert session["media"]["spotify_id"] == "sp_c"
        assert session["playback"]["is_playing"] is True

    def test_stale_seq_is_noop(self, client, admin_headers, user_headers):
        """Two clients report the same track end: only the first advances."""
        code = _create_hangout(client, admin_headers)
        client.post(f"/api/sessions/{code}/media", json=_media(), headers=admin_headers)  # seq -> 1
        client.post(f"/api/sessions/{code}/queue", json=_media("B", "sp_b"), headers=admin_headers)
        client.post(f"/api/sessions/{code}/queue", json=_media("C", "sp_c"), headers=admin_headers)

        first = client.post(f"/api/sessions/{code}/queue/next?seq=1", headers=admin_headers).json()
        second = client.post(f"/api/sessions/{code}/queue/next?seq=1", headers=user_headers).json()
        assert first["advanced"] is True
        assert second["advanced"] is False
        # Song C still queued — no double-skip
        assert [q["spotify_id"] for q in second["queue"]] == ["sp_c"]

    def test_advance_empty_queue_clears_now_playing(self, client, admin_headers):
        code = _create_hangout(client, admin_headers)
        client.post(f"/api/sessions/{code}/media", json=_media(), headers=admin_headers)
        res = client.post(f"/api/sessions/{code}/queue/next?seq=1", headers=admin_headers)
        data = res.json()
        assert data["advanced"] is False
        session = client.get(f"/api/sessions/{code}").json()
        assert session["playback"]["is_playing"] is False
        # Now-playing cleared, so the next added item starts immediately
        assert session["media"] is None
        res = client.post(f"/api/sessions/{code}/queue", json=_media("B", "sp_b"), headers=admin_headers)
        assert res.json()["started"] is True


class TestMediaVotes:
    def _playing_room(self, client, admin_headers):
        code = _create_hangout(client, admin_headers)
        client.post(f"/api/sessions/{code}/media", json=_media(), headers=admin_headers)
        return code

    def test_vote_counts_and_toggle(self, client, admin_headers, user_headers):
        code = self._playing_room(client, admin_headers)
        res = client.post(f"/api/sessions/{code}/media/vote?vote=up", headers=user_headers)
        data = res.json()
        assert data["likes"] == 1 and data["dislikes"] == 0
        assert data["voters"] == [{"user_id": 2, "vote": 1}]
        # Same vote again removes it
        res = client.post(f"/api/sessions/{code}/media/vote?vote=up", headers=user_headers)
        assert res.json()["likes"] == 0
        # Opposite vote switches
        client.post(f"/api/sessions/{code}/media/vote?vote=up", headers=user_headers)
        res = client.post(f"/api/sessions/{code}/media/vote?vote=down", headers=user_headers)
        data = res.json()
        assert data["likes"] == 0 and data["dislikes"] == 1

    def test_majority_dislike_skips_to_queue(self, client, admin_headers, user_headers):
        code = self._playing_room(client, admin_headers)
        client.post(f"/api/sessions/{code}/queue", json=_media("B", "sp_b"), headers=admin_headers)
        client.post(f"/api/sessions/{code}/media/vote?vote=down", headers=admin_headers)
        res = client.post(f"/api/sessions/{code}/media/vote?vote=down", headers=user_headers)
        assert res.json()["skipped"] is True
        session = client.get(f"/api/sessions/{code}").json()
        assert session["media"]["spotify_id"] == "sp_b"

    def test_single_dislike_does_not_skip(self, client, admin_headers, user_headers):
        code = self._playing_room(client, admin_headers)
        client.post(f"/api/sessions/{code}/queue", json=_media("B", "sp_b"), headers=admin_headers)
        res = client.post(f"/api/sessions/{code}/media/vote?vote=down", headers=user_headers)
        assert res.json()["skipped"] is False
        session = client.get(f"/api/sessions/{code}").json()
        assert session["media"]["spotify_id"] == "sp_a"

    def test_vote_without_media_404(self, client, admin_headers):
        code = _create_hangout(client, admin_headers)
        res = client.post(f"/api/sessions/{code}/media/vote?vote=up", headers=admin_headers)
        assert res.status_code == 404

    def test_votes_reset_on_media_change(self, client, admin_headers, user_headers):
        code = self._playing_room(client, admin_headers)
        client.post(f"/api/sessions/{code}/media/vote?vote=up", headers=user_headers)
        client.post(f"/api/sessions/{code}/media", json=_media("B", "sp_b"), headers=admin_headers)
        res = client.post(f"/api/sessions/{code}/media/vote?vote=up", headers=user_headers)
        data = res.json()
        assert data["likes"] == 1 and len(data["voters"]) == 1


class TestFavorites:
    def test_toggle_and_list(self, client, user_headers):
        res = client.post("/api/favorites", json=_media(), headers=user_headers)
        assert res.json()["favorited"] is True
        favs = client.get("/api/favorites", headers=user_headers).json()["favorites"]
        assert len(favs) == 1 and favs[0]["spotify_id"] == "sp_a"

        res = client.post("/api/favorites", json=_media(), headers=user_headers)
        assert res.json()["favorited"] is False
        assert client.get("/api/favorites", headers=user_headers).json()["favorites"] == []

    def test_favorites_are_per_user(self, client, admin_headers, user_headers):
        client.post("/api/favorites", json=_media(), headers=user_headers)
        favs = client.get("/api/favorites", headers=admin_headers).json()["favorites"]
        assert favs == []

    def test_favorites_require_auth(self, client):
        assert client.get("/api/favorites").status_code == 401
