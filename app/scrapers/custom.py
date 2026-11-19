"""Custom user-specified credit card Playwright scraper and URL discovery."""

import base64
import hashlib
import logging
from pathlib import Path
import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qs, quote_plus, urlparse

from playwright.async_api import Page

from app.catalog import (
    NON_CARD_URL_TOKENS,
    TAIWAN_BANKS,
    TAIWAN_BANK_HINTS,
    discover_bank_cards_on_page,
    list_cards_for_bank,
    normalize_card_query,
)
from app.db import list_cards, log_scrape, upsert_card
from app.i18n import (
    canonicalize_bank_name,
    canonicalize_card_name,
    normalize_lang,
    t_backend,
    translate_bank_name,
    translate_card_name,
)
from app.models import CardIn, CardOut, ScrapeResultItem
from app.scrapers.base import (
    build_rules_from_blocks,
    check_page_discontinued,
    collect_dom_text_blocks,
    detect_discontinued_marker,
    expand_hidden_tabs,
    extract_percentage,
    is_non_reward_snippet,
    navigate_and_wait,
    summarize_scraper_error,
    validate_public_http_url,
)

logger = logging.getLogger(__name__)
from app.scrapers.manager import (
    SCRAPER_REGISTRY,
    ScraperBusyError,
    open_scraper_page,
)

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


def infer_bank_name(url: str, page_title: str, explicit_bank: Optional[str]) -> str:
    """Infer Taiwan bank name from explicit input, URL domain, or page title."""
    if explicit_bank and explicit_bank.strip():
        return explicit_bank.strip()

    combined = f"{url} {page_title}".lower()
    for token, bank_label in TAIWAN_BANK_HINTS:
        if token in combined or bank_label in page_title:
            return bank_label

    return "自訂銀行"


def _bank_name_compatible(bank_query: str, bank_target: str) -> bool:
    return not bank_query or bank_query in bank_target or bank_target in bank_query


def match_builtin_scraper_code(card_name: str, bank_name: Optional[str] = None) -> Optional[str]:
    """Return matching SCRAPER_REGISTRY key if card_name refers to a dedicated scraper."""
    query = normalize_card_query(card_name)
    bank_query = normalize_card_query(bank_name or "")
    if not query:
        return None

    # 1. Exact match first
    for code, scraper in SCRAPER_REGISTRY.items():
        target = normalize_card_query(scraper.card_name)
        bank_target = normalize_card_query(scraper.bank_name)
        if target and target == query and _bank_name_compatible(bank_query, bank_target):
            return code

    # 2. Substring fallback only with >= 3-char minimum overlap
    if len(query) >= 3:
        for code, scraper in SCRAPER_REGISTRY.items():
            target = normalize_card_query(scraper.card_name)
            bank_target = normalize_card_query(scraper.bank_name)
            if (
                target
                and len(target) >= 3
                and (target in query or query in target)
                and _bank_name_compatible(bank_query, bank_target)
            ):
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

    cards = list_cards(db_path)

    # 1. Exact match first (including bank-prefix stripped match when bank_name is supplied)
    for card in cards:
        target = normalize_card_query(card.card_name)
        bank_target = normalize_card_query(card.bank_name)
        if not _bank_name_compatible(bank_query, bank_target):
            continue
        if target == query:
            return card
        if bank_query:
            bank_short = bank_query.replace("銀行", "").replace("台北", "")
            stripped_target = (
                target[len(bank_short) :]
                if bank_short and target.startswith(bank_short) and len(target) > len(bank_short)
                else target
            )
            if stripped_target == query:
                return card

    # 2. Substring fallback with >= 3-char minimum length to avoid cross-card overwrites
    if len(query) < 3:
        return None

    best_match: Optional[CardOut] = None
    best_overlap = 0
    for card in cards:
        target = normalize_card_query(card.card_name)
        bank_target = normalize_card_query(card.bank_name)
        if not target or len(target) < 3 or not _bank_name_compatible(bank_query, bank_target):
            continue
        if target in query or query in target:
            overlap = min(len(target), len(query))
            if overlap > best_overlap:
                best_overlap = overlap
                best_match = card
    return best_match


