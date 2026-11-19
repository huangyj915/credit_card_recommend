const PRESETS = {
  office: {
    convenience_store: 2000,
    dining: 6000,
    delivery: 3000,
    ecommerce: 5000,
    mobile_pay: 4000,
    supermarket: 2500,
    transport: 1500,
    travel: 0,
    overseas: 0,
    general: 2000,
  },
  travel: {
    convenience_store: 1000,
    dining: 5000,
    delivery: 1000,
    ecommerce: 3000,
    mobile_pay: 2000,
    supermarket: 1000,
    transport: 3000,
    travel: 15000,
    overseas: 25000,
    general: 2000,
  },
  commuter: {
    convenience_store: 3500,
    dining: 4500,
    delivery: 2000,
    ecommerce: 2000,
    mobile_pay: 5000,
    supermarket: 4000,
    transport: 4500,
    travel: 0,
    overseas: 0,
    general: 1500,
  },
};

const MAX_CHANNEL_SPEND_DIGITS = 7;
const MAX_CHANNEL_SPEND_NTD = 9999999;

let channelsData = [];
let cardsData = [];
let banksCatalog = [];
let selectedBankCards = [];
let appConfig = { admin_protected: false, public_readonly: false, docs_enabled: true };
let adminAuthenticated = false;

function t(key, vars) {
  return window.I18N.t(key, vars);
}

function currentLang() {
  return window.I18N.getLang();
}

function apiUrl(path) {
  const sep = path.includes("?") ? "&" : "?";
  return `${path}${sep}lang=${encodeURIComponent(currentLang())}`;
}

function buildAdminHeaders(extra = {}) {
  return {
    "X-Lang": currentLang(),
    "X-Requested-With": "fetch",
    ...extra,
  };
}

async function refreshAdminSession() {
  if (!appConfig.admin_protected) {
    adminAuthenticated = false;
    return;
  }
  try {
    const res = await fetch("/api/admin/session");
    if (res.ok) {
      const data = await res.json();
      adminAuthenticated = Boolean(data.authenticated);
    }
  } catch (_) {
    adminAuthenticated = false;
  }
}

async function adminLogin() {
  const input = document.getElementById("adminTokenInput");
  const errEl = document.getElementById("adminAuthError");
  const token = (input ? input.value : "").trim();
  if (!token) return;
  if (errEl) errEl.textContent = "";

  const res = await fetch(apiUrl("/api/admin/login"), {
    method: "POST",
    headers: buildAdminHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ token }),
  });
  const data = await res.json();
  if (!res.ok) {
    if (errEl) errEl.textContent = data.detail || t("scraper.adminLoginFailed");
    return;
  }
  if (input) input.value = "";
  adminAuthenticated = true;
  renderAuthBar();
  await loadScrapersAndLogs();
}

async function adminLogout() {
  await fetch(apiUrl("/api/admin/logout"), {
    method: "POST",
    headers: buildAdminHeaders(),
  });
  adminAuthenticated = false;
  renderAuthBar();
  await loadScrapersAndLogs();
}

function renderAuthBar() {
  const bar = document.getElementById("scraperAuthBar");
  const docsLink = document.getElementById("docsLink");
  if (docsLink && appConfig.docs_enabled === false) {
    docsLink.classList.add("hidden");
  }

  if (appConfig.public_readonly) {
    bar.classList.remove("hidden");
    bar.innerHTML = `
      <div class="auth-readonly">
        ${t("scraper.readonlyBanner")}
      </div>
    `;
    document.getElementById("runScrapeBtn").disabled = true;
    document.getElementById("runCustomScrapeBtn").disabled = true;
    document.getElementById("discoverBankCardsBtn").disabled = true;
    return;
  }

  if (appConfig.admin_protected) {
    bar.classList.remove("hidden");
    if (adminAuthenticated) {
      bar.innerHTML = `
        <div class="auth-signed-in">
          <span>${escapeHtml(t("scraper.adminSignedIn"))}</span>
          <button type="button" id="adminLogoutBtn" class="btn btn-secondary">${escapeHtml(t("scraper.adminLogoutBtn"))}</button>
        </div>
      `;
      document.getElementById("adminLogoutBtn").addEventListener("click", adminLogout);
      return;
    }

    bar.innerHTML = `
      <form id="adminLoginForm" class="auth-input-wrap">
        <label for="adminTokenInput">${escapeHtml(t("scraper.adminLabel"))}</label>
        <div class="select-with-action">
          <input type="password" id="adminTokenInput" autocomplete="current-password" placeholder="${escapeHtml(t("scraper.adminPlaceholder"))}" required />
          <button type="submit" class="btn btn-secondary">${escapeHtml(t("scraper.adminLoginBtn"))}</button>
        </div>
        <div id="adminAuthError" class="auth-error"></div>
      </form>
    `;
    document.getElementById("adminLoginForm").addEventListener("submit", (e) => {
      e.preventDefault();
      adminLogin();
    });
    return;
  }

  bar.classList.add("hidden");
  bar.innerHTML = "";
}

