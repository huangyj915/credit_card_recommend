"""Playwright scraper orchestrator and registry."""

from pathlib import Path
from typing import Dict, List, Optional

from playwright.async_api import async_playwright

from app.db import log_scrape, upsert_card
from app.models import ScrapeResultItem
from app.scrapers.base import BaseBankScraper
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


def list_available_scrapers() -> List[Dict[str, str]]:
    return [
        {
            "bank_code": code,
            "bank_name": scraper.bank_name,
            "card_name": scraper.card_name,
            "card_slug": scraper.card_slug,
            "official_url": scraper.official_url,
        }
        for code, scraper in SCRAPER_REGISTRY.items()
    ]


async def _launch_browser(p):
    """Launch Playwright Chromium, falling back to system Google Chrome if bundled browser is absent."""
    try:
        return await p.chromium.launch(headless=True)
    except Exception:
        return await p.chromium.launch(headless=True, channel="chrome")


async def run_scrapers(
    bank_codes: List[str],
    mode: str = "live",
    db_path: Optional[Path] = None,
) -> List[ScrapeResultItem]:
    """Execute selected bank Playwright scrapers and update SQLite on success."""
    results: List[ScrapeResultItem] = []

    async with async_playwright() as p:
        browser = await _launch_browser(p)
        context = await browser.new_context(
            user_agent=USER_AGENT,
            locale="zh-TW",
            viewport={"width": 1280, "height": 900},
        )

        try:
            for code in bank_codes:
                scraper = SCRAPER_REGISTRY.get(code)
                if scraper is None:
                    results.append(
                        ScrapeResultItem(
                            bank_code=code,
                            card_slug="",
                            status="error",
                            message=f"未知的銀行爬蟲代碼: {code}",
                        )
                    )
                    continue

                page = await context.new_page()
                try:
                    if mode == "demo_html":
                        card_data = await scraper.scrape_demo_html(page)
                    else:
                        card_data = await scraper.scrape_live(page)

                    if not card_data.rules:
                        msg = "頁面已開啟但未解析出結構化回饋規則（可能因官網改版、JS 動態載入或 WAF 阻擋），已保留既有資料。"
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
                    msg = f"成功透過 Playwright ({mode}) 解析並更新 {len(card_data.rules)} 條通路規則"
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
                    msg = f"爬取失敗：{type(exc).__name__}: {str(exc)[:180]}"
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
                    await page.close()
        finally:
            await context.close()
            await browser.close()

    return results
