"""Custom user-specified credit card Playwright scraper and URL discovery."""

import hashlib
import ipaddress
from pathlib import Path
import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

from playwright.async_api import Page, async_playwright

from app.catalog import TAIWAN_BANK_HINTS, normalize_card_query
from app.db import list_cards, log_scrape, upsert_card
from app.models import CardIn, CardOut, ScrapeResultItem
from app.scrapers.base import (
    build_rules_from_blocks,
    check_page_discontinued,
    detect_discontinued_marker,
    extract_percentage,
)
from app.scrapers.manager import SCRAPER_REGISTRY, USER_AGENT, _launch_browser

SEARCH_BLOCK_MARKERS = (
    "captcha",
    "unusual traffic",
    "verify you are human",
    "are you a robot",
    "cloudflare",
    "請進行人機驗證",
)


def build_custom_card_slug(card_name: str, bank_name: Optional[str] = None) -> str:
    """Create a stable, URL-safe slug for a custom card."""
    raw_key = f"{(bank_name or '').strip()}|{card_name.strip()}".lower()
    digest = hashlib.sha1(raw_key.encode("utf-8")).hexdigest()[:8]
    ascii_part = re.sub(r"[^a-z0-9]+", "-", card_name.lower()).strip("-")
    if ascii_part:
        return f"custom-{ascii_part[:24]}-{digest}"
    return f"custom-{digest}"


def validate_public_http_url(raw_url: str) -> Tuple[bool, str]:
    """Ensure a URL is a public http(s) address and not a local/private target."""
    try:
        parsed = urlparse(raw_url.strip())
    except ValueError:
        return False, "網址格式不正確"

    if parsed.scheme not in ("http", "https"):
        return False, "僅支援 http 或 https 開頭的網址"

    host = (parsed.hostname or "").lower()
    if not host:
        return False, "網址缺少主機名稱"
    if host in ("localhost", "127.0.0.1", "::1") or host.endswith(".local"):
        return False, "不允許存取本機或內部網路網址"

    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False, "不允許存取私有或保留 IP 網址"
    except ValueError:
        pass

    return True, ""


def infer_bank_name(url: str, page_title: str, explicit_bank: Optional[str]) -> str:
    """Infer Taiwan bank name from explicit input, URL domain, or page title."""
    if explicit_bank and explicit_bank.strip():
        return explicit_bank.strip()

    combined = f"{url} {page_title}".lower()
    for token, bank_label in TAIWAN_BANK_HINTS:
        if token in combined or bank_label in page_title:
            return bank_label

    return "自訂銀行"


def match_builtin_scraper_code(card_name: str, bank_name: Optional[str] = None) -> Optional[str]:
    """Return matching SCRAPER_REGISTRY key if card_name refers to a dedicated scraper."""
    query = normalize_card_query(card_name)
    bank_query = normalize_card_query(bank_name or "")
    if not query:
        return None

    for code, scraper in SCRAPER_REGISTRY.items():
        target = normalize_card_query(scraper.card_name)
        bank_target = normalize_card_query(scraper.bank_name)
        if target and (target in query or query in target):
            if not bank_query or bank_query in bank_target or bank_target in bank_query:
                return code
    return None


