"""
Listen-later, lists, likes, notifications, feed, compatibility,
rating history, artist follows, image proxy.
"""

ALBUM = {
    "spotify_id": "spotify:album:backlog1",
    "name": "Backlog Album",
    "artist": "Someone",
    "image": "https://i.scdn.co/image/x",
    "release_date": "2025-11-01",
}


class TestListenLater:
    def test_toggle_and_list(self, client, user_headers):
        res = client.post("/api/listen-later", json=ALBUM, headers=user_headers)
        assert res.json()["saved"] is True
        items = client.get("/api/listen-later", headers=user_headers).json()["items"]
        assert len(items) == 1 and items[0]["name"] == "Backlog Album"
        # Toggle off
        res = client.post("/api/listen-later", json=ALBUM, headers=user_headers)
        assert res.json()["saved"] is False
        assert client.get("/api/listen-later", headers=user_headers).json()["items"] == []

    def test_backlog_is_per_user(self, client, user_headers, admin_headers):
        client.post("/api/listen-later", json=ALBUM, headers=user_headers)
        assert client.get("/api/listen-later", headers=admin_headers).json()["items"] == []

    def test_library_flag(self, client, user_headers):
        in_library = {**ALBUM, "spotify_id": "spotify:album:test123"}
        client.post("/api/listen-later", json=in_library, headers=user_headers)
        items = client.get("/api/listen-later", headers=user_headers).json()["items"]
        assert items[0]["library_album_id"] == 1


class TestLists:
    def _create(self, client, headers, title="Faves"):
        return client.post("/api/lists", json={"title": title}, headers=headers).json()

    def test_create_add_reorder_remove(self, client, user_headers):
        lst = self._create(client, user_headers)
        res = client.post(f"/api/lists/{lst['id']}/items",
                          json={"album_id": 1, "note": "classic"}, headers=user_headers)
        assert res.status_code == 200
        detail = client.get(f"/api/lists/{lst['id']}", headers=user_headers).json()
        assert len(detail["items"]) == 1
        assert detail["items"][0]["note"] == "classic"

        # Duplicate add rejected
        res = client.post(f"/api/lists/{lst['id']}/items",
                          json={"album_id": 1}, headers=user_headers)
        assert res.status_code == 400

        item_id = detail["items"][0]["id"]
        res = client.put(f"/api/lists/{lst['id']}/reorder",
                         json={"item_ids": [item_id]}, headers=user_headers)
        assert res.status_code == 200

        res = client.delete(f"/api/lists/{lst['id']}/items/{item_id}", headers=user_headers)
        assert res.status_code == 200
        assert client.get(f"/api/lists/{lst['id']}", headers=user_headers).json()["items"] == []

    def test_only_owner_edits(self, client, user_headers, admin_headers):
        lst = self._create(client, user_headers)
        # Different non-admin user would 403; admin may edit
        res = client.post(f"/api/lists/{lst['id']}/items", json={"album_id": 1}, headers=admin_headers)
        assert res.status_code == 200

    def test_owner_check_blocks_stranger(self, client, user_headers, admin_headers):
        lst = self._create(client, admin_headers)
        # user 2 is not owner and not admin
        res = client.delete(f"/api/lists/{lst['id']}", headers=user_headers)
        assert res.status_code == 403

    def test_listing_includes_covers_and_count(self, client, user_headers):
        lst = self._create(client, user_headers)
        client.post(f"/api/lists/{lst['id']}/items", json={"album_id": 1}, headers=user_headers)
        lists = client.get("/api/lists", headers=user_headers).json()["lists"]
        assert lists[0]["item_count"] == 1
        assert lists[0]["covers"] == ["https://example.com/cover.jpg"]


class TestLikes:
    def _rate(self, client, headers, score=7.5, comment="solid"):
        client.post("/api/rankings/album", json={"album_id": 1, "score": score, "comment": comment},
                    headers=headers)
        results = client.get("/api/results", headers=headers).json()["results"]
        return results[0]["album_rankings"][0]["ranking_id"]

    def test_like_toggle_and_notification(self, client, user_headers, admin_headers):
        ranking_id = self._rate(client, admin_headers)
        res = client.post("/api/likes/toggle",
                          json={"kind": "album", "ranking_id": ranking_id}, headers=user_headers)
        assert res.json() == {"ok": True, "liked": True, "count": 1}

        notifs = client.get("/api/notifications", headers=admin_headers).json()
        assert any(n["type"] == "rating_like" for n in notifs["notifications"])

        res = client.post("/api/likes/toggle",
                          json={"kind": "album", "ranking_id": ranking_id}, headers=user_headers)
        assert res.json()["liked"] is False and res.json()["count"] == 0

    def test_self_like_no_notification(self, client, admin_headers):
        ranking_id = self._rate(client, admin_headers)
        client.post("/api/likes/toggle",
                    json={"kind": "album", "ranking_id": ranking_id}, headers=admin_headers)
        notifs = client.get("/api/notifications", headers=admin_headers).json()
        assert not any(n["type"] == "rating_like" for n in notifs["notifications"])

    def test_results_carry_like_counts(self, client, user_headers, admin_headers):
        ranking_id = self._rate(client, admin_headers)
        client.post("/api/likes/toggle",
                    json={"kind": "album", "ranking_id": ranking_id}, headers=user_headers)
        results = client.get("/api/results", headers=user_headers).json()["results"]
        rank = results[0]["album_rankings"][0]
        assert rank["likes"] == 1 and rank["liked_by_me"] == 1

    def test_missing_ranking_404(self, client, user_headers):
        res = client.post("/api/likes/toggle",
                          json={"kind": "track", "ranking_id": 999}, headers=user_headers)
        assert res.status_code == 404


