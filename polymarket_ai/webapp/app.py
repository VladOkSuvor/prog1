"""Веб-версія Polymarket AI.

Легкий Flask-бекенд поверх існуючих модулів збору/валідації/AI-аналізу
(collectors, processing) — без дублювання логіки з CLI (main.py).

Юзкейси:
  1. Explorer   — пошук/фільтри/сортування по відкритих ринках
  2. Closing Soon — ринки, що закриваються найближчим часом
  3. AI Signal  — аналіз одного ринку за клацанням (BUY_YES/BUY_NO/HOLD, ROI, EV)
  4. Bulk Scan  — AI-аналіз топ-N відфільтрованих ринків за один запит
  5. Watchlist  — збереження цікавих ринків (JSON-файл на диску)
  6. CSV export — на клієнті, без додаткового запиту до сервера

Запуск:
    python -m polymarket_ai.webapp.app
    (або: FLASK_APP=polymarket_ai/webapp/app.py flask run)
"""

import os
import json
import threading
import time
from datetime import datetime, timezone
from urllib.parse import quote

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

from ..collectors.market_fetcher import MarketFetcher
from ..processing.validators import MarketValidator
from ..processing.ai_analyzer import MarketAIAnalyzer, AIAnalysisError
from ..processing.translator import MarketTranslator, TranslationError
from ..utils.logger import get_logger
from ..utils.exceptions import PolymarketAIError
from ..config import API_BASE_URL, DEBUG_MODE

logger = get_logger(__name__)

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
WATCHLIST_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "watchlist.json")
TRANSLATIONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "translations.json")

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="")


@app.errorhandler(PolymarketAIError)
def handle_polymarket_ai_error(error):
    """Фолбек для помилок AI-модулів, не спійманих явно у самому ендпоінті."""
    logger.error(f"[webapp] unhandled PolymarketAIError: {error}")
    return jsonify({"error": str(error)}), 502


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    """Фолбек для решти помилок — JSON замість HTML-сторінки Flask за замовчуванням."""
    if isinstance(error, HTTPException):
        return error
    logger.error(f"[webapp] unhandled exception: {error}")
    return jsonify({"error": f"Внутрішня помилка сервера: {error}"}), 500

# ---------------------------------------------------------------------------
# Простий in-memory кеш ринків. Gamma API не любить, коли його довбають
# запитом на кожну зміну фільтра в UI — тож фетчимо пачку один раз і
# кешуємо на CACHE_TTL секунд. Кнопка "Оновити" в UI форсує повторний фетч.
# ---------------------------------------------------------------------------
CACHE_TTL = 300  # 5 хвилин
MAX_MARKETS = 3000
PAGE_SIZE = 500

_cache = {"markets": [], "fetched_at": 0.0, "fetching": False}
_cache_lock = threading.Lock()


def _fetch_open_markets():
    """Пагінований збір відкритих ринків через /events/keyset.

    Дві причини, чому раніше збір "плавав" і щоразу показував різні ринки:

    1. Gamma API повертає щонайбільше 100 подій за сторінку незалежно від
       запитаного `limit` (навіть limit=500) — тож стара перевірка останньої
       сторінки `event_count < PAGE_SIZE(500)` спрацьовувала одразу після
       першої ж сторінки, і пагінація фактично НІКОЛИ не йшла далі топ-100
       найновіших подій. Через величезну кількість короткострокових крипто
       ринків "Up or Down" (5/15 хв), що створюються щохвилини, цей топ-100
       повністю змінювався за лічені хвилини — звідси й "різні дані щоразу".
       Тепер кінець пагінації визначається виключно по `next_cursor`.
    2. Список відсортований за createdAt DESC, а offset-пагінація на живих
       даних з постійними вставками зсуває вже видані сторінки (частина
       ринків губиться або дублюється між запитами). Keyset-курсор
       прив'язаний до конкретного запису, тому такого зсуву немає.
    """
    fetcher = MarketFetcher(API_BASE_URL)
    all_raw = []
    seen_ids = set()
    cursor = None
    try:
        while len(all_raw) < MAX_MARKETS:
            endpoint = (
                f"/events/keyset?closed=false&order=createdAt&ascending=false"
                f"&limit={PAGE_SIZE}"
                f"&liquidity_num_min=0&volume_num_min=0&show_hidden=true"
            )
            if cursor:
                endpoint += f"&after_cursor={quote(cursor, safe='')}"
            fetched = fetcher.fetch_events_as_markets(endpoint)
            if not fetched:
                break
            batch, event_count, next_cursor = fetched
            for m in batch:
                mid = m.get("id")
                if mid and mid not in seen_ids:
                    seen_ids.add(mid)
                    all_raw.append(m)
            if not next_cursor or event_count == 0:
                break
            cursor = next_cursor
    finally:
        fetcher.close()

    validation = MarketValidator.validate_batch(all_raw)
    logger.debug(
        f"[webapp] fetched {len(all_raw)} raw, {len(validation['valid'])} valid"
    )
    return validation["valid"]


