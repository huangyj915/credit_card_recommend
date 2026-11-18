"""Taiwan issuing banks and credit card directory with optional Playwright discovery."""

from pathlib import Path
import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin

from playwright.async_api import async_playwright

from app.db import list_cards, list_directory_cards, upsert_directory_cards
from app.models import BankCardCatalogItem, BankCatalogItem, BankDiscoverResponse
from app.scrapers.base import detect_discontinued_marker
from app.scrapers.manager import USER_AGENT, _launch_browser

# Curated Taiwan issuing banks and representative credit cards.
# Only verified official URLs are pre-populated; others can be discovered via Playwright.
TAIWAN_BANKS: List[Dict] = [
    {
        "bank_code": "cathay",
        "bank_name": "國泰世華",
        "domain_tokens": ["cathaybk"],
        "list_url": "https://www.cathaybk.com.tw/cathaybk/personal/product/credit-card/cards/",
        "cards": [
            {
                "card_name": "CUBE 卡",
                "official_url": "https://www.cathaybk.com.tw/cathaybk/personal/product/credit-card/cards/cube/",
            },
            {"card_name": "蝦皮購物聯名卡", "official_url": ""},
            {"card_name": "長榮航空聯名卡", "official_url": ""},
            {"card_name": "亞洲萬里通聯名卡", "official_url": ""},
            {"card_name": "世界卡", "official_url": ""},
        ],
    },
    {
        "bank_code": "taishin",
        "bank_name": "台新銀行",
        "domain_tokens": ["taishinbank"],
        "list_url": "https://www.taishinbank.com.tw/TSB/personal/credit/intro/overview/",
        "cards": [
            {
                "card_name": "@GoGo 卡",
                "official_url": "https://www.taishinbank.com.tw/TSB/personal/credit/intro/overview/cg021/",
            },
            {"card_name": "FlyGo 卡", "official_url": ""},
            {"card_name": "玫瑰 Giving 卡", "official_url": ""},
            {"card_name": "太陽 / 玫瑰卡（切換刷）", "official_url": ""},
            {"card_name": "街口聯名卡", "official_url": ""},
            {"card_name": "遠傳 friDay 聯名卡", "official_url": ""},
        ],
    },
    {
        "bank_code": "esun",
        "bank_name": "玉山銀行",
        "domain_tokens": ["esunbank"],
        "list_url": "https://www.esunbank.com/zh-tw/personal/credit-card/intro",
        "cards": [
            {
                "card_name": "U Bear 信用卡",
                "official_url": "https://www.esunbank.com/zh-tw/personal/credit-card/intro/bank-card/u-bear",
            },
            {"card_name": "玉山 Unicard", "official_url": ""},
            {"card_name": "玉山熊本熊卡", "official_url": ""},
            {"card_name": "Pi 拍錢包信用卡", "official_url": ""},
            {"card_name": "星宇航空聯名卡", "official_url": ""},
            {"card_name": "家樂福聯名卡", "official_url": ""},
            {"card_name": "漢神巨蛋聯名卡", "official_url": ""},
        ],
    },
    {
        "bank_code": "fubon",
        "bank_name": "台北富邦",
        "domain_tokens": ["fubon"],
        "list_url": "https://www.fubon.com/banking/personal/credit_card/all_card/all_card.htm",
        "cards": [
            {
                "card_name": "富邦 J 卡",
                "official_url": "https://www.fubon.com/banking/personal/credit_card/all_card/jcard/jcard.htm",
            },
            {"card_name": "富邦 Costco 聯名卡", "official_url": ""},
            {"card_name": "富邦 momo 卡", "official_url": ""},
            {"card_name": "Open Possible 聯名卡", "official_url": ""},
            {"card_name": "尊御世界卡", "official_url": ""},
        ],
    },
    {
        "bank_code": "ctbc",
        "bank_name": "中國信託",
        "domain_tokens": ["ctbcbank"],
        "list_url": "https://www.ctbcbank.com/twrbo/zh_tw/cc_index/cc_product/cc_introduction_index.html",
        "cards": [
            {"card_name": "LINE Pay 信用卡", "official_url": ""},
            {"card_name": "ALL ME 卡", "official_url": ""},
            {"card_name": "英雄聯盟信用卡", "official_url": ""},
            {"card_name": "中油聯名卡", "official_url": ""},
            {"card_name": "中華航空聯名卡", "official_url": ""},
            {"card_name": "LaLaport 聯名卡", "official_url": ""},
            {"card_name": "商旅鈦金卡", "official_url": ""},
        ],
    },
    {
        "bank_code": "sinopac",
        "bank_name": "永豐銀行",
        "domain_tokens": ["sinopac"],
        "list_url": "https://bank.sinopac.com/sinopacBT/personal/credit-card/introduction/list.html",
        "cards": [
            {
                "card_name": "DAWHO 現金回饋信用卡",
                "official_url": "https://bank.sinopac.com/sinopacBT/personal/credit-card/introduction/bankcard/DAWHO.html",
            },
            {"card_name": "永豐幣倍卡", "official_url": ""},
            {"card_name": "永豐 SPORT 卡", "official_url": ""},
            {"card_name": "55688 聯名卡", "official_url": ""},
            {"card_name": "現金回饋 Green 卡", "official_url": ""},
            {"card_name": "MITSUI OUTLET PARK 聯名卡", "official_url": ""},
        ],
    },
    {
        "bank_code": "ubot",
        "bank_name": "聯邦銀行",
        "domain_tokens": ["ubot"],
        "list_url": "https://card.ubot.com.tw/",
        "cards": [
            {
                "card_name": "吉鶴卡",
                "official_url": "https://card.ubot.com.tw/eCard/Activity/jihe/",
            },
            {"card_name": "聯邦賴點卡", "official_url": ""},
            {"card_name": "聯邦綠卡", "official_url": ""},
            {"card_name": "幸福 M 卡", "official_url": ""},
            {"card_name": "LINE Bank 聯名卡", "official_url": ""},
            {"card_name": "微風聯名卡", "official_url": ""},
        ],
    },
    {
        "bank_code": "dbs",
        "bank_name": "星展銀行",
        "domain_tokens": ["dbs"],
        "list_url": "https://www.dbs.com.tw/personal-zh/cards/credit-cards/default.page",
        "cards": [
            {"card_name": "星展 eco 永續卡", "official_url": ""},
            {"card_name": "星展饗樂生活卡", "official_url": ""},
            {"card_name": "星展炫晶御璽卡", "official_url": ""},
            {"card_name": "星展飛行世界商務卡", "official_url": ""},
            {"card_name": "傳說對決聯名卡", "official_url": ""},
        ],
    },
    {
        "bank_code": "hsbc",
        "bank_name": "匯豐銀行",
        "domain_tokens": ["hsbc"],
        "list_url": "https://www.hsbc.com.tw/credit-cards/",
        "cards": [
            {"card_name": "匯豐現金回饋御璽卡", "official_url": ""},
            {"card_name": "匯豐匯鑽卡", "official_url": ""},
            {"card_name": "匯豐 Live+ 現金回饋卡", "official_url": ""},
            {"card_name": "匯豐旅人無限卡", "official_url": ""},
            {"card_name": "匯豐旅人御璽卡", "official_url": ""},
        ],
    },
    {
        "bank_code": "megabank",
        "bank_name": "兆豐銀行",
        "domain_tokens": ["megabank"],
        "list_url": "https://www.megabank.com.tw/personal/credit-card/card/overview",
        "cards": [
            {"card_name": "e 秒刷鈦金卡", "official_url": ""},
            {"card_name": "宇宙明星 BT21 信用卡", "official_url": ""},
            {"card_name": "利多御璽卡", "official_url": ""},
            {"card_name": "Mega One 一卡通聯名卡", "official_url": ""},
        ],
    },
    {
        "bank_code": "firstbank",
        "bank_name": "第一銀行",
        "domain_tokens": ["firstbank"],
        "list_url": "https://card.firstbank.com.tw/",
        "cards": [
            {"card_name": "iLEO 信用卡", "official_url": ""},
            {"card_name": "綠活卡", "official_url": ""},
            {"card_name": "御璽商旅卡", "official_url": ""},
            {"card_name": "桃園市市民卡聯名卡", "official_url": ""},
        ],
    },
    {
        "bank_code": "hncb",
        "bank_name": "華南銀行",
        "domain_tokens": ["hncb"],
        "list_url": "https://www.hncb.com.tw/wps/portal/HNCB/card",
        "cards": [
            {"card_name": "SnY 信用卡", "official_url": ""},
            {"card_name": "i 網購生活卡", "official_url": ""},
            {"card_name": "超鑽現金回饋卡", "official_url": ""},
            {"card_name": "Rich+ 富家卡", "official_url": ""},
        ],
    },
    {
        "bank_code": "feib",
        "bank_name": "遠東商銀",
        "domain_tokens": ["feib"],
        "list_url": "https://www.feib.com.tw/foreign/creditcard",
        "cards": [
            {"card_name": "遠東樂家+卡", "official_url": ""},
            {"card_name": "Bankee 信用卡", "official_url": ""},
            {"card_name": "遠東快樂信用卡", "official_url": ""},
            {"card_name": "C'est Moi 旅遊卡", "official_url": ""},
        ],
    },
    {
        "bank_code": "scsb",
        "bank_name": "上海商銀",
        "domain_tokens": ["scsb"],
        "list_url": "https://www.scsb.com.tw/content/card/card01.jsp",
        "cards": [
            {"card_name": "小小兵回饋卡", "official_url": ""},
            {"card_name": "Teresa 卡", "official_url": ""},
            {"card_name": "簡單卡", "official_url": ""},
            {"card_name": "Cloud Bank 雲端卡", "official_url": ""},
        ],
    },
    {
        "bank_code": "yuanta",
        "bank_name": "元大銀行",
        "domain_tokens": ["yuantabank"],
        "list_url": "https://www.yuantabank.com.tw/bank/creditCard/creditCard/list.do",
        "cards": [
            {"card_name": "元大鑽金卡", "official_url": ""},
            {"card_name": "鑽金智富卡", "official_url": ""},
            {"card_name": "分享黑啤卡", "official_url": ""},
            {"card_name": "Hello Kitty 鑽金聯名卡", "official_url": ""},
        ],
    },
    {
        "bank_code": "rakuten",
        "bank_name": "樂天信用卡",
        "domain_tokens": ["rakuten"],
        "list_url": "https://www.card.rakuten.com.tw/",
        "cards": [
            {"card_name": "樂天信用卡", "official_url": ""},
            {"card_name": "樂天 Panda J 卡", "official_url": ""},
            {"card_name": "樂天虎航聯名卡", "official_url": ""},
        ],
    },
    {
        "bank_code": "chb",
        "bank_name": "彰化銀行",
        "domain_tokens": ["bankchb", "chb"],
        "list_url": "https://www.bankchb.com/frontend/creditCard.html",
        "cards": [
            {"card_name": "My 樂現金回饋卡", "official_url": ""},
            {"card_name": "My 購卡", "official_url": ""},
            {"card_name": "馬偕認同卡", "official_url": ""},
        ],
    },
    {
        "bank_code": "tcb",
        "bank_name": "合作金庫",
        "domain_tokens": ["tcb-bank"],
        "list_url": "https://www.tcb-bank.com.tw/personal-banking/credit-card",
        "cards": [
            {"card_name": "卡娜赫拉的小動物悠遊聯名卡", "official_url": ""},
            {"card_name": "i 享樂生活卡", "official_url": ""},
            {"card_name": "活力御璽卡", "official_url": ""},
        ],
    },
    {
        "bank_code": "kgi",
        "bank_name": "凱基銀行",
        "domain_tokens": ["kgibank"],
        "list_url": "https://www.kgibank.com.tw/zh-tw/personal/credit-card",
        "cards": [
            {"card_name": "魔 BUY 悠遊卡", "official_url": ""},
            {"card_name": "現金回饋卡", "official_url": ""},
            {"card_name": "魔 FUN 悠遊卡", "official_url": ""},
        ],
    },
    {
        "bank_code": "landbank",
        "bank_name": "土地銀行",
        "domain_tokens": ["landbank"],
        "list_url": "https://www.landbank.com.tw/",
        "cards": [
            {"card_name": "JCB 極緻卡", "official_url": ""},
            {"card_name": "一卡通聯名卡", "official_url": ""},
        ],
    },
    {
        "bank_code": "bot",
        "bank_name": "臺灣銀行",
        "domain_tokens": ["bot.com"],
        "list_url": "https://www.bot.com.tw/",
        "cards": [
            {"card_name": "導盲犬認同卡", "official_url": ""},
            {"card_name": "一卡通 Titanium 商旅卡", "official_url": ""},
        ],
    },
]

