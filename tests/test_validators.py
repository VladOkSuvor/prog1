"""Тести для MarketValidator."""

from polymarket_ai.processing.validators import MarketValidator


class TestMarketValidator:
    def _valid_market(self, **overrides):
        market = {
            "id": "123",
            "title": "Will Bitcoin reach $100k by 2026?",
            "status": "open",
            "yes_price": 0.65,
            "no_price": 0.35,
            "volume": 1000,
        }
        market.update(overrides)
        return market

    def test_valid_market_passes(self):
        is_valid, errors = MarketValidator.validate(self._valid_market())
        assert is_valid
        assert errors == []

    def test_missing_required_field(self):
        market = self._valid_market()
        del market["title"]
        is_valid, errors = MarketValidator.validate(market)
        assert not is_valid
        assert any("title" in e for e in errors)

    def test_title_too_short(self):
        is_valid, errors = MarketValidator.validate(self._valid_market(title="Hi"))
        assert not is_valid
        assert any("too short" in e for e in errors)

    def test_price_out_of_range(self):
        is_valid, errors = MarketValidator.validate(self._valid_market(yes_price=1.5))
        assert not is_valid
        assert any("yes_price" in e for e in errors)

    def test_negative_volume(self):
        is_valid, errors = MarketValidator.validate(self._valid_market(volume=-5))
        assert not is_valid
        assert any("negative" in e for e in errors)

    def test_invalid_status(self):
        is_valid, errors = MarketValidator.validate(self._valid_market(status="weird"))
        assert not is_valid
        assert any("status" in e for e in errors)

    def test_validate_batch_splits_valid_and_invalid(self):
        markets = [self._valid_market(id="1"), self._valid_market(id="2", status="bogus")]
        result = MarketValidator.validate_batch(markets)
        assert len(result["valid"]) == 1
        assert len(result["invalid"]) == 1
        assert result["valid"][0]["id"] == "1"