def _score_candidate_url(href: str, card_name: str, snippet_text: str = "") -> int:
    """Score search result URLs so official Taiwan bank card intro pages rank highest."""
    lowered = href.lower()
    snippet_lower = (snippet_text or "").lower()
    if any(
        skip in lowered
        for skip in (
            "bing.com",
            "microsoft.com",
            "duckduckgo.com",
            "google.com",
            "wikipedia.org",
        )
    ):
        return -100
    if any(tok in lowered for tok in NON_CARD_URL_TOKENS):
        return -100
    if any(auth_word in snippet_lower for auth_word in ("會員服務: 登入", "使用者密碼", "忘記密碼", "卡友登入")):
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

    norm_card = normalize_card_query(card_name)
    ascii_tokens = [t for t in re.findall(r"[a-z0-9]{2,}", card_name.lower()) if t not in ("card",)]
    zh_tokens = re.findall(r"[\u4e00-\u9fff]{2,}", card_name.replace("信用卡", ""))
    combined = f"{lowered} {snippet_lower}"
    has_card_match = (
        (norm_card and norm_card in normalize_card_query(combined))
        or any(t in combined for t in ascii_tokens)
        or any(t in combined for t in zh_tokens)
    )
    if not has_card_match:
        return -50

    score += 25
    return score


def unwrap_search_result_url(href: str) -> str:
    """Decode Bing /ck/a?...&u=a1<base64> redirect URLs to their actual destination."""
    if not href:
        return ""
    parsed = urlparse(href)
    if "bing.com" in (parsed.hostname or "").lower() and parsed.path.startswith("/ck/"):
        encoded = parse_qs(parsed.query).get("u", [""])[0]
        if encoded.startswith("a1") and len(encoded) > 2:
            payload = encoded[2:]
            payload += "=" * (-len(payload) % 4)
            try:
                decoded = base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8", errors="ignore")
                if decoded.startswith(("http://", "https://")):
                    return decoded
            except Exception:
                pass
    return href


def _match_bank_code_by_name(bank_name: Optional[str]) -> Optional[str]:
    if not bank_name:
        return None
    norm = normalize_card_query(bank_name).replace("銀行", "")
    if not norm:
        return None
    for bank in TAIWAN_BANKS:
        b_norm = normalize_card_query(bank["bank_name"]).replace("銀行", "")
        if norm == b_norm or norm in b_norm or b_norm in norm:
            return bank["bank_code"]
    return None


def _lookup_catalog_url(card_name: str, bank_name: Optional[str], db_path: Optional[Path]) -> Optional[str]:
    query = normalize_card_query(card_name)
    if not query:
        return None
    bank_code = _match_bank_code_by_name(bank_name)
    codes = [bank_code] if bank_code else [b["bank_code"] for b in TAIWAN_BANKS]
    for code in codes:
        if not code:
            continue
        for item in list_cards_for_bank(code, db_path=db_path) or []:
            if not item.official_url:
                continue
            target = normalize_card_query(item.card_name)
            if target and (target == query or target in query or query in target):
                return item.official_url
    return None


