"""Тести для MarketNormalizer."""

from polymarket_ai.processing.normalizer import MarketNormalizer


class TestMarketNormalizer:
    def test_normalize_single_valid_market(self):
        raw = {
            "id": "123",
            "title": "Will Bitcoin reach $100k?",
            "category": "finance",
            "yes_price": 0.65,
            "no_price": 0.35,
            "volume": 10000,
            "start_date": "2024-01-01T00:00:00Z",
            "end_date": "2024-12-31T23:59:59Z",
            "status": "open",
        }
        result = MarketNormalizer().normalize_single(raw)
        assert result["id"] == "123"
        assert result["yes_price"] == 0.65
        assert result["status"] == "open"

    def test_normalize_handles_missing_required_field(self):
        raw = {"title": "No ID"}
        result = MarketNormalizer().normalize_single(raw)
        assert result is None

    def test_normalize_handles_price_as_percentage(self):
        raw = {"id": "123", "title": "Test", "yes_price": 65, "status": "open"}
        result = MarketNormalizer().normalize_single(raw)
        assert result["yes_price"] == 0.65

    def test_normalize_maps_alternate_field_names(self):
        raw = {
            "market_id": "abc",
            "question": "Will it rain tomorrow?",
            "outcomePrices": "[0.3, 0.7]",
            "status": "active",
        }
        result = MarketNormalizer().normalize_single(raw)
        assert result["id"] == "abc"
        assert result["title"] == "Will it rain tomorrow?"
        assert result["yes_price"] == 0.3
        assert result["status"] == "open"  # "active" -> "open"

    def test_normalize_status_unknown_defaults_to_open(self):
        raw = {"id": "1", "title": "Test market", "status": "weird_status"}
        result = MarketNormalizer().normalize_single(raw)
        assert result["status"] == "open"

    def test_normalize_batch_skips_invalid_entries(self):
        raw_markets = [
            {"id": "1", "title": "Valid market", "status": "open"},
            {"title": "No ID"},
            {"id": "2", "title": "Another valid one", "status": "closed"},
        ]
        result = MarketNormalizer().normalize_batch(raw_markets)
        assert len(result) == 2
        assert {m["id"] for m in result} == {"1", "2"}

    def test_normalize_batch_skips_entry_that_raises(self):
        raw_markets = [
            {"id": "1", "title": "Valid market", "status": "open"},
            None,  # would raise inside normalize_single
        ]
        result = MarketNormalizer().normalize_batch(raw_markets)
        assert len(result) == 1
