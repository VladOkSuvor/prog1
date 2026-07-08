"""Валідація даних про ринки."""

from typing import Dict, List, Tuple, TypedDict

from ..utils.logger import get_logger
from ..config import (
    MIN_MARKET_TITLE_LENGTH,
    MAX_MARKET_TITLE_LENGTH,
    MIN_PRICE,
    MAX_PRICE,
    MAX_VOLUME,
)

logger = get_logger(__name__)


class ValidationResult(TypedDict):
    """Результат валідації партії ринків."""
    valid: List[Dict]
    invalid: List[Tuple[Dict, List[str]]]


class MarketValidator:
    """Валідатор для перевірки даних ринків."""
    
    @staticmethod
    def validate(market: Dict) -> Tuple[bool, List[str]]:
        """
        Валідувати ринок.
        
        Args:
            market: Дані ринку
            
        Returns:
            (is_valid, list_of_errors)
        """
        errors = []
        
        # Перевірити обов'язкові поля
        required_fields = ["id", "title", "status"]
        for field in required_fields:
            if not market.get(field):
                errors.append(f"Missing required field: {field}")
        
        # Перевірити title
        title = market.get("title", "")
        if title:
            if len(title) < MIN_MARKET_TITLE_LENGTH:
                errors.append(f"Title too short (min {MIN_MARKET_TITLE_LENGTH} chars)")
            elif len(title) > MAX_MARKET_TITLE_LENGTH:
                errors.append(f"Title too long (max {MAX_MARKET_TITLE_LENGTH} chars)")
        
        # Перевірити prices
        for price_field in ["yes_price", "no_price"]:
            if price_field in market:
                price = market[price_field]
                if not isinstance(price, (int, float)):
                    errors.append(f"{price_field} must be a number")
                elif not (MIN_PRICE <= price <= MAX_PRICE):
                    errors.append(f"{price_field} must be between {MIN_PRICE} and {MAX_PRICE}")
        
        # Перевірити volume
        volume = market.get("volume")
        if volume is not None:
            if not isinstance(volume, (int, float)):
                errors.append("volume must be a number")
            elif volume < 0:
                errors.append("volume cannot be negative")
            elif volume > MAX_VOLUME:
                errors.append(f"volume exceeds maximum ({MAX_VOLUME})")
        
        # Перевірити status
        valid_statuses = ["open", "closed", "resolved", "cancelled"]
        if market.get("status") not in valid_statuses:
            errors.append(f"status must be one of {valid_statuses}")
        
        return len(errors) == 0, errors
    
    @staticmethod
    def validate_batch(markets: List[Dict]) -> ValidationResult:
        """
        Валідувати партію ринків.
        
        Args:
            markets: Список ринків
            
        Returns:
            ValidationResult з ключами: valid (список валідних ринків), invalid (список кортежів (ринок, помилки))
        """
        valid = []
        invalid = []
        
        for market in markets:
            is_valid, errors = MarketValidator.validate(market)
            if is_valid:
                valid.append(market)
            else:
                invalid.append((market, errors))
        
        logger.debug(f"Validation: {len(valid)} valid, {len(invalid)} invalid")
        
        return {
            "valid": valid,
            "invalid": invalid,
        }