function roundHalfEven(val) {
  const num = Number(val) || 0;
  const floor = Math.floor(num);
  const diff = num - floor;
  if (Math.abs(diff - 0.5) < 1e-9) {
    return floor % 2 === 0 ? floor : floor + 1;
  }
  return Math.round(num);
}

function formatNtd(amount) {
  const locale = currentLang() === "en" ? "en-US" : "zh-TW";
  return `NT$ ${roundHalfEven(amount).toLocaleString(locale)}`;
}

function escapeHtml(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function safeHttpUrl(raw) {
  const trimmed = String(raw ?? "").trim();
  if (!trimmed) return "";
  try {
    const parsed = new URL(trimmed, window.location.origin);
    if (parsed.protocol === "http:" || parsed.protocol === "https:") {
      return parsed.href;
    }
  } catch (_) {}
  return "";
}

function formatLastUpdated(raw) {
  const value = String(raw ?? "").trim();
  if (!value) {
    return { dateText: t("date.unmarked"), fullText: t("date.noRecord") };
  }

  const utcMatch = value.match(/^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}) UTC$/);
  const parsed = utcMatch ? new Date(`${utcMatch[1]}T${utcMatch[2]}Z`) : new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return { dateText: value, fullText: t("date.lastUpdatedRaw", { value }) };
  }

  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-US", {
      timeZone: "Asia/Taipei",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    })
      .formatToParts(parsed)
      .map((p) => [p.type, p.value])
  );
  const dateText = `${parts.year}-${parts.month}-${parts.day}`;
  const fullText = t("date.lastUpdatedFull", {
    date: dateText,
    time: `${parts.hour}:${parts.minute}:${parts.second}`,
  });
  return { dateText, fullText };
}

function getSpendingPayload() {
  const spending = {};
  document.querySelectorAll(".channel-input").forEach((input) => {
    const val = parseFloat(input.value);
    if (!Number.isNaN(val) && val > 0) {
      spending[input.dataset.code] = val;
    }
  });
  return spending;
}

function updateTotalSpend() {
  const spending = getSpendingPayload();
  const total = Object.values(spending).reduce((acc, v) => acc + v, 0);
  document.getElementById("totalSpendDisplay").textContent = formatNtd(total);
}

function applyPreset(presetKey) {
  const preset = PRESETS[presetKey] || {};
  document.querySelectorAll(".channel-input").forEach((input) => {
    const val = preset[input.dataset.code] ?? 0;
    input.value = val;
  });
  updateTotalSpend();
  runRecommendation();
}

function sanitizeChannelInput(input) {
  let digits = String(input.value ?? "").replace(/\D/g, "");
  if (digits.length > MAX_CHANNEL_SPEND_DIGITS) {
    digits = digits.slice(0, MAX_CHANNEL_SPEND_DIGITS);
  }
  if (digits.length > 1) {
    digits = digits.replace(/^0+/, "") || "0";
  }
  if (digits !== "" && Number(digits) > MAX_CHANNEL_SPEND_NTD) {
    digits = String(MAX_CHANNEL_SPEND_NTD);
  }
  if (input.value !== digits) {
    input.value = digits;
  }
}