BANK_BY_CODE: Dict[str, Dict] = {b["bank_code"]: b for b in TAIWAN_BANKS}

TAIWAN_BANK_HINTS: List[Tuple[str, str]] = [
    (token, bank["bank_name"])
    for bank in TAIWAN_BANKS
    for token in bank["domain_tokens"]
]

GENERIC_NAV_LABELS = {
    "信用卡",
    "信用卡首頁",
    "信用卡介紹",
    "信用卡總覽",
    "全部信用卡",
    "所有信用卡",
    "申辦信用卡",
    "立即辦卡",
    "線上辦卡",
    "辦卡進度查詢",
    "更多信用卡",
    "卡片介紹",
    "我的信用卡",
    "刷卡優惠",
    "信用卡優惠",
    "卡友權益",
    "聯名卡",
    "商務卡",
}


def normalize_card_query(text: str) -> str:
    """Normalize a card or bank name for deduplication and fuzzy matching."""
    cleaned = re.sub(r"[\s\-_@()（）【】「」]+", "", text or "").lower()
    return cleaned.replace("信用卡", "").replace("卡", "")


def _bank_matches(bank_name_a: str, bank_name_b: str) -> bool:
    a = normalize_card_query(bank_name_a).replace("銀行", "")
    b = normalize_card_query(bank_name_b).replace("銀行", "")
    return bool(a and b and (a == b or a in b or b in a))


