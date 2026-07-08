"""Модуль для двонаправленого AI-аналізу ринків Polymarket."""

import json
import requests
from typing import Dict, Optional

from ..utils.logger import get_logger
from ..utils.exceptions import PolymarketAIError

logger = get_logger(__name__)


class AIAnalysisError(PolymarketAIError):
    """Помилка виклику AI API з людинозрозумілим поясненням причини."""


class MarketAIAnalyzer:
    """Аналізатор ринків, що використовує LLM та математичне очікування."""

    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        """
        Ініціалізація аналітика.

        Args:
            api_key: Ключ до Groq API
            model: Назва моделі
        """
        self.api_key = api_key
        self.model = model
        self.api_url = "https://api.groq.com/openai/v1/chat/completions"
        logger.debug(f"MarketAIAnalyzer initialized with model: {model}")

    def generate_trading_signal(self, market: Dict, context_news: str = "No recent news provided.") -> Optional[Dict]:
        """
        Формує промт, надсилає до LLM та повертає структурований сигнал.
        
        Args:
            market: Dict з даними ринку (title, end_date, yes_price, no_price)
            context_news: Контекст новин для аналізу
            
        Returns:
            Dict з сигналом торгівлі, або None якщо ринок вже фактично вирішений

        Raises:
            AIAnalysisError: якщо запит до Groq впав (auth/rate-limit/мережа/парсинг) —
                повідомлення вже сформульоване для показу користувачу.
        """
        title = market.get("title", "N/A")
        end_date = market.get("end_date", "N/A")
        
        try:
            yes_price = float(market.get("yes_price", 0.5))
            # Відсікаємо тільки технічно нульові позиції (ринок фактично вже вирішений).
            # Поріг знижено до 0.02/0.98: ринки з ціною 3-10% — це і є
            # найцікавіші нішеві/непопулярні події з великим потенційним ROI.
            if yes_price <= 0.02 or yes_price >= 0.98:
                logger.debug(f"Skipping settled market: {title} (price: {yes_price})")
                return None

            no_price = round(1.0 - yes_price, 2)
        except (ValueError, TypeError):
            logger.error(f"Invalid price data for market: {title}")
            return None

        # Формуємо наш релевантний промт
        system_prompt = (
            "Ти — професійний алгоритмічний трейдер та AI-аналітик, який спеціалізується на скальпінгу "
            "на prediction-ринках. Твоє завдання — оцінити ймовірність події, порівняти її з ціною ринку "
            "та розрахувати релевантне Математичне Очікування (EV) для обох напрямків (YES та NO).\n\n"
            "Формули для розрахунку у твоєму внутрішньому аналізі:\n"
            "1. ROI_YES = ((1.0 - price_YES) / price_YES) * 100%\n"
            "2. ROI_NO = ((1.0 - price_NO) / price_NO) * 100%\n"
            "3. EV_YES = (ai_prob_yes * ROI_YES) - ((1.0 - ai_prob_yes) * 100)\n"
            "4. EV_NO = (ai_prob_no * ROI_NO) - ((1.0 - ai_prob_no) * 100)\n\n"
            "Поверни результат СУВОРO у форматі JSON без зайвого тексту навколо:\n"
            "{\n"
            "  \"signal\": \"BUY_YES\" або \"BUY_NO\" або \"HOLD\",\n"
            "  \"ai_probability_yes_pct\": float,\n"
            "  \"market_probability_yes_pct\": float,\n"
            "  \"potential_roi_pct\": float,\n"
            "  \"expected_value_pct\": float,\n"
            "  \"reasoning\": \"коротке обґрунтування\"\n"
            "}"
        )

        user_content = (
            f"### ВХІДНІ ДАНІ ПОДІЇ:\n"
            f"- Назва події: {title}\n"
            f"- Дедлайн: {end_date}\n"
            f"- Ціна YES: {yes_price:.2f}$\n"
            f"- Ціна NO: {no_price:.2f}$\n"
            f"- Контекст/Новини: {context_news}\n\n"
            f"Знайди контракт з EV > +5%. Якщо ринок оцінений справедливо, став сигнал 'HOLD'."
        )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": self.model,
            "response_format": {"type": "json_object"},  # Гарантує чистий JSON на виході
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.2  # Низька температура для точніших розрахунків
        }

        logger.debug(f"Sending request to Groq API for market: {title[:50]}...")
        try:
            response = requests.post(self.api_url, headers=headers, json=data, timeout=15)
        except requests.exceptions.Timeout as e:
            logger.error("API request timeout")
            raise AIAnalysisError("Таймаут запиту до Groq (15с) — спробуй ще раз.") from e
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error calling Groq: {e}")
            raise AIAnalysisError(f"Мережева помилка запиту до Groq: {e}") from e

        if response.status_code != 200:
            logger.error(f"API Error: status code {response.status_code}: {response.text[:300]}")
            if response.status_code == 401:
                raise AIAnalysisError(
                    "Groq відхилив ключ (401 Unauthorized) — перевір ключ у Налаштуваннях "
                    "(⚙) або змінну GROQ_API_KEY на сервері. Ключ можна створити на "
                    "console.groq.com/keys."
                )
            if response.status_code == 429:
                raise AIAnalysisError(
                    "Groq: перевищено ліміт безкоштовного тіру (429 — RPM/RPD/TPM) — "
                    "спробуй трохи пізніше."
                )
            raise AIAnalysisError(
                f"Groq API повернув помилку {response.status_code}: {response.text[:300]}"
            )

        try:
            result_json = response.json()["choices"][0]["message"]["content"]
            analysis = json.loads(result_json)
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            logger.error(f"Failed to parse AI response: {e}")
            raise AIAnalysisError(f"Не вдалося розпарсити відповідь AI: {e}") from e

        logger.debug(f"AI analysis complete: signal={analysis.get('signal')}")
        return analysis

    def analyze_batch(self, markets: list, context_news: str = "") -> list:
        """
        Аналізувати партію ринків.
        
        Args:
            markets: Список ринків для аналізу
            context_news: Спільний контекст новин для всіх
            
        Returns:
            Список результатів аналізу (тільки з сигналами BUY)
        """
        results = []
        for idx, market in enumerate(markets):
            logger.debug(f"Analyzing market {idx + 1}/{len(markets)}: {market.get('title')[:50]}...")
            signal = self.generate_trading_signal(market, context_news)
            if signal and signal.get("signal") != "HOLD":
                results.append({
                    "market": market,
                    "analysis": signal
                })
        return results