function renderChannels(savedValues = null) {
  const container = document.getElementById("channelsList");
  container.innerHTML = channelsData
    .map((ch) => {
      const val = savedValues && savedValues[ch.code] !== undefined ? savedValues[ch.code] : 0;
      return `
      <div class="channel-row">
        <div class="channel-meta">
          <span class="channel-title">${ch.icon} ${escapeHtml(ch.label)}</span>
          <span class="channel-examples">${escapeHtml(ch.examples)}</span>
        </div>
        <div class="input-wrap">
          <span>NT$</span>
          <input
            type="number"
            min="0"
            max="${MAX_CHANNEL_SPEND_NTD}"
            maxlength="${MAX_CHANNEL_SPEND_DIGITS}"
            inputmode="numeric"
            step="500"
            value="${val}"
            class="channel-input"
            data-code="${escapeHtml(ch.code)}"
          />
        </div>
      </div>
    `;
    })
    .join("");

  container.querySelectorAll(".channel-input").forEach((input) => {
    input.addEventListener("keydown", (e) => {
      if (["e", "E", "+", "-", "."].includes(e.key)) {
        e.preventDefault();
      }
    });
    input.addEventListener("input", () => {
      sanitizeChannelInput(input);
      updateTotalSpend();
    });
  });
}

function formatConditionNote(note, sourceUrl, backendTruncated = false) {
  const text = String(note || "").trim();
  if (!text) return "-";

  const maxChars = currentLang() === "en" ? 105 : 68;
  const endsWithEllipsis = text.endsWith("…") || text.endsWith("...");
  const isTruncated = backendTruncated || endsWithEllipsis || text.length > maxChars;

  let display = text;
  if (display.length > maxChars) {
    let cut = display.slice(0, maxChars);
    if (currentLang() === "en") {
      const lastSpace = cut.lastIndexOf(" ");
      if (lastSpace > maxChars * 0.6) {
        cut = cut.slice(0, lastSpace);
      }
    }
    display = `${cut.replace(/[，、；,;\s]+$/, "")}…`;
  } else if (isTruncated && !endsWithEllipsis) {
    display = `${display.replace(/[，、；,;\s]+$/, "")}…`;
  }

  const safeDisplay = escapeHtml(display);
  const safeTitle = escapeHtml(text);
  const safeUrl = safeHttpUrl(sourceUrl);
  if (isTruncated && safeUrl) {
    return `<span title="${safeTitle}">${safeDisplay}</span><a href="${escapeHtml(safeUrl)}" target="_blank" rel="noopener noreferrer" class="note-more-link">more</a>`;
  }
  return `<span title="${safeTitle}">${safeDisplay}</span>`;
}

