# 台灣信用卡回饋比較與常用通路推薦系統

使用 **Python + FastAPI + Playwright + SQLite** 打造的個人化信用卡比較網站。  
只要輸入你每個月在「超商、餐飲、外送、網購、行動支付、旅遊、海外」等通路的花費，系統就會自動精算**每月上限、低消門檻與方案切換**，幫你算出最划算的**單卡排行**與**多卡分刷組合**。

---

## 一、給新手的前後端架構白話說明

你提到原本只聽過在 Python 用 Playwright，對網頁前後端還沒有概念。這個專案採用**全 Python 即可啟動、零複雜前端編譯工具（不需 Node.js / React）**的標準架構：

1. **Playwright 爬蟲層（資料採集）— [`app/scrapers/`](app/scrapers/)**
   - 就像你寫的自動開瀏覽器程式一樣，用無頭瀏覽器（Chromium）打開銀行官網頁面，把文字與回饋比率抓下來，整理成結構化資料存進資料庫。
2. **SQLite 資料庫（資料儲存）— [`app/db.py`](app/db.py)**
   - 一個輕量級的單一檔案資料庫（`data/cards.db`），不需要另外安裝 MySQL/PostgreSQL，用來保存各張信用卡規則、優惠上限與爬蟲紀錄。
3. **Python 後端伺服器（大腦與計算）— [`app/main.py`](app/main.py) & [`app/recommender.py`](app/recommender.py)**
   - 使用 **FastAPI** 框架，負責：
     - 提供網頁給瀏覽器看（`GET /`）
     - 接收使用者輸入的消費金額，計算每張卡實得回饋並排序（`POST /api/recommend`）
     - 接受前端按鈕觸發，啟動 Playwright 執行爬蟲（`POST /api/scrape`）
4. **網站前端介面（使用者畫面）— [`static/`](static/)**
   - 由單純的 `index.html`、`styles.css`、`app.js` 組成，負責把表單、卡片排行榜、比較表格畫在瀏覽器上，並透過 `fetch()` 向 Python 後端拿計算結果。

---

## 二、專案目錄結構

```text
credit_card_recommend/
├── app/
│   ├── main.py              # FastAPI 主程式與 API 路由
│   ├── channels.py          # 台灣 10 大常用消費通路標準定義
│   ├── models.py            # 資料結構驗證（Pydantic）
│   ├── db.py                # SQLite 資料庫讀寫
│   ├── seed_data.py         # 6 張台灣熱門卡開箱範例規則庫
│   ├── recommender.py       # 回饋精算（上限/門檻/方案切換/多卡組合）
│   └── scrapers/
│       ├── base.py          # Playwright 共用基底與中文規則解析器
│       ├── manager.py       # 爬蟲調度器（支援即時官網 & 離線示範 HTML）
│       └── banks/           # 各銀行專屬爬蟲（國泰、玉山、台新）
├── static/                  # 前端網頁（HTML / CSS / JS）
├── tests/                   # 推薦邏輯、Playwright 爬蟲與 API 自動化測試
└── requirements.txt
```

---

## 三、安裝與啟動步驟

### 1. 建立虛擬環境並安裝套件

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 2. 啟動網站

```bash
.venv/bin/uvicorn app.main:app --reload --port 8000
```

啟動後打開瀏覽器前往：
- **網站主畫面**：http://127.0.0.1:8000
- **自動產生的 API 互動文件**：http://127.0.0.1:8000/docs

### 3. 執行自動化測試

```bash
.venv/bin/pytest -v
```

---

## 四、如何新增下一家銀行的 Playwright 爬蟲？

1. 在 `app/scrapers/banks/` 新增檔案（例如 `fubon.py`），繼承 `BaseBankScraper`。
2. 填入 `bank_code`、`bank_name`、`card_name`、`card_slug`、`official_url`。
3. 在 `parse_page(self, page, source_type)` 中使用 Playwright `page.locator(...)` 擷取頁面上包含 `%` 與通路關鍵字的區塊，呼叫 `build_rules_from_blocks(...)` 即可自動轉換成標準化通路規則。
4. 到 `app/scrapers/manager.py` 的 `SCRAPER_REGISTRY` 註冊新銀行代碼，前端「Playwright 爬蟲中心」就會自動出現該銀行的勾選項目！

> **免責聲明**：各家銀行信用卡回饋率、每月上限與排除項目會隨活動檔期異動，本系統內建規則僅供試算與開發範本參考，實際消費請以發卡銀行最新公告為準。
