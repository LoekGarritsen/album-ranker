"""Guest (unauthenticated) queue-advance behavior.

A hangout room whose only listeners are anonymous guests must still
auto-advance the shared queue when a track ends — advance is deliberately
unauthenticated (seq-guarded, attribution comes from the queue item).
"""


def _media(n):
    return {
        "type": "track",
        "spotify_id": f"guest_q_{n}",
        "name": f"Guest Queue Song {n}",
        "artist": "Guest Artist",
        "image": None,
        "duration_ms": 90000,
    }


def _make_hangout_room(client, headers):
    res = client.post(
        "/api/sessions",
        json={"name": "Guest Room", "is_public": True, "mode": "hangout"},
        headers=headers,
    )
    assert res.status_code == 200
    return res.json()["code"]


class TestGuestQueueAdvance:
    def test_guest_can_advance_queue(self, client, admin_headers):
        code = _make_hangout_room(client, admin_headers)
        # Authed user starts something and queues a second item
        assert client.post(f"/api/sessions/{code}/queue", json=_media(1), headers=admin_headers).json()["started"]
        assert not client.post(f"/api/sessions/{code}/queue", json=_media(2), headers=admin_headers).json()["started"]

        # No Authorization header at all — the anonymous-guest path
        res = client.post(f"/api/sessions/{code}/queue/next")
        assert res.status_code == 200
        body = res.json()
        assert body["advanced"] is True
        assert body["queue"] == []

        session = client.get(f"/api/sessions/{code}").json()
        assert session["media"]["spotify_id"] == "guest_q_2"

    def test_guest_advance_with_stale_seq_is_noop(self, client, admin_headers):
        code = _make_hangout_room(client, admin_headers)
        client.post(f"/api/sessions/{code}/queue", json=_media(1), headers=admin_headers)
        client.post(f"/api/sessions/{code}/queue", json=_media(2), headers=admin_headers)

        # media_seq is 1 after the first item auto-started; seq=0 is stale
        res = client.post(f"/api/sessions/{code}/queue/next?seq=0")
        assert res.status_code == 200
        assert res.json()["advanced"] is False
        # Item 2 still queued
        assert [i["spotify_id"] for i in res.json()["queue"]] == ["guest_q_2"]

    def test_guest_advance_on_empty_queue_pauses(self, client, admin_headers):
        code = _make_hangout_room(client, admin_headers)
        client.post(f"/api/sessions/{code}/queue", json=_media(1), headers=admin_headers)

        res = client.post(f"/api/sessions/{code}/queue/next")
        assert res.status_code == 200
        assert res.json()["advanced"] is False

        session = client.get(f"/api/sessions/{code}").json()
        assert session["playback"]["is_playing"] is False

    def test_guest_still_cannot_add_or_remove_or_vote(self, client, admin_headers):
        code = _make_hangout_room(client, admin_headers)
        client.post(f"/api/sessions/{code}/queue", json=_media(1), headers=admin_headers)
        added = client.post(f"/api/sessions/{code}/queue", json=_media(2), headers=admin_headers)
        item_id = added.json()["queue"][0]["id"]

        assert client.post(f"/api/sessions/{code}/queue", json=_media(3)).status_code == 401
        assert client.delete(f"/api/sessions/{code}/queue/{item_id}").status_code == 401
        assert client.post(f"/api/sessions/{code}/queue/{item_id}/vote?vote=up").status_code == 401
