"""Base Playwright scraper and Taiwanese credit-card text parsing utilities."""

from abc import ABC, abstractmethod
import ipaddress
import re
import socket
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

from playwright.async_api import Page

from app.channels import CHANNEL_MAP
from app.i18n import normalize_lang
from app.models import CardIn, RewardRuleIn


def _is_public_ip(ip_obj: ipaddress._BaseAddress) -> bool:
    if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.ipv4_mapped is not None:
        ip_obj = ip_obj.ipv4_mapped
    return not (
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_reserved
        or ip_obj.is_multicast
        or ip_obj.is_unspecified
    )


def validate_public_http_url(
    raw_url: str,
    lang: Optional[str] = None,
    check_dns: bool = True,
) -> Tuple[bool, str]:
    """Ensure a URL is a public http(s) address and does not resolve to a local/private IP."""
    resolved_lang = normalize_lang(lang)
    is_en = resolved_lang == "en"
    try:
        parsed = urlparse((raw_url or "").strip())
    except ValueError:
        return False, "Invalid URL format" if is_en else "網址格式不正確"

    if parsed.scheme.lower() not in ("http", "https"):
        return False, "Only http or https URLs are supported" if is_en else "僅支援 http 或 https 開頭的網址"

    host = (parsed.hostname or "").lower()
    if not host:
        return False, "URL is missing a hostname" if is_en else "網址缺少主機名稱"
    if (
        host in ("localhost", "127.0.0.1", "::1", "0.0.0.0")
        or host.endswith(".local")
        or host.endswith(".internal")
    ):
        return (
            False,
            "Local or internal network URLs are not allowed" if is_en else "不允許存取本機或內部網路網址",
        )

    try:
        ip = ipaddress.ip_address(host)
        if not _is_public_ip(ip):
            return (
                False,
                "Private or reserved IP URLs are not allowed" if is_en else "不允許存取私有或保留 IP 網址",
            )
        return True, ""
    except ValueError:
        pass

    if check_dns:
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
        try:
            infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
            for info in infos:
                addr = info[4][0].split("%")[0]
                resolved_ip = ipaddress.ip_address(addr)
                if not _is_public_ip(resolved_ip):
                    return (
                        False,
                        "URL resolves to a private or internal IP address"
                        if is_en
                        else "網址解析結果為私有或內部網路 IP，已拒絕存取",
                    )
        except socket.gaierror:
            pass

    return True, ""


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
    ("overseas", ["海外", "國外", "日本", "韓國", "日韓", "外幣", "海外實體", "國外實體", "外幣實體"]),
]


DISCONTINUED_MARKERS = (
    "停發",
    "停止發行",
    "停止申辦",
    "不再受理",
    "已下架",
    "已終止",
    "終止發行",
    "停辦",
    "discontinued",
)

DISCONTINUED_BODY_PHRASES = (
    "本卡已停發",
    "本卡停止發行",
    "本卡已停止發行",
    "本卡已停止申辦",
    "本卡停止申辦",
    "已全面停發",
    "停止受理新卡",
    "不再受理新卡",
    "不再受理申辦",
    "信用卡已停發",
    "已停止新卡申辦",
    "本信用卡已停辦",
    "停止發行及申請",
    "停發暨換發公告",
)


def detect_discontinued_marker(text: str) -> Optional[str]:
    """Return matching discontinued marker if short label/context mentions card retirement."""
    lowered = (text or "").lower()
    for marker in DISCONTINUED_MARKERS:
        if marker in lowered:
            return marker
    return None


def detect_discontinued_in_page_fields(
    title: str = "",
    heading_text: str = "",
    badge_text: str = "",
    body_text: str = "",
    url: str = "",
) -> Optional[str]:
    """Detect whether a credit card page represents a discontinued card without menu false positives."""
    url_lower = (url or "").lower()
    if any(tok in url_lower for tok in ("discontinued", "stop-issue", "stop_issue", "停發")):
        return "網址標示停發"

    for field in (title, heading_text, badge_text):
        marker = detect_discontinued_marker(field)
        if marker:
            return marker

    body_lower = (body_text or "").lower()
    for phrase in DISCONTINUED_BODY_PHRASES:
        if phrase in body_lower:
            return phrase
    return None


async def check_page_discontinued(page: Page, url: str = "") -> Optional[str]:
    """Inspect a loaded Playwright Page to determine whether the card is discontinued."""
    snapshot = await page.evaluate(
        """() => {
            const title = document.title || "";
            const heading = Array.from(document.querySelectorAll("h1, main h2"))
                .slice(0, 5)
                .map((el) => el.innerText || "")
                .join(" ");
            const badges = Array.from(
                document.querySelectorAll("[class*='badge'], [class*='tag'], [class*='status'], [class*='notice'], [class*='alert']")
            )
                .slice(0, 15)
                .map((el) => el.innerText || "")
                .join(" ");
            const body = (document.body?.innerText || "").slice(0, 4000);
            return { title, heading, badges, body };
        }"""
    )
    return detect_discontinued_in_page_fields(
        title=snapshot.get("title", ""),
        heading_text=snapshot.get("heading", ""),
        badge_text=snapshot.get("badges", ""),
        body_text=snapshot.get("body", ""),
        url=url or page.url,
    )


