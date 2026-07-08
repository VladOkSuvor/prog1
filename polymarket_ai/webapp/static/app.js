/* Polymarket AI — фронтенд (без залежностей, vanilla JS). */

const state = {
  explorer: { page: 1, limit: 24, markets: [], total: 0 },
  closing: { markets: [] },
  watchlist: { markets: [] },
  categoriesLoaded: false,
  groqConfigured: false, // чи є GROQ_API_KEY на сервері (.env) — тоді браузерний ключ не обов'язковий
};

const API_KEY_STORAGE = "polymarket_ai_groq_key";

// ---------------------------------------------------------------------
// Утиліти
// ---------------------------------------------------------------------
function $(sel) { return document.querySelector(sel); }
function $all(sel) { return Array.from(document.querySelectorAll(sel)); }

function getApiKey() {
  return localStorage.getItem(API_KEY_STORAGE) || "";
}

function hasGroqAccess() {
  return !!getApiKey() || state.groqConfigured;
}

function toast(message, type = "") {
  const el = $("#toast");
  el.textContent = message;
  el.className = "toast" + (type ? " " + type : "");
  el.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.add("hidden"), 4500);
}

async function api(path, opts = {}) {
  const headers = Object.assign({}, opts.headers || {});
  const key = getApiKey();
  if (key) headers["X-Groq-Key"] = key;
  if (opts.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";

  const res = await fetch(path, Object.assign({}, opts, { headers }));
  let data;
  try { data = await res.json(); } catch (e) { data = null; }
  if (!res.ok) {
    const msg = (data && data.error) || `Помилка запиту (${res.status})`;
    throw new Error(msg);
  }
  return data;
}

function fmtVolume(v) {
  if (v == null) return "—";
  if (v >= 1_000_000) return "$" + (v / 1_000_000).toFixed(2) + "M";
  if (v >= 1_000) return "$" + (v / 1_000).toFixed(1) + "K";
  return "$" + Math.round(v);
}

function fmtPrice(p) {
  if (p == null) return "—";
  return (p * 100).toFixed(1) + "¢";
}

function fmtDaysLeft(days) {
  if (days == null) return "дата невідома";
  if (days < 0) return "вже закрився";
  if (days < 1) return Math.round(days * 24) + " год";
  return Math.round(days) + " дн.";
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s == null ? "" : s;
  return div.innerHTML;
}

// ---------------------------------------------------------------------
// Картка ринку
// ---------------------------------------------------------------------
function marketCardHTML(m) {
  const category = m.category || "other";
  const closesLabel = m.hours_left != null
    ? `<span class="hours-left">⏳ ${m.hours_left} год</span>`
    : `<span class="pill">${fmtDaysLeft(m.days_left)}</span>`;

  return `
    <div class="market-card" data-id="${escapeHtml(m.id)}">
      <div class="card-top">
        <div class="card-title" data-role="title">${escapeHtml(m.title)}</div>
        <button class="star-btn ${m.watchlisted ? "active" : ""}" data-action="star" title="Додати/прибрати зі списку спостереження">${m.watchlisted ? "★" : "☆"}</button>
      </div>
      <div class="card-title-uk muted hidden" data-role="title-uk"></div>
      <div class="card-meta">
        <span class="pill">${escapeHtml(category)}</span>
        <span class="pill">Обсяг: ${fmtVolume(m.volume)}</span>
        ${closesLabel}
      </div>
      <div class="price-row">
        <div class="price-box yes"><span class="label">Yes</span>${fmtPrice(m.yes_price)}</div>
        <div class="price-box no"><span class="label">No</span>${fmtPrice(1 - (m.yes_price ?? 0.5))}</div>
      </div>
      <div class="card-actions">
        <button class="btn btn-accent" data-action="analyze">🤖 AI-аналіз</button>
        <button class="btn btn-ghost" data-action="translate">🇺🇦 Переклад</button>
      </div>
    </div>
  `;
}

function renderGrid(container, markets, emptyMessage) {
  if (!markets.length) {
    container.innerHTML = `<div class="empty-state">${emptyMessage}</div>`;
    return;
  }
  container.innerHTML = markets.map(marketCardHTML).join("");
}

function attachCardHandlers(container, sourceArrayGetter) {
  container.addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    const card = e.target.closest(".market-card");
    const id = card.getAttribute("data-id");
    const markets = sourceArrayGetter();
    const market = markets.find((m) => String(m.id) === String(id));

    if (btn.dataset.action === "star") {
      await toggleWatchlist(id, btn, market);
    } else if (btn.dataset.action === "analyze") {
      openAnalysisModal(market);
    } else if (btn.dataset.action === "translate") {
      await toggleTranslation(id, card, market, btn);
    }
  });
}

