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

let channelsData = [];
let cardsData = [];

function formatNtd(amount) {
  return `NT$ ${Math.round(amount).toLocaleString("zh-TW")}`;
}

function escapeHtml(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function formatLastUpdated(raw) {
  const value = String(raw ?? "").trim();
  if (!value) {
    return { dateText: "未標註", fullText: "尚無更新紀錄" };
  }

  const utcMatch = value.match(/^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}) UTC$/);
  const parsed = utcMatch ? new Date(`${utcMatch[1]}T${utcMatch[2]}Z`) : new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return { dateText: value, fullText: `最後更新：${value}` };
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
  const fullText = `最後更新：${dateText} ${parts.hour}:${parts.minute}:${parts.second}（台灣時間）`;
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

function renderChannels() {
  const container = document.getElementById("channelsList");
  container.innerHTML = channelsData
    .map(
      (ch) => `
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
            step="500"
            value="0"
            class="channel-input"
            data-code="${escapeHtml(ch.code)}"
          />
        </div>
      </div>
    `
    )
    .join("");

  container.querySelectorAll(".channel-input").forEach((input) => {
    input.addEventListener("input", updateTotalSpend);
  });
}

function renderRecommendations(data) {
  const comboEl = document.getElementById("comboSection");
  const listEl = document.getElementById("recommendList");

  if (!data.total_spend_ntd || data.total_spend_ntd <= 0) {
    comboEl.classList.add("hidden");
    listEl.innerHTML = `<div class="empty-state">請在左側輸入至少一個通路的每月消費金額。</div>`;
    return;
  }

  if (data.combo && data.combo.allocations.length > 0) {
    const c = data.combo;
    comboEl.classList.remove("hidden");
    comboEl.innerHTML = `
      <div class="combo-header">
        <span class="combo-title">💡 最佳多卡分刷組合（共 ${c.selected_cards.length} 張卡）</span>
        <span class="combo-gain">每月最高省 ${formatNtd(c.total_reward_ntd)}（${c.effective_rate_pct}%）｜比單卡多賺 ${formatNtd(c.gain_over_best_single_ntd)}</span>
      </div>
      <div class="card-sub">建議搭配卡片：${c.selected_cards.map(escapeHtml).join(" ＋ ")}</div>
      <div class="combo-grid">
        ${c.allocations
          .map(
            (a) => `
          <div class="combo-item">
            <div><strong>${escapeHtml(a.channel_label)}</strong>（${formatNtd(a.spend_ntd)}）</div>
            <div>刷 <strong>${escapeHtml(a.bank_name)} ${escapeHtml(a.card_name)}</strong>${a.plan_name ? ` [${escapeHtml(a.plan_name)}]` : ""}</div>
            <div class="rate-high">${a.applied_rate}% → 賺 ${formatNtd(a.reward_ntd)}</div>
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
          ? `<span class="source-pill source-scraped">Playwright 爬取</span>`
          : `<span class="source-pill source-seed">範例規則庫</span>`;
      const updated = formatLastUpdated(rec.last_updated);
      const dateBadge = `<span class="date-pill" title="${escapeHtml(updated.fullText)}">資料更新：${escapeHtml(updated.dateText)}</span>`;
      const planBadge = rec.recommended_plan
        ? `<span class="plan-pill">建議切換方案：${escapeHtml(rec.recommended_plan)}</span>`
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
            <td>${b.cap_ntd ? formatNtd(b.cap_ntd) : "無上限"}</td>
            <td class="rate-high">${formatNtd(b.actual_reward_ntd)}</td>
            <td>${escapeHtml(b.note || "-")}</td>
          </tr>
        `
        )
        .join("");

      return `
        <article class="card-result ${rank === 1 ? "top-rank" : ""}">
          <div class="card-top">
            <div>
              <div>
                <span class="rank-pill">第 ${rank} 名</span>
                ${sourceBadge}
                ${dateBadge}
                ${planBadge}
              </div>
              <h3 class="card-name">${escapeHtml(rec.bank_name)} ${escapeHtml(rec.card_name)}</h3>
              <div class="card-sub">
                回饋型態：${escapeHtml(rec.reward_unit)} ｜ 年費：${escapeHtml(rec.annual_fee)}
                ${rec.official_url ? `｜ <a href="${escapeHtml(rec.official_url)}" target="_blank">銀行官網</a>` : ""}
              </div>
            </div>
            <div class="reward-box">
              <div class="reward-amount">每月省 ${formatNtd(rec.total_reward_ntd)}</div>
              <div class="reward-rate">綜合回饋率 ${rec.effective_rate_pct}%（年省約 ${formatNtd(rec.total_reward_ntd * 12)}）</div>
            </div>
          </div>
          ${highlights ? `<div class="highlights">${highlights}</div>` : ""}
          <details ${rank === 1 ? "open" : ""}>
            <summary>查看各通路精算明細</summary>
            <div class="table-wrap">
              <table class="breakdown-table">
                <thead>
                  <tr>
                    <th>消費通路</th>
                    <th>月消費</th>
                    <th>套用回饋率</th>
                    <th>月回饋上限</th>
                    <th>實得回饋</th>
                    <th>條件說明</th>
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
      return `
        <tr>
          <td>
            <strong>${escapeHtml(card.bank_name)} ${escapeHtml(card.card_name)}</strong>
            <br><small>${card.source_type === "scraped" ? "Playwright 爬取" : "範例規則庫"}</small>
            <br><small class="card-updated" title="${escapeHtml(updated.fullText)}">更新：${escapeHtml(updated.dateText)}</small>
          </td>
          ${cells}
        </tr>
      `;
    })
    .join("");

  table.innerHTML = `
    <thead>
      <tr>
        <th>信用卡</th>
        ${headerCols}
      </tr>
    </thead>
    <tbody>${bodyRows}</tbody>
  `;
}