def _get_markets(force_refresh=False):
    """Повертає закешований список ринків, оновлюючи його за потреби."""
    with _cache_lock:
        stale = (time.time() - _cache["fetched_at"]) > CACHE_TTL
        if not force_refresh and not stale and _cache["markets"]:
            return _cache["markets"]

    markets = _fetch_open_markets()

    with _cache_lock:
        if markets:
            _cache["markets"] = markets
            _cache["fetched_at"] = time.time()
        # Якщо фетч не дав результатів, лишаємо попередній кеш (краще
        # показати трохи застарілі дані, ніж порожній екран).
        return _cache["markets"]


def _parse_date(value):
    """ISO-строка -> aware datetime (UTC), або None."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []
    return []


def _save_watchlist(ids):
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(ids, f, ensure_ascii=False, indent=2)


_translations_lock = threading.Lock()


def _load_translations():
    """dict: market_id -> {"title": <оригінал>, "title_uk": <переклад>}."""
    if os.path.exists(TRANSLATIONS_FILE):
        try:
            with open(TRANSLATIONS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_translations(data):
    with open(TRANSLATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _get_api_key():
    """Ключ з заголовка X-Groq-Key (введений в UI) має пріоритет над env."""
    return request.headers.get("X-Groq-Key") or os.getenv("GROQ_API_KEY", "")


def _matches_filters(m, now, q, category, min_volume, min_prob, max_prob, max_days):
    """Перевіряє один ринок проти фільтрів Explorer-вкладки."""
    if q and q not in (m.get("title") or "").lower():
        return False
    if category and category != (m.get("category") or "").lower():
        return False
    if (m.get("volume") or 0) < min_volume:
        return False
    yes_price = m.get("yes_price")
    if min_prob is not None and (yes_price is None or yes_price < min_prob):
        return False
    if max_prob is not None and (yes_price is None or yes_price > max_prob):
        return False
    if max_days is not None:
        end_date = _parse_date(m.get("end_date"))
        if not end_date:
            return False
        days_left = (end_date - now).total_seconds() / 86400
        if days_left < 0 or days_left > max_days:
            return False
    return True


def _serialize_market(m, watchlist_ids, now=None):
    """Готує ринок для JSON-відповіді: додає watchlisted / days_left."""
    now = now or datetime.now(timezone.utc)
    out = dict(m)
    end_date = _parse_date(m.get("end_date"))
    out["days_left"] = round((end_date - now).total_seconds() / 86400, 2) if end_date else None
    out["watchlisted"] = m.get("id") in watchlist_ids
    return out


# ---------------------------------------------------------------------------
# Статичні файли (frontend)
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


# ---------------------------------------------------------------------------
# 1. Explorer — пошук / фільтри / сортування / пагінація
# ---------------------------------------------------------------------------
@app.route("/api/markets")
def list_markets():
    markets = _get_markets()
    watchlist_ids = set(_load_watchlist())
    now = datetime.now(timezone.utc)

    q = request.args.get("q", "").strip().lower()
    category = request.args.get("category", "").strip().lower()
    min_volume = float(request.args.get("min_volume") or 0)
    max_days = request.args.get("max_days")
    max_days = float(max_days) if max_days not in (None, "") else None
    min_prob = request.args.get("min_prob")
    min_prob = float(min_prob) / 100 if min_prob not in (None, "") else None
    max_prob = request.args.get("max_prob")
    max_prob = float(max_prob) / 100 if max_prob not in (None, "") else None
    sort_by = request.args.get("sort", "volume")
    order = request.args.get("order", "desc")
    page = max(1, int(request.args.get("page", 1) or 1))
    limit = min(200, max(1, int(request.args.get("limit", 25) or 25)))

    filtered = [
        m for m in markets
        if _matches_filters(m, now, q, category, min_volume, min_prob, max_prob, max_days)
    ]

    reverse = order != "asc"
    if sort_by == "volume":
        filtered.sort(key=lambda m: m.get("volume") or 0, reverse=reverse)
    elif sort_by == "closing":
        far = datetime.max.replace(tzinfo=timezone.utc)
        filtered.sort(key=lambda m: _parse_date(m.get("end_date")) or far, reverse=reverse)
    elif sort_by == "price":
        filtered.sort(key=lambda m: m.get("yes_price") or 0, reverse=reverse)
    elif sort_by == "title":
        filtered.sort(key=lambda m: (m.get("title") or "").lower(), reverse=reverse)

    total = len(filtered)
    start = (page - 1) * limit
    page_items = [_serialize_market(m, watchlist_ids, now) for m in filtered[start:start + limit]]

    categories = sorted({(m.get("category") or "other") for m in markets})

    return jsonify({
        "total": total,
        "page": page,
        "limit": limit,
        "markets": page_items,
        "categories": categories,
        "cached_at": _cache["fetched_at"],
        "cache_size": len(markets),
    })


@app.route("/api/markets/refresh", methods=["POST"])
def refresh_markets():
    markets = _get_markets(force_refresh=True)
    return jsonify({"total": len(markets), "cached_at": _cache["fetched_at"]})


@app.route("/api/markets/<market_id>")
def market_detail(market_id):
    markets = _get_markets()
    m = next((x for x in markets if x.get("id") == market_id), None)
    if not m:
        return jsonify({"error": "Ринок не знайдено (можливо, кеш застарів — натисни Оновити)"}), 404
    watchlist_ids = set(_load_watchlist())
    return jsonify(_serialize_market(m, watchlist_ids))


# ---------------------------------------------------------------------------
# 2. Closing Soon — радар найближчих дедлайнів
# ---------------------------------------------------------------------------
@app.route("/api/deadlines")
def deadlines():
    window_hours = float(request.args.get("hours", 24))
    markets = _get_markets()
    watchlist_ids = set(_load_watchlist())
    now = datetime.now(timezone.utc)

    soon = []
    for m in markets:
        end_date = _parse_date(m.get("end_date"))
        if not end_date:
            continue
        hours_left = (end_date - now).total_seconds() / 3600
        if 0 <= hours_left <= window_hours:
            item = _serialize_market(m, watchlist_ids, now)
            item["hours_left"] = round(hours_left, 1)
            soon.append(item)

    soon.sort(key=lambda m: m["hours_left"])
    return jsonify({"markets": soon[:200], "window_hours": window_hours})


# ---------------------------------------------------------------------------
# 3. AI Signal — аналіз одного ринку за клацанням
# ---------------------------------------------------------------------------
@app.route("/api/markets/<market_id>/analyze", methods=["POST"])
def analyze_market(market_id):
    markets = _get_markets()
    m = next((x for x in markets if x.get("id") == market_id), None)
    if not m:
        return jsonify({"error": "Ринок не знайдено (натисни Оновити)"}), 404

    api_key = _get_api_key()
    if not api_key:
        return jsonify({
            "error": "GROQ_API_KEY не задано. Введи ключ у Налаштуваннях "
                     "або встанови змінну середовища GROQ_API_KEY на сервері."
        }), 400

    analyzer = MarketAIAnalyzer(api_key=api_key)
    try:
        signal = analyzer.generate_trading_signal(m)
    except AIAnalysisError as e:
        return jsonify({"error": str(e)}), 502
    if not signal:
        return jsonify({
            "error": "Ринок вже фактично вирішений (ціна YES ≤2% або ≥98%) — "
                     "AI-сигнал для нього не рахується."
        }), 502
    return jsonify({"market": m, "analysis": signal})


# ---------------------------------------------------------------------------
# 3b. Translate — переклад заголовків ринків на українську (з дисковим кешем)
# ---------------------------------------------------------------------------
MAX_TRANSLATE_MARKETS = 50  # захист від довгих запитів / від ліміту безкоштовного тіру Groq


@app.route("/api/translate", methods=["POST"])
def translate_markets():
    body = request.get_json(silent=True) or {}
    market_ids = list(dict.fromkeys(body.get("market_ids") or []))[:MAX_TRANSLATE_MARKETS]
    if not market_ids:
        return jsonify({"error": "Порожній список ринків для перекладу"}), 400

    api_key = _get_api_key()
    markets_by_id = {m["id"]: m for m in _get_markets()}

    with _translations_lock:
        cache = _load_translations()

        to_translate_ids = []
        to_translate_titles = []
        for mid in market_ids:
            m = markets_by_id.get(mid)
            if not m:
                continue
            title = m.get("title") or ""
            cached = cache.get(mid)
            if not cached or cached.get("title") != title:
                to_translate_ids.append(mid)
                to_translate_titles.append(title)

        if to_translate_titles:
            if not api_key:
                return jsonify({
                    "error": "GROQ_API_KEY не задано. Введи ключ у Налаштуваннях "
                             "або встанови змінну середовища GROQ_API_KEY на сервері."
                }), 400
            translator = MarketTranslator(api_key=api_key)
            try:
                translated = translator.translate_batch(to_translate_titles)
            except TranslationError as e:
                return jsonify({"error": str(e)}), 502

            for mid, title, title_uk in zip(to_translate_ids, to_translate_titles, translated):
                cache[mid] = {"title": title, "title_uk": title_uk}
            _save_translations(cache)

        result = {
            mid: cache[mid]["title_uk"]
            for mid in market_ids
            if mid in cache and markets_by_id.get(mid)
        }

    return jsonify({"translations": result})


# ---------------------------------------------------------------------------
# 4. Bulk Scan — AI по топ-N відфільтрованих ринків за один запит
# ---------------------------------------------------------------------------
MAX_SCAN_MARKETS = 15  # захист від довгих запитів / від ліміту безкоштовного тіру Groq


@app.route("/api/scan", methods=["POST"])
def scan_signals():
    body = request.get_json(silent=True) or {}
    market_ids = list(body.get("market_ids") or [])[:MAX_SCAN_MARKETS]

    api_key = _get_api_key()
    if not api_key:
        return jsonify({"error": "GROQ_API_KEY не задано"}), 400
    if not market_ids:
        return jsonify({"error": "Порожній список ринків для сканування"}), 400

    markets_by_id = {m["id"]: m for m in _get_markets()}
    analyzer = MarketAIAnalyzer(api_key=api_key)

    found = []
    scanned = 0
    errors = 0
    for mid in market_ids:
        m = markets_by_id.get(mid)
        if not m:
            continue
        scanned += 1
        try:
            signal = analyzer.generate_trading_signal(m)
        except Exception as e:  # noqa: BLE001 — сканування не має падати через один ринок
            logger.error(f"[webapp] scan error for {mid}: {e}")
            errors += 1
            continue
        if signal and signal.get("signal") != "HOLD":
            found.append({"market": m, "analysis": signal})

    return jsonify({"scanned": scanned, "errors": errors, "signals": found})


# ---------------------------------------------------------------------------
# 5. Watchlist — збережені ринки (JSON-файл на диску)
# ---------------------------------------------------------------------------
@app.route("/api/watchlist", methods=["GET"])
def get_watchlist():
    ids = _load_watchlist()
    markets_by_id = {m["id"]: m for m in _get_markets()}
    now = datetime.now(timezone.utc)
    watchlist_ids = set(ids)
    items = [
        _serialize_market(markets_by_id[i], watchlist_ids, now)
        for i in ids if i in markets_by_id
    ]
    missing = [i for i in ids if i not in markets_by_id]
    return jsonify({"markets": items, "missing_ids": missing})


@app.route("/api/watchlist/<market_id>", methods=["POST"])
def add_to_watchlist(market_id):
    ids = _load_watchlist()
    if market_id not in ids:
        ids.append(market_id)
        _save_watchlist(ids)
    return jsonify({"ok": True, "watchlist_size": len(ids)})


@app.route("/api/watchlist/<market_id>", methods=["DELETE"])
def remove_from_watchlist(market_id):
    ids = _load_watchlist()
    if market_id in ids:
        ids.remove(market_id)
        _save_watchlist(ids)
    return jsonify({"ok": True, "watchlist_size": len(ids)})


# ---------------------------------------------------------------------------
@app.route("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "cache_size": len(_cache["markets"]),
        "cached_at": _cache["fetched_at"],
        "groq_configured": bool(os.getenv("GROQ_API_KEY")),
    })


def main():
    port = int(os.getenv("WEB_PORT", "5050"))
    # WEB_HOST=0.0.0.0 потрібен у Docker, щоб порт був доступний ззовні контейнера.
    host = os.getenv("WEB_HOST", "127.0.0.1")
    logger.debug(f"Starting Polymarket AI web app on http://{host}:{port}")
    app.run(host=host, port=port, debug=DEBUG_MODE, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