// ---------------------------------------------------------------------
// Переклад заголовка на українську
// ---------------------------------------------------------------------
async function toggleTranslation(id, card, market, btn) {
  const ukEl = card.querySelector('[data-role="title-uk"]');

  if (market && market.title_uk) {
    const showing = !ukEl.classList.contains("hidden");
    ukEl.classList.toggle("hidden", showing);
    btn.textContent = showing ? "🇺🇦 Переклад" : "🇺🇦 Сховати переклад";
    return;
  }

  if (!hasGroqAccess()) {
    toast("Спочатку встав Groq ключ у Налаштуваннях (⚙)", "error");
    $("#settingsModal").classList.remove("hidden");
    return;
  }

  const originalLabel = btn.textContent;
  btn.disabled = true;
  btn.textContent = "…";
  try {
    const data = await api("/api/translate", { method: "POST", body: JSON.stringify({ market_ids: [id] }) });
    const translated = data.translations && data.translations[id];
    if (!translated) {
      toast("Не вдалося отримати переклад", "error");
      btn.textContent = originalLabel;
      return;
    }
    if (market) market.title_uk = translated;
    ukEl.textContent = translated;
    ukEl.classList.remove("hidden");
    btn.textContent = "🇺🇦 Сховати переклад";
  } catch (err) {
    toast(err.message, "error");
    btn.textContent = originalLabel;
  } finally {
    btn.disabled = false;
  }
}

// ---------------------------------------------------------------------
// Watchlist
// ---------------------------------------------------------------------
async function toggleWatchlist(id, btn, market) {
  const isActive = btn.classList.contains("active");
  try {
    if (isActive) {
      await api(`/api/watchlist/${encodeURIComponent(id)}`, { method: "DELETE" });
      btn.classList.remove("active");
      btn.textContent = "☆";
      if (market) market.watchlisted = false;
    } else {
      await api(`/api/watchlist/${encodeURIComponent(id)}`, { method: "POST" });
      btn.classList.add("active");
      btn.textContent = "★";
      if (market) market.watchlisted = true;
    }
    await refreshWatchlistCount();
  } catch (err) {
    toast(err.message, "error");
  }
}

async function refreshWatchlistCount() {
  try {
    const data = await api("/api/watchlist");
    state.watchlist.markets = data.markets;
    $("#watchlistCount").textContent = data.markets.length;
  } catch (err) {
    // тихо ігноруємо — не критично для решти UI
  }
}

async function loadWatchlistTab() {
  const grid = $("#watchlistGrid");
  const emptyMsg = $("#watchlistEmpty");
  try {
    const data = await api("/api/watchlist");
    state.watchlist.markets = data.markets;
    $("#watchlistCount").textContent = data.markets.length;
    if (!data.markets.length) {
      grid.innerHTML = "";
      emptyMsg.style.display = "block";
    } else {
      emptyMsg.style.display = "none";
      renderGrid(grid, data.markets, "");
    }
  } catch (err) {
    toast(err.message, "error");
  }
}

// ---------------------------------------------------------------------
// Explorer
// ---------------------------------------------------------------------
function buildExplorerQuery() {
  const params = new URLSearchParams();
  const q = $("#searchInput").value.trim();
  const category = $("#categorySelect").value;
  const minVolume = $("#minVolumeInput").value;
  const minProb = $("#minProbInput").value;
  const maxProb = $("#maxProbInput").value;
  const maxDays = $("#maxDaysSelect").value;
  const sort = $("#sortSelect").value;
  const order = $("#orderToggle").dataset.order || "desc";

  if (q) params.set("q", q);
  if (category) params.set("category", category);
  if (minVolume) params.set("min_volume", minVolume);
  if (minProb) params.set("min_prob", minProb);
  if (maxProb) params.set("max_prob", maxProb);
  if (maxDays) params.set("max_days", maxDays);
  params.set("sort", sort);
  params.set("order", order);
  params.set("page", state.explorer.page);
  params.set("limit", state.explorer.limit);
  return params.toString();
}

