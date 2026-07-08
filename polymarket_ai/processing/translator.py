"""Переклад заголовків ринків Polymarket на українську мову через Groq LLM."""

import json
import requests
from typing import List

from ..utils.logger import get_logger
from ..utils.exceptions import PolymarketAIError

logger = get_logger(__name__)


class TranslationError(PolymarketAIError):
    """Помилка виклику Groq API під час перекладу з людинозрозумілим поясненням причини."""


class MarketTranslator:
    """Перекладає заголовки ринків (англ.) на українську одним батч-запитом до Groq."""

    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        self.api_key = api_key
        self.model = model
        self.api_url = "https://api.groq.com/openai/v1/chat/completions"

    def translate_batch(self, titles: List[str]) -> List[str]:
        """
        Перекладає список заголовків на українську, зберігаючи порядок і довжину списку.

        Args:
            titles: Оригінальні (англомовні) заголовки ринків

        Returns:
            Список перекладів у тій самій кількості та порядку, що й titles

        Raises:
            TranslationError: якщо запит до Groq впав (auth/rate-limit/мережа/парсинг)
        """
        if not titles:
            return []

        system_prompt = (
            "Ти — професійний перекладач фінансових новин. Переклади заголовки "
            "prediction-market подій з англійської на українську: природно, коротко, "
            "без дослівщини. Власні назви (імена людей, назви команд, компаній, "
            "тікери) залишай як є або транслітеруй за загальновживаною нормою.\n\n"
            "Поверни результат СУВОРО у форматі JSON без зайвого тексту навколо:\n"
            '{"translations": ["переклад 1", "переклад 2", ...]}\n\n'
            "Масив translations має містити РІВНО стільки елементів, скільки заголовків "
            "надано, у тому самому порядку."
        )

        user_content = "Заголовки для перекладу:\n" + "\n".join(
            f"{i + 1}. {t}" for i, t in enumerate(titles)
        )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        data = {
            "model": self.model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.2,
        }

        logger.debug(f"Translating {len(titles)} market title(s) via Groq")
        try:
            response = requests.post(self.api_url, headers=headers, json=data, timeout=20)
        except requests.exceptions.Timeout as e:
            logger.error("Translation request timeout")
            raise TranslationError("Таймаут запиту до Groq (20с) — спробуй ще раз.") from e
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error calling Groq for translation: {e}")
            raise TranslationError(f"Мережева помилка запиту до Groq: {e}") from e

        if response.status_code != 200:
            logger.error(f"Translation API error {response.status_code}: {response.text[:300]}")
            if response.status_code == 401:
                raise TranslationError(
                    "Groq відхилив ключ (401 Unauthorized) — перевір ключ у Налаштуваннях (⚙)."
                )
            if response.status_code == 429:
                raise TranslationError(
                    "Groq: перевищено ліміт безкоштовного тіру (429) — спробуй трохи пізніше."
                )
            raise TranslationError(
                f"Groq API повернув помилку {response.status_code}: {response.text[:300]}"
            )

        try:
            result_json = response.json()["choices"][0]["message"]["content"]
            parsed = json.loads(result_json)
            translations = parsed["translations"]
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            logger.error(f"Failed to parse translation response: {e}")
            raise TranslationError(f"Не вдалося розпарсити відповідь AI: {e}") from e

        if len(translations) != len(titles):
            logger.error(
                f"Translation count mismatch: expected {len(titles)}, got {len(translations)}"
            )
            raise TranslationError(
                "AI повернув невірну кількість перекладів — спробуй ще раз."
            )

        return translations