function renderRecommendations(data) {
  const comboEl = document.getElementById("comboSection");
  const listEl = document.getElementById("recommendList");

  if (!data.total_spend_ntd || data.total_spend_ntd <= 0) {
    comboEl.classList.add("hidden");
    listEl.innerHTML = `<div class="empty-state">${escapeHtml(t("recommend.emptyZero"))}</div>`;
    return;
  }

  if (data.combo && data.combo.allocations.length > 0) {
    const c = data.combo;
    const cardJoiner = currentLang() === "en" ? " + " : " ＋ ";
    comboEl.classList.remove("hidden");
    comboEl.innerHTML = `
      <div class="combo-header">
        <span class="combo-title">${escapeHtml(t("combo.title", { count: c.selected_cards.length }))}</span>
        <span class="combo-gain">${escapeHtml(
          t("combo.gain", {
            reward: formatNtd(c.total_reward_ntd),
            rate: c.effective_rate_pct,
            gain: formatNtd(c.gain_over_best_single_ntd),
          })
        )}</span>
      </div>
      <div class="card-sub">${escapeHtml(t("combo.suggestedCards"))}${c.selected_cards.map(escapeHtml).join(cardJoiner)}</div>
      <div class="combo-grid">
        ${c.allocations
          .map(
            (a) => `
          <div class="combo-item">
            <div><strong>${escapeHtml(a.channel_label)}</strong> (${formatNtd(a.spend_ntd)})</div>
            <div>${escapeHtml(t("combo.useCardPrefix"))} <strong>${escapeHtml(a.bank_name)} ${escapeHtml(a.card_name)}</strong>${a.plan_name ? ` [${escapeHtml(a.plan_name)}]` : ""}</div>
            <div class="rate-high">${escapeHtml(t("combo.earn", { rate: a.applied_rate, reward: formatNtd(a.reward_ntd) }))}</div>
          </div>
        `
          )
          .join("")}
      </div>
    `;
  } else {
    comboEl.classList.add("hidden");
  }

  listEl.innerHTML = data.recommendations
    .map((rec, idx) => {
      const rank = idx + 1;
      const sourceBadge =
        rec.source_type === "scraped"
          ? `<span class="source-pill source-scraped">${escapeHtml(t("card.sourceScraped"))}</span>`
          : `<span class="source-pill source-seed">${escapeHtml(t("card.sourceSeed"))}</span>`;
      const updated = formatLastUpdated(rec.last_updated);
      const dateBadge = `<span class="date-pill" title="${escapeHtml(updated.fullText)}">${escapeHtml(
        t("card.dateUpdated", { date: updated.dateText })
      )}</span>`;
      const planBadge = rec.recommended_plan
        ? `<span class="plan-pill">${escapeHtml(t("card.planBadge", { plan: rec.recommended_plan }))}</span>`
        : "";
      const highlights = rec.matched_highlights
        .map((h) => `<span class="highlight-tag">${escapeHtml(h)}</span>`)
        .join("");

      const rows = rec.breakdown
        .map(
          (b) => `
          <tr>
            <td>${escapeHtml(b.channel_label)}</td>
            <td>${formatNtd(b.spend_ntd)}</td>
            <td>${b.applied_rate}%${b.applied_plan ? ` (${escapeHtml(b.applied_plan)})` : ""}</td>
            <td>${b.cap_ntd ? formatNtd(b.cap_ntd) : escapeHtml(t("card.unlimited"))}</td>
            <td class="rate-high">${formatNtd(b.actual_reward_ntd)}</td>
            <td>${formatConditionNote(b.note, rec.official_url, Boolean(b.note_truncated))}</td>
          </tr>
        `
        )
        .join("");

      const metaSep = currentLang() === "en" ? " | " : "｜";
      const safeOfficialUrl = safeHttpUrl(rec.official_url);
      return `
        <article class="card-result ${rank === 1 ? "top-rank" : ""}">
          <div class="card-top">
            <div>
              <div>
                <span class="rank-pill">${escapeHtml(t("card.rank", { rank }))}</span>
                ${sourceBadge}
                ${dateBadge}
                ${planBadge}
              </div>
              <h3 class="card-name">${escapeHtml(rec.bank_name)} ${escapeHtml(rec.card_name)}</h3>
              <div class="card-sub">
                ${escapeHtml(t("card.meta", { unit: rec.reward_unit, fee: rec.annual_fee }))}
                ${safeOfficialUrl ? `${metaSep}<a href="${escapeHtml(safeOfficialUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(t("card.officialSite"))}</a>` : ""}
              </div>
            </div>
            <div class="reward-box">
              <div class="reward-amount">${escapeHtml(t("card.monthlySave", { amount: formatNtd(rec.total_reward_ntd) }))}</div>
              <div class="reward-rate">${escapeHtml(
                t("card.effectiveRate", {
                  rate: rec.effective_rate_pct,
                  annual: formatNtd(rec.total_reward_ntd * 12),
                })
              )}</div>
            </div>
          </div>
          ${highlights ? `<div class="highlights">${highlights}</div>` : ""}
          <details ${rank === 1 ? "open" : ""}>
            <summary>${escapeHtml(t("card.breakdownSummary"))}</summary>
            <div class="table-wrap">
              <table class="breakdown-table">
                <thead>
                  <tr>
                    <th>${escapeHtml(t("card.colChannel"))}</th>
                    <th>${escapeHtml(t("card.colSpend"))}</th>
                    <th>${escapeHtml(t("card.colRate"))}</th>
                    <th>${escapeHtml(t("card.colCap"))}</th>
                    <th>${escapeHtml(t("card.colActual"))}</th>
                    <th>${escapeHtml(t("card.colNote"))}</th>
                  </tr>
                </thead>
                <tbody>${rows}</tbody>
              </table>
            </div>
          </details>
        </article>
      `;
    })
    .join("");
}

function renderMatrix() {
  const table = document.getElementById("matrixTable");
  if (!cardsData.length || !channelsData.length) return;

  const headerCols = channelsData
    .map((ch) => `<th>${ch.icon} ${escapeHtml(ch.label)}</th>`)
    .join("");

  const bodyRows = cardsData
    .map((card) => {
      const cells = channelsData
        .map((ch) => {
          const matching = card.rules.filter((r) => r.channel_code === ch.code);
          if (!matching.length) {
            const base = ch.code === "overseas" ? card.base_rate_foreign : card.base_rate_domestic;
            return `<td>${base}%</td>`;
          }
          const best = matching.reduce((a, b) => (b.rate > a.rate ? b : a));
          const cls = best.rate >= 3.0 ? "rate-high" : "";
          const planNote = best.plan_name ? `<br><small>(${escapeHtml(best.plan_name)})</small>` : "";
          return `<td class="${cls}">${best.rate}%${planNote}</td>`;
        })
        .join("");

      const updated = formatLastUpdated(card.last_updated);
      const sourceText =
        card.source_type === "scraped" ? t("card.sourceScraped") : t("card.sourceSeed");
      return `
        <tr>
          <td>
            <strong>${escapeHtml(card.bank_name)} ${escapeHtml(card.card_name)}</strong>
            <br><small>${escapeHtml(sourceText)}</small>
            <br><small class="card-updated" title="${escapeHtml(updated.fullText)}">${escapeHtml(
              t("matrix.updatedShort", { date: updated.dateText })
            )}</small>
          </td>
          ${cells}
        </tr>
      `;
    })
    .join("");

  table.innerHTML = `
    <thead>
      <tr>
        <th>${escapeHtml(t("matrix.colCard"))}</th>
        ${headerCols}
      </tr>
    </thead>
    <tbody>${bodyRows}</tbody>
  `;
}

async function runRecommendation() {
  const maxCardsRaw = document.getElementById("maxComboCards")?.value || "";
  const payload = {
    monthly_spending: getSpendingPayload(),
    only_no_min_spend: document.getElementById("onlyNoMinSpend").checked,
    deduct_overseas_fee: Boolean(document.getElementById("deductOverseasFee")?.checked),
    max_combo_cards: maxCardsRaw ? Number(maxCardsRaw) : null,
    lang: currentLang(),
  };
  const res = await fetch(apiUrl("/api/recommend"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  renderRecommendations(data);
}

async function loadScrapersAndLogs() {
  const [scrapersRes, logsRes] = await Promise.all([
    fetch(apiUrl("/api/scrapers")),
    fetch(apiUrl("/api/scrape-logs?limit=10")),
  ]);
  const scrapers = await scrapersRes.json();
  const logs = logsRes.ok ? await logsRes.json() : null;

  const cardBySlug = Object.fromEntries(cardsData.map((c) => [c.card_slug, c]));
  document.getElementById("scraperBanks").innerHTML = scrapers
    .map((s) => {
      const card = cardBySlug[s.card_slug];
      const updated = card ? formatLastUpdated(card.last_updated) : null;
      return `
      <label class="scraper-bank-card">
        <input type="checkbox" class="scraper-check" value="${escapeHtml(s.bank_code)}" checked />
        <strong>${escapeHtml(s.bank_name)} ${escapeHtml(s.card_name)}</strong>
        <div class="card-sub">${escapeHtml(t("scraper.codeLabel", { code: s.bank_code }))}</div>
        ${updated ? `<div class="card-sub" title="${escapeHtml(updated.fullText)}">${escapeHtml(t("card.dateUpdated", { date: updated.dateText }))}</div>` : ""}
      </label>
    `;
    })
    .join("");

  const logsEl = document.getElementById("scrapeLogs");
  if (logs === null) {
    logsEl.innerHTML = `<div class="card-sub">${escapeHtml(t("logs.adminRequired"))}</div>`;
  } else if (!logs.length) {
    logsEl.innerHTML = `<div class="card-sub">${escapeHtml(t("logs.empty"))}</div>`;
  } else {
    const logSep = currentLang() === "en" ? " | " : "｜ ";
    logsEl.innerHTML = logs
      .map(
        (log) => `
        <div class="log-row">
          <strong>[${escapeHtml(log.status.toUpperCase())}]</strong>
          ${escapeHtml(log.bank_code)} (${escapeHtml(log.card_slug)}) — ${escapeHtml(log.message)}
          <span class="card-sub">${logSep}${escapeHtml(log.scraped_at)}</span>
        </div>
      `
      )
      .join("");
  }
}

async function handleScrapeResponse(data) {
  document.getElementById("scrapeResults").innerHTML = (data.results || [])
    .map((r) => {
      const safeUrl = safeHttpUrl(r.url);
      return `
      <div class="scrape-item scrape-${escapeHtml(r.status)}">
        <strong>${escapeHtml(r.bank_code)} (${escapeHtml(r.card_slug || "custom")})</strong>: ${escapeHtml(r.message)}
        ${safeUrl ? `<div class="card-sub">${escapeHtml(t("scraper.sourceUrl"))}<a href="${escapeHtml(safeUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(safeUrl)}</a></div>` : ""}
      </div>
    `;
    })
    .join("");

  // Refresh cards and recommendation after scrape updates SQLite
  const cardsRes = await fetch(apiUrl("/api/cards"));
  cardsData = await cardsRes.json();
  renderMatrix();
  await loadScrapersAndLogs();
  await runRecommendation();
}

async function runScrape() {
  const btn = document.getElementById("runScrapeBtn");
  const selected = Array.from(document.querySelectorAll(".scraper-check:checked")).map(
    (el) => el.value
  );
  if (!selected.length) {
    alert(t("scraper.selectAtLeastOne"));
    return;
  }
  const mode = document.querySelector("input[name='scrapeMode']:checked").value;

  btn.disabled = true;
  btn.textContent = t("scraper.runningBtn");

  try {
    const res = await fetch(apiUrl("/api/scrape"), {
      method: "POST",
      headers: buildAdminHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ bank_codes: selected, mode, lang: currentLang() }),
    });
    const data = await res.json();
    if (!res.ok) {
      document.getElementById("scrapeResults").innerHTML = `
        <div class="scrape-item scrape-error">${escapeHtml(data.detail || t("scraper.failed"))}</div>
      `;
      return;
    }
    await handleScrapeResponse(data);
  } finally {
    btn.disabled = false;
    btn.textContent = t("scraper.runBtn");
  }
}

async function loadBankCatalog() {
  const res = await fetch(apiUrl("/api/banks"));
  banksCatalog = await res.json();
  const select = document.getElementById("customBankSelect");
  const current = select.value;
  select.innerHTML = [
    `<option value="">${escapeHtml(t("custom.bankPlaceholder"))}</option>`,
    ...banksCatalog.map(
      (b) =>
        `<option value="${escapeHtml(b.bank_code)}">${escapeHtml(
          t("custom.bankCountOption", { bank: b.bank_name, count: b.card_count })
        )}</option>`
    ),
    `<option value="__other__">${escapeHtml(t("custom.otherBankOption"))}</option>`,
  ].join("");
  if (current) {
    select.value = current;
  }
}

function renderBankCardOptions(cards) {
  selectedBankCards = cards || [];
  const cardSelect = document.getElementById("customCardSelect");
  if (!selectedBankCards.length) {
    cardSelect.innerHTML = `<option value="">${escapeHtml(t("custom.noPresetCards"))}</option>`;
    cardSelect.disabled = true;
    return;
  }
  cardSelect.disabled = false;
  cardSelect.innerHTML = [
    `<option value="">${escapeHtml(
      t("custom.selectCardCount", { count: selectedBankCards.length })
    )}</option>`,
    ...selectedBankCards.map((c, idx) => {
      const tag = c.in_db
        ? t("custom.tagInDb")
        : c.catalog_source === "discovered"
          ? t("custom.tagDiscovered")
          : "";
      return `<option value="${idx}">${escapeHtml(c.card_name)}${escapeHtml(tag)}</option>`;
    }),
    `<option value="__manual__">${escapeHtml(t("custom.manualCardOption"))}</option>`,
  ].join("");
}

async function onCustomBankChange() {
  const bankCode = document.getElementById("customBankSelect").value;
  const manualWrap = document.getElementById("customBankManualWrap");
  const cardSelect = document.getElementById("customCardSelect");
  const discoverBtn = document.getElementById("discoverBankCardsBtn");
  const statusEl = document.getElementById("bankDiscoverStatus");

  statusEl.classList.add("hidden");
  statusEl.textContent = "";

  if (!bankCode) {
    manualWrap.classList.add("hidden");
    cardSelect.innerHTML = `<option value="">${escapeHtml(t("custom.selectBankFirst"))}</option>`;
    cardSelect.disabled = true;
    discoverBtn.disabled = true;
    selectedBankCards = [];
    return;
  }

  if (bankCode === "__other__") {
    manualWrap.classList.remove("hidden");
    cardSelect.innerHTML = `<option value="__manual__">${escapeHtml(t("custom.otherBankEnterBelow"))}</option>`;
    cardSelect.disabled = true;
    discoverBtn.disabled = true;
    selectedBankCards = [];
    return;
  }

  manualWrap.classList.add("hidden");
  discoverBtn.disabled = appConfig.public_readonly;
  cardSelect.disabled = true;
  cardSelect.innerHTML = `<option value="">${escapeHtml(t("custom.loadingCards"))}</option>`;

  const res = await fetch(apiUrl(`/api/banks/${encodeURIComponent(bankCode)}/cards`));
  if (!res.ok) {
    renderBankCardOptions([]);
    return;
  }
  const cards = await res.json();
  renderBankCardOptions(cards);
}

function onCustomCardSelectChange() {
  const val = document.getElementById("customCardSelect").value;
  const nameInput = document.getElementById("customCardName");
  const urlInput = document.getElementById("customCardUrl");

  if (val === "" || val === "__manual__") {
    if (val === "__manual__") {
      nameInput.value = "";
      urlInput.value = "";
      nameInput.focus();
    }
    return;
  }

  const chosen = selectedBankCards[Number(val)];
  if (!chosen) return;
  nameInput.value = chosen.card_name || "";
  urlInput.value = chosen.official_url || "";
}

async function discoverMoreBankCards() {
  const bankCode = document.getElementById("customBankSelect").value;
  if (!bankCode || bankCode === "__other__") return;

  const btn = document.getElementById("discoverBankCardsBtn");
  const statusEl = document.getElementById("bankDiscoverStatus");
  btn.disabled = true;
  btn.textContent = t("custom.discoveringBtn");
  statusEl.classList.remove("hidden");
  statusEl.textContent = t("custom.discoverStatus");

  try {
    const res = await fetch(apiUrl(`/api/banks/${encodeURIComponent(bankCode)}/discover`), {
      method: "POST",
      headers: buildAdminHeaders(),
    });
    const data = await res.json();
    if (!res.ok) {
      statusEl.textContent = data.detail || t("custom.discoverFailed");
      return;
    }
    renderBankCardOptions(data.cards || []);
    await loadBankCatalog();
    document.getElementById("customBankSelect").value = bankCode;
    statusEl.textContent = data.message;
  } finally {
    btn.disabled = appConfig.public_readonly;
    btn.textContent = t("custom.discoverBtn");
  }
}

function getSelectedCustomBankName() {
  const bankCode = document.getElementById("customBankSelect").value;
  if (!bankCode) return "";
  if (bankCode === "__other__") {
    return document.getElementById("customBankName").value.trim();
  }
  const found = banksCatalog.find((b) => b.bank_code === bankCode);
  return found ? found.bank_name : "";
}

async function runCustomScrape(e) {
  e.preventDefault();
  const btn = document.getElementById("runCustomScrapeBtn");
  const cardName = document.getElementById("customCardName").value.trim();
  const bankName = getSelectedCustomBankName();
  const officialUrl = document.getElementById("customCardUrl").value.trim();

  if (!cardName) {
    alert(t("custom.enterCardName"));
    return;
  }

  btn.disabled = true;
  btn.textContent = t("custom.runningBtn");

  try {
    const res = await fetch(apiUrl("/api/scrape/custom"), {
      method: "POST",
      headers: buildAdminHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        card_name: cardName,
        bank_name: bankName || null,
        official_url: officialUrl || null,
        mode: "live",
        lang: currentLang(),
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      document.getElementById("scrapeResults").innerHTML = `
        <div class="scrape-item scrape-error">${escapeHtml(data.detail || t("custom.failed"))}</div>
      `;
      return;
    }
    await handleScrapeResponse(data);
    await loadBankCatalog();
    const bankCode = document.getElementById("customBankSelect").value;
    if (bankCode && bankCode !== "__other__") {
      await onCustomBankChange();
    }
  } finally {
    btn.disabled = appConfig.public_readonly;
    btn.textContent = t("custom.runBtn");
  }
}

function setupTabs() {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");
    });
  });
}

async function switchLanguage(nextLang) {
  if (window.I18N.normalizeLang(nextLang) === currentLang()) {
    return;
  }

  const savedSpending = getSpendingPayload();
  const selectedBank = document.getElementById("customBankSelect").value;
  window.I18N.setLang(nextLang);

  const [chRes, cardsRes] = await Promise.all([
    fetch(apiUrl("/api/channels")),
    fetch(apiUrl("/api/cards")),
  ]);
  channelsData = await chRes.json();
  cardsData = await cardsRes.json();

  renderAuthBar();
  renderChannels(savedSpending);
  updateTotalSpend();
  renderMatrix();

  await Promise.all([loadScrapersAndLogs(), loadBankCatalog()]);
  if (selectedBank) {
    document.getElementById("customBankSelect").value = selectedBank;
    await onCustomBankChange();
  } else {
    document.getElementById("customCardSelect").innerHTML =
      `<option value="">${escapeHtml(t("custom.selectBankFirst"))}</option>`;
  }

  await runRecommendation();
}

function setupLanguageSwitcher() {
  document.querySelectorAll(".lang-btn[data-lang]").forEach((btn) => {
    btn.addEventListener("click", () => switchLanguage(btn.dataset.lang));
  });
}

async function init() {
  window.I18N.applyStaticTranslations();
  setupTabs();
  setupLanguageSwitcher();

  const [chRes, cardsRes, cfgRes] = await Promise.all([
    fetch(apiUrl("/api/channels")),
    fetch(apiUrl("/api/cards")),
    fetch("/api/config"),
  ]);
  channelsData = await chRes.json();
  cardsData = await cardsRes.json();
  if (cfgRes.ok) {
    appConfig = await cfgRes.json();
  }
  await refreshAdminSession();
  renderAuthBar();

  renderChannels();
  renderMatrix();
  await Promise.all([loadScrapersAndLogs(), loadBankCatalog()]);

  document.querySelectorAll(".chip[data-preset]").forEach((btn) => {
    btn.addEventListener("click", () => applyPreset(btn.dataset.preset));
  });

  document.getElementById("clearInputsBtn").addEventListener("click", () => {
    document.querySelectorAll(".channel-input").forEach((i) => (i.value = 0));
    updateTotalSpend();
    runRecommendation();
  });

  document.getElementById("spendingForm").addEventListener("submit", (e) => {
    e.preventDefault();
    runRecommendation();
  });

  document.getElementById("onlyNoMinSpend").addEventListener("change", runRecommendation);
  document.getElementById("deductOverseasFee")?.addEventListener("change", runRecommendation);
  document.getElementById("maxComboCards")?.addEventListener("change", runRecommendation);
  document.getElementById("runScrapeBtn").addEventListener("click", runScrape);
  document.getElementById("customBankSelect").addEventListener("change", onCustomBankChange);
  document.getElementById("customCardSelect").addEventListener("change", onCustomCardSelectChange);
  document.getElementById("discoverBankCardsBtn").addEventListener("click", discoverMoreBankCards);
  document.getElementById("customScrapeForm").addEventListener("submit", runCustomScrape);

  // Default preset on load so user immediately sees rich recommendations
  applyPreset("office");
}

init();
