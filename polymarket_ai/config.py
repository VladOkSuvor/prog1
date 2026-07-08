"""Configuration для Polymarket AI."""

import os
from enum import Enum

from dotenv import load_dotenv

load_dotenv()  # підхоплює .env з кореня проєкту (GROQ_API_KEY, POLYMARKET_API_URL, ...)

# API Configuration
API_BASE_URL = os.getenv("POLYMARKET_API_URL", "https://gamma-api.polymarket.com")
API_TIMEOUT = int(os.getenv("API_TIMEOUT", 30))   # збільшено: пагінація потребує більше часу
API_RETRIES = int(os.getenv("API_RETRIES", 5))    # збільшено: більше спроб при збоях мережі

# Logging Configuration
DEBUG_MODE = os.getenv("DEBUG_MODE", "true").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG" if DEBUG_MODE else "INFO")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
# LOG_JSON=true -> кожен лог-рядок серіалізується у JSON (timestamp/level/logger/message/...),
# зручно для збору логів у Docker/production; не вимагає зміни жодного виклику logger.debug(...).
LOG_JSON = os.getenv("LOG_JSON", "false").lower() == "true"

# Market Categories
class MarketCategory(str, Enum):
    POLITICS = "politics"
    SPORTS = "sports"
    TECHNOLOGY = "technology"
    FINANCE = "finance"
    SCIENCE = "science"
    ENTERTAINMENT = "entertainment"
    OTHER = "other"


# Market Status
class MarketStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"


# Validation Thresholds
MIN_MARKET_TITLE_LENGTH = 5
MAX_MARKET_TITLE_LENGTH = 500
MIN_PRICE = 0.0
MAX_PRICE = 1.0
MAX_VOLUME = 1_000_000_000

# AI Configuration
AI_PROBABILITY_MIN = 0.0
AI_PROBABILITY_MAX = 1.0
AI_CONFIDENCE_MIN = 0.0
AI_CONFIDENCE_MAX = 1.0
RISK_SCORE_MIN = 0
RISK_SCORE_MAX = 100
