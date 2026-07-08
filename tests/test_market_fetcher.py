"""Тести для MarketFetcher (з мокнутим APIClient.get, без мережі)."""

from unittest.mock import patch

from polymarket_ai.collectors.market_fetcher import MarketFetcher

RAW_MARKET = {"id": "1", "title": "Will it happen?", "status": "open"}


class TestFetchMarkets:
    def test_list_response_is_normalized(self):
        fetcher = MarketFetcher("https://example.com")
        with patch.object(fetcher.api_client, "get", return_value=[RAW_MARKET]):
            result = fetcher.fetch_markets()
        assert len(result) == 1
        assert result[0]["id"] == "1"

    def test_dict_response_with_markets_key(self):
        fetcher = MarketFetcher("https://example.com")
        with patch.object(fetcher.api_client, "get", return_value={"markets": [RAW_MARKET]}):
            result = fetcher.fetch_markets()
        assert len(result) == 1

    def test_none_response_returns_none(self):
        fetcher = MarketFetcher("https://example.com")
        with patch.object(fetcher.api_client, "get", return_value=None):
            result = fetcher.fetch_markets()
        assert result is None

    def test_unexpected_response_type_returns_none(self):
        fetcher = MarketFetcher("https://example.com")
        with patch.object(fetcher.api_client, "get", return_value="not a dict or list"):
            result = fetcher.fetch_markets()
        assert result is None


class TestFetchEventsAsMarkets:
    def test_extracts_nested_markets_and_copies_end_date(self):
        event = {
            "id": "evt1",
            "title": "Event",
            "endDate": "2026-01-01T00:00:00Z",
            "markets": [{"id": "m1", "title": "Sub market", "status": "open"}],
        }
        fetcher = MarketFetcher("https://example.com")
        with patch.object(fetcher.api_client, "get", return_value={"events": [event], "next_cursor": "abc"}):
            result = fetcher.fetch_events_as_markets()

        markets, event_count, next_cursor = result
        assert event_count == 1
        assert next_cursor == "abc"
        assert len(markets) == 1
        assert markets[0]["id"] == "m1"
        assert markets[0]["end_date"] is not None

    def test_event_without_nested_markets_used_as_market(self):
        event = {"id": "evt2", "title": "Standalone event", "status": "open"}
        fetcher = MarketFetcher("https://example.com")
        with patch.object(fetcher.api_client, "get", return_value={"events": [event]}):
            markets, event_count, next_cursor = fetcher.fetch_events_as_markets()

        assert event_count == 1
        assert next_cursor is None
        assert len(markets) == 1
        assert markets[0]["id"] == "evt2"

    def test_none_response_returns_none(self):
        fetcher = MarketFetcher("https://example.com")
        with patch.object(fetcher.api_client, "get", return_value=None):
            result = fetcher.fetch_events_as_markets()
        assert result is None


class TestFetchMarketById:
    def test_returns_normalized_market(self):
        fetcher = MarketFetcher("https://example.com")
        with patch.object(fetcher.api_client, "get", return_value=RAW_MARKET):
            result = fetcher.fetch_market_by_id("1")
        assert result["id"] == "1"

    def test_returns_none_when_not_found(self):
        fetcher = MarketFetcher("https://example.com")
        with patch.object(fetcher.api_client, "get", return_value=None):
            result = fetcher.fetch_market_by_id("missing")
        assert result is None


class TestContextManager:
    def test_close_closes_api_client(self):
        with patch.object(MarketFetcher, "close") as mock_close:
            with MarketFetcher("https://example.com"):
                pass
            mock_close.assert_called_once()
