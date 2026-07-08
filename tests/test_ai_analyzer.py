"""Тести для MarketAIAnalyzer з мокнутим Groq API (без реальних мережевих запитів)."""

import json
import pytest
import requests
from unittest.mock import patch, MagicMock

from polymarket_ai.processing.ai_analyzer import MarketAIAnalyzer, AIAnalysisError

MARKET = {
    "title": "Will BTC hit $100k?",
    "end_date": "2025-12-31",
    "yes_price": 0.65,
    "no_price": 0.35,
}


def _mock_groq_response(payload: dict, status_code: int = 200):
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.text = json.dumps(payload)
    mock_response.json.return_value = {
        "choices": [{"message": {"content": json.dumps(payload)}}]
    }
    return mock_response


class TestGenerateTradingSignal:
    @patch("polymarket_ai.processing.ai_analyzer.requests.post")
    def test_buy_yes_signal(self, mock_post):
        mock_post.return_value = _mock_groq_response({
            "signal": "BUY_YES",
            "ai_probability_yes_pct": 75.0,
            "market_probability_yes_pct": 65.0,
            "potential_roi_pct": 15.4,
            "expected_value_pct": 8.2,
            "reasoning": "Strong bullish momentum",
        })

        analyzer = MarketAIAnalyzer(api_key="test_key")
        signal = analyzer.generate_trading_signal(MARKET)

        assert signal["signal"] == "BUY_YES"
        assert signal["potential_roi_pct"] == 15.4

    def test_settled_market_returns_none_without_api_call(self):
        analyzer = MarketAIAnalyzer(api_key="test_key")
        with patch("polymarket_ai.processing.ai_analyzer.requests.post") as mock_post:
            result = analyzer.generate_trading_signal({**MARKET, "yes_price": 0.99})
            assert result is None
            mock_post.assert_not_called()

    @patch("polymarket_ai.processing.ai_analyzer.requests.post")
    def test_unauthorized_raises_ai_analysis_error(self, mock_post):
        mock_post.return_value = _mock_groq_response({"error": "invalid key"}, status_code=401)
        analyzer = MarketAIAnalyzer(api_key="bad_key")
        with pytest.raises(AIAnalysisError, match="401"):
            analyzer.generate_trading_signal(MARKET)

    @patch("polymarket_ai.processing.ai_analyzer.requests.post")
    def test_rate_limited_raises_ai_analysis_error(self, mock_post):
        mock_post.return_value = _mock_groq_response({"error": "rate limited"}, status_code=429)
        analyzer = MarketAIAnalyzer(api_key="test_key")
        with pytest.raises(AIAnalysisError, match="429"):
            analyzer.generate_trading_signal(MARKET)

    @patch("polymarket_ai.processing.ai_analyzer.requests.post")
    def test_timeout_raises_ai_analysis_error(self, mock_post):
        mock_post.side_effect = requests.exceptions.Timeout()
        analyzer = MarketAIAnalyzer(api_key="test_key")
        with pytest.raises(AIAnalysisError, match="Таймаут"):
            analyzer.generate_trading_signal(MARKET)

    @patch("polymarket_ai.processing.ai_analyzer.requests.post")
    def test_malformed_json_raises_ai_analysis_error(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": [{"message": {"content": "not json"}}]}
        mock_post.return_value = mock_response

        analyzer = MarketAIAnalyzer(api_key="test_key")
        with pytest.raises(AIAnalysisError):
            analyzer.generate_trading_signal(MARKET)


class TestAnalyzeBatch:
    @patch("polymarket_ai.processing.ai_analyzer.requests.post")
    def test_filters_out_hold_signals(self, mock_post):
        responses = [
            _mock_groq_response({
                "signal": "HOLD", "ai_probability_yes_pct": 50.0,
                "market_probability_yes_pct": 50.0, "potential_roi_pct": 0.0,
                "expected_value_pct": 0.0, "reasoning": "fair price",
            }),
            _mock_groq_response({
                "signal": "BUY_NO", "ai_probability_yes_pct": 20.0,
                "market_probability_yes_pct": 50.0, "potential_roi_pct": 20.0,
                "expected_value_pct": 10.0, "reasoning": "overpriced YES",
            }),
        ]
        mock_post.side_effect = responses

        analyzer = MarketAIAnalyzer(api_key="test_key")
        markets = [dict(MARKET, title="Market A"), dict(MARKET, title="Market B")]
        results = analyzer.analyze_batch(markets)

        assert len(results) == 1
        assert results[0]["analysis"]["signal"] == "BUY_NO"
