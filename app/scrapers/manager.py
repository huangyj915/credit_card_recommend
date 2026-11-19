"""Playwright scraper orchestrator and registry."""

import asyncio
from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
import sys
from typing import AsyncIterator, Dict, List, Optional
from urllib.parse import urlparse
from weakref import WeakKeyDictionary

from playwright.async_api import BrowserContext, Page, async_playwright

from app.db import log_scrape, upsert_card
from app.i18n import normalize_lang, t_backend, translate_bank_name, translate_card_name
from app.models import ScrapeResultItem
from app.scrapers.base import (
    BaseBankScraper,
    check_page_discontinued,
    summarize_scraper_error,
    validate_public_http_url,
)

logger = logging.getLogger(__name__)
from app.scrapers.banks.cathay import CathayCubeScraper
from app.scrapers.banks.esun import EsunUBearScraper
from app.scrapers.banks.taishin import TaishinGogoScraper

SCRAPER_REGISTRY: Dict[str, BaseBankScraper] = {
    "cathay": CathayCubeScraper(),
    "esun": EsunUBearScraper(),
    "taishin": TaishinGogoScraper(),
}

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)

BLOCKED_RESOURCE_TYPES = frozenset({"image", "media", "font"})
BLOCKED_TRACKING_DOMAINS = (
    "google-analytics.com",
    "analytics.google.com",
    "googletagmanager.com",
    "doubleclick.net",
    "googleadservices.com",
    "googlesyndication.com",
    "connect.facebook.net",
    "facebook.net",
    "hotjar.com",
    "clarity.ms",
)

_BROWSER_LAUNCH_ARGS = ["--disable-dev-shm-usage"]
_CACHED_CHANNEL: Optional[str] = None  # None = unprobed, "" = bundled chromium, "chrome" = system chrome


class ScraperBusyError(RuntimeError):
    """Raised when a Playwright scraper slot is already in use."""


def list_available_scrapers(lang: Optional[str] = None) -> List[Dict[str, str]]:
    resolved_lang = normalize_lang(lang)
    return [
        {
            "bank_code": code,
            "bank_name": translate_bank_name(scraper.bank_name, resolved_lang),
            "card_name": translate_card_name(scraper.card_name, resolved_lang),
            "card_slug": scraper.card_slug,
            "official_url": scraper.official_url,
        }
        for code, scraper in SCRAPER_REGISTRY.items()
    ]


_PLAYWRIGHT_SEMAPHORES: "WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore]" = WeakKeyDictionary()


def get_playwright_semaphore() -> asyncio.Semaphore:
    """Return a per-event-loop semaphore limiting Playwright to 1 concurrent browser."""
    loop = asyncio.get_running_loop()
    sem = _PLAYWRIGHT_SEMAPHORES.get(loop)
    if sem is None:
        sem = asyncio.Semaphore(1)
        _PLAYWRIGHT_SEMAPHORES[loop] = sem
    return sem


@asynccontextmanager
async def acquire_playwright_slot() -> AsyncIterator[None]:
    """Acquire the single Playwright concurrency slot or fail fast with ScraperBusyError."""
    sem = get_playwright_semaphore()
    if sem.locked():
        raise ScraperBusyError("Playwright scraper is currently busy.")
    async with sem:
        yield


def _build_user_agent(browser_version: str) -> str:
    """Construct a User-Agent matching the actual Chromium version and host OS platform."""
    ver = (browser_version or "").strip() or "134.0.0.0"
    if sys.platform == "darwin":
        platform_tok = "Macintosh; Intel Mac OS X 10_15_7"
    elif sys.platform.startswith("win"):
        platform_tok = "Windows NT 10.0; Win64; x64"
    else:
        platform_tok = "X11; Linux x86_64"
    return (
        f"Mozilla/5.0 ({platform_tok}) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{ver} Safari/537.36"
    )


