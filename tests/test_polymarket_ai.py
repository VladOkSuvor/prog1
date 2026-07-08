"""Тести для класу PolymarketAI (пагінація/дедуплікація), фетчер мокнутий."""

from unittest.mock import patch

from polymarket_ai.main import PolymarketAI

MARKET_OPEN = {"id": "1", "title": "Test market", "status": "open"}


class TestFetchAndValidateMarkets:
    def test_valid_and_invalid_split(self):
        pm = PolymarketAI()
        raw = [MARKET_OPEN, {"title": "no id or status"}]
        with patch.object(pm.fetcher, "fetch_markets", return_value=raw):
            result = pm.fetch_and_validate_markets()
        assert result["stats"]["total"] == 2
        assert result["stats"]["valid"] == 1
        assert result["stats"]["invalid"] == 1

    def test_none_from_fetcher_returns_none(self):
        pm = PolymarketAI()
        with patch.object(pm.fetcher, "fetch_markets", return_value=None):
            result = pm.fetch_and_validate_markets()
        assert result is None

    def test_get_valid_markets_returns_empty_list_on_failure(self):
        pm = PolymarketAI()
        with patch.object(pm.fetcher, "fetch_markets", return_value=None):
            result = pm.get_valid_markets()
        assert result == []


class TestFetchAllMarketsPaginated:
    def test_stops_when_batch_smaller_than_page_size(self):
        pm = PolymarketAI()
        full_page = [{"id": str(i), "title": f"Market {i}", "status": "open"} for i in range(PolymarketAI.PAGE_SIZE)]
        last_page = [{"id": "last", "title": "Last market", "status": "open"}]

        with patch.object(pm.fetcher, "fetch_markets", side_effect=[full_page, last_page]) as mock_fetch:
            result = pm.fetch_all_markets_paginated(max_total=10_000)

        assert mock_fetch.call_count == 2
        assert result["stats"]["total"] == PolymarketAI.PAGE_SIZE + 1

    def test_dedups_by_id_across_pages(self):
        pm = PolymarketAI()
        page1 = [{"id": "1", "title": "A", "status": "open"}] * PolymarketAI.PAGE_SIZE
        page2 = [{"id": "1", "title": "A", "status": "open"}]  # дублікат -> має бути відкинутий

        with patch.object(pm.fetcher, "fetch_markets", side_effect=[page1, page2]):
            result = pm.fetch_all_markets_paginated(max_total=10_000)

        assert result["stats"]["total"] == 1

    def test_empty_first_batch_returns_none(self):
        pm = PolymarketAI()
        with patch.object(pm.fetcher, "fetch_markets", return_value=None):
            result = pm.fetch_all_markets_paginated()
        assert result is None


class TestFetchAllEventsPaginated:
    def test_stops_when_no_next_cursor(self):
        pm = PolymarketAI()
        batch = [{"id": "1", "title": "Event market", "status": "open"}]
        with patch.object(pm.fetcher, "fetch_events_as_markets", return_value=(batch, 1, None)) as mock_fetch:
            result = pm.fetch_all_events_paginated(max_total=10_000)

        assert mock_fetch.call_count == 1
        assert result["stats"]["total"] == 1

    def test_follows_cursor_across_pages(self):
        pm = PolymarketAI()
        page1 = ([{"id": "1", "title": "A", "status": "open"}], 1, "cursor-2")
        page2 = ([{"id": "2", "title": "B", "status": "open"}], 1, None)

        with patch.object(pm.fetcher, "fetch_events_as_markets", side_effect=[page1, page2]) as mock_fetch:
            result = pm.fetch_all_events_paginated(max_total=10_000)

        assert mock_fetch.call_count == 2
        assert result["stats"]["total"] == 2

    def test_empty_result_returns_none(self):
        pm = PolymarketAI()
        with patch.object(pm.fetcher, "fetch_events_as_markets", return_value=None):
            result = pm.fetch_all_events_paginated()
        assert result is None