NON_REWARD_SNIPPET_MARKERS = (
    "循環信用",
    "循環利率",
    "差別循環",
    "預借現金",
    "年利率",
    "總費用年百分率",
    "分期利率",
    "違約金",
    "滯納金",
    "活存年息",
    "優利活存",
    "熱門etf",
    "股票/etf",
    "手續費0.",
    "管理費",
)

_FEE_RATE_RE = re.compile(
    r"(?:手續費|服務費|管理費|年利率|循環(?:信用)?利率|分期利率|違約金)[^\d%\n]{0,12}\d+(?:\.\d+)?(?:\s*[~～\-]\s*\d+(?:\.\d+)?)?\s*%"
    r"|\d+(?:\.\d+)?\s*%\s*(?:服務費|管理費|年利率|手續費|違約金)"
)
_POSITIVE_RATE_RE = re.compile(
    r"(?:(?:回饋|現金|點數|小樹點|紅利|哩|折抵|加碼|最高|享)[^\d%\n]{0,10}(\d+(?:\.\d+)?)\s*%)"
    r"|(?:(\d+(?:\.\d+)?)\s*%[^\n]{0,10}(?:回饋|現金|點數|小樹點|紅利|哩|折抵|加碼))"
)
_ASCII_WORD_RE = re.compile(r"^[a-z0-9 ]+$")
_UBER_TRANSPORT_RE = re.compile(r"(?<![a-z0-9])uber(?!\s*eats|[a-z0-9])")


def is_non_reward_snippet(text: str) -> bool:
    """Return True if a scraped text block is an APR, fee, deposit, or ETF notice rather than a card reward."""
    lowered = (text or "").lower()
    if any(tok in lowered for tok in NON_REWARD_SNIPPET_MARKERS):
        return True
    if ("服務費" in lowered or "手續費" in lowered) and not any(
        tok in lowered for tok in ("回饋", "點", "現金", "紅利", "哩", "折抵")
    ):
        return True
    return False


def extract_percentage(text: str) -> Optional[float]:
    """Extract the primary/highest realistic reward percentage rate (<= 15%) from a rule snippet."""
    if is_non_reward_snippet(text):
        return None
    cleaned = _FEE_RATE_RE.sub(" ", text)

    positive_vals: List[float] = []
    for m in _POSITIVE_RATE_RE.finditer(cleaned):
        raw = m.group(1) or m.group(2)
        if raw:
            val = float(raw)
            if 0.0 < val <= 15.0:
                positive_vals.append(val)
    if positive_vals:
        return max(positive_vals)

    matches = re.findall(r"(\d+(?:\.\d+)?)\s*%", cleaned)
    if not matches:
        return None
    values = [float(m) for m in matches if 0.0 < float(m) <= 15.0]
    return max(values) if values else None


