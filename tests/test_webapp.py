"""Smoke-тести Flask-роутів webapp/app.py (кеш ринків і файли підмінені фікстурою)."""

import json

from tests.conftest import SAMPLE_MARKETS


class TestHealth:
    def test_health_ok(self, webapp_client):
        resp = webapp_client.get("/api/health")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"


class TestListMarkets:
    def test_returns_cached_markets(self, webapp_client):
        resp = webapp_client.get("/api/markets")
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["total"] == len(SAMPLE_MARKETS)

    def test_search_filter(self, webapp_client):
        resp = webapp_client.get("/api/markets?q=bitcoin")
        data = resp.get_json()
        assert data["total"] == 1
        assert data["markets"][0]["id"] == "1"

    def test_category_filter(self, webapp_client):
        resp = webapp_client.get("/api/markets?category=politics")
        data = resp.get_json()
        assert data["total"] == 1
        assert data["markets"][0]["id"] == "2"

    def test_min_volume_filter(self, webapp_client):
        resp = webapp_client.get("/api/markets?min_volume=10000")
        data = resp.get_json()
        assert data["total"] == 1
        assert data["markets"][0]["id"] == "1"

    def test_market_detail_not_found(self, webapp_client):
        resp = webapp_client.get("/api/markets/does-not-exist")
        assert resp.status_code == 404


class TestWatchlist:
    def test_add_and_list_and_remove(self, webapp_client):
        add_resp = webapp_client.post("/api/watchlist/1")
        assert add_resp.status_code == 200
        assert add_resp.get_json()["watchlist_size"] == 1

        list_resp = webapp_client.get("/api/watchlist")
        data = list_resp.get_json()
        assert len(data["markets"]) == 1
        assert data["markets"][0]["id"] == "1"

        remove_resp = webapp_client.delete("/api/watchlist/1")
        assert remove_resp.get_json()["watchlist_size"] == 0

    def test_market_list_reflects_watchlisted_flag(self, webapp_client):
        webapp_client.post("/api/watchlist/1")
        resp = webapp_client.get("/api/markets")
        markets_by_id = {m["id"]: m for m in resp.get_json()["markets"]}
        assert markets_by_id["1"]["watchlisted"] is True
        assert markets_by_id["2"]["watchlisted"] is False


class TestAnalyzeWithoutApiKey:
    def test_returns_400_without_groq_key(self, webapp_client, monkeypatch):
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        resp = webapp_client.post("/api/markets/1/analyze")
        assert resp.status_code == 400
        assert "GROQ_API_KEY" in resp.get_json()["error"]

    def test_returns_404_for_unknown_market(self, webapp_client):
        resp = webapp_client.post("/api/markets/does-not-exist/analyze")
        assert resp.status_code == 404


class TestScan:
    def test_empty_market_ids_returns_400(self, webapp_client, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test_key")
        resp = webapp_client.post(
            "/api/scan", data=json.dumps({"market_ids": []}), content_type="application/json"
        )
        assert resp.status_code == 400

    def test_missing_api_key_returns_400(self, webapp_client, monkeypatch):
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        resp = webapp_client.post(
            "/api/scan", data=json.dumps({"market_ids": ["1"]}), content_type="application/json"
        )
        assert resp.status_code == 400


class TestTranslate:
    def test_empty_market_ids_returns_400(self, webapp_client):
        resp = webapp_client.post(
            "/api/translate", data=json.dumps({"market_ids": []}), content_type="application/json"
        )
        assert resp.status_code == 400

    def test_missing_api_key_returns_400(self, webapp_client, monkeypatch):
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        resp = webapp_client.post(
            "/api/translate", data=json.dumps({"market_ids": ["1"]}), content_type="application/json"
        )
        assert resp.status_code == 400

    def test_unknown_market_id_returns_empty_translations(self, webapp_client):
        resp = webapp_client.post(
            "/api/translate", data=json.dumps({"market_ids": ["does-not-exist"]}), content_type="application/json"
        )
        assert resp.status_code == 200
        assert resp.get_json()["translations"] == {}


class TestUnknownRoute:
    def test_404_for_unknown_api_route(self, webapp_client):
        resp = webapp_client.get("/api/totally-not-a-route")
        assert resp.status_code == 404