def match_existing_card(
    card_name: str,
    bank_name: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> Optional[CardOut]:
    """Find an existing database card matching the entered card name."""
    query = normalize_card_query(card_name)
    bank_query = normalize_card_query(bank_name or "")
    if not query:
        return None

    for card in list_cards(db_path):
        target = normalize_card_query(card.card_name)
        bank_target = normalize_card_query(card.bank_name)
        if target and (target == query or target in query or query in target):
            if not bank_query or bank_query in bank_target or bank_target in bank_query:
                return card
    return None


def _score_candidate_url(href: str, card_name: str) -> int:
    """Score search result URLs so official Taiwan bank pages rank highest."""
    lowered = href.lower()
    if any(skip in lowered for skip in ("bing.com", "microsoft.com", "duckduckgo.com", "google.com")):
        return -100
    score = 0
    if ".com.tw" in lowered:
        score += 30
    if "credit" in lowered or "card" in lowered:
        score += 20
    for token, _ in TAIWAN_BANK_HINTS:
        if token in lowered:
            score += 50
            break
    if any(word in lowered for word in ("blog", "pixnet", "dcard", "ptt.cc", "facebook", "youtube")):
        score -= 25
    if normalize_card_query(card_name) and normalize_card_query(card_name) in lowered:
        score += 10
    return score


async def discover_official_url(
    page: Page,
    card_name: str,
    bank_name: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Use Playwright to search Bing for a card's official introduction URL.

    Returns (url, error_reason). Stops immediately without bypassing if blocked.
    """
    query = " ".join(part for part in [bank_name, card_name, "信用卡", "回饋"] if part).strip()
    search_url = f"https://www.bing.com/search?q={query}"

    try:
        await page.goto(search_url, wait_until="domcontentloaded", timeout=15000)
        body_text = (await page.locator("body").inner_text()).lower()
    except Exception as exc:
        return None, f"搜尋引擎連線失敗（{type(exc).__name__}）"

    if any(marker in body_text for marker in SEARCH_BLOCK_MARKERS):
        return None, "搜尋引擎觸發驗證或防爬機制，無法自動搜尋"

    links = page.locator("li.b_algo")
    count = min(await links.count(), 15)
    candidates: List[Tuple[int, str]] = []
    skipped_discontinued = 0
    for i in range(count):
        item = links.nth(i)
        anchor = item.locator("h2 a").first
        if await anchor.count() == 0:
            continue
        href = await anchor.get_attribute("href")
        if not href:
            continue
        ok, _ = validate_public_http_url(href)
        if not ok:
            continue
        snippet_text = (await item.inner_text()).strip()
        if detect_discontinued_marker(snippet_text) or detect_discontinued_marker(href):
            skipped_discontinued += 1
            continue
        score = _score_candidate_url(href, card_name)
        if score > 0:
            candidates.append((score, href))

    if not candidates:
        if skipped_discontinued > 0:
            return None, "搜尋結果顯示該信用卡可能已停發或停止申辦，已略過抓取"
        return None, "搜尋結果中找不到合適的銀行官網介紹頁"

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1], None


async def parse_generic_card_page(
    page: Page,
    card_name: str,
    official_url: str,
    bank_name: Optional[str] = None,
    card_slug: Optional[str] = None,
    annual_fee: str = "依銀行官網公告",
    reward_unit: str = "現金回饋 / 點數",
) -> CardIn:
    """Extract standardized reward rules from any loaded credit card web page."""
    title = (await page.title()).strip()
    resolved_bank = infer_bank_name(official_url, title, bank_name)
    resolved_slug = card_slug or build_custom_card_slug(card_name, resolved_bank)

    blocks: List[Dict[str, Optional[str]]] = []
    seen_texts = set()
    candidates = page.locator(
        "section, article, li, tr, [class*='benefit'], [class*='card'], "
        "[class*='reward'], [class*='promo'], p"
    )
    count = min(await candidates.count(), 150)

    base_domestic = 0.5
    base_foreign = 0.5

    for i in range(count):
        text = re.sub(r"\s+", " ", (await candidates.nth(i).inner_text())).strip()
        if "%" not in text or len(text) < 6 or len(text) > 400 or text in seen_texts:
            continue
        seen_texts.add(text)

        if "一般消費" in text or "國內消費" in text:
            parsed_base = extract_percentage(text)
            if parsed_base is not None and parsed_base <= 5.0:
                base_domestic = parsed_base
        if "海外" in text or "國外" in text:
            parsed_foreign = extract_percentage(text)
            if parsed_foreign is not None and parsed_foreign <= 5.0:
                base_foreign = parsed_foreign

        blocks.append({"plan_name": None, "title": "", "text": text})

    rules = build_rules_from_blocks(blocks)
    return CardIn(
        bank_name=resolved_bank,
        card_name=card_name.strip(),
        card_slug=resolved_slug,
        official_url=official_url,
        annual_fee=annual_fee,
        base_rate_domestic=base_domestic,
        base_rate_foreign=base_foreign,
        reward_unit=reward_unit,
        notes=f"透過 Playwright 依使用者指定卡名爬取解析（來源：{official_url}）。",
        source_type="scraped",
        rules=rules,
    )


async def scrape_custom_card(
    card_name: str,
    bank_name: Optional[str] = None,
    official_url: Optional[str] = None,
    mode: str = "live",
    db_path: Optional[Path] = None,
) -> ScrapeResultItem:
    """Scrape a user-specified credit card using Playwright and update SQLite."""
    cleaned_name = card_name.strip()
    cleaned_bank = bank_name.strip() if bank_name else None
    cleaned_url = official_url.strip() if official_url else None

    if detect_discontinued_marker(cleaned_name):
        return ScrapeResultItem(
            bank_code="custom",
            card_slug="",
            status="warning",
            message=f"「{cleaned_name}」標示為停發／停止申辦卡片，已依設定略過不抓取。",
            url=cleaned_url or "",
        )

    if cleaned_url:
        ok, err = validate_public_http_url(cleaned_url)
        if not ok:
            return ScrapeResultItem(
                bank_code="custom",
                card_slug="",
                status="error",
                message=f"網址驗證失敗：{err}",
                url=cleaned_url,
            )

    matched_code = match_builtin_scraper_code(cleaned_name, cleaned_bank)
    existing_card = match_existing_card(cleaned_name, cleaned_bank, db_path=db_path)

    target_url = cleaned_url
    target_slug = existing_card.card_slug if existing_card else build_custom_card_slug(cleaned_name, cleaned_bank)
    bank_code = matched_code or "custom"

    if not target_url and matched_code:
        target_url = SCRAPER_REGISTRY[matched_code].official_url
        target_slug = SCRAPER_REGISTRY[matched_code].card_slug
    elif not target_url and existing_card and existing_card.official_url:
        target_url = existing_card.official_url

    if mode == "demo_html":
        if not matched_code:
            msg = (
                f"「{cleaned_name}」屬於自訂新卡片，沒有內建離線示範 HTML；"
                "請改用即時爬取（live），或直接提供該卡官網網址進行測試。"
            )
            log_scrape("custom", target_slug, target_url or "", "warning", msg, 0, db_path=db_path)
            return ScrapeResultItem(
                bank_code="custom",
                card_slug=target_slug,
                status="warning",
                message=msg,
                url=target_url or "",
            )

    async with async_playwright() as p:
        browser = await _launch_browser(p)
        context = await browser.new_context(
            user_agent=USER_AGENT,
            locale="zh-TW",
            viewport={"width": 1280, "height": 900},
        )
        page = await context.new_page()
        try:
            if matched_code and not cleaned_url:
                scraper = SCRAPER_REGISTRY[matched_code]
                card_data = (
                    await scraper.scrape_demo_html(page)
                    if mode == "demo_html"
                    else await scraper.scrape_live(page)
                )
            else:
                if not target_url:
                    discovered, reason = await discover_official_url(page, cleaned_name, cleaned_bank)
                    if not discovered:
                        msg = (
                            f"無法自動定位「{cleaned_name}」的官網頁面（{reason}），"
                            "請於下方補填該卡的「官方介紹頁網址」再試一次。"
                        )
                        log_scrape(bank_code, target_slug, "", "warning", msg, 0, db_path=db_path)
                        return ScrapeResultItem(
                            bank_code=bank_code,
                            card_slug=target_slug,
                            status="warning",
                            message=msg,
                        )
                    target_url = discovered

                await page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass

                card_data = await parse_generic_card_page(
                    page=page,
                    card_name=existing_card.card_name if existing_card else cleaned_name,
                    official_url=target_url,
                    bank_name=cleaned_bank or (existing_card.bank_name if existing_card else None),
                    card_slug=target_slug,
                    annual_fee=existing_card.annual_fee if existing_card else "依銀行官網公告",
                    reward_unit=existing_card.reward_unit if existing_card else "現金回饋 / 點數",
                )

            discontinued_reason = await check_page_discontinued(page, target_url or "")
            if discontinued_reason:
                msg = (
                    f"偵測到「{card_data.card_name}」已停發或停止申辦（{discontinued_reason}），"
                    "已略過不寫入資料庫。"
                )
                log_scrape(
                    bank_code,
                    card_data.card_slug,
                    target_url or "",
                    "warning",
                    msg,
                    0,
                    db_path=db_path,
                )
                return ScrapeResultItem(
                    bank_code=bank_code,
                    card_slug=card_data.card_slug,
                    status="warning",
                    message=msg,
                    url=target_url or "",
                )

            if not card_data.rules:
                msg = (
                    f"已開啟頁面但未解析出「{card_data.card_name}」的結構化回饋規則"
                    "（可能因官網改版、JS 動態載入或防爬阻擋），未更動既有資料。"
                )
                log_scrape(bank_code, card_data.card_slug, target_url or "", "warning", msg, 0, db_path=db_path)
                return ScrapeResultItem(
                    bank_code=bank_code,
                    card_slug=card_data.card_slug,
                    status="warning",
                    message=msg,
                    url=target_url or "",
                )

            upsert_card(card_data, db_path=db_path)
            msg = f"成功透過 Playwright 解析並更新「{card_data.bank_name} {card_data.card_name}」共 {len(card_data.rules)} 條通路規則"
            log_scrape(
                bank_code,
                card_data.card_slug,
                target_url or card_data.official_url,
                "success",
                msg,
                len(card_data.rules),
                db_path=db_path,
            )
            return ScrapeResultItem(
                bank_code=bank_code,
                card_slug=card_data.card_slug,
                status="success",
                message=msg,
                rules_count=len(card_data.rules),
                url=target_url or card_data.official_url,
            )
        except Exception as exc:
            msg = f"爬取「{cleaned_name}」失敗：{type(exc).__name__}: {str(exc)[:180]}"
            log_scrape(bank_code, target_slug, target_url or "", "error", msg, 0, db_path=db_path)
            return ScrapeResultItem(
                bank_code=bank_code,
                card_slug=target_slug,
                status="error",
                message=msg,
                url=target_url or "",
            )
        finally:
            await page.close()
            await context.close()
            await browser.close()