async function loadExplorer() {
  const grid = $("#explorerGrid");
  grid.innerHTML = `<div class="empty-state"><span class="loading-spinner"></span>Завантаження…</div>`;
  try {
    const data = await api("/api/markets?" + buildExplorerQuery());
    state.explorer.markets = data.markets;
    state.explorer.total = data.total;

    if (!state.categoriesLoaded && data.categories) {
      const sel = $("#categorySelect");
      data.categories.forEach((c) => {
        if (!c) return;
        const opt = document.createElement("option");
        opt.value = c.toLowerCase();
        opt.textContent = c;
        sel.appendChild(opt);
      });
      state.categoriesLoaded = true;
    }

    renderGrid(grid, data.markets, "Нічого не знайдено за цими фільтрами.");
    renderPagination(data.total, data.page, data.limit);

    const cacheAge = data.cached_at ? Math.round((Date.now() / 1000 - data.cached_at) / 60) : null;
    $("#cacheInfo").textContent = cacheAge != null
      ? `${data.cache_size} ринків у кеші · оновлено ${cacheAge} хв тому`
      : "";
    $("#resultsInfo").textContent = `Знайдено: ${data.total} ринків`;
  } catch (err) {
    grid.innerHTML = `<div class="empty-state">Помилка завантаження: ${escapeHtml(err.message)}</div>`;
    toast(err.message, "error");
  }
}

function renderPagination(total, page, limit) {
  const pages = Math.max(1, Math.ceil(total / limit));
  const container = $("#pagination");
  container.innerHTML = "";
  if (pages <= 1) return;

  const makeBtn = (label, targetPage, opts = {}) => {
    const b = document.createElement("button");
    b.className = "btn" + (opts.active ? " active" : "");
    b.textContent = label;
    b.disabled = !!opts.disabled;
    b.addEventListener("click", () => {
      state.explorer.page = targetPage;
      loadExplorer();
    });
    return b;
  };

  container.appendChild(makeBtn("«", Math.max(1, page - 1), { disabled: page === 1 }));

  const start = Math.max(1, page - 2);
  const end = Math.min(pages, start + 4);
  for (let p = start; p <= end; p++) {
    container.appendChild(makeBtn(String(p), p, { active: p === page }));
  }

  container.appendChild(makeBtn("»", Math.min(pages, page + 1), { disabled: page === pages }));
}

// ---------------------------------------------------------------------
// Closing soon
// ---------------------------------------------------------------------
async function loadClosingTab() {
  const grid = $("#closingGrid");
  grid.innerHTML = `<div class="empty-state"><span class="loading-spinner"></span>Завантаження…</div>`;
  const hours = $("#windowSelect").value;
  try {
    const data = await api(`/api/deadlines?hours=${hours}`);
    state.closing.markets = data.markets;
    renderGrid(grid, data.markets, "Немає ринків, що закриються в цьому вікні часу.");
  } catch (err) {
    grid.innerHTML = `<div class="empty-state">Помилка: ${escapeHtml(err.message)}</div>`;
    toast(err.message, "error");
  }
}

// ---------------------------------------------------------------------
// AI-аналіз одного ринку
// ---------------------------------------------------------------------
function signalClass(signal) {
  if (signal === "BUY_YES") return "buy_yes";
  if (signal === "BUY_NO") return "buy_no";
  return "hold";
}

function signalLabel(signal) {
  if (signal === "BUY_YES") return "🟢 BUY YES";
  if (signal === "BUY_NO") return "🔴 BUY NO";
  return "⚪ HOLD";
}

