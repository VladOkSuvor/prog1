"""Тести для MarketTranslator з мокнутим Groq API (без реальних мережевих запитів)."""

import json
import pytest
import requests
from unittest.mock import patch, MagicMock

from polymarket_ai.processing.translator import MarketTranslator, TranslationError


def _mock_groq_response(translations, status_code: int = 200):
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.text = json.dumps({"translations": translations})
    mock_response.json.return_value = {
        "choices": [{"message": {"content": json.dumps({"translations": translations})}}]
    }
    return mock_response


class TestTranslateBatch:
    def test_empty_input_returns_empty_without_api_call(self):
        translator = MarketTranslator(api_key="test_key")
        with patch("polymarket_ai.processing.translator.requests.post") as mock_post:
            assert translator.translate_batch([]) == []
            mock_post.assert_not_called()

    @patch("polymarket_ai.processing.translator.requests.post")
    def test_translates_titles_in_order(self, mock_post):
        mock_post.return_value = _mock_groq_response(["Чи досягне Bitcoin $100k?", "Хто виграє вибори?"])
        translator = MarketTranslator(api_key="test_key")

        result = translator.translate_batch(["Will Bitcoin hit $100k?", "Who will win the election?"])

        assert result == ["Чи досягне Bitcoin $100k?", "Хто виграє вибори?"]

    @patch("polymarket_ai.processing.translator.requests.post")
    def test_count_mismatch_raises_translation_error(self, mock_post):
        mock_post.return_value = _mock_groq_response(["тільки один переклад"])
        translator = MarketTranslator(api_key="test_key")

        with pytest.raises(TranslationError, match="кількість"):
            translator.translate_batch(["Title A", "Title B"])

    @patch("polymarket_ai.processing.translator.requests.post")
    def test_unauthorized_raises_translation_error(self, mock_post):
        mock_post.return_value = _mock_groq_response([], status_code=401)
        translator = MarketTranslator(api_key="bad_key")

        with pytest.raises(TranslationError, match="401"):
            translator.translate_batch(["Title A"])

    @patch("polymarket_ai.processing.translator.requests.post")
    def test_network_error_raises_translation_error(self, mock_post):
        mock_post.side_effect = requests.exceptions.ConnectionError()
        translator = MarketTranslator(api_key="test_key")

        with pytest.raises(TranslationError, match="Мережева"):
            translator.translate_batch(["Title A"])