async function runRecommendation() {
  const payload = {
    monthly_spending: getSpendingPayload(),
    only_no_min_spend: document.getElementById("onlyNoMinSpend").checked,
  };
  const res = await fetch("/api/recommend", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  renderRecommendations(data);
}

async function loadScrapersAndLogs() {
  const [scrapersRes, logsRes] = await Promise.all([
    fetch("/api/scrapers"),
    fetch("/api/scrape-logs?limit=10"),
  ]);
  const scrapers = await scrapersRes.json();
  const logs = await logsRes.json();

  const cardBySlug = Object.fromEntries(cardsData.map((c) => [c.card_slug, c]));
  document.getElementById("scraperBanks").innerHTML = scrapers
    .map((s) => {
      const card = cardBySlug[s.card_slug];
      const updated = card ? formatLastUpdated(card.last_updated) : null;
      return `
      <label class="scraper-bank-card">
        <input type="checkbox" class="scraper-check" value="${escapeHtml(s.bank_code)}" checked />
        <strong>${escapeHtml(s.bank_name)} ${escapeHtml(s.card_name)}</strong>
        <div class="card-sub">代碼：${escapeHtml(s.bank_code)}</div>
        ${updated ? `<div class="card-sub" title="${escapeHtml(updated.fullText)}">資料更新：${escapeHtml(updated.dateText)}</div>` : ""}
      </label>
    `;
    })
    .join("");

  const logsEl = document.getElementById("scrapeLogs");
  if (!logs.length) {
    logsEl.innerHTML = `<div class="card-sub">尚無爬蟲執行紀錄。</div>`;
  } else {
    logsEl.innerHTML = logs
      .map(
        (log) => `
        <div class="log-row">
          <strong>[${escapeHtml(log.status.toUpperCase())}]</strong>
          ${escapeHtml(log.bank_code)} (${escapeHtml(log.card_slug)}) — ${escapeHtml(log.message)}
          <span class="card-sub">｜ ${escapeHtml(log.scraped_at)}</span>
        </div>
      `
      )
      .join("");
  }
}

async function runScrape() {
  const btn = document.getElementById("runScrapeBtn");
  const selected = Array.from(document.querySelectorAll(".scraper-check:checked")).map(
    (el) => el.value
  );
  if (!selected.length) {
    alert("請至少勾選一家銀行爬蟲。");
    return;
  }
  const mode = document.querySelector("input[name='scrapeMode']:checked").value;

  btn.disabled = true;
  btn.textContent = "Playwright 執行中，請稍候...";

  try {
    const res = await fetch("/api/scrape", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ bank_codes: selected, mode }),
    });
    const data = await res.json();
    document.getElementById("scrapeResults").innerHTML = data.results
      .map(
        (r) => `
        <div class="scrape-item scrape-${escapeHtml(r.status)}">
          <strong>${escapeHtml(r.bank_code)} (${escapeHtml(r.card_slug)})</strong>：${escapeHtml(r.message)}
        </div>
      `
      )
      .join("");

    // Refresh cards and recommendation after scrape updates SQLite
    const cardsRes = await fetch("/api/cards");
    cardsData = await cardsRes.json();
    renderMatrix();
    await loadScrapersAndLogs();
    await runRecommendation();
  } finally {
    btn.disabled = false;
    btn.textContent = "啟動 Playwright 執行爬蟲";
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

async function init() {
  setupTabs();

  const [chRes, cardsRes] = await Promise.all([fetch("/api/channels"), fetch("/api/cards")]);
  channelsData = await chRes.json();
  cardsData = await cardsRes.json();

  renderChannels();
  renderMatrix();
  await loadScrapersAndLogs();

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
  document.getElementById("runScrapeBtn").addEventListener("click", runScrape);

  // Default preset on load so user immediately sees rich recommendations
  applyPreset("office");
}

init();