def list_cards_for_bank(
    bank_code: str,
    db_path: Optional[Path] = None,
) -> Optional[List[BankCardCatalogItem]]:
    """Return merged card catalog for a bank (DB cards + Playwright-discovered + built-in)."""
    bank = BANK_BY_CODE.get(bank_code)
    if bank is None:
        return None

    bank_name = bank["bank_name"]
    merged: Dict[str, BankCardCatalogItem] = {}

    # 1. Built-in curated catalog cards
    for entry in bank["cards"]:
        key = normalize_card_query(entry["card_name"])
        merged[key] = BankCardCatalogItem(
            card_name=entry["card_name"],
            bank_name=bank_name,
            official_url=entry.get("official_url", ""),
            in_db=False,
            catalog_source="catalog",
        )

    # 2. Cards previously discovered via Playwright from the bank's overview page
    for row in list_directory_cards(bank_code, db_path=db_path):
        if detect_discontinued_marker(row["card_name"]) or detect_discontinued_marker(row.get("official_url") or ""):
            continue
        key = normalize_card_query(row["card_name"])
        existing = merged.get(key)
        if existing is None:
            merged[key] = BankCardCatalogItem(
                card_name=row["card_name"],
                bank_name=bank_name,
                official_url=row.get("official_url") or "",
                in_db=False,
                catalog_source="discovered",
            )
        elif row.get("official_url") and not existing.official_url:
            existing.official_url = row["official_url"]
            existing.catalog_source = "discovered"

    # 3. Cards already stored in SQLite cards table (highest priority)
    for card in list_cards(db_path=db_path):
        if not _bank_matches(card.bank_name, bank_name):
            continue
        key = normalize_card_query(card.card_name)
        merged[key] = BankCardCatalogItem(
            card_name=card.card_name,
            bank_name=card.bank_name,
            official_url=card.official_url,
            in_db=True,
            card_slug=card.card_slug,
            source_type=card.source_type,
            last_updated=card.last_updated,
            catalog_source="db",
        )

    return list(merged.values())


