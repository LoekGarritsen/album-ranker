"""
Tests for the GIF search proxy.
"""


class TestGifSearch:
    def test_requires_auth(self, client):
        res = client.get("/api/gifs/search")
        assert res.status_code == 401

    def test_returns_503_without_api_key(self, client, admin_headers, monkeypatch):
        import config
        monkeypatch.setattr(config, "GIPHY_API_KEY", "")
        res = client.get("/api/gifs/search", params={"q": "cat"}, headers=admin_headers)
        assert res.status_code == 503

    def test_proxies_and_slims_giphy_results(self, client, admin_headers, monkeypatch):
        import config
        from routers import gifs as gifs_module
        monkeypatch.setattr(config, "GIPHY_API_KEY", "test-key")

        giphy_payload = {
            "data": [{
                "id": "abc123",
                "title": "Excited Cat",
                "images": {
                    "fixed_width": {"url": "https://media2.giphy.com/media/abc123/200w.gif", "width": "200", "height": "150"},
                    "original": {"url": "https://media2.giphy.com/media/abc123/giphy.gif", "width": "480", "height": "360"},
                },
            }]
        }

        class FakeResponse:
            status_code = 200
            def json(self):
                return giphy_payload

        class FakeClient:
            def __init__(self, *a, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def get(self, url, params=None):
                assert params["api_key"] == "test-key"
                assert params["q"] == "cat"
                return FakeResponse()

        monkeypatch.setattr(gifs_module.httpx, "AsyncClient", FakeClient)
        res = client.get("/api/gifs/search", params={"q": "cat"}, headers=admin_headers)
        assert res.status_code == 200
        gifs = res.json()["gifs"]
        assert gifs == [{
            "id": "abc123",
            "title": "Excited Cat",
            "preview": "https://media2.giphy.com/media/abc123/200w.gif",
            "url": "https://media2.giphy.com/media/abc123/giphy.gif",
            "width": 200,
            "height": 150,
        }]