async def _launch_browser(p):
    """Launch Chromium using PLAYWRIGHT_CHANNEL or a once-cached chrome/bundled fallback."""
    global _CACHED_CHANNEL
    env_channel = os.getenv("PLAYWRIGHT_CHANNEL", "").strip().lower()
    if env_channel in ("bundled", "chromium", "none"):
        return await p.chromium.launch(headless=True, args=_BROWSER_LAUNCH_ARGS)
    if env_channel:
        return await p.chromium.launch(
            headless=True, channel=env_channel, args=_BROWSER_LAUNCH_ARGS
        )

    if _CACHED_CHANNEL is not None:
        if _CACHED_CHANNEL:
            return await p.chromium.launch(
                headless=True, channel=_CACHED_CHANNEL, args=_BROWSER_LAUNCH_ARGS
            )
        return await p.chromium.launch(headless=True, args=_BROWSER_LAUNCH_ARGS)

    try:
        browser = await p.chromium.launch(
            headless=True, channel="chrome", args=_BROWSER_LAUNCH_ARGS
        )
        _CACHED_CHANNEL = "chrome"
        return browser
    except Exception:
        _CACHED_CHANNEL = ""
        return await p.chromium.launch(headless=True, args=_BROWSER_LAUNCH_ARGS)


def _is_blocked_tracking_host(host: str) -> bool:
    return any(host == dom or host.endswith(f".{dom}") for dom in BLOCKED_TRACKING_DOMAINS)


async def _install_context_routes(
    context: BrowserContext,
    block_resources: bool = True,
    enforce_public_urls: bool = True,
) -> None:
    async def _handle_route(route) -> None:
        req = route.request
        if block_resources and req.resource_type in BLOCKED_RESOURCE_TYPES:
            await route.abort()
            return

        parsed = urlparse(req.url)
        scheme = parsed.scheme.lower()
        if scheme in ("http", "https"):
            host = (parsed.hostname or "").lower()
            if block_resources and _is_blocked_tracking_host(host):
                await route.abort()
                return
            if enforce_public_urls:
                ok, _ = validate_public_http_url(req.url, check_dns=req.is_navigation_request())
                if not ok:
                    await route.abort()
                    return

        await route.continue_()

    await context.route("**/*", _handle_route)


@asynccontextmanager
async def open_scraper_context(
    default_timeout_ms: int = 20000,
    block_resources: bool = True,
    enforce_public_urls: bool = True,
) -> AsyncIterator[BrowserContext]:
    """Acquire Playwright slot, launch Chromium with resource/SSRF guards, and guarantee cleanup."""
    async with acquire_playwright_slot():
        async with async_playwright() as p:
            browser = None
            context = None
            try:
                browser = await _launch_browser(p)
                ua = _build_user_agent(getattr(browser, "version", ""))
                context = await browser.new_context(
                    user_agent=ua,
                    locale="zh-TW",
                    timezone_id="Asia/Taipei",
                    viewport={"width": 1280, "height": 900},
                )
                context.set_default_timeout(default_timeout_ms)
                await _install_context_routes(
                    context,
                    block_resources=block_resources,
                    enforce_public_urls=enforce_public_urls,
                )
                yield context
            finally:
                if context is not None:
                    try:
                        await context.close()
                    except Exception:
                        pass
                if browser is not None:
                    try:
                        await browser.close()
                    except Exception:
                        pass


@asynccontextmanager
async def open_scraper_page(
    default_timeout_ms: int = 20000,
    block_resources: bool = True,
    enforce_public_urls: bool = True,
) -> AsyncIterator[Page]:
    """Open a single guarded Playwright Page and guarantee full Browser/Context/Page cleanup."""
    async with open_scraper_context(
        default_timeout_ms=default_timeout_ms,
        block_resources=block_resources,
        enforce_public_urls=enforce_public_urls,
    ) as context:
        page = await context.new_page()
        try:
            yield page
        finally:
            try:
                await page.close()
            except Exception:
                pass