async def discover_official_url(
    page: Page,
    card_name: str,
    bank_name: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Use Playwright to search Bing for a card's official introduction URL.

    Returns (url, error_reason). Stops immediately without bypassing if blocked.
    """
    query = " ".join(part for part in [bank_name, card_name, "信用卡"] if part).strip()
    search_url = f"https://www.bing.com/search?q={quote_plus(query)}"

    try:
        response = await page.goto(search_url, wait_until="domcontentloaded", timeout=15000)
        if response is not None and response.status >= 400:
            return None, f"搜尋引擎回應異常（HTTP {response.status}）"
        snapshot = await page.evaluate(
            """() => {
                const bodyText = (document.body?.innerText || "").toLowerCase();
                const items = Array.from(document.querySelectorAll("li.b_algo")).slice(0, 15);
                const results = items.map((item) => {
                    const anchor = item.querySelector("h2 a");
                    return {
                        href: anchor ? (anchor.getAttribute("href") || "") : "",
                        snippet: (item.textContent || "").trim(),
                    };
                }).filter((x) => x.href);
                return { bodyText, results };
            }"""
        )
    except Exception as exc:
        return None, f"搜尋引擎連線失敗（{type(exc).__name__}）"

    body_text = snapshot.get("bodyText") or ""
    if any(marker in body_text for marker in SEARCH_BLOCK_MARKERS):
        return None, "搜尋引擎觸發驗證或防爬機制，無法自動搜尋"

    candidates: List[Tuple[int, str]] = []
    skipped_discontinued = 0
    for entry in snapshot.get("results") or []:
        href = unwrap_search_result_url(entry.get("href") or "")
        if not href:
            continue
        ok, _ = validate_public_http_url(href)
        if not ok:
            continue
        snippet_text = entry.get("snippet") or ""
        if detect_discontinued_marker(snippet_text) or detect_discontinued_marker(href):
            skipped_discontinued += 1
            continue
        score = _score_candidate_url(href, card_name, snippet_text)
        if score > 0:
            candidates.append((score, href))

    if not candidates:
        if skipped_discontinued > 0:
            return None, "搜尋結果顯示該信用卡可能已停發或停止申辦，已略過抓取"
        return None, "搜尋結果中找不到合適的銀行官網介紹頁"

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1], None


_PROMO_BASE_EXCLUDE_MARKERS = ("加碼", "最高", "活動", "新戶", "限時", "登錄", "指定")


def _is_clean_base_rate_snippet(text: str) -> bool:
    return not any(tok in text for tok in _PROMO_BASE_EXCLUDE_MARKERS)


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

    raw_texts = await collect_dom_text_blocks(
        page,
        "section, article, li, tr, dd, h2, h3, h4, h5, h6, [class*='benefit'], [class*='card'], [class*='reward'], [class*='promo'], [class*='info'], [class*='feature'], [class*='item'], p, div",
        max_items=120,
        include_hidden_tabs=True,
    )

    blocks: List[Dict[str, Optional[str]]] = []
    seen_texts = set()
    base_domestic = 0.5
    base_foreign = 0.5
    found_clean_domestic = False
    found_clean_foreign = False

    for text in raw_texts:
        if "%" not in text or len(text) < 6 or len(text) > 400 or text in seen_texts:
            continue
        seen_texts.add(text)
        if is_non_reward_snippet(text):
            continue

        is_clean = _is_clean_base_rate_snippet(text)
        if "一般消費" in text or "國內消費" in text:
            parsed_base = extract_percentage(text)
            if parsed_base is not None and parsed_base <= 5.0:
                if is_clean and not found_clean_domestic:
                    base_domestic = parsed_base
                    found_clean_domestic = True
                elif not found_clean_domestic:
                    base_domestic = parsed_base
        if "海外" in text or "國外" in text:
            parsed_foreign = extract_percentage(text)
            if parsed_foreign is not None and parsed_foreign <= 5.0:
                if is_clean and not found_clean_foreign:
                    base_foreign = parsed_foreign
                    found_clean_foreign = True
                elif not found_clean_foreign:
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
    lang: Optional[str] = None,
) -> ScrapeResultItem:
    """Scrape a user-specified credit card using Playwright and update SQLite."""
    resolved_lang = normalize_lang(lang)
    raw_name = card_name.strip()
    cleaned_name = canonicalize_card_name(raw_name)
    cleaned_bank = canonicalize_bank_name(bank_name) if bank_name and bank_name.strip() else None
    cleaned_url = official_url.strip() if official_url else None
    display_name = translate_card_name(cleaned_name, resolved_lang) if cleaned_name == raw_name or resolved_lang == "en" else raw_name

    if detect_discontinued_marker(cleaned_name):
        return ScrapeResultItem(
            bank_code="custom",
            card_slug="",
            status="warning",
            message=t_backend("custom_discontinued_query", resolved_lang, card_name=display_name),
            url=cleaned_url or "",
        )

    if cleaned_url:
        ok, err = validate_public_http_url(cleaned_url, lang=resolved_lang)
        if not ok:
            return ScrapeResultItem(
                bank_code="custom",
                card_slug="",
                status="error",
                message=t_backend("custom_url_invalid", resolved_lang, err=err),
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
    elif not target_url:
        target_url = _lookup_catalog_url(cleaned_name, cleaned_bank, db_path)

    if mode == "demo_html":
        if not matched_code:
            msg = t_backend("custom_demo_unsupported", resolved_lang, card_name=display_name)
            log_scrape("custom", target_slug, target_url or "", "warning", msg, 0, db_path=db_path)
            return ScrapeResultItem(
                bank_code="custom",
                card_slug=target_slug,
                status="warning",
                message=msg,
                url=target_url or "",
            )

    try:
        async with open_scraper_page(
            block_resources=(mode != "demo_html"),
            enforce_public_urls=(mode != "demo_html"),
        ) as page:
            try:
                if not target_url and mode == "live":
                    bank_code_hint = _match_bank_code_by_name(cleaned_bank)
                    if bank_code_hint:
                        await discover_bank_cards_on_page(
                            page, bank_code_hint, db_path=db_path, lang=resolved_lang
                        )
                        target_url = _lookup_catalog_url(cleaned_name, cleaned_bank, db_path)

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
                            msg = t_backend(
                                "custom_url_not_found",
                                resolved_lang,
                                card_name=display_name,
                                reason=reason,
                            )
                            log_scrape(bank_code, target_slug, "", "warning", msg, 0, db_path=db_path)
                            return ScrapeResultItem(
                                bank_code=bank_code,
                                card_slug=target_slug,
                                status="warning",
                                message=msg,
                            )
                        target_url = discovered

                    await navigate_and_wait(page, target_url, timeout_ms=20000)
                    if page.url.startswith(("http://", "https://")):
                        ok_final, err_final = validate_public_http_url(page.url, lang=resolved_lang)
                        if not ok_final:
                            raise RuntimeError(err_final)
                    await expand_hidden_tabs(page)

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
                    msg = t_backend(
                        "custom_discontinued_page",
                        resolved_lang,
                        card_name=translate_card_name(card_data.card_name, resolved_lang),
                        reason=discontinued_reason,
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
                    msg = t_backend(
                        "custom_no_rules",
                        resolved_lang,
                        card_name=translate_card_name(card_data.card_name, resolved_lang),
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
                msg = t_backend(
                    "custom_success",
                    resolved_lang,
                    bank_name=translate_bank_name(card_data.bank_name, resolved_lang),
                    card_name=translate_card_name(card_data.card_name, resolved_lang),
                    count=len(card_data.rules),
                )
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
                logger.warning("Custom card scrape '%s' failed: %s", cleaned_name, exc, exc_info=True)
                msg = t_backend(
                    "custom_error",
                    resolved_lang,
                    card_name=display_name,
                    exc_type=type(exc).__name__,
                    err=summarize_scraper_error(exc, resolved_lang),
                )
                log_scrape(bank_code, target_slug, target_url or "", "error", msg, 0, db_path=db_path)
                return ScrapeResultItem(
                    bank_code=bank_code,
                    card_slug=target_slug,
                    status="error",
                    message=msg,
                    url=target_url or "",
                )
    except ScraperBusyError:
        raise
