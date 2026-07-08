"""Нормалізація даних про ринки."""

from typing import List, Dict, Optional
from datetime import datetime

from ..utils.logger import get_logger

logger = get_logger(__name__)


class MarketNormalizer:
    """Нормалізатор для приведення ринків до стандартного формату."""
    
    # Маппінг можливих назв полів з різних API
    FIELD_MAPPINGS = {
        "id": ["id", "market_id", "uid"],
        "title": ["title", "question"],
        "category": ["category", "category_id"],
        "yes_price": ["yes_price", "buy_price", "odds_yes", "outcomePrices"],
        "no_price": ["no_price", "sell_price", "odds_no"],
        "volume": ["volume", "volume_24h", "total_volume", "volumeClob"],
        "start_date": ["start_date", "created_at", "start_time", "startDate"],
        "end_date": ["end_date", "resolve_date", "end_time", "endDate", "acceptingOrdersUntil", "closedTime"],
        "status": ["status", "state"],
    }
    
    STATUS_MAPPING = {
        "open": "open",
        "active": "open",
        "live": "open",
        "closed": "closed",
        "ended": "closed",
        "resolved": "resolved",
        "settled": "resolved",
        "cancelled": "cancelled",
        "canceled": "cancelled",
    }
    
    def normalize_batch(self, raw_markets: List[Dict]) -> List[Dict]:
        """
        Нормалізувати партію ринків.
        
        Args:
            raw_markets: Список сирих даних ринків
            
        Returns:
            Список нормалізованих ринків
        """
        normalized = []
        
        for market in raw_markets:
            try:
                normalized_market = self.normalize_single(market)
                if normalized_market:
                    normalized.append(normalized_market)
            except Exception as e:
                logger.debug(f"Failed to normalize market: {str(e)}")
                continue
        
        return normalized
    
    def normalize_single(self, market: Dict) -> Optional[Dict]:
        """
        Нормалізувати один ринок.
        
        Args:
            market: Сирі дані ринку
            
        Returns:
            Нормалізований ринок або None
        """
        try:
            normalized = {
                "id": self._get_field(market, self.FIELD_MAPPINGS["id"]),
                "title": self._get_field(market, self.FIELD_MAPPINGS["title"]),
                "category": self._get_field(market, self.FIELD_MAPPINGS["category"], default="other"),
                "yes_price": self._get_price(market, self.FIELD_MAPPINGS["yes_price"]),
                "no_price": self._get_price(market, self.FIELD_MAPPINGS["no_price"]),
                "volume": self._get_float(market, self.FIELD_MAPPINGS["volume"], default=0),
                "start_date": self._get_datetime(market, self.FIELD_MAPPINGS["start_date"]),
                "end_date": self._get_datetime(market, self.FIELD_MAPPINGS["end_date"]),
                "status": self._normalize_status(self._get_field(market, self.FIELD_MAPPINGS["status"], default="open")),
                "ai_probability": None,
                "ai_confidence": None,
                "risk_score": None,
                "expected_value": None,
            }
            
            # Валідація обов'язкових полів
            if not all([normalized["id"], normalized["title"], normalized["status"]]):
                logger.debug(f"Missing required fields in market: {market.get('id', 'unknown')}")
                return None
            
            return normalized
            
        except Exception as e:
            logger.debug(f"Error normalizing market: {str(e)}")
            return None
    
    def _get_field(self, obj: Dict, keys: List[str], default: Optional[str] = None) -> Optional[str]:
        """Отримати поле з об'єкта, намагаючись різні назви ключів."""
        for key in keys:
            if key in obj and obj[key] is not None:
                return str(obj[key]).strip()
        return default
    
    def _get_price(self, obj: Dict, keys: List[str]) -> float:
        """Отримати ціну як float (0-1)."""
        for key in keys:
            if key in obj and obj[key] is not None:
                try:
                    value = obj[key]
                    
                    # Спеціальна обробка для outcomePrices (масив JSON як строка)
                    if key == "outcomePrices" and isinstance(value, str):
                        import json
                        prices = json.loads(value)
                        if isinstance(prices, list) and len(prices) > 0:
                            value = float(prices[0])  # Беремо першу ціну (YES)
                        else:
                            continue
                    
                    price = float(value)
                    # Нормалізувати якщо це відсоток (0-100)
                    if price > 1:
                        price = price / 100
                    return max(0, min(1, price))
                except (ValueError, TypeError, json.JSONDecodeError):
                    continue
        return 0.5
    
    def _get_float(self, obj: Dict, keys: List[str], default: float = 0) -> float:
        """Отримати float значення."""
        for key in keys:
            if key in obj and obj[key] is not None:
                try:
                    return float(obj[key])
                except (ValueError, TypeError):
                    continue
        return default
    
    def _get_datetime(self, obj: Dict, keys: List[str]) -> Optional[str]:
        """Отримати datetime як ISO 8601 строку."""
        for key in keys:
            if key in obj and obj[key] is not None:
                try:
                    if isinstance(obj[key], str):
                        dt = datetime.fromisoformat(obj[key].replace('Z', '+00:00'))
                    elif isinstance(obj[key], (int, float)):
                        dt = datetime.fromtimestamp(obj[key])
                    else:
                        continue
                    return dt.isoformat()
                except (ValueError, TypeError):
                    continue
        return None
    
    def _normalize_status(self, status: str) -> str:
        """Нормалізувати статус ринку."""
        normalized = status.lower().strip()
        return self.STATUS_MAPPING.get(normalized, "open")