async def run_scrapers(
    bank_codes: List[str],
    mode: str = "live",
    db_path: Optional[Path] = None,
    lang: Optional[str] = None,
) -> List[ScrapeResultItem]:
    """Execute selected bank Playwright scrapers and update SQLite on success."""
    resolved_lang = normalize_lang(lang)
    results: List[ScrapeResultItem] = []

    async with open_scraper_context(
        block_resources=(mode != "demo_html"),
        enforce_public_urls=(mode != "demo_html"),
    ) as context:
        for code in bank_codes:
            scraper = SCRAPER_REGISTRY.get(code)
            if scraper is None:
                results.append(
                    ScrapeResultItem(
                        bank_code=code,
                        card_slug="",
                        status="error",
                        message=t_backend("unknown_bank_code", resolved_lang, code=code),
                    )
                )
                continue

            page = await context.new_page()
            try:
                if mode == "demo_html":
                    card_data = await scraper.scrape_demo_html(page)
                else:
                    card_data = await scraper.scrape_live(page)

                discontinued_reason = await check_page_discontinued(page, scraper.official_url)
                if discontinued_reason:
                    msg = t_backend(
                        "scraper_discontinued",
                        resolved_lang,
                        bank_name=translate_bank_name(scraper.bank_name, resolved_lang),
                        card_name=translate_card_name(scraper.card_name, resolved_lang),
                        reason=discontinued_reason,
                    )
                    log_scrape(
                        bank_code=code,
                        card_slug=scraper.card_slug,
                        url=scraper.official_url,
                        status="warning",
                        message=msg,
                        rules_count=0,
                        db_path=db_path,
                    )
                    results.append(
                        ScrapeResultItem(
                            bank_code=code,
                            card_slug=scraper.card_slug,
                            status="warning",
                            message=msg,
                            rules_count=0,
                            url=scraper.official_url,
                        )
                    )
                    continue

                if not card_data.rules:
                    msg = t_backend("scraper_no_rules", resolved_lang)
                    log_scrape(
                        bank_code=code,
                        card_slug=scraper.card_slug,
                        url=scraper.official_url,
                        status="warning",
                        message=msg,
                        rules_count=0,
                        db_path=db_path,
                    )
                    results.append(
                        ScrapeResultItem(
                            bank_code=code,
                            card_slug=scraper.card_slug,
                            status="warning",
                            message=msg,
                            rules_count=0,
                            url=scraper.official_url,
                        )
                    )
                    continue

                upsert_card(card_data, db_path=db_path)
                msg = t_backend(
                    "scraper_success",
                    resolved_lang,
                    mode=mode,
                    count=len(card_data.rules),
                )
                log_scrape(
                    bank_code=code,
                    card_slug=scraper.card_slug,
                    url=scraper.official_url,
                    status="success",
                    message=msg,
                    rules_count=len(card_data.rules),
                    db_path=db_path,
                )
                results.append(
                    ScrapeResultItem(
                        bank_code=code,
                        card_slug=scraper.card_slug,
                        status="success",
                        message=msg,
                        rules_count=len(card_data.rules),
                        url=scraper.official_url,
                    )
                )
            except Exception as exc:
                logger.warning("Bank scraper '%s' failed: %s", code, exc, exc_info=True)
                msg = t_backend(
                    "scraper_error",
                    resolved_lang,
                    exc_type=type(exc).__name__,
                    err=summarize_scraper_error(exc, resolved_lang),
                )
                log_scrape(
                    bank_code=code,
                    card_slug=scraper.card_slug,
                    url=scraper.official_url,
                    status="error",
                    message=msg,
                    rules_count=0,
                    db_path=db_path,
                )
                results.append(
                    ScrapeResultItem(
                        bank_code=code,
                        card_slug=scraper.card_slug,
                        status="error",
                        message=msg,
                        rules_count=0,
                        url=scraper.official_url,
                    )
                )
            finally:
                try:
                    await page.close()
                except Exception:
                    pass

    return results
