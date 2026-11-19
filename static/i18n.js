(function () {
  const STORAGE_KEY = "cc_lang";
  const DEFAULT_LANG = "zh-TW";

  const TRANSLATIONS = {
    "zh-TW": {
      "page.title": "台灣信用卡回饋比較 & 常用通路推薦系統",
      "hero.title": "台灣信用卡回饋比較 & 通路推薦",
      "hero.subtitle":
        "輸入你每個月在各通路的消費金額，系統自動精算回饋上限與切換方案，幫你找出最划算的「無腦單卡」與「多卡組合」。",
      "hero.docsLink": "API 文件 (/docs)",
      "lang.aria": "切換語言",

      "input.heading": "1. 設定你的每月常用通路消費",
      "input.hint":
        "可先點選下方情境範本，或直接輸入各通路每月花費（新台幣，單一通路最多 7 位數 / NT$ 9,999,999）",
      "preset.office": "🧋 小資外食網購族",
      "preset.travel": "✈️ 日本旅遊高消費族",
      "preset.commuter": "🚆 通勤超商日常族",
      "preset.clear": "清空歸零",
      "input.onlyNoMinSpend": "僅顯示「無低消門檻」限制的卡片",
      "input.deductOverseasFee": "扣除海外 1.5% 國外交易手續費（計算淨回饋）",
      "input.maxComboCards": "多卡組合張數上限",
      "input.maxComboUnlimited": "不限張數",
      "input.maxCombo2": "最多 2 張卡",
      "input.maxCombo3": "最多 3 張卡",
      "input.totalSpendLabel": "每月預估總消費",
      "input.submit": "開始推薦最適合我的信用卡",

      "tabs.recommend": "🏆 推薦結果",
      "tabs.matrix": "📊 各卡通路比較表",
      "tabs.scraper": "🕷️ Playwright 爬蟲中心",

      "recommend.emptyDefault": "請在左側輸入你的每月通路消費，系統將自動計算推薦排名。",
      "recommend.emptyZero": "請在左側輸入至少一個通路的每月消費金額。",
      "combo.title": "💡 最佳多卡分刷組合（共 {count} 張卡）",
      "combo.gain": "每月最高省 {reward}（{rate}%）｜比單卡多賺 {gain}",
      "combo.suggestedCards": "建議搭配卡片：",
      "combo.useCardPrefix": "刷",
      "combo.earn": "{rate}% → 賺 {reward}",

      "card.rank": "第 {rank} 名",
      "card.sourceScraped": "Playwright 爬取",
      "card.sourceSeed": "範例規則庫",
      "card.dateUpdated": "資料更新：{date}",
      "card.planBadge": "建議切換方案：{plan}",
      "card.meta": "回饋型態：{unit} ｜ 年費：{fee}",
      "card.officialSite": "銀行官網",
      "card.monthlySave": "每月省 {amount}",
      "card.effectiveRate": "綜合回饋率 {rate}%（年省約 {annual}）",
      "card.breakdownSummary": "查看各通路精算明細",
      "card.colChannel": "消費通路",
      "card.colSpend": "月消費",
      "card.colRate": "套用回饋率",
      "card.colCap": "月回饋上限",
      "card.colActual": "實得回饋",
      "card.colNote": "條件說明",
      "card.unlimited": "無上限",

      "matrix.heading": "各家信用卡通路回饋總覽",
      "matrix.hint":
        "顯示目前資料庫中所有卡片於各標準化通路的最高回饋率（含方案切換或上限條件）",
      "matrix.colCard": "信用卡",
      "matrix.updatedShort": "更新：{date}",

      "scraper.heading": "Playwright 銀行官網爬蟲控制台",
      "scraper.hint":
        "銀行官網常有動態 JavaScript 渲染或版型差異。你可以選擇「即時爬取銀行官網」，或用「離線示範 HTML」測試 Playwright Chromium 的解析流程。",
      "scraper.readonlyBanner":
        "🔒 <strong>目前為公開展示模式</strong>：訪客可正常使用推薦試算與各卡比較表；為保護主機資源，爬蟲與卡片寫入功能已鎖定。",
      "scraper.adminLabel": "🔐 管理員密碼（驗證後由伺服器核發 HttpOnly Session Cookie）",
      "scraper.adminPlaceholder": "請輸入管理員密碼 (ADMIN_TOKEN)",
      "scraper.adminLoginBtn": "登入",
      "scraper.adminLogoutBtn": "登出",
      "scraper.adminSignedIn": "🔓 已登入管理員（HttpOnly Cookie 保護中）",
      "scraper.adminLoginFailed": "管理員驗證失敗",
      "logs.adminRequired": "請先登入管理員以檢視近期爬取紀錄。",
      "scraper.modeDemo":
        "離線示範 HTML（啟動 Playwright Chromium 解析示範銀行頁面，最快且穩定）",
      "scraper.modeLive": "即時爬取銀行官網（實際連線至各銀行官網擷取）",
      "scraper.runBtn": "啟動 Playwright 執行爬蟲",
      "scraper.runningBtn": "Playwright 執行中，請稍候...",
      "scraper.selectAtLeastOne": "請至少勾選一家銀行爬蟲。",
      "scraper.failed": "執行失敗",
      "scraper.codeLabel": "代碼：{code}",
      "scraper.sourceUrl": "來源網址：",

      "custom.heading": "指定卡片名稱爬取（先選台灣發卡銀行，再挑選或輸入卡片）",
      "custom.hint":
        "忘記完整卡名時，可先從台灣銀行列表選擇發卡行，系統會自動列出該行信用卡供你直接點選；若清單沒有，也可點「從官網載入更多卡名」或手動輸入。",
      "custom.step1": "1. 選擇發卡銀行",
      "custom.bankPlaceholder": "-- 請選擇台灣發卡銀行 --",
      "custom.bankCountOption": "{bank}（{count} 張可選）",
      "custom.otherBankOption": "其他銀行（自行輸入）",
      "custom.otherBankLabel": "自行輸入銀行名稱（選填）",
      "custom.otherBankPlaceholder": "例：王道銀行",
      "custom.step2": "2. 選擇該銀行信用卡",
      "custom.selectBankFirst": "請先選擇左側發卡銀行",
      "custom.otherBankEnterBelow": "請於下方自行輸入信用卡名稱",
      "custom.loadingCards": "載入該銀行卡片中...",
      "custom.noPresetCards": "-- 尚無預設卡名，請於下方手動輸入 --",
      "custom.selectCardCount": "-- 請選擇卡片名稱（共 {count} 張）--",
      "custom.tagInDb": "（已收錄）",
      "custom.tagDiscovered": "（官網擷取）",
      "custom.manualCardOption": "其他 / 自行輸入卡名",
      "custom.discoverBtn": "🔍 從官網載入更多卡名",
      "custom.discoveringBtn": "擷取官網卡片中...",
      "custom.discoverStatus":
        "正在啟動 Playwright 開啟該銀行信用卡總覽頁，請稍候...",
      "custom.discoverFailed": "載入失敗",
      "custom.step3": "3. 信用卡名稱（選取上方卡片自動帶入，或手動輸入）*",
      "custom.cardNamePlaceholder": "例：富邦 J 卡 / 星展 eco 永續卡",
      "custom.urlLabel": "官方介紹頁網址（選填，直接指定最準確）",
      "custom.runBtn": "依卡名啟動 Playwright 爬取",
      "custom.runningBtn": "Playwright 搜尋與解析中...",
      "custom.enterCardName": "請輸入或選擇想爬取的信用卡名稱。",
      "custom.failed": "自訂爬取失敗",

      "logs.heading": "最近爬取紀錄 (SQLite scrape_logs)",
      "logs.empty": "尚無爬蟲執行紀錄。",

      "date.unmarked": "未標註",
      "date.noRecord": "尚無更新紀錄",
      "date.lastUpdatedRaw": "最後更新：{value}",
      "date.lastUpdatedFull": "最後更新：{date} {time}（台灣時間）",

      "footer.disclaimer":
        "提醒：銀行信用卡權益與回饋上限經常調整，本網站內建之規則庫僅供試算參考，實際回饋請以各發卡銀行最新官網公告為準。",
    },
    en: {
      "page.title": "Taiwan Credit Card Cashback Comparison & Channel Recommender",
      "hero.title": "Taiwan Credit Card Rewards & Channel Recommender",
      "hero.subtitle":
        "Enter your monthly spending by category. We calculate reward caps and switchable plans to help you find the best single card and multi-card combo.",
      "hero.docsLink": "API Docs (/docs)",
      "lang.aria": "Switch language",

      "input.heading": "1. Set Your Monthly Spending by Channel",
      "input.hint":
        "Pick a spending preset below or enter your monthly spend per category (NTD, up to 7 digits / NT$ 9,999,999 per channel).",
      "preset.office": "🧋 Dining & Online Shopper",
      "preset.travel": "✈️ Japan Travel Spender",
      "preset.commuter": "🚆 Daily Commuter",
      "preset.clear": "Reset to Zero",
      "input.onlyNoMinSpend": "Only show cards with no minimum spend requirement",
      "input.deductOverseasFee": "Deduct 1.5% foreign transaction fee (overseas net reward)",
      "input.maxComboCards": "Max cards in combo",
      "input.maxComboUnlimited": "Unlimited",
      "input.maxCombo2": "Up to 2 cards",
      "input.maxCombo3": "Up to 3 cards",
      "input.totalSpendLabel": "Est. Monthly Total",
      "input.submit": "Find Best Credit Cards",

      "tabs.recommend": "🏆 Recommendations",
      "tabs.matrix": "📊 Card Comparison Matrix",
      "tabs.scraper": "🕷️ Playwright Scraper",

      "recommend.emptyDefault":
        "Enter your monthly spending on the left to calculate card rankings.",
      "recommend.emptyZero":
        "Please enter monthly spending for at least one channel on the left.",
      "combo.title": "💡 Best Multi-Card Combo ({count} cards)",
      "combo.gain": "Save up to {reward}/mo ({rate}%) | +{gain} vs. best single card",
      "combo.suggestedCards": "Recommended cards: ",
      "combo.useCardPrefix": "Use",
      "combo.earn": "{rate}% → Earn {reward}",

      "card.rank": "#{rank}",
      "card.sourceScraped": "Playwright Scraped",
      "card.sourceSeed": "Built-in Rules",
      "card.dateUpdated": "Updated: {date}",
      "card.planBadge": "Recommended Plan: {plan}",
      "card.meta": "Reward Unit: {unit} | Annual Fee: {fee}",
      "card.officialSite": "Official Site",
      "card.monthlySave": "Save {amount}/mo",
      "card.effectiveRate": "Effective rate {rate}% (~{annual}/yr)",
      "card.breakdownSummary": "View channel reward breakdown",
      "card.colChannel": "Channel",
      "card.colSpend": "Monthly Spend",
      "card.colRate": "Applied Rate",
      "card.colCap": "Monthly Cap",
      "card.colActual": "Actual Reward",
      "card.colNote": "Conditions",
      "card.unlimited": "Unlimited",

      "matrix.heading": "Credit Card Reward Overview by Channel",
      "matrix.hint":
        "Shows the highest reward rate per standardized channel across all cards in the database (including switchable plans and capped tiers).",
      "matrix.colCard": "Credit Card",
      "matrix.updatedShort": "Updated: {date}",

      "scraper.heading": "Playwright Bank Scraper Console",
      "scraper.hint":
        'Bank websites often use dynamic JavaScript rendering or varying layouts. Choose "Live Bank Website" to scrape directly, or "Offline Demo HTML" to test Playwright Chromium parsing.',
      "scraper.readonlyBanner":
        "🔒 <strong>Public Demo Mode</strong>: Visitors can use recommendations and the comparison matrix normally; scrapers and card writes are disabled to protect server resources.",
      "scraper.adminLabel":
        "🔐 Admin Password (exchanged for an HttpOnly session cookie)",
      "scraper.adminPlaceholder": "Enter admin password (ADMIN_TOKEN)",
      "scraper.adminLoginBtn": "Sign in",
      "scraper.adminLogoutBtn": "Sign out",
      "scraper.adminSignedIn": "🔓 Signed in as admin (HttpOnly cookie active)",
      "scraper.adminLoginFailed": "Admin authentication failed",
      "logs.adminRequired": "Sign in as admin to view recent scrape logs.",
      "scraper.modeDemo":
        "Offline Demo HTML (launches Playwright Chromium on sample bank pages — fastest & reliable)",
      "scraper.modeLive":
        "Live Bank Website (fetches directly from official bank pages)",
      "scraper.runBtn": "Run Playwright Scrapers",
      "scraper.runningBtn": "Running Playwright, please wait...",
      "scraper.selectAtLeastOne": "Please select at least one bank scraper.",
      "scraper.failed": "Execution failed",
      "scraper.codeLabel": "Code: {code}",
      "scraper.sourceUrl": "Source URL: ",

      "custom.heading":
        "Scrape Specific Card (Select Issuing Bank, Then Pick or Enter Card)",
      "custom.hint":
        'Select a Taiwan issuing bank to list its known cards, click "Load More Cards from Bank Site" to discover more, or enter a card name manually.',
      "custom.step1": "1. Select Issuing Bank",
      "custom.bankPlaceholder": "-- Select a Taiwan Issuing Bank --",
      "custom.bankCountOption": "{bank} ({count} cards)",
      "custom.otherBankOption": "Other Bank (Enter manually)",
      "custom.otherBankLabel": "Enter Bank Name (Optional)",
      "custom.otherBankPlaceholder": "e.g., O-Bank",
      "custom.step2": "2. Select Credit Card",
      "custom.selectBankFirst": "Please select an issuing bank first",
      "custom.otherBankEnterBelow": "Please enter the card name below",
      "custom.loadingCards": "Loading bank cards...",
      "custom.noPresetCards": "-- No preset cards; enter manually below --",
      "custom.selectCardCount": "-- Select a card ({count} available) --",
      "custom.tagInDb": " (In DB)",
      "custom.tagDiscovered": " (Discovered)",
      "custom.manualCardOption": "Other / Enter card name manually",
      "custom.discoverBtn": "🔍 Load More Cards from Bank Site",
      "custom.discoveringBtn": "Fetching bank cards...",
      "custom.discoverStatus":
        "Launching Playwright to open the bank's credit card list page, please wait...",
      "custom.discoverFailed": "Load failed",
      "custom.step3": "3. Card Name (auto-filled above or enter manually) *",
      "custom.cardNamePlaceholder": "e.g., Fubon J Card / DBS eco Card",
      "custom.urlLabel": "Official Card Page URL (Optional, most accurate)",
      "custom.runBtn": "Scrape Card with Playwright",
      "custom.runningBtn": "Searching & parsing with Playwright...",
      "custom.enterCardName": "Please enter or select a credit card name to scrape.",
      "custom.failed": "Custom scrape failed",

      "logs.heading": "Recent Scrape Logs (SQLite scrape_logs)",
      "logs.empty": "No scrape logs yet.",

      "date.unmarked": "Unmarked",
      "date.noRecord": "No update record",
      "date.lastUpdatedRaw": "Last updated: {value}",
      "date.lastUpdatedFull": "Last updated: {date} {time} (Taipei Time)",

      "footer.disclaimer":
        "Disclaimer: Credit card rewards and monthly caps change frequently. Built-in rules are for estimation only; please refer to each issuing bank's official announcement.",
    },
  };

  function normalizeLang(raw) {
    if (!raw) return DEFAULT_LANG;
    const cleaned = String(raw).trim().toLowerCase().replace("_", "-");
    if (cleaned === "en" || cleaned.startsWith("en-")) return "en";
    return DEFAULT_LANG;
  }

  function detectInitialLang() {
    try {
      const params = new URLSearchParams(window.location.search);
      const urlLang = params.get("lang");
      if (urlLang) {
        const normalized = normalizeLang(urlLang);
        localStorage.setItem(STORAGE_KEY, normalized);
        return normalized;
      }
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) return normalizeLang(saved);
    } catch (_) {
      // Ignore storage/URL errors in restricted contexts
    }
    return DEFAULT_LANG;
  }

  let currentLang = detectInitialLang();

  function getLang() {
    return currentLang;
  }

  function t(key, vars) {
    const table = TRANSLATIONS[currentLang] || TRANSLATIONS[DEFAULT_LANG];
    let text = table[key] ?? TRANSLATIONS[DEFAULT_LANG][key] ?? key;
    if (vars) {
      for (const [k, v] of Object.entries(vars)) {
        text = text.replaceAll(`{${k}}`, String(v ?? ""));
      }
    }
    return text;
  }

  function applyStaticTranslations() {
    document.documentElement.lang = currentLang === "en" ? "en" : "zh-Hant";
    document.title = t("page.title");

    document.querySelectorAll("[data-i18n]").forEach((el) => {
      el.textContent = t(el.dataset.i18n);
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
      el.setAttribute("placeholder", t(el.dataset.i18nPlaceholder));
    });
    document.querySelectorAll("[data-i18n-aria-label]").forEach((el) => {
      el.setAttribute("aria-label", t(el.dataset.i18nAriaLabel));
    });

    document.querySelectorAll(".lang-btn[data-lang]").forEach((btn) => {
      const active = btn.dataset.lang === currentLang;
      btn.classList.toggle("active", active);
      btn.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  function setLang(lang) {
    currentLang = normalizeLang(lang);
    try {
      localStorage.setItem(STORAGE_KEY, currentLang);
    } catch (_) {
      // Ignore storage errors
    }
    applyStaticTranslations();
    return currentLang;
  }

  window.I18N = {
    getLang,
    setLang,
    t,
    applyStaticTranslations,
    normalizeLang,
  };
})();