def list_bank_catalog(db_path: Optional[Path] = None) -> List[BankCatalogItem]:
    """Return all Taiwan issuing banks with current card counts."""
    items: List[BankCatalogItem] = []
    for bank in TAIWAN_BANKS:
        cards = list_cards_for_bank(bank["bank_code"], db_path=db_path) or []
        items.append(
            BankCatalogItem(
                bank_code=bank["bank_code"],
                bank_name=bank["bank_name"],
                list_url=bank["list_url"],
                card_count=len(cards),
            )
        )
    return items


def extract_card_candidates_from_links(
    links: List[Tuple[str, ...]],
    base_url: str,
) -> List[Dict[str, str]]:
    """Filter raw (text, href[, context]) tuples from a bank overview page, excluding discontinued cards."""
    results: List[Dict[str, str]] = []
    seen = set()

    for item in links:
        raw_text = item[0] if len(item) > 0 else ""
        raw_href = item[1] if len(item) > 1 else ""
        raw_context = item[2] if len(item) > 2 else ""

        text = re.sub(r"\s+", " ", (raw_text or "")).strip()
        if not text or len(text) < 2 or len(text) > 32:
            continue
        if text in GENERIC_NAV_LABELS:
            continue
        if "卡" not in text and "card" not in text.lower():
            continue
        if any(noise in text for noise in ("注意事項", "權益", "總覽", "說明", "申請", "申辦", "查詢", "客服", "更多")):
            continue
        if (
            detect_discontinued_marker(text)
            or detect_discontinued_marker(raw_href)
            or detect_discontinued_marker(raw_context)
        ):
            continue

        norm = normalize_card_query(text)
        if not norm or norm in seen:
            continue
        seen.add(norm)

        resolved_url = ""
        if raw_href and not raw_href.startswith(("javascript:", "#")):
            resolved_url = urljoin(base_url, raw_href)

        results.append({"card_name": text, "official_url": resolved_url})

    return results