async function openAnalysisModal(market) {
  const modal = $("#analysisModal");
  const content = $("#analysisContent");
  modal.classList.remove("hidden");

  if (!hasGroqAccess()) {
    content.innerHTML = `
      <h3>${escapeHtml(market.title)}</h3>
      <p class="muted">Groq ключ не задано. Відкрий Налаштування (⚙) і встав ключ, щоб отримати AI-сигнал.</p>
      <button class="btn btn-accent" onclick="document.getElementById('settingsModal').classList.remove('hidden')">Відкрити Налаштування</button>
    `;
    return;
  }

  content.innerHTML = `
    <h3>${escapeHtml(market.title)}</h3>
    <p class="muted"><span class="loading-spinner"></span>AI аналізує ринок…</p>
  `;

  try {
    const data = await api(`/api/markets/${encodeURIComponent(market.id)}/analyze`, { method: "POST" });
    const a = data.analysis;
    content.innerHTML = `
      <h3>${escapeHtml(market.title)}</h3>
      <span class="signal-badge ${signalClass(a.signal)}">${signalLabel(a.signal)}</span>
      <div class="stat-row">
        <div class="stat-box"><div class="value">${(a.potential_roi_pct ?? 0).toFixed(1)}%</div><div class="label">ROI</div></div>
        <div class="stat-box"><div class="value">${(a.expected_value_pct ?? 0).toFixed(1)}%</div><div class="label">Мат. очікування</div></div>
        <div class="stat-box"><div class="value">${(a.ai_probability_yes_pct ?? 0)}%</div><div class="label">AI ймовірність YES</div></div>
      </div>
      <div class="reasoning-box">${escapeHtml(a.reasoning || "Без пояснення")}</div>
    `;
  } catch (err) {
    content.innerHTML = `
      <h3>${escapeHtml(market.title)}</h3>
      <p class="muted">Помилка: ${escapeHtml(err.message)}</p>
    `;
  }
}

// ---------------------------------------------------------------------
// Bulk scan
// ---------------------------------------------------------------------
async function runScan() {
  if (!hasGroqAccess()) {
    toast("Спочатку встав Groq ключ у Налаштуваннях (⚙)", "error");
    $("#settingsModal").classList.remove("hidden");
    return;
  }
  const ids = state.explorer.markets.slice(0, 10).map((m) => m.id);
  if (!ids.length) {
    toast("Немає ринків для сканування — зміни фільтри", "error");
    return;
  }

  const modal = $("#scanModal");
  const content = $("#scanContent");
  modal.classList.remove("hidden");
  content.innerHTML = `<p class="muted"><span class="loading-spinner"></span>Сканую ${ids.length} ринків через AI (може зайняти хвилину)…</p>`;

  try {
    const data = await api("/api/scan", { method: "POST", body: JSON.stringify({ market_ids: ids }) });
    if (!data.signals.length) {
      content.innerHTML = `<p class="muted">Проскановано: ${data.scanned}. Жодного сигналу BUY_YES/BUY_NO не знайдено (усе HOLD).</p>`;
      return;
    }
    content.innerHTML = `<p class="muted">Проскановано: ${data.scanned}, знайдено сигналів: ${data.signals.length}</p>` +
      data.signals.map(({ market, analysis }) => `
        <div class="scan-item">
          <div class="scan-item-title">${escapeHtml(market.title)}</div>
          <span class="signal-badge ${signalClass(analysis.signal)}">${signalLabel(analysis.signal)}</span>
          <div class="stat-row">
            <div class="stat-box"><div class="value">${(analysis.potential_roi_pct ?? 0).toFixed(1)}%</div><div class="label">ROI</div></div>
            <div class="stat-box"><div class="value">${(analysis.expected_value_pct ?? 0).toFixed(1)}%</div><div class="label">EV</div></div>
          </div>
          <div class="reasoning-box">${escapeHtml(analysis.reasoning || "")}</div>
        </div>
      `).join("");
  } catch (err) {
    content.innerHTML = `<p class="muted">Помилка: ${escapeHtml(err.message)}</p>`;
  }
}

