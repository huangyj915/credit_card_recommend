"""Base Playwright scraper and Taiwanese credit-card text parsing utilities."""

from abc import ABC, abstractmethod
import re
from typing import Dict, List, Optional, Tuple

from playwright.async_api import Page

from app.channels import CHANNEL_MAP
from app.models import CardIn, RewardRuleIn


# Keyword -> standardized channel_code mapping for Taiwan bank pages
CHANNEL_KEYWORDS: List[Tuple[str, List[str]]] = [
    ("convenience_store", ["7-11", "7-eleven", "全家", "萊爾富", "ok超商", "超商"]),
    ("delivery", ["uber eats", "ubereats", "foodpanda", "外送"]),
    ("ecommerce", ["momo", "pchome", "蝦皮", "酷澎", "coupang", "網購", "網路消費", "電商", "amazon"]),
    ("mobile_pay", ["line pay", "街口", "apple pay", "全盈", "台灣pay", "行動支付", "台新pay"]),
    ("dining", ["餐飲", "餐廳", "美食", "王品", "星巴克", "咖啡"]),
    ("supermarket", ["全聯", "家樂福", "好市多", "costco", "大潤發", "超市", "量販"]),
    ("transport", ["高鐵", "台鐵", "捷運", "uber", "加油", "中油", "交通", "計程車"]),
    ("travel", ["機票", "航空", "飯店", "agoda", "booking", "klook", "kkday", "旅遊", "住宿", "旅行社"]),
    ("overseas", ["海外", "國外", "日本", "韓國", "日韓", "外幣", "實體消費"]),
]


def extract_percentage(text: str) -> Optional[float]:
    """Extract the primary/highest percentage rate from a Chinese/English rule snippet."""
    matches = re.findall(r"(\d+(?:\.\d+)?)\s*%", text)
    if not matches:
        return None
    values = [float(m) for m in matches if 0.0 < float(m) <= 30.0]
    return max(values) if values else None


def extract_monthly_cap(text: str) -> Optional[float]:
    """Extract monthly reward cap in NTD from phrases like '上限500元' or '每月最高300點'."""
    patterns = [
        r"(?:上限|最高)[^\d%]{0,8}(\d{1,3}(?:,\d{3})*|\d+)(?!\s*(?:\d|\.|%))\s*(?:元|點|ntd)?",
        r"(\d{1,3}(?:,\d{3})*|\d+)\s*(?:元|點)\s*(?:/月|每月|上限)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            raw = match.group(1).replace(",", "")
            return float(raw)
    return None


def detect_channels_from_text(text: str) -> List[str]:
    """Map descriptive Taiwanese merchant/channel text to standardized channel codes."""
    lowered = text.lower()
    found: List[str] = []
    for channel_code, keywords in CHANNEL_KEYWORDS:
        if any(kw in lowered for kw in keywords):
            found.append(channel_code)
    return found


def detect_payment_methods(text: str) -> List[str]:
    """Extract common payment methods mentioned in a rule block."""
    lowered = text.lower()
    candidates = [
        ("LINE Pay", "line pay"),
        ("Apple Pay", "apple pay"),
        ("街口支付", "街口"),
        ("全盈+PAY", "全盈"),
        ("台新Pay", "台新pay"),
        ("實體刷卡", "實體"),
        ("線上刷卡", "網購"),
    ]
    methods = [label for label, kw in candidates if kw in lowered]
    return methods or ["實體/線上刷卡"]


def build_rules_from_blocks(
    blocks: List[Dict[str, Optional[str]]],
) -> List[RewardRuleIn]:
    """Convert extracted DOM blocks (title, text, plan_name) into deduplicated RewardRuleIn items."""
    best_by_key: Dict[Tuple[str, Optional[str]], RewardRuleIn] = {}

    for block in blocks:
        raw_text = f"{block.get('title') or ''} {block.get('text') or ''}".strip()
        if not raw_text:
            continue
        rate = extract_percentage(raw_text)
        if rate is None:
            continue

        plan_name = block.get("plan_name")
        cap = extract_monthly_cap(raw_text)
        channels = detect_channels_from_text(raw_text)
        if not channels:
            channels = ["general"]

        methods = detect_payment_methods(raw_text)
        snippet = re.sub(r"\s+", " ", raw_text)[:120]

        for ch_code in channels:
            ch_label = CHANNEL_MAP[ch_code]["label"]
            rule = RewardRuleIn(
                channel_code=ch_code,
                channel_label=ch_label,
                plan_name=plan_name,
                rate=rate,
                monthly_cap_ntd=cap,
                payment_methods=methods,
                conditions=snippet,
            )
            key = (ch_code, plan_name)
            existing = best_by_key.get(key)
            if existing is None or rule.rate > existing.rate:
                best_by_key[key] = rule

    return list(best_by_key.values())


class BaseBankScraper(ABC):
    """Abstract Playwright scraper for a bank's official credit card introduction page."""

    bank_code: str = ""
    bank_name: str = ""
    card_name: str = ""
    card_slug: str = ""
    official_url: str = ""
    demo_html: str = ""

    async def scrape_live(self, page: Page, timeout_ms: int = 20000) -> CardIn:
        """Navigate to the live bank official URL and parse the page using Playwright."""
        await page.goto(self.official_url, wait_until="domcontentloaded", timeout=timeout_ms)
        # Allow dynamic JS sections a short window to render
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        return await self.parse_page(page, source_type="scraped")

    async def scrape_demo_html(self, page: Page) -> CardIn:
        """Load built-in sample bank HTML into Playwright Chromium to verify parsing locally."""
        await page.set_content(self.demo_html, wait_until="domcontentloaded")
        return await self.parse_page(page, source_type="scraped")

    @abstractmethod
    async def parse_page(self, page: Page, source_type: str = "scraped") -> CardIn:
        """Extract CardIn and RewardRuleIn list from the loaded Playwright Page."""