def extract_monthly_cap(text: str) -> Optional[float]:
    """Extract realistic monthly reward cap (>= 50 NTD) while ignoring '無上限', dates, and percentages."""
    patterns = [
        r"(?<!無)(?:每月)?(?:加碼)?(?:回饋)?(?:上限|最高)[^\d%\n]{0,10}?(?:NT\$|NTD|\$)?\s*(\d{1,3}(?:,\d{3})*|\d+)(?!\s*(?:\d|\.|%|/|年|次|筆|名|折))\s*(?:元|點|NTD|刷卡金)",
        r"(?<!無)(?:上限|最高)[^\d%\n]{0,8}(?:NT\$|NTD)\s*(\d{1,3}(?:,\d{3})*|\d+)(?!\s*(?:\d|\.|%|/|年|次|筆|名|折))",
        r"(?:NT\$|NTD|\$)?\s*(\d{1,3}(?:,\d{3})*|\d+)\s*(?:元|點|NTD)\s*(?:/月|每月|上限)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            val = float(match.group(1).replace(",", ""))
            if 50.0 <= val <= 100000.0:
                return val
    return None


def _keyword_matches(kw: str, lowered: str) -> bool:
    if kw == "uber":
        return bool(_UBER_TRANSPORT_RE.search(lowered))
    if _ASCII_WORD_RE.fullmatch(kw):
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", lowered))
    return kw in lowered


def detect_channels_from_text(text: str) -> List[str]:
    """Map descriptive Taiwanese merchant/channel text to standardized channel codes."""
    lowered = text.lower()
    found: List[str] = []
    for channel_code, keywords in CHANNEL_KEYWORDS:
        if any(_keyword_matches(kw, lowered) for kw in keywords):
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
        if not raw_text or is_non_reward_snippet(raw_text):
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
        clean_text = re.sub(r"\s+", " ", raw_text).strip()
        snippet = f"{clean_text[:119].rstrip()}…" if len(clean_text) > 120 else clean_text

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


class ScraperHttpStatusError(RuntimeError):
    """Raised when a scraped target responds with an HTTP error status (>= 400)."""

    def __init__(self, status: int, status_text: str = "", url: str = "") -> None:
        self.status = status
        self.status_text = status_text
        self.url = url
        super().__init__(f"HTTP {status} ({status_text or 'Error'}) for {url}")


def summarize_scraper_error(exc: Exception, lang: Optional[str] = None) -> str:
    """Return a safe, categorized error summary for public logs without exposing raw internals."""
    is_en = normalize_lang(lang) == "en"
    if isinstance(exc, ScraperHttpStatusError):
        return f"HTTP {exc.status}"
    exc_name = type(exc).__name__.lower()
    raw = str(exc).lower()
    if isinstance(exc, TimeoutError) or "timeout" in exc_name or "timed out" in raw:
        return "Request timed out" if is_en else "連線逾時"
    if any(
        tok in raw
        for tok in (
            "err_name_not_resolved",
            "err_connection",
            "err_aborted",
            "err_ssl",
            "err_cert",
            "net::",
        )
    ):
        return "Target site unreachable or blocked" if is_en else "目標網站無法連線或遭阻擋"
    if "private" in raw or "internal" in raw or "私有" in raw or "內部網路" in raw:
        return "Disallowed target URL" if is_en else "目標網址未通過安全驗證"
    return "Page fetch or parse error" if is_en else "頁面擷取或解析異常"


async def navigate_and_wait(page: Page, url: str, timeout_ms: int = 20000) -> None:
    """Navigate to url, verify HTTP status < 400, and give dynamic JS a brief settle window."""
    response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    if response is not None and response.status >= 400:
        raise ScraperHttpStatusError(response.status, response.status_text or "Error", url)
    try:
        await page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass


async def expand_hidden_tabs(page: Page, max_clicks: int = 10) -> None:
    """Click safe non-navigation tab/accordion toggles so lazy-rendered tab panels appear."""
    try:
        clicked = await page.evaluate(
            """(maxClicks) => {
                const toggles = Array.from(
                    document.querySelectorAll(
                        "[role='tab'], .nav-tabs button, .nav-tabs a, [data-bs-toggle='tab'], [data-toggle='tab'], [class*='accordion'] button"
                    )
                );
                let count = 0;
                for (const el of toggles) {
                    if (count >= maxClicks) break;
                    if (el.closest("header, nav, footer")) continue;
                    const href = (el.getAttribute("href") || "").trim();
                    if (href && !href.startsWith("#") && !href.startsWith("javascript:")) continue;
                    const style = window.getComputedStyle(el);
                    if (style.display === "none" || style.visibility === "hidden") continue;
                    try {
                        el.click();
                        count += 1;
                    } catch (_) {}
                }
                return count;
            }""",
            max_clicks,
        )
        if clicked:
            await page.wait_for_timeout(150)
    except Exception:
        pass


async def collect_dom_text_blocks(
    page: Page,
    selector: str,
    max_items: int = 120,
    include_hidden_tabs: bool = True,
) -> List[str]:
    """Collect deduplicated candidate text blocks containing '%' in a single IPC call."""
    return await page.evaluate(
        """({ selector, maxItems, includeHiddenTabs }) => {
            const root = document.querySelector("main, [role='main']") || document.body;
            if (!root) return [];
            const nodes = Array.from(root.querySelectorAll(selector));
            const out = [];
            const seen = new Set();
            const hiddenTabSel = "[role='tabpanel'], [class*='tab-pane'], [class*='tab-content'], [class*='tab_content'], [class*='accordion'], .collapse, [data-plan]";

            for (const el of nodes) {
                if (el.closest("header, nav, footer, script, style, noscript, template")) continue;
                const style = window.getComputedStyle(el);
                const isHidden = style.display === "none" || style.visibility === "hidden" || el.getClientRects().length === 0;
                if (isHidden && !(includeHiddenTabs && el.closest(hiddenTabSel))) continue;

                const raw = isHidden ? (el.textContent || "") : (el.innerText || el.textContent || "");
                const text = raw.replace(/\\s+/g, " ").trim();
                if (!text.includes("%") || text.length < 6 || text.length > 400 || seen.has(text)) continue;
                seen.add(text);
                out.push(text);
                if (out.length >= maxItems) break;
            }
            return out;
        }""",
        {
            "selector": selector,
            "maxItems": max_items,
            "includeHiddenTabs": include_hidden_tabs,
        },
    )


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
        await navigate_and_wait(page, self.official_url, timeout_ms=timeout_ms)
        await expand_hidden_tabs(page)
        return await self.parse_page(page, source_type="scraped")

    async def scrape_demo_html(self, page: Page) -> CardIn:
        """Load built-in sample bank HTML into Playwright Chromium to verify parsing locally."""
        await page.set_content(self.demo_html, wait_until="domcontentloaded")
        return await self.parse_page(page, source_type="scraped")

    @abstractmethod
    async def parse_page(self, page: Page, source_type: str = "scraped") -> CardIn:
        """Extract CardIn and RewardRuleIn list from the loaded Playwright Page."""
