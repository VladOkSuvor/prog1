"""Market data model та JSON schema."""

from typing import Optional, Dict, Any
from datetime import datetime
import json

# JSON Schema для Market
MARKET_JSON_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "Prediction Market Object",
    "type": "object",
    "required": [
        "id",
        "title",
        "category",
        "yes_price",
        "no_price",
        "volume",
        "start_date",
        "end_date",
        "status"
    ],
    "properties": {
        "id": {
            "type": "string",
            "description": "Унікальний ідентифікатор ринку",
            "pattern": "^[a-zA-Z0-9-]+$"
        },
        "title": {
            "type": "string",
            "description": "Назва питання ринку",
            "minLength": 5,
            "maxLength": 500
        },
        "category": {
            "type": "string",
            "description": "Категорія ринку",
            "enum": ["politics", "sports", "technology", "finance", "science", "entertainment", "other"]
        },
        "yes_price": {
            "type": "number",
            "description": "Ціна контракту YES (0-1)",
            "minimum": 0,
            "maximum": 1
        },
        "no_price": {
            "type": "number",
            "description": "Ціна контракту NO (0-1)",
            "minimum": 0,
            "maximum": 1
        },
        "volume": {
            "type": "number",
            "description": "Обсяг торгівлі (у USD)",
            "minimum": 0
        },
        "start_date": {
            "type": "string",
            "format": "date-time",
            "description": "Дата початку ринку (ISO 8601)"
        },
        "end_date": {
            "type": "string",
            "format": "date-time",
            "description": "Дата завершення ринку (ISO 8601)"
        },
        "status": {
            "type": "string",
            "description": "Статус ринку",
            "enum": ["open", "closed", "resolved", "cancelled"]
        },
        "ai_probability": {
            "type": ["number", "null"],
            "description": "AI прогноз ймовірності YES (0-1)",
            "minimum": 0,
            "maximum": 1
        },
        "ai_confidence": {
            "type": ["number", "null"],
            "description": "Впевненість AI у прогнозі (0-1)",
            "minimum": 0,
            "maximum": 1
        },
        "risk_score": {
            "type": ["number", "null"],
            "description": "Оцінка ризику позиції (0-100)",
            "minimum": 0,
            "maximum": 100
        },
        "expected_value": {
            "type": ["number", "null"],
            "description": "Очікувана вартість позиції (у USD)"
        }
    }
}


class Market:
    """Модель для представлення prediction market."""
    
    def __init__(
        self,
        market_id: str,
        title: str,
        category: str,
        yes_price: float,
        no_price: float,
        volume: float,
        start_date: str,
        end_date: str,
        status: str,
        ai_probability: Optional[float] = None,
        ai_confidence: Optional[float] = None,
        risk_score: Optional[float] = None,
        expected_value: Optional[float] = None,
    ):
        """Ініціалізація Market."""
        self.id = market_id
        self.title = title
        self.category = category
        self.yes_price = yes_price
        self.no_price = no_price
        self.volume = volume
        self.start_date = start_date
        self.end_date = end_date
        self.status = status
        self.ai_probability = ai_probability
        self.ai_confidence = ai_confidence
        self.risk_score = risk_score
        self.expected_value = expected_value
    
    def to_dict(self) -> Dict[str, Any]:
        """Перетворити об'єкт у dict."""
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "yes_price": self.yes_price,
            "no_price": self.no_price,
            "volume": self.volume,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "status": self.status,
            "ai_probability": self.ai_probability,
            "ai_confidence": self.ai_confidence,
            "risk_score": self.risk_score,
            "expected_value": self.expected_value,
        }
    
    def to_json(self) -> str:
        """Перетворити об'єкт у JSON."""
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Market":
        """Створити Market з dict (ключ "id" з to_dict() -> параметр market_id)."""
        data = dict(data)
        data["market_id"] = data.pop("id")
        return cls(**data)
    
    def __repr__(self) -> str:
        return f"Market(id={self.id}, title={self.title[:30]}..., status={self.status})"
