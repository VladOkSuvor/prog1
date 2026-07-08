"""Тести для моделі Market."""

import json

from polymarket_ai.models.market import Market


def _make_market(**overrides):
    defaults = dict(
        market_id="123",
        title="Will Bitcoin reach $100k?",
        category="finance",
        yes_price=0.65,
        no_price=0.35,
        volume=10000.0,
        start_date="2024-01-01T00:00:00Z",
        end_date="2024-12-31T23:59:59Z",
        status="open",
    )
    defaults.update(overrides)
    return Market(**defaults)


class TestMarket:
    def test_to_dict_contains_all_fields(self):
        market = _make_market()
        d = market.to_dict()
        assert d["id"] == "123"
        assert d["yes_price"] == 0.65
        assert d["ai_probability"] is None

    def test_to_json_roundtrip(self):
        market = _make_market()
        parsed = json.loads(market.to_json())
        assert parsed["id"] == "123"
        assert parsed["title"] == "Will Bitcoin reach $100k?"

    def test_from_dict_reconstructs_market(self):
        market = _make_market()
        rebuilt = Market.from_dict(market.to_dict())
        assert rebuilt.id == market.id
        assert rebuilt.yes_price == market.yes_price

    def test_optional_ai_fields_default_to_none(self):
        market = _make_market()
        assert market.ai_probability is None
        assert market.ai_confidence is None
        assert market.risk_score is None
        assert market.expected_value is None

    def test_repr_truncates_title(self):
        market = _make_market(title="A" * 100)
        assert len(repr(market)) < 150
