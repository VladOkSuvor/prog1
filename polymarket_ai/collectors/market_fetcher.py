"""Market fetcher для збирання даних про ринки."""

from typing import List, Dict, Optional

from .api_client import APIClient
from ..processing.normalizer import MarketNormalizer
from ..utils.logger import get_logger
from ..config import API_BASE_URL

logger = get_logger(__name__)


class MarketFetcher:
    """Фетчер для збирання ринків з API."""
    
    def __init__(self, api_base_url: str = API_BASE_URL):
        """
        Ініціалізація fetcher.
        
        Args:
            api_base_url: Базовий URL API
        """
        self.api_client = APIClient(api_base_url)
        self.normalizer = MarketNormalizer()
    
    def fetch_markets(self, endpoint: str = "/markets") -> Optional[List[Dict]]:
        """
        Отримати список ринків.
        
        Args:
            endpoint: API endpoint для ринків
            
        Returns:
            Список нормалізованих ринків або None
        """
        logger.debug(f"Fetching markets from {endpoint}")
        
        raw_data = self.api_client.get(endpoint)
        if raw_data is None:
            logger.error("Failed to fetch markets from API")
            return None
        
        # Обробити різні формати відповіді
        if isinstance(raw_data, list):
            raw_markets = raw_data
        elif isinstance(raw_data, dict):
            raw_markets = raw_data.get("markets", [])
        else:
            logger.error(f"Unexpected response format: {type(raw_data)}")
            return None
        
        logger.debug(f"Received {len(raw_markets)} markets from API")
        
        # Нормалізувати ринки
        normalized_markets = self.normalizer.normalize_batch(raw_markets)
        logger.debug(f"Normalized {len(normalized_markets)} markets")
        
        return normalized_markets
    
    def fetch_events_as_markets(self, endpoint: str = "/events") -> Optional[tuple]:
        """
        Отримати ринки через endpoint /events або /events/keyset.

        Повертає кортеж (normalized_markets, event_count, next_cursor) де:
          - event_count — кількість event-об'єктів на сторінці (для коректного
            визначення останньої сторінки при offset-пагінації);
          - next_cursor — курсор для keyset-пагінації (/events/keyset), або
            None, якщо відповідь його не містить (напр. звичайний /events)
            чи це остання сторінка.

        Дата події (endDate/end_date) з батьківського event-об'єкту
        копіюється в кожен дочірній market, якщо там її нема —
        інакше markets втрачають дату і відсіюються пізніше.
        """
        logger.debug(f"Fetching events from {endpoint}")

        raw_data = self.api_client.get(endpoint)
        if raw_data is None:
            logger.error("Failed to fetch events from API")
            return None

        if isinstance(raw_data, list):
            events = raw_data
            next_cursor = None
        elif isinstance(raw_data, dict):
            events = raw_data.get("events", [])
            next_cursor = raw_data.get("next_cursor")
        else:
            logger.error(f"Unexpected events response format: {type(raw_data)}")
            return None

        event_count = len(events)

        # Поля дати що можуть бути на рівні event, але не на рівні market
        EVENT_DATE_FIELDS = ("endDate", "end_date", "startDate", "start_date",
                             "closedTime", "acceptingOrdersUntil")

        raw_markets: List[Dict] = []
        for event in events:
            inner = event.get("markets", [])
            if isinstance(inner, list) and inner:
                for market in inner:
                    # Копіюємо дату з батьківського event якщо в market її немає
                    enriched = dict(market)
                    for field in EVENT_DATE_FIELDS:
                        if not enriched.get(field) and event.get(field):
                            enriched[field] = event[field]
                    raw_markets.append(enriched)
            elif event.get("id") and event.get("title"):
                # Сама подія без вкладених markets — додаємо як ринок
                raw_markets.append(event)

        logger.debug(f"Extracted {len(raw_markets)} markets from {event_count} events")

        normalized_markets = self.normalizer.normalize_batch(raw_markets)
        logger.debug(f"Normalized {len(normalized_markets)} event-markets")
        return normalized_markets, event_count, next_cursor

    def fetch_market_by_id(self, market_id: str) -> Optional[Dict]:
        """
        Отримати конкретний ринок за ID.
        
        Args:
            market_id: ID ринку
            
        Returns:
            Нормалізований ринок або None
        """
        logger.debug(f"Fetching market {market_id}")
        
        raw_market = self.api_client.get(f"/markets/{market_id}")
        if raw_market is None:
            logger.error(f"Failed to fetch market {market_id}")
            return None
        
        normalized_market = self.normalizer.normalize_single(raw_market)
        return normalized_market
    
    def close(self):
        """Закрити ресурси."""
        self.api_client.close()
    
    def __enter__(self):
        """Context manager enter."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
