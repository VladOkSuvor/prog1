"""Спільні фікстури для тестів webapp."""

import time

import pytest

from polymarket_ai.webapp import app as app_module

SAMPLE_MARKETS = [
    {
        "id": "1",
        "title": "Will Bitcoin reach $100k?",
        "category": "finance",
        "yes_price": 0.65,
        "no_price": 0.35,
        "volume": 50000.0,
        "start_date": "2026-01-01T00:00:00+00:00",
        "end_date": "2026-12-31T23:59:59+00:00",
        "status": "open",
        "ai_probability": None,
        "ai_confidence": None,
        "risk_score": None,
        "expected_value": None,
    },
    {
        "id": "2",
        "title": "Who wins the election?",
        "category": "politics",
        "yes_price": 0.5,
        "no_price": 0.5,
        "volume": 1000.0,
        "start_date": "2026-01-01T00:00:00+00:00",
        "end_date": "2026-08-01T00:00:00+00:00",
        "status": "open",
        "ai_probability": None,
        "ai_confidence": None,
        "risk_score": None,
        "expected_value": None,
    },
]


@pytest.fixture
def webapp_client(tmp_path, monkeypatch):
    """Flask test client з ізольованими watchlist/translations файлами та фейковим кешем ринків."""
    monkeypatch.setattr(app_module, "WATCHLIST_FILE", str(tmp_path / "watchlist.json"))
    monkeypatch.setattr(app_module, "TRANSLATIONS_FILE", str(tmp_path / "translations.json"))
    monkeypatch.setattr(
        app_module, "_cache", {"markets": list(SAMPLE_MARKETS), "fetched_at": time.time(), "fetching": False}
    )
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as client:
        yield client
