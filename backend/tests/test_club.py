"""
Club rounds: lifecycle, nomination/vote rules, winner pick, blind rating.
"""


def _create_round(client, headers, title="Week 1"):
    res = client.post("/api/club/rounds", json={"title": title}, headers=headers)
    assert res.status_code == 200
    return res.json()


def _nominate_library_album(client, headers, round_id):
    """Nominate the seeded library album — winner import is then a no-op."""
    return client.post(f"/api/club/rounds/{round_id}/nominate", json={
        "spotify_id": "spotify:album:test123",
        "name": "Test Album",
        "artist": "Test Artist",
        "cover_url": "https://example.com/cover.jpg",
        "release_date": "2024-01-01",
    }, headers=headers)


def _advance(client, headers, round_id, status):
    return client.post(f"/api/club/rounds/{round_id}/status", json={"status": status}, headers=headers)


class TestRoundLifecycle:
    def test_create_and_list(self, client, user_headers):
        detail = _create_round(client, user_headers)
        assert detail["status"] == "nominating"
        data = client.get("/api/club/rounds", headers=user_headers).json()
        assert data["current"]["id"] == detail["id"]

    def test_only_one_open_round(self, client, user_headers):
        _create_round(client, user_headers)
        res = client.post("/api/club/rounds", json={"title": "Another"}, headers=user_headers)
        assert res.status_code == 400

    def test_status_must_advance_in_order(self, client, user_headers):
        detail = _create_round(client, user_headers)
        res = _advance(client, user_headers, detail["id"], "rating")
        assert res.status_code == 400

    def test_non_creator_cannot_advance(self, client, user_headers, admin_headers):
        detail = _create_round(client, admin_headers)
        _nominate_library_album(client, user_headers, detail["id"])
        res = _advance(client, user_headers, detail["id"], "voting")
        assert res.status_code == 403

    def test_admin_can_advance_any_round(self, client, user_headers, admin_headers):
        detail = _create_round(client, user_headers)
        _nominate_library_album(client, user_headers, detail["id"])
        res = _advance(client, admin_headers, detail["id"], "voting")
        assert res.status_code == 200

    def test_voting_requires_nominations(self, client, user_headers):
        detail = _create_round(client, user_headers)
        res = _advance(client, user_headers, detail["id"], "voting")
        assert res.status_code == 400


class TestNominationsAndVotes:
    def test_nomination_replaces_own(self, client, user_headers):
        detail = _create_round(client, user_headers)
        _nominate_library_album(client, user_headers, detail["id"])
        res = client.post(f"/api/club/rounds/{detail['id']}/nominate", json={
            "spotify_id": "spotify:album:other", "name": "Other", "artist": "Someone",
        }, headers=user_headers)
        noms = res.json()["nominations"]
        assert len(noms) == 1
        assert noms[0]["spotify_id"] == "spotify:album:other"

    def test_vote_toggle_and_switch(self, client, user_headers, admin_headers):
        detail = _create_round(client, user_headers)
        _nominate_library_album(client, user_headers, detail["id"])
        client.post(f"/api/club/rounds/{detail['id']}/nominate", json={
            "spotify_id": "spotify:album:other", "name": "Other", "artist": "Someone",
        }, headers=admin_headers)
        _advance(client, user_headers, detail["id"], "voting")

        data = client.get("/api/club/rounds", headers=user_headers).json()["current"]
        nom_ids = [n["id"] for n in data["nominations"]]

        res = client.post(f"/api/club/rounds/{detail['id']}/vote",
                          json={"nomination_id": nom_ids[0]}, headers=user_headers)
        assert res.json()["my_vote"] == nom_ids[0]
        # Switch vote
        res = client.post(f"/api/club/rounds/{detail['id']}/vote",
                          json={"nomination_id": nom_ids[1]}, headers=user_headers)
        assert res.json()["my_vote"] == nom_ids[1]
        # Toggle off
        res = client.post(f"/api/club/rounds/{detail['id']}/vote",
                          json={"nomination_id": nom_ids[1]}, headers=user_headers)
        assert res.json()["my_vote"] is None

    def test_no_votes_outside_voting(self, client, user_headers):
        detail = _create_round(client, user_headers)
        nom = _nominate_library_album(client, user_headers, detail["id"]).json()
        res = client.post(f"/api/club/rounds/{detail['id']}/vote",
                          json={"nomination_id": nom["nominations"][0]["id"]}, headers=user_headers)
        assert res.status_code == 400


class TestBlindRating:
    def _to_rating(self, client, user_headers, admin_headers):
        detail = _create_round(client, admin_headers)
        _nominate_library_album(client, admin_headers, detail["id"])
        _advance(client, admin_headers, detail["id"], "voting")
        res = _advance(client, admin_headers, detail["id"], "rating")
        assert res.status_code == 200
        assert res.json()["album"]["id"] == 1
        return detail["id"]

    def test_scores_hidden_until_you_rate(self, client, user_headers, admin_headers):
        round_id = self._to_rating(client, user_headers, admin_headers)
        client.post("/api/rankings/album", json={"album_id": 1, "score": 8.0},
                    headers=admin_headers)

        albums = client.get("/api/albums", headers=user_headers).json()
        album = albums[0]
        assert album["blind"] is True
        assert album["average_album_score"] is None
        admin_rank = next(r for r in album["album_rankings"] if r["user_id"] == 1)
        assert admin_rank["score"] is None

        # Rating owner still sees their own score
        albums = client.get("/api/albums", headers=admin_headers).json()
        admin_rank = next(r for r in albums[0]["album_rankings"] if r["user_id"] == 1)
        assert admin_rank["score"] == 8.0

    def test_rating_lifts_the_veil_for_rater(self, client, user_headers, admin_headers):
        round_id = self._to_rating(client, user_headers, admin_headers)
        client.post("/api/rankings/album", json={"album_id": 1, "score": 8.0}, headers=admin_headers)
        res = client.post("/api/rankings/album", json={"album_id": 1, "score": 6.0}, headers=user_headers)
        assert res.json().get("blind") is True

        album = client.get("/api/albums", headers=user_headers).json()[0]
        assert album["blind"] is False
        admin_rank = next(r for r in album["album_rankings"] if r["user_id"] == 1)
        assert admin_rank["score"] == 8.0

    def test_reveal_shows_everything(self, client, user_headers, admin_headers):
        round_id = self._to_rating(client, user_headers, admin_headers)
        client.post("/api/rankings/album", json={"album_id": 1, "score": 8.0}, headers=admin_headers)
        _advance(client, admin_headers, round_id, "revealed")

        album = client.get("/api/albums", headers=user_headers).json()[0]
        assert album["blind"] is False
        assert album["average_album_score"] == 8.0

    def test_results_masked_while_blind(self, client, user_headers, admin_headers):
        self._to_rating(client, user_headers, admin_headers)
        client.post("/api/rankings/album", json={"album_id": 1, "score": 8.0}, headers=admin_headers)
        results = client.get("/api/results", headers=user_headers).json()["results"]
        assert results[0]["blind"] is True
        assert results[0]["average_album_score"] is None
        admin_rank = next(r for r in results[0]["album_rankings"] if r["user_id"] == 1)
        assert admin_rank["score"] is None

    def test_club_notifications_fan_out(self, client, user_headers, admin_headers):
        _create_round(client, admin_headers)
        notifs = client.get("/api/notifications", headers=user_headers).json()
        assert notifs["unread"] >= 1
        assert notifs["notifications"][0]["type"] == "club_round"
