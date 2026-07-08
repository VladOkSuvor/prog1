"""API client для prediction markets."""

import random
import time
import requests
from typing import Optional, Dict, Any

from ..utils.logger import get_logger
from ..config import API_TIMEOUT, API_RETRIES

logger = get_logger(__name__)

BACKOFF_BASE_DELAY = 0.5   # секунд, перед 1-м повтором
BACKOFF_MAX_DELAY = 10.0   # стеля затримки між спробами


class APIClient:
    """Клієнт для роботи з API prediction markets."""

    def __init__(self, base_url: str, timeout: int = API_TIMEOUT, retries: int = API_RETRIES):
        """
        Ініціалізація API клієнта.

        Args:
            base_url: Базовий URL API
            timeout: Timeout запиту в секундах
            retries: Кількість спроб повторного запиту
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()

    def _backoff_sleep(self, attempt: int) -> None:
        """Експоненційна затримка з джиттером перед наступною спробою."""
        delay = min(BACKOFF_BASE_DELAY * (2 ** attempt), BACKOFF_MAX_DELAY)
        time.sleep(delay * (0.5 + random.random() / 2))  # ±50% джиттер

    def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        GET запит до API. Мережеві збої (timeout/connection) повторюються
        з експоненційною затримкою; HTTP/парсинг помилки — ні (немає сенсу
        повторювати запит, що впав на 4xx чи побитому JSON).

        Args:
            endpoint: API endpoint (з '/')
            params: Query параметри

        Returns:
            Відповідь JSON або None у випадку помилки
        """
        url = f"{self.base_url}{endpoint}"

        for attempt in range(self.retries):
            try:
                logger.debug(f"GET {url} (attempt {attempt + 1}/{self.retries})")
                response = self.session.get(url, params=params, timeout=self.timeout)
                response.raise_for_status()

                logger.debug(f"Response status: {response.status_code}")
                return response.json()

            except requests.exceptions.Timeout:
                logger.warning(f"Timeout при запиті до {url}")
                if attempt == self.retries - 1:
                    logger.error(f"Failed after {self.retries} retries")
                    return None
                self._backoff_sleep(attempt)

            except requests.exceptions.ConnectionError:
                logger.warning(f"Connection error до {url}")
                if attempt == self.retries - 1:
                    logger.error(f"Connection failed after {self.retries} retries")
                    return None
                self._backoff_sleep(attempt)

            except requests.exceptions.HTTPError as e:
                logger.error(f"HTTP error {e.response.status_code}: {e}")
                return None

            except requests.exceptions.RequestException as e:
                logger.error(f"Request error: {str(e)}")
                return None

            except ValueError:
                logger.error("Invalid JSON response from API")
                return None

        return None
    
    def close(self):
        """Закрити сесію."""
        self.session.close()
    
    def __enter__(self):
        """Context manager enter."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