async def discover_bank_cards_via_playwright(
    bank_code: str,
    db_path: Optional[Path] = None,
) -> Optional[BankDiscoverResponse]:
    """Use Playwright Chromium to fetch additional active card names from the bank's overview page."""
    bank = BANK_BY_CODE.get(bank_code)
    if bank is None:
        return None

    list_url = bank["list_url"]
    bank_name = bank["bank_name"]
    discovered: List[Dict[str, str]] = []

    try:
        async with async_playwright() as p:
            browser = await _launch_browser(p)
            context = await browser.new_context(
                user_agent=USER_AGENT,
                locale="zh-TW",
                viewport={"width": 1280, "height": 900},
            )
            page = await context.new_page()
            try:
                await page.goto(list_url, wait_until="domcontentloaded", timeout=20000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass

                raw_pairs = await page.evaluate(
                    """() => {
                        const nodes = Array.from(document.querySelectorAll("a, h2, h3, h4, [class*='card-title'], [class*='card_name']")).slice(0, 250);
                        return nodes.map((el) => {
                            const text = (el.innerText || "").trim();
                            const href = el.getAttribute("href") || "";
                            const cardBox = el.closest("li, article, [class*='card'], [class*='item'], section");
                            const boxText = cardBox ? (cardBox.innerText || "").slice(0, 180) : "";
                            const sectionHeading = el.closest("section")?.querySelector("h1, h2, h3")?.innerText || "";
                            return [text, href, `${sectionHeading} ${boxText}`.trim()];
                        });
                    }"""
                )

                discovered = extract_card_candidates_from_links(
                    [tuple(pair) for pair in raw_pairs],
                    list_url,
                )
            finally:
                await page.close()
                await context.close()
                await browser.close()
    except Exception as exc:
        cards = list_cards_for_bank(bank_code, db_path=db_path) or []
        return BankDiscoverResponse(
            bank_code=bank_code,
            bank_name=bank_name,
            status="error",
            message=f"無法連線擷取「{bank_name}」官網卡片清單（{type(exc).__name__}），已保留現有清單。",
            cards=cards,
        )

    if not discovered:
        cards = list_cards_for_bank(bank_code, db_path=db_path) or []
        return BankDiscoverResponse(
            bank_code=bank_code,
            bank_name=bank_name,
            status="warning",
            message=f"已開啟「{bank_name}」官網但未解析出額外卡名（可能為動態渲染或防爬限制），已保留現有清單。",
            cards=cards,
        )

    upsert_directory_cards(bank_code, bank_name, discovered, db_path=db_path)
    cards = list_cards_for_bank(bank_code, db_path=db_path) or []
    return BankDiscoverResponse(
        bank_code=bank_code,
        bank_name=bank_name,
        status="success",
        message=f"已從「{bank_name}」官網擷取 {len(discovered)} 張卡片名稱並合併至清單。",
        cards=cards,
    )
