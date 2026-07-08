"""Main entry point для Polymarket AI."""

from typing import List, Dict, Optional, Tuple, TypedDict
from datetime import datetime
from urllib.parse import quote
import os

from .collectors.market_fetcher import MarketFetcher
from .processing.validators import MarketValidator
from .processing.ai_analyzer import MarketAIAnalyzer
from .utils.logger import get_logger
from .config import API_BASE_URL, DEBUG_MODE

logger = get_logger(__name__)


class ValidationStats(TypedDict):
    """Статистика валідації ринків."""
    total: int
    valid: int
    invalid: int


class FetchValidationResult(TypedDict):
    """Результат отримання та валідації ринків."""
    raw_markets: List[Dict]
    valid_markets: List[Dict]
    invalid_markets: List[Tuple[Dict, List[str]]]
    stats: ValidationStats


class PolymarketAI:
    """Основний класс для управління системою аналізу prediction markets."""

    # Максимальна кількість елементів на одну сторінку (ліміт Gamma API)
    PAGE_SIZE = 500

    def __init__(self, api_base_url: str = API_BASE_URL):
        """
        Ініціалізація системи.

        Args:
            api_base_url: Базовий URL API
        """
        self.fetcher = MarketFetcher(api_base_url)
        logger.debug(f"PolymarketAI initialized with API: {api_base_url}")

    def fetch_and_validate_markets(self, endpoint: str = "/markets") -> Optional[FetchValidationResult]:
        """
        Отримати та валідувати ринки.

        Args:
            endpoint: API endpoint

        Returns:
            FetchValidationResult з ключами: raw_markets, valid_markets, invalid_markets, stats
        """
        logger.debug("Starting market fetch and validation")

        raw_markets = self.fetcher.fetch_markets(endpoint)
        if raw_markets is None:
            logger.error("Failed to fetch markets")
            return None

        logger.debug(f"Fetched {len(raw_markets)} markets")

        validation_result = MarketValidator.validate_batch(raw_markets)

        valid_count = len(validation_result["valid"])
        invalid_count = len(validation_result["invalid"])

        logger.debug(f"Validation complete: {valid_count} valid, {invalid_count} invalid")

        return {
            "raw_markets": raw_markets,
            "valid_markets": validation_result["valid"],
            "invalid_markets": validation_result["invalid"],
            "stats": {
                "total": len(raw_markets),
                "valid": valid_count,
                "invalid": invalid_count,
            },
        }

    def fetch_all_markets_paginated(
        self,
        max_total: int = 10_000,
        base_params: str = "active=true&volume_num_min=0",
    ) -> Optional[FetchValidationResult]:
        """
        Отримати ВСІ ринки через пагінацію (offset), включаючи непопулярні.

        Gamma API підтримує `offset` для посторінкового перебору.
        `volume_num_min=0` явно знімає мінімальний поріг об'єму,
        тому API повертає навіть ринки з нульовим обсягом торгів.

        Args:
            max_total:    Максимальна кількість ринків яку хочемо зібрати.
            base_params:  Базові query-параметри (без limit/offset).

        Returns:
            FetchValidationResult або None
        """
        all_raw: List[Dict] = []
        seen_ids: set = set()
        offset = 0
        page = 0

        while len(all_raw) < max_total:
            endpoint = (
                f"/markets?{base_params}"
                f"&limit={self.PAGE_SIZE}&offset={offset}"
            )
            logger.debug(
                f"[Pagination] page={page+1}, offset={offset}, "
                f"collected={len(all_raw)}/{max_total}"
            )

            batch = self.fetcher.fetch_markets(endpoint)

            if not batch:
                logger.debug("[Pagination] Empty batch — end of data reached")
                break

            new_count = 0
            for m in batch:
                mid = m.get("id")
                if mid and mid not in seen_ids:
                    seen_ids.add(mid)
                    all_raw.append(m)
                    new_count += 1

            logger.debug(f"[Pagination] Got {len(batch)} markets, {new_count} new unique")

            if len(batch) < self.PAGE_SIZE:
                logger.debug("[Pagination] Last page (batch < PAGE_SIZE)")
                break

            offset += self.PAGE_SIZE
            page += 1

        if not all_raw:
            logger.error("fetch_all_markets_paginated: no markets collected")
            return None

        logger.debug(f"[Pagination] Total unique markets collected: {len(all_raw)}")

        validation_result = MarketValidator.validate_batch(all_raw)
        valid_count = len(validation_result["valid"])
        invalid_count = len(validation_result["invalid"])

        logger.debug(f"[Pagination] Validation: {valid_count} valid, {invalid_count} invalid")

        return {
            "raw_markets": all_raw,
            "valid_markets": validation_result["valid"],
            "invalid_markets": validation_result["invalid"],
            "stats": {
                "total": len(all_raw),
                "valid": valid_count,
                "invalid": invalid_count,
            },
        }

    def fetch_all_events_paginated(
        self,
        max_total: int = 5_000,
        closed: str = "false",
        order: str = "createdAt",
        ascending: str = "false",
    ) -> Optional[FetchValidationResult]:
        """
        Пагінований збір ринків виключно через /events/keyset endpoint.

        /events/keyset повертає згруповані події з вкладеним масивом markets,
        так само як /events, але через стабільну курсорну (keyset) пагінацію
        замість offset. Дві причини, чому offset-варіант "плавав":

        1. Gamma API повертає щонайбільше 100 подій за сторінку незалежно
           від запитаного `limit` — перевірка "остання сторінка, якщо
           event_count < limit" на практиці спрацьовувала одразу після
           першої ж сторінки, тож пагінація ніколи не йшла далі топ-100
           найновіших подій. Тепер кінець визначається лише по `next_cursor`.
        2. Список відсортований за createdAt DESC, а нові ринки (напр.
           крипто "Up or Down" на 5/15 хв) створюються по кілька штук
           щохвилини — з offset кожна нова вставка зсуває вже видані
           сторінки, тож частина ринків губиться або дублюється між
           запитами. Keyset-курсор прив'язаний до конкретного запису.

        Параметри відповідають полям Gamma API:
          closed=false      — тільки відкриті події
          order=createdAt   — поле сортування (createdAt, volume, etc.) — саме так зветься поле в Gamma API
          ascending=false   — від новіших до старіших (DESC)
        """
        all_raw: List[Dict] = []
        seen_ids: set = set()
        cursor: Optional[str] = None
        page = 0

        while len(all_raw) < max_total:
            endpoint = (
                f"/events/keyset"
                f"?closed={closed}"
                f"&order={order}"
                f"&ascending={ascending}"
                f"&limit={self.PAGE_SIZE}"
                f"&liquidity_num_min=0"
                f"&volume_num_min=0"
                f"&show_hidden=true"
            )
            if cursor:
                endpoint += f"&after_cursor={quote(cursor, safe='')}"
            logger.debug(
                f"[Events] page={page+1}, collected={len(all_raw)}/{max_total}"
            )

            fetched = self.fetcher.fetch_events_as_markets(endpoint)

            if not fetched:
                logger.debug("[Events] Empty batch — end of data reached")
                break

            # fetch_events_as_markets повертає (markets, event_count, next_cursor)
            batch, event_count, next_cursor = fetched

            new_count = 0
            for m in batch:
                mid = m.get("id")
                if mid and mid not in seen_ids:
                    seen_ids.add(mid)
                    all_raw.append(m)
                    new_count += 1

            logger.debug(
                f"[Events] events={event_count}, markets={len(batch)}, new_unique={new_count}"
            )

            # Останню сторінку визначає сам API через відсутність next_cursor
            if not next_cursor or event_count == 0:
                logger.debug("[Events] Last page reached")
                break

            cursor = next_cursor
            page += 1

        if not all_raw:
            logger.error("fetch_all_events_paginated: no markets collected")
            return None

        validation_result = MarketValidator.validate_batch(all_raw)
        valid_count = len(validation_result["valid"])
        invalid_count = len(validation_result["invalid"])

        logger.debug(f"[Events] Total unique: {len(all_raw)}, valid: {valid_count}, invalid: {invalid_count}")

        return {
            "raw_markets": all_raw,
            "valid_markets": validation_result["valid"],
            "invalid_markets": validation_result["invalid"],
            "stats": {"total": len(all_raw), "valid": valid_count, "invalid": invalid_count},
        }

    def get_valid_markets(self, endpoint: str = "/markets") -> List[Dict]:
        """
        Отримати список валідних ринків.

        Args:
            endpoint: API endpoint

        Returns:
            Список валідних ринків
        """
        result = self.fetch_and_validate_markets(endpoint)
        if result is None:
            return []

        return result["valid_markets"]

    def close(self):
        """Закрити ресурси."""
        self.fetcher.close()

    def __enter__(self):
        """Context manager enter."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


def main():
    """Запуск збору ринків з фокусом на короткострокові події та AI аналіз."""
    if not DEBUG_MODE:
        logger.debug("Run with DEBUG_MODE=true for detailed logs")
    
    # Ініціалізуємо AI Аналітика (читаємо з змінної середовища)
    AI_KEY = os.getenv("GROQ_API_KEY", "")

    if not AI_KEY:
        logger.warning("⚠️  GROQ_API_KEY не встановлено. AI аналіз буде пропущено.")
        logger.warning("Встанови змінну: export GROQ_API_KEY='gsk_...'")
        analyzer = None
    else:
        try:
            analyzer = MarketAIAnalyzer(api_key=AI_KEY, model="llama-3.3-70b-versatile")
            logger.debug("✅ AI Аналітика ініціалізована успішно")
        except Exception as e:
            logger.error(f"❌ Помилка при ініціалізації AI: {str(e)}")
            analyzer = None

    with PolymarketAI() as pm_ai:
        logger.debug("Fetching markets...")

        # Єдиний пагінований збір через /events.
        # closed=false    — тільки відкриті події
        # order=createdAt — сортування за датою створення (нові нішеві ринки першими)
        # ascending=false — від новіших до старіших (DESC)
        logger.debug("🌐 Запускаємо збір через /events (createdAt DESC, до 5 000 подій)...")
        result = pm_ai.fetch_all_events_paginated(
            max_total=5_000,
            closed="false",
            order="createdAt",
            ascending="false",
        )

        # Запасний план: якщо /events не відповів — один запит до /markets
        if not result or not result.get("valid_markets"):
            logger.debug("⚠️ /events не дав результатів. Запасний запит до /markets...")
            result = pm_ai.fetch_and_validate_markets(
                endpoint=f"/markets?limit={PolymarketAI.PAGE_SIZE}&closed=false&order=created_at&ascending=false"
            )
        
        if result and result.get("valid_markets"):
            logger.debug("\n" + "="*70)
            logger.debug("--- АНАЛІЗ ШВИДКИХ ПОДІЙ ЗА ДОПОМОГОЮ AI ---")
            logger.debug("="*70)
            
            # Дедлайн — кінець 2026 року (широко, щоб не різати нішеві події)
            deadline = datetime.fromisoformat("2026-12-31T23:59:59")
            logger.debug(f"📅 Дедлайн: {deadline.strftime('%d.%m.%Y')}")
            logger.debug(f"🤖 AI аналіз: {'✅ УВІМКНЕНО' if analyzer else '❌ ВИМКНЕНО'}")
            logger.debug("="*70)

            signals_found = 0
            markets_analyzed = 0
            market_titles = []
            now = datetime.now()

            # Лічильники для діагностики — показуємо ЧОМУ відсіюються ринки
            skipped_no_date = 0
            skipped_past = 0
            skipped_deadline = 0
            skipped_dedup = 0

            # Деdup по префіксу: 70 символів — відсікає лише дуже однорідний спам
            # (типу 50 варіацій температури), але залишає різні події з схожим початком
            seen_title_prefixes: set = set()

            for market in result.get("valid_markets", []):
                end_date_str = market.get("end_date") or market.get("closedTime") or market.get("acceptingOrdersUntil")

                if not end_date_str:
                    skipped_no_date += 1
                    continue

                try:
                    clean_date_str = end_date_str.split('+')[0]
                    end_date = datetime.fromisoformat(clean_date_str)

                    if end_date <= now:
                        skipped_past += 1
                        continue

                    if end_date >= deadline:
                        skipped_deadline += 1
                        continue

                    title_prefix = market['title'][:70].strip()
                    if title_prefix in seen_title_prefixes:
                        skipped_dedup += 1
                        continue
                    seen_title_prefixes.add(title_prefix)
                    markets_analyzed += 1
                    market_titles.append(market['title'])
                    pretty_date = end_date.strftime("%d.%m.%Y %H:%M")

                    logger.debug(f"\n🔎 Аналізуємо ринок #{markets_analyzed}: '{market['title'][:60]}...'")

                    if not analyzer:
                        logger.debug("   ⏭️  Пропущено (AI недоступний)")
                        continue

                    ai_signal = analyzer.generate_trading_signal(market)

                    if not ai_signal or ai_signal.get("signal") == "HOLD":
                        continue

                    signals_found += 1
                    signal_type = ai_signal.get("signal")
                    roi = ai_signal.get("potential_roi_pct", 0)
                    ev = ai_signal.get("expected_value_pct", 0)
                    reason = ai_signal.get("reasoning", "No reason provided")

                    icon = "🟢 [YES]" if signal_type == "BUY_YES" else "🔴 [NO]"

                    logger.debug(
                        f"\n🔥 СИГНАЛ ЗНАЙДЕНО! | {icon} | ID: {market['id']}\n"
                        f"   📝 Подія: {market['title']}\n"
                        f"   📅 Завершення: {pretty_date}\n"
                        f"   💰 Об'єм: ${market.get('volume', 0):,.0f}\n"
                        f"   📈 Потенційний ROI: +{roi:.1f}%\n"
                        f"   🎯 Мат. очікування: +{ev:.1f}%\n"
                        f"   🧠 Обґрунтування: {reason}\n"
                        f"   " + "-"*60
                    )
                        
                except Exception as e:
                    logger.debug(f"❌ Помилка при обробці ринку: {str(e)}")
                    continue
            
            logger.debug("\n" + "="*70)
            logger.debug(f"📊 РЕЗУЛЬТАТИ АНАЛІЗУ:")
            logger.debug(f"   ✅ Пройшли фільтри: {markets_analyzed}")
            logger.debug(f"   🎯 Знайдено сигналів (BUY): {signals_found}")
            logger.debug(f"   ⛔ Відсіяно (немає дати): {skipped_no_date}")
            logger.debug(f"   ⛔ Відсіяно (вже закінчились): {skipped_past}")
            logger.debug(f"   ⛔ Відсіяно (після дедлайну): {skipped_deadline}")
            logger.debug(f"   ⛔ Відсіяно (дублікати): {skipped_dedup}")
            if signals_found == 0 and analyzer:
                logger.debug("   💭 AI не знайшов надійних сигналів з EV > +5%")
            
            if market_titles:
                logger.debug("\n📋 ВСІ ПОЗИЦІЇ ДО ДЕДЛАЙНУ:")
                for i, title in enumerate(market_titles, 1):
                    logger.debug(f"   {i}. {title}")
            
            logger.debug("="*70)
        else:
            logger.error("❌ Не вдалось завантажити ринки з API")
            if result:
                logger.debug(f"Result structure: {result.keys() if isinstance(result, dict) else type(result)}")



if __name__ == "__main__":
    main()