// ---------------------------------------------------------------------
// CSV export
// ---------------------------------------------------------------------
function exportCSV() {
  const markets = state.explorer.markets;
  if (!markets.length) {
    toast("Немає даних для експорту", "error");
    return;
  }
  const cols = ["id", "title", "category", "yes_price", "no_price", "volume", "end_date", "days_left"];
  const rows = [cols.join(",")];
  for (const m of markets) {
    rows.push(cols.map((c) => `"${String(m[c] ?? "").replace(/"/g, '""')}"`).join(","));
  }
  const blob = new Blob([rows.join("\n")], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "polymarket_export.csv";
  a.click();
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------
// Налаштування (API ключ)
// ---------------------------------------------------------------------
function renderKeyStatus() {
  const status = $("#keyStatus");
  const existing = getApiKey();
  const parts = [];
  if (existing) parts.push(`Ключ активний у цьому браузері (••••${existing.slice(-4)}).`);
  if (state.groqConfigured) parts.push("На сервері також задано GROQ_API_KEY (.env) — свій ключ вводити не обов'язково.");
  if (!parts.length) parts.push("Ключ не задано — введи свій або задай GROQ_API_KEY у .env на сервері.");
  status.textContent = parts.join(" ");
}

async function loadGroqStatus() {
  try {
    const data = await api("/api/health");
    state.groqConfigured = !!data.groq_configured;
  } catch (err) {
    // тихо ігноруємо — не критично для решти UI
  } finally {
    renderKeyStatus();
  }
}

function initSettings() {
  const input = $("#apiKeyInput");
  const existing = getApiKey();
  if (existing) {
    input.placeholder = "Ключ збережено (••••" + existing.slice(-4) + ")";
  }
  renderKeyStatus();

  $("#saveKeyBtn").addEventListener("click", () => {
    const val = input.value.trim();
    if (!val) { toast("Введи ключ перед збереженням", "error"); return; }
    localStorage.setItem(API_KEY_STORAGE, val);
    input.value = "";
    input.placeholder = "Ключ збережено (••••" + val.slice(-4) + ")";
    renderKeyStatus();
    toast("Groq ключ збережено", "success");
  });

  $("#clearKeyBtn").addEventListener("click", () => {
    localStorage.removeItem(API_KEY_STORAGE);
    input.placeholder = "sk-…";
    renderKeyStatus();
    toast("Ключ видалено");
  });
}

// ---------------------------------------------------------------------
// Вкладки / модалки
// ---------------------------------------------------------------------
function initTabs() {
  $all(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      $all(".tab-btn").forEach((b) => b.classList.remove("active"));
      $all(".tab-panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      const tab = btn.dataset.tab;
      $("#tab-" + tab).classList.add("active");

      if (tab === "closing") loadClosingTab();
      if (tab === "watchlist") loadWatchlistTab();
    });
  });
}

function initModals() {
  $all("[data-close]").forEach((btn) => {
    btn.addEventListener("click", () => {
      $("#" + btn.dataset.close).classList.add("hidden");
    });
  });
  $all(".modal-overlay").forEach((overlay) => {
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) overlay.classList.add("hidden");
    });
  });
  $("#settingsBtn").addEventListener("click", () => $("#settingsModal").classList.remove("hidden"));
}

function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

// ---------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------
function initExplorerControls() {
  const triggerReload = () => { state.explorer.page = 1; loadExplorer(); };

  $("#searchInput").addEventListener("input", debounce(triggerReload, 400));
  $("#categorySelect").addEventListener("change", triggerReload);
  $("#minVolumeInput").addEventListener("input", debounce(triggerReload, 500));
  $("#minProbInput").addEventListener("input", debounce(triggerReload, 500));
  $("#maxProbInput").addEventListener("input", debounce(triggerReload, 500));
  $("#maxDaysSelect").addEventListener("change", triggerReload);
  $("#sortSelect").addEventListener("change", triggerReload);

  const orderBtn = $("#orderToggle");
  orderBtn.dataset.order = "desc";
  orderBtn.addEventListener("click", () => {
    const next = orderBtn.dataset.order === "desc" ? "asc" : "desc";
    orderBtn.dataset.order = next;
    orderBtn.textContent = next === "desc" ? "↓" : "↑";
    triggerReload();
  });

  $("#refreshBtn").addEventListener("click", async () => {
    $("#refreshBtn").disabled = true;
    try {
      await api("/api/markets/refresh", { method: "POST" });
      toast("Дані оновлено з Gamma API", "success");
      await loadExplorer();
    } catch (err) {
      toast(err.message, "error");
    } finally {
      $("#refreshBtn").disabled = false;
    }
  });

  $("#windowSelect").addEventListener("change", loadClosingTab);
  $("#scanBtn").addEventListener("click", runScan);
  $("#exportBtn").addEventListener("click", exportCSV);
}

document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  initModals();
  initSettings();
  initExplorerControls();
  loadGroqStatus();

  attachCardHandlers($("#explorerGrid"), () => state.explorer.markets);
  attachCardHandlers($("#closingGrid"), () => state.closing.markets);
  attachCardHandlers($("#watchlistGrid"), () => state.watchlist.markets);

  refreshWatchlistCount();
  loadExplorer();
});
