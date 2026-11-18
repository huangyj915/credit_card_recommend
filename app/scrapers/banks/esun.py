"""Playwright scraper for E.SUN Bank (玉山銀行 U Bear 信用卡)."""

from typing import Dict, List, Optional
from playwright.async_api import Page

from app.models import CardIn
from app.scrapers.base import BaseBankScraper, build_rules_from_blocks, extract_percentage


class EsunUBearScraper(BaseBankScraper):
    bank_code = "esun"
    bank_name = "玉山銀行"
    card_name = "U Bear 信用卡"
    card_slug = "esun-ubear"
    official_url = (
        "https://www.esunbank.com/zh-tw/personal/credit-card/intro/bank-card/u-bear"
    )

    demo_html = """
    <!doctype html>
    <html lang="zh-Hant">
    <head><title>玉山 U Bear 信用卡</title></head>
    <body>
      <main>
        <h1>玉山 U Bear 信用卡</h1>
        <p class="base-rate">一般消費享 1% 現金回饋無上限，當期帳單直接折抵。</p>
        <div class="benefit-list">
          <div class="benefit-item">網購電商（momo、蝦皮、PChome）網路消費享 3% 現金回饋，每月加碼上限 200 元</div>
          <div class="benefit-item">行動支付綁定 LINE Pay、街口支付消費享 3% 現金回饋，上限 200 元</div>
          <div class="benefit-item">Uber Eats、foodpanda 外送平台享 3% 回饋，上限 200 元</div>
        </div>
      </main>
    </body>
    </html>
    """

    async def parse_page(self, page: Page, source_type: str = "scraped") -> CardIn:
        blocks: List[Dict[str, Optional[str]]] = []

        items = page.locator(".benefit-item, section, article, li, [class*='feature'], [class*='benefit']")
        count = min(await items.count(), 80)
        for i in range(count):
            text = (await items.nth(i).inner_text()).strip()
            if "%" not in text or len(text) > 400:
                continue
            blocks.append({"plan_name": None, "title": "", "text": text})

        base_domestic = 1.0
        base_loc = page.locator(".base-rate").first
        if await base_loc.count() > 0:
            parsed = extract_percentage(await base_loc.inner_text())
            if parsed is not None:
                base_domestic = parsed

        rules = build_rules_from_blocks(blocks)
        return CardIn(
            bank_name=self.bank_name,
            card_name=self.card_name,
            card_slug=self.card_slug,
            official_url=self.official_url,
            annual_fee="電子帳單免年費",
            base_rate_domestic=base_domestic,
            base_rate_foreign=base_domestic,
            reward_unit="當期帳單直接折抵",
            notes="透過 Playwright 爬取玉山 U Bear 卡頁面並自動解析回饋與上限。",
            source_type=source_type,
            rules=rules,
        )
