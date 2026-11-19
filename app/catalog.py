"""Taiwan issuing banks and credit card directory with optional Playwright discovery."""

from pathlib import Path
import re
from typing import Dict, List, Optional, Tuple
import unicodedata
from urllib.parse import urljoin

from playwright.async_api import Page

from app.db import (
    list_cards,
    list_directory_cards,
    load_catalog_snapshot,
    replace_directory_cards,
)
from app.i18n import (
    normalize_lang,
    t_backend,
    translate_bank_name,
    translate_card_name,
)
from app.models import BankCardCatalogItem, BankCatalogItem, BankDiscoverResponse, CardOut
from app.scrapers.base import detect_discontinued_marker, navigate_and_wait
from app.scrapers.manager import ScraperBusyError, open_scraper_page

# Curated Taiwan issuing banks and representative credit cards.
# Only verified official URLs are pre-populated; others can be discovered via Playwright.
TAIWAN_BANKS: List[Dict] = [
    {
        "bank_code": "cathay",
        "bank_name": "國泰世華",
        "domain_tokens": ["cathaybk"],
        "list_url": "https://www.cathaybk.com.tw/cathaybk/personal/product/credit-card/cards/",
        "link_include": ["/product/credit-card/cards/"],
        "cards": [
            {
                "card_name": "CUBE 卡",
                "official_url": "https://www.cathaybk.com.tw/cathaybk/personal/product/credit-card/cards/cube/",
            },
            {
                "card_name": "蝦皮購物聯名卡",
                "official_url": "https://www.cathaybk.com.tw/cathaybk/personal/product/credit-card/cards/shopee",
            },
            {
                "card_name": "長榮航空聯名卡",
                "official_url": "https://www.cathaybk.com.tw/cathaybk/personal/product/credit-card/cards/eva",
            },
            {
                "card_name": "亞洲萬里通聯名卡",
                "official_url": "https://www.cathaybk.com.tw/cathaybk/personal/product/credit-card/cards/asia-miles",
            },
            {
                "card_name": "世界卡",
                "official_url": "https://www.cathaybk.com.tw/cathaybk/personal/product/credit-card/cards/world",
            },
        ],
    },
    {
        "bank_code": "taishin",
        "bank_name": "台新銀行",
        "domain_tokens": ["taishinbank"],
        "list_url": "https://www.taishinbank.com.tw/TSB/personal/credit/intro/overview/",
        "link_include": ["/TSB/personal/credit/intro/overview/cg"],
        "cards": [
            {
                "card_name": "@GoGo 卡",
                "official_url": "https://www.taishinbank.com.tw/TSB/personal/credit/intro/overview/cg021/",
            },
            {
                "card_name": "台新 Richart 卡",
                "official_url": "https://www.taishinbank.com.tw/TSB/personal/credit/intro/overview/cg047/card001/",
            },
            {
                "card_name": "街口聯名卡",
                "official_url": "https://www.taishinbank.com.tw/TSB/personal/credit/intro/overview/cg038/card001/",
            },
            {
                "card_name": "遠傳 friDay 聯名卡",
                "official_url": "https://www.taishinbank.com.tw/TSB/personal/credit/intro/overview/cg019/card001/",
            },
            {
                "card_name": "Gogoro Rewards 聯名卡",
                "official_url": "https://www.taishinbank.com.tw/TSB/personal/credit/intro/overview/cg042/card001/",
            },
            {
                "card_name": "玫瑰卡",
                "official_url": "https://www.taishinbank.com.tw/TSB/personal/credit/intro/overview/cg013/card0001/",
            },
            {
                "card_name": "太陽卡",
                "official_url": "https://www.taishinbank.com.tw/TSB/personal/credit/intro/overview/cg012/card0001/",
            },
        ],
    },
    {
        "bank_code": "esun",
        "bank_name": "玉山銀行",
        "domain_tokens": ["esunbank"],
        "list_url": "https://www.esunbank.com/zh-tw/personal/credit-card/intro",
        "link_include": ["/intro/bank-card/", "/intro/co-branded-card/", "/intro/world-card/"],
        "cards": [
            {
                "card_name": "U Bear 信用卡",
                "official_url": "https://www.esunbank.com/zh-tw/personal/credit-card/intro/bank-card/u-bear",
            },
            {
                "card_name": "玉山 Unicard",
                "official_url": "https://www.esunbank.com/zh-tw/personal/credit-card/intro/bank-card/unicard",
            },
            {
                "card_name": "玉山熊本熊卡",
                "official_url": "https://www.esunbank.com/zh-tw/personal/credit-card/intro/bank-card/kumamon_card",
            },
            {
                "card_name": "Pi 拍錢包信用卡",
                "official_url": "https://www.esunbank.com/zh-tw/personal/credit-card/intro/co-branded-card/pi-card",
            },
            {
                "card_name": "星宇航空聯名卡",
                "official_url": "https://www.esunbank.com/zh-tw/personal/credit-card/intro/co-branded-card/starlux-card",
            },
            {
                "card_name": "玉山易遊卡",
                "official_url": "https://www.esunbank.com/zh-tw/personal/credit-card/intro/co-branded-card/eztravel",
            },
            {
                "card_name": "玉山數位 e 卡",
                "official_url": "https://www.esunbank.com/zh-tw/personal/credit-card/intro/bank-card/e-card",
            },
            {
                "card_name": "玉山 Only 卡",
                "official_url": "https://www.esunbank.com/zh-tw/personal/credit-card/intro/bank-card/only-card",
            },
        ],
    },
    {
        "bank_code": "fubon",
        "bank_name": "台北富邦",
        "domain_tokens": ["fubon"],
        "list_url": "https://www.fubon.com/banking/personal/credit_card/all_card/all_card.htm",
        "link_include": ["/personal/credit_card/all_card/"],
        "link_exclude": ["all_card.htm", "purchasing_card", "_bccard"],
        "cards": [
            {
                "card_name": "富邦 J 卡",
                "official_url": "https://www.fubon.com/banking/personal/credit_card/all_card/omiyage/omiyage.htm",
            },
            {
                "card_name": "Costco 聯名卡",
                "official_url": "https://www.fubon.com/banking/personal/credit_card/all_card/costco/costco.htm",
            },
            {
                "card_name": "momo 卡",
                "official_url": "https://www.fubon.com/banking/personal/credit_card/all_card/momo/momo.htm",
            },
            {
                "card_name": "Open Possible 聯名卡",
                "official_url": "https://www.fubon.com/banking/personal/credit_card/all_card/openpossible/openpossible.htm",
            },
            {
                "card_name": "富邦尊御世界卡",
                "official_url": "https://www.fubon.com/banking/personal/credit_card/all_card/imperial/imperial.htm",
            },
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
        "list_url": "https://bank.sinopac.com/sinopacBT/personal/credit-card/introduction/bankcard/list.html",
        "list_urls": [
            "https://bank.sinopac.com/sinopacBT/personal/credit-card/introduction/bankcard/list.html",
            "https://bank.sinopac.com/sinopacBT/personal/credit-card/introduction/co-brand/list.html",
        ],
        "link_include": ["/introduction/bankcard/", "/introduction/co-brand/"],
        "link_exclude": ["list.html"],
        "cards": [
            {
                "card_name": "DAWHO 現金回饋信用卡",
                "official_url": "https://bank.sinopac.com/sinopacBT/personal/credit-card/introduction/bankcard/DAWHO.html",
            },
            {
                "card_name": "永豐幣倍卡",
                "official_url": "https://bank.sinopac.com/sinopacBT/personal/credit-card/introduction/bankcard/dual-currency-card.html",
            },
            {
                "card_name": "永豐 SPORT 卡",
                "official_url": "https://bank.sinopac.com/sinopacBT/personal/credit-card/introduction/bankcard/sportcard.html",
            },
            {
                "card_name": "DAWAY 卡",
                "official_url": "https://bank.sinopac.com/sinopacBT/personal/credit-card/introduction/bankcard/DAWAY.html",
            },
            {
                "card_name": "現金回饋 Green 卡",
                "official_url": "https://bank.sinopac.com/sinopacBT/personal/credit-card/introduction/bankcard/cashcard.html",
            },
            {
                "card_name": "永豐 55688 聯名卡",
                "official_url": "https://bank.sinopac.com/sinopacBT/personal/credit-card/introduction/co-brand/taxicard.html",
            },
            {
                "card_name": "MITSUI OUTLET PARK 卡",
                "official_url": "https://bank.sinopac.com/sinopacBT/personal/credit-card/introduction/co-brand/mitsui-outlet-park-card.html",
            },
        ],
    },
    {
        "bank_code": "ubot",
        "bank_name": "聯邦銀行",
        "domain_tokens": ["ubot"],
        "list_url": "https://card.ubot.com.tw/Card?category=%E9%8A%80%E8%A1%8C%E5%8D%A1",
        "list_urls": [
            "https://card.ubot.com.tw/Card?category=%E9%8A%80%E8%A1%8C%E5%8D%A1",
            "https://card.ubot.com.tw/Card?category=%E8%81%AF%E5%90%8D%E5%8D%A1",
            "https://card.ubot.com.tw/Card?category=%E9%A0%82%E7%B4%9A%E5%8D%A1",
            "https://card.ubot.com.tw/Card?category=%E7%99%BE%E8%B2%A8%E5%8D%A1",
        ],
        "link_include": ["/CardDetail/"],
        "cards": [
            {
                "card_name": "吉鶴卡",
                "official_url": "https://card.ubot.com.tw/CardDetail/cardDetail202",
            },
            {
                "card_name": "聯邦賴點卡",
                "official_url": "https://card.ubot.com.tw/CardDetail/cardDetail201",
            },
            {
                "card_name": "聯邦綠卡",
                "official_url": "https://card.ubot.com.tw/CardDetail/cardDetail204",
            },
            {
                "card_name": "聯邦 M 卡",
                "official_url": "https://card.ubot.com.tw/CardDetail/cardDetail203",
            },
            {
                "card_name": "LINE Bank 聯名卡",
                "official_url": "https://card.ubot.com.tw/CardDetail/cardDetail601",
            },
            {
                "card_name": "聯邦 MaiCoin 聯名卡",
                "official_url": "https://card.ubot.com.tw/CardDetail/cardDetail409",
            },
        ],
    },
    {
        "bank_code": "dbs",
        "bank_name": "星展銀行",
        "domain_tokens": ["dbs"],
        "list_url": "https://www.dbs.com.tw/personal-zh/cards/dbs-credit-cards/default.page",
        "link_include": ["/personal-zh/cards/"],
        "link_exclude": ["/offers/", "/services/", "/MGM/", "/ploan/", "default.page", "/hoap/"],
        "cards": [
            {
                "card_name": "星展 eco 永續卡",
                "official_url": "https://www.dbs.com.tw/personal-zh/cards/dbs_eco/index.html",
            },
            {
                "card_name": "星展饗樂生活卡",
                "official_url": "https://www.dbs.com.tw/personal-zh/cards/dbs-funlife/index.html",
            },
            {
                "card_name": "星展飛行世界商務卡",
                "official_url": "https://www.dbs.com.tw/personal-zh/cards/travelworld/index.html",
            },
            {
                "card_name": "星展炫晶商務御璽卡",
                "official_url": "https://www.dbs.com.tw/personal-zh/cards/livefresh_biz_signature_ipass/index.html",
            },
            {
                "card_name": "星展傳說對決聯名卡",
                "official_url": "https://www.dbs.com.tw/personal-zh/cards/dbs-aov/index.html",
            },
            {
                "card_name": "星展 PChome Prime 聯名卡",
                "official_url": "https://www.dbs.com.tw/personal-zh/cards/dbs-pchomeprime/index.html",
            },
        ],
    },
    {
        "bank_code": "hsbc",
        "bank_name": "匯豐銀行",
        "domain_tokens": ["hsbc"],
        "list_url": "https://www.hsbc.com.tw/credit-cards/",
        "link_include": ["/credit-cards/products/"],
        "cards": [
            {
                "card_name": "匯豐現金回饋御璽卡",
                "official_url": "https://www.hsbc.com.tw/credit-cards/products/cashback-signature/",
            },
            {
                "card_name": "匯豐匯鑽卡",
                "official_url": "https://www.hsbc.com.tw/credit-cards/products/cashback-titanium/",
            },
            {
                "card_name": "匯豐 Live+ 現金回饋卡",
                "official_url": "https://www.hsbc.com.tw/credit-cards/products/liveplus/",
            },
            {
                "card_name": "匯豐旅人無限卡",
                "official_url": "https://www.hsbc.com.tw/credit-cards/products/travel/visa-infinite/",
            },
            {
                "card_name": "匯豐旅人御璽卡",
                "official_url": "https://www.hsbc.com.tw/credit-cards/products/travelone-signature/",
            },
            {
                "card_name": "匯豐旅人輕旅卡",
                "official_url": "https://www.hsbc.com.tw/credit-cards/products/travelone/",
            },
            {
                "card_name": "卓越理財信用卡",
                "official_url": "https://www.hsbc.com.tw/credit-cards/products/premier/",
            },
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
        "list_url": "https://www.card.rakuten.com.tw/corp/product/",
        "cards": [
            {
                "card_name": "樂天信用卡",
                "official_url": "https://www.card.rakuten.com.tw/corp/product/",
            },
            {
                "card_name": "樂天 Panda J 卡",
                "official_url": "https://www.card.rakuten.com.tw/corp/product/",
            },
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
    "雙幣卡",
    "金卡/普卡",
    "白金卡",
    "推薦卡片",
    "熱門卡片",
    "精選卡片",
    "整併卡",
    "停發卡",
    "附卡",
    "適用信用卡",
    "世界卡/無限卡",
    "銀行卡",
    "聯名認同卡",
    "頂級卡",
    "百貨卡",
}

NON_CARD_KEYWORDS = (
    "掛失",
    "登錄",
    "理財",
    "分期",
    "繳費",
    "帳單",
    "客服",
    "常見問題",
    "優惠",
    "活動",
    "紅利",
    "點數",
    "小樹點",
    "推薦卡",
    "熱門卡",
    "精選卡",
    "所有卡",
    "全部卡",
    "整併卡",
    "簽帳金融卡",
    "金融卡",
    "debit",
    "預借現金",
    "額度",
    "密碼",
    "開卡",
    "年費",
    "循環利率",
    "注意事項",
    "權益",
    "總覽",
    "說明",
    "申請",
    "申辦",
    "辦卡",
    "查詢",
    "更多",
    "介紹",
    "首頁",
    "專區",
    "服務",
    "比較",
    "升級為",
    "公司卡",
    "採購卡",
)

NON_CARD_URL_TOKENS = (
    "/auth",
    "/signin",
    "/member",
    "/application",
    "/apply",
    "/ebank",
    "/activation",
    "/mgm/",
    "/ploan/",
    "/offers/",
    "/cardrights/",
    "/cardactivity",
    "reportlost",
    "lostcard",
    "loan",
    "bonus",
    "point",
    "promotion",
    "event",
    "faq",
    "fee",
    "interest",
    "login",
    "service",
    "debit",
    "discontinued",
    "stop-issue",
    "stop_issue",
)

SENTENCE_PUNCTUATION_RE = re.compile(r"[？?!！。，,;；]")


def is_valid_active_card_candidate(
    card_name: str,
    official_url: str = "",
    context: str = "",
    require_url: bool = False,
) -> bool:
    """Return True only when a candidate looks like an actual active credit card product."""
    text = re.sub(r"\s+", " ", (card_name or "")).strip()
    if not text or len(text) < 2 or len(text) > 24:
        return False
    if text in GENERIC_NAV_LABELS:
        return False
    if SENTENCE_PUNCTUATION_RE.search(text):
        return False
    if "卡" not in text and "card" not in text.lower():
        return False

    lowered = text.lower()
    if any(kw in lowered for kw in NON_CARD_KEYWORDS):
        return False

    if (
        detect_discontinued_marker(text)
        or detect_discontinued_marker(official_url)
        or detect_discontinued_marker(context)
    ):
        return False

    cleaned_url = (official_url or "").strip()
    if require_url and not cleaned_url:
        return False
    if cleaned_url:
        url_lower = cleaned_url.lower()
        if any(tok in url_lower for tok in NON_CARD_URL_TOKENS):
            return False

    return True


def normalize_card_query(text: str) -> str:
    """Normalize a card or bank name for deduplication and fuzzy matching."""
    nfkc = unicodedata.normalize("NFKC", text or "").replace("滙", "匯")
    cleaned = re.sub(r"[\s\-_@()（）【】「」]+", "", nfkc).lower()
    return cleaned.replace("信用卡", "").replace("卡", "")


def _bank_matches(bank_name_a: str, bank_name_b: str) -> bool:
    a = normalize_card_query(bank_name_a).replace("銀行", "")
    b = normalize_card_query(bank_name_b).replace("銀行", "")
    return bool(a and b and (a == b or a in b or b in a))


def _bank_card_dedup_key(card_name: str, bank_name: str) -> str:
    """Normalize card name within a specific bank so '玉山 U Bear' == 'U Bear'."""
    key = normalize_card_query(card_name)
    bank_short = normalize_card_query(bank_name).replace("銀行", "").replace("台北", "")
    if bank_short and key.startswith(bank_short) and len(key) > len(bank_short):
        key = key[len(bank_short):]
    return key


def _merge_cards_for_bank(
    bank: Dict,
    directory_rows: List[dict],
    all_db_cards: List[CardOut],
    resolved_lang: str,
) -> List[BankCardCatalogItem]:
    bank_name = bank["bank_name"]
    merged: Dict[str, BankCardCatalogItem] = {}

    # 1. Built-in curated catalog cards
    for entry in bank["cards"]:
        key = _bank_card_dedup_key(entry["card_name"], bank_name)
        merged[key] = BankCardCatalogItem(
            card_name=entry["card_name"],
            bank_name=bank_name,
            official_url=entry.get("official_url", ""),
            in_db=False,
            catalog_source="catalog",
        )

    # 2. Cards previously discovered via Playwright from the bank's overview page
    for row in directory_rows:
        if not is_valid_active_card_candidate(
            row["card_name"],
            row.get("official_url") or "",
            require_url=True,
        ):
            continue
        key = _bank_card_dedup_key(row["card_name"], bank_name)
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
    for card in all_db_cards:
        if not _bank_matches(card.bank_name, bank_name):
            continue
        key = _bank_card_dedup_key(card.card_name, bank_name)
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

    items = list(merged.values())
    if resolved_lang == "en":
        for item in items:
            item.card_name = translate_card_name(item.card_name, resolved_lang)
            item.bank_name = translate_bank_name(item.bank_name, resolved_lang)
    return items


def list_cards_for_bank(
    bank_code: str,
    db_path: Optional[Path] = None,
    lang: Optional[str] = None,
) -> Optional[List[BankCardCatalogItem]]:
    """Return merged card catalog for a bank (DB cards + Playwright-discovered + built-in)."""
    bank = BANK_BY_CODE.get(bank_code)
    if bank is None:
        return None

    resolved_lang = normalize_lang(lang)
    directory_rows = list_directory_cards(bank_code, db_path=db_path)
    all_db_cards = list_cards(db_path=db_path)
    return _merge_cards_for_bank(bank, directory_rows, all_db_cards, resolved_lang)


def list_bank_catalog(db_path: Optional[Path] = None, lang: Optional[str] = None) -> List[BankCatalogItem]:
    """Return all Taiwan issuing banks with current card counts using a single DB snapshot."""
    resolved_lang = normalize_lang(lang)
    all_db_cards, dir_by_bank = load_catalog_snapshot(db_path=db_path)
    items: List[BankCatalogItem] = []
    for bank in TAIWAN_BANKS:
        cards = _merge_cards_for_bank(
            bank,
            dir_by_bank.get(bank["bank_code"], []),
            all_db_cards,
            "zh-TW",
        )
        items.append(
            BankCatalogItem(
                bank_code=bank["bank_code"],
                bank_name=translate_bank_name(bank["bank_name"], resolved_lang),
                list_url=bank["list_url"],
                card_count=len(cards),
            )
        )
    return items


def extract_card_candidates_from_links(
    links: List[Tuple[str, ...]],
    base_url: str,
    require_url: bool = False,
) -> List[Dict[str, str]]:
    """Filter raw (text, href[, context]) tuples into actual active credit card products."""
    results: List[Dict[str, str]] = []
    seen = set()

    for item in links:
        raw_text = item[0] if len(item) > 0 else ""
        raw_href = item[1] if len(item) > 1 else ""
        raw_context = item[2] if len(item) > 2 else ""

        text = re.sub(r"\s+", " ", (raw_text or "")).strip()
        resolved_url = ""
        if raw_href and not raw_href.startswith(("javascript:", "#")):
            resolved_url = urljoin(base_url, raw_href)

        if not is_valid_active_card_candidate(
            text,
            resolved_url,
            context=raw_context,
            require_url=require_url,
        ):
            continue

        norm = normalize_card_query(text)
        if not norm or norm in seen:
            continue
        seen.add(norm)

        results.append({"card_name": text, "official_url": resolved_url})

    return results


def _filter_bank_links(
    raw_pairs: List[Tuple[str, ...]],
    base_url: str,
    link_include: List[str],
    link_exclude: List[str],
) -> List[Dict[str, str]]:
    """Apply bank-specific URL include/exclude rules before validating card candidates."""
    filtered: List[Tuple[str, ...]] = []
    for pair in raw_pairs:
        raw_href = pair[1] if len(pair) > 1 else ""
        if not raw_href or raw_href.startswith(("javascript:", "#")):
            continue
        resolved = urljoin(base_url, raw_href)
        lowered = resolved.lower()
        if link_include and not any(tok.lower() in lowered for tok in link_include):
            continue
        if link_exclude and any(tok.lower() in lowered for tok in link_exclude):
            continue
        filtered.append(pair)
    return extract_card_candidates_from_links(filtered, base_url, require_url=True)


async def discover_bank_cards_on_page(
    page: Page,
    bank_code: str,
    db_path: Optional[Path] = None,
    lang: Optional[str] = None,
) -> Optional[BankDiscoverResponse]:
    """Discover active cards for bank_code using an already-open Playwright Page."""
    bank = BANK_BY_CODE.get(bank_code)
    if bank is None:
        return None

    resolved_lang = normalize_lang(lang)
    list_urls: List[str] = bank.get("list_urls") or [bank["list_url"]]
    link_include: List[str] = bank.get("link_include") or []
    link_exclude: List[str] = bank.get("link_exclude") or []
    bank_name = bank["bank_name"]
    display_bank_name = translate_bank_name(bank_name, resolved_lang)
    discovered: List[Dict[str, str]] = []
    seen_norms = set()
    page_errors: List[Exception] = []

    for page_url in list_urls:
        try:
            await navigate_and_wait(page, page_url, timeout_ms=20000)

            raw_pairs = await page.evaluate(
                """(hasLinkFilter) => {
                    const isNavChrome = (el) => Boolean(
                        el.closest("header, nav, footer, [role='navigation']")
                    );
                    const genericLinkRe = /^(了解更多|瞭解更多|詳細介紹|信用卡介紹|卡片介紹|看更多|立即查看|更多資訊)$/;
                    const findCardBox = (el) => {
                        let cur = el.parentElement;
                        while (cur && cur !== document.body) {
                            if (cur.matches("li, article, [class*='card-list'], [class*='list-box'], [class*='card-item'], [class*='card_item'], [class*='card-box'], [class*='card-wrap'], [class*='product'], [class*='item'], [class*='box']")) {
                                if (cur.querySelector("a[href]")) return cur;
                            }
                            cur = cur.parentElement;
                        }
                        return el.closest("section");
                    };
                    const pickCardHref = (el, cardBox) => {
                        const ownHref = el.getAttribute("href") || "";
                        if (ownHref && !ownHref.startsWith("#") && !ownHref.startsWith("javascript:")) {
                            return ownHref;
                        }
                        if (!cardBox) return "";
                        const links = Array.from(cardBox.querySelectorAll("a[href]"))
                            .map((a) => ({
                                href: a.getAttribute("href") || "",
                                txt: (a.innerText || "").trim(),
                            }))
                            .filter((x) => x.href && !x.href.startsWith("#") && !x.href.startsWith("javascript:"));
                        const detail = links.find((x) => !/申辦|申請|apply/i.test(x.txt + x.href));
                        return (detail || links[0] || {}).href || "";
                    };
                    const pickCardName = (el, cardBox) => {
                        const firstLine = (el.innerText || "").split(/\\r?\\n/)[0].replace(/\\s+/g, " ").trim();
                        const boxTitle = cardBox
                            ? (cardBox.querySelector("h1, h2, h3, h4, [class*='card-title'], [class*='card_name'], [class*='title'], [class*='name']")?.innerText || "")
                                .split(/\\r?\\n/)[0]
                                .replace(/\\s+/g, " ")
                                .trim()
                            : "";
                        if ((!firstLine || genericLinkRe.test(firstLine) || firstLine.length > 24) && boxTitle) {
                            return boxTitle;
                        }
                        return firstLine;
                    };

                    const selector = hasLinkFilter
                        ? "a[href]"
                        : "main a, [role='main'] a, article a, [class*='card'] a, [class*='card'] h2, [class*='card'] h3, [class*='card'] h4, [class*='card-title'], [class*='card_name'], [class*='list-box'] p[class*='title'], [class*='list'] a";
                    const nodes = Array.from(document.querySelectorAll(selector)).slice(0, 450);

                    return nodes
                        .filter((el) => !isNavChrome(el))
                        .map((el) => {
                            const cardBox = findCardBox(el);
                            const name = pickCardName(el, cardBox);
                            const href = pickCardHref(el, cardBox);
                            const boxText = cardBox ? (cardBox.innerText || "").slice(0, 180) : "";
                            const sectionHeading = el.closest("section")?.querySelector("h1, h2, h3")?.innerText || "";
                            return [name, href, `${sectionHeading} ${boxText}`.trim()];
                        });
                }""",
                bool(link_include),
            )

            page_items = _filter_bank_links(
                [tuple(pair) for pair in raw_pairs],
                page_url,
                link_include,
                link_exclude,
            )
            for item in page_items:
                norm = normalize_card_query(item["card_name"])
                if norm and norm not in seen_norms:
                    seen_norms.add(norm)
                    discovered.append(item)
        except Exception as page_exc:
            page_errors.append(page_exc)

    if not discovered and page_errors and len(page_errors) == len(list_urls):
        exc = page_errors[0]
        cards = list_cards_for_bank(bank_code, db_path=db_path, lang=resolved_lang) or []
        return BankDiscoverResponse(
            bank_code=bank_code,
            bank_name=display_bank_name,
            status="error",
            message=(
                t_backend(
                    "discover_error",
                    resolved_lang,
                    bank_name=display_bank_name,
                    err=type(exc).__name__,
                    count=len(cards),
                )
                if resolved_lang == "en"
                else f"無法連線擷取「{bank_name}」官網卡片清單（{type(exc).__name__}），已保留現有清單。"
            ),
            cards=cards,
        )

    if not discovered:
        cards = list_cards_for_bank(bank_code, db_path=db_path, lang=resolved_lang) or []
        return BankDiscoverResponse(
            bank_code=bank_code,
            bank_name=display_bank_name,
            status="warning",
            message=(
                t_backend(
                    "discover_empty",
                    resolved_lang,
                    bank_name=display_bank_name,
                    count=len(cards),
                )
                if resolved_lang == "en"
                else f"已開啟「{bank_name}」官網但未解析出額外卡名（可能為動態渲染或防爬限制），已保留現有清單。"
            ),
            cards=cards,
        )

    replace_directory_cards(bank_code, bank_name, discovered, db_path=db_path)
    cards = list_cards_for_bank(bank_code, db_path=db_path, lang=resolved_lang) or []
    return BankDiscoverResponse(
        bank_code=bank_code,
        bank_name=display_bank_name,
        status="success",
        message=(
            t_backend(
                "discover_success",
                resolved_lang,
                bank_name=display_bank_name,
                count=len(discovered),
            )
            if resolved_lang == "en"
            else f"已從「{bank_name}」官網擷取 {len(discovered)} 張卡片名稱並合併至清單。"
        ),
        cards=cards,
    )


async def discover_bank_cards_via_playwright(
    bank_code: str,
    db_path: Optional[Path] = None,
    lang: Optional[str] = None,
) -> Optional[BankDiscoverResponse]:
    """Use Playwright Chromium to fetch additional active card names from the bank's overview page."""
    bank = BANK_BY_CODE.get(bank_code)
    if bank is None:
        return None

    resolved_lang = normalize_lang(lang)
    bank_name = bank["bank_name"]
    display_bank_name = translate_bank_name(bank_name, resolved_lang)

    try:
        async with open_scraper_page() as page:
            return await discover_bank_cards_on_page(page, bank_code, db_path=db_path, lang=resolved_lang)
    except ScraperBusyError:
        raise
    except Exception as exc:
        cards = list_cards_for_bank(bank_code, db_path=db_path, lang=resolved_lang) or []
        return BankDiscoverResponse(
            bank_code=bank_code,
            bank_name=display_bank_name,
            status="error",
            message=(
                t_backend(
                    "discover_error",
                    resolved_lang,
                    bank_name=display_bank_name,
                    err=type(exc).__name__,
                    count=len(cards),
                )
                if resolved_lang == "en"
                else f"無法連線擷取「{bank_name}」官網卡片清單（{type(exc).__name__}），已保留現有清單。"
            ),
            cards=cards,
        )