class TestNotifications:
    def test_mark_read(self, client, user_headers, admin_headers):
        # Session creation notifies other users
        client.post("/api/sessions", json={"name": "Party", "mode": "hangout"}, headers=admin_headers)
        notifs = client.get("/api/notifications", headers=user_headers).json()
        assert notifs["unread"] == 1
        assert notifs["notifications"][0]["type"] == "session_started"
        assert notifs["notifications"][0]["payload"]["name"] == "Party"

        client.post("/api/notifications/read", json={}, headers=user_headers)
        assert client.get("/api/notifications", headers=user_headers).json()["unread"] == 0

    def test_private_session_not_announced(self, client, user_headers, admin_headers):
        client.post("/api/sessions", json={"name": "Secret", "is_public": False},
                    headers=admin_headers)
        assert client.get("/api/notifications", headers=user_headers).json()["unread"] == 0

    def test_requires_auth(self, client):
        assert client.get("/api/notifications").status_code == 401


class TestFeed:
    def test_feed_collects_events(self, client, user_headers, admin_headers):
        client.post("/api/rankings/album", json={"album_id": 1, "score": 9.0, "comment": "banger"},
                    headers=admin_headers)
        client.post("/api/rankings/track", json={"track_id": 1, "score": 8.0}, headers=admin_headers)
        client.post("/api/lists", json={"title": "Gems"}, headers=user_headers)

        feed = client.get("/api/feed", headers=user_headers).json()["feed"]
        kinds = {e["kind"] for e in feed}
        assert {"album_rating", "track_burst", "album_added", "list_created"} <= kinds


class TestCompatibility:
    def test_compatibility_score(self, client, user_headers, admin_headers):
        client.post("/api/rankings/album", json={"album_id": 1, "score": 8.0}, headers=admin_headers)
        client.post("/api/rankings/album", json={"album_id": 1, "score": 7.0}, headers=user_headers)
        data = client.get("/api/comparison?user1_id=1&user2_id=2", headers=user_headers).json()
        compat = data["compatibility"]
        assert compat["shared_albums"] == 1
        assert compat["mean_diff"] == 1.0
        assert compat["score"] == round(100 * (1 - 1.0 / 9))

    def test_no_shared_ratings(self, client, user_headers, admin_headers):
        client.post("/api/rankings/album", json={"album_id": 1, "score": 8.0}, headers=admin_headers)
        data = client.get("/api/comparison?user1_id=1&user2_id=2", headers=user_headers).json()
        assert data["compatibility"] is None


class TestRatingHistory:
    def test_growers_track_rerates(self, client, admin_headers):
        client.post("/api/rankings/album", json={"album_id": 1, "score": 5.0}, headers=admin_headers)
        client.post("/api/rankings/album", json={"album_id": 1, "score": 8.0}, headers=admin_headers)
        data = client.get("/api/rating-history/growers", headers=admin_headers).json()
        assert len(data["growers"]) == 1
        g = data["growers"][0]
        assert g["first_score"] == 5.0 and g["last_score"] == 8.0 and g["delta"] == 3.0
        assert data["fell_off"] == []

    def test_same_score_resubmit_not_a_change(self, client, admin_headers):
        client.post("/api/rankings/album", json={"album_id": 1, "score": 5.0}, headers=admin_headers)
        client.post("/api/rankings/album", json={"album_id": 1, "score": 5.0}, headers=admin_headers)
        data = client.get("/api/rating-history/growers", headers=admin_headers).json()
        assert data["growers"] == [] and data["fell_off"] == []


class TestFollows:
    def test_follow_toggle_and_shared_list(self, client, user_headers, admin_headers):
        body = {"spotify_artist_id": "artist1", "name": "Radiohead", "image": None}
        assert client.post("/api/artists/follows", json=body, headers=user_headers).json()["followed"] is True

        artists = client.get("/api/artists/follows", headers=admin_headers).json()["artists"]
        assert artists[0]["name"] == "Radiohead"
        assert artists[0]["followed_by_me"] == 0  # admin doesn't follow yet

        assert client.post("/api/artists/follows", json=body, headers=user_headers).json()["followed"] is False
        assert client.get("/api/artists/follows", headers=user_headers).json()["artists"] == []


class TestImageProxy:
    def test_rejects_non_spotify_hosts(self, client, user_headers):
        res = client.get("/api/image-proxy?url=https://evil.example.com/x.png", headers=user_headers)
        assert res.status_code == 400

    def test_requires_auth(self, client):
        res = client.get("/api/image-proxy?url=https://i.scdn.co/image/x")
        assert res.status_code == 401
