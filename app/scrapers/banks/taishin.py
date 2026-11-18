"""Playwright scraper for Taishin Bank (台新銀行 @GoGo 卡)."""

from typing import Dict, List, Optional
from playwright.async_api import Page

from app.models import CardIn
from app.scrapers.base import BaseBankScraper, build_rules_from_blocks, extract_percentage


class TaishinGogoScraper(BaseBankScraper):
    bank_code = "taishin"
    bank_name = "台新銀行"
    card_name = "@GoGo 卡"
    card_slug = "taishin-gogo"
    official_url = (
        "https://www.taishinbank.com.tw/TSB/personal/credit/intro/overview/cg021/"
    )

    demo_html = """
    <!doctype html>
    <html lang="zh-Hant">
    <head><title>台新銀行 @GoGo 卡</title></head>
    <body>
      <main>
        <h1>@GoGo 信用卡</h1>
        <p class="base-rate">一般消費享 0.3% 台新 Point(信用卡)回饋。</p>
        <section class="benefit-section">
          <div class="benefit-item">精選網購（蝦皮、momo、酷澎、PChome）最高 3% 回饋，每月上限 1,500 元</div>
          <div class="benefit-item">行動支付綁定 LINE Pay、全盈+PAY、台新Pay 最高 3% 回饋，每月上限 1,500 元</div>
          <div class="benefit-item">外送平台 Uber Eats、foodpanda 消費享 3% 回饋，每月上限 1,500 元</div>
        </section>
      </main>
    </body>
    </html>
    """

    async def parse_page(self, page: Page, source_type: str = "scraped") -> CardIn:
        blocks: List[Dict[str, Optional[str]]] = []

        items = page.locator(".benefit-item, section, article, li, [class*='benefit'], [class*='card']")
        count = min(await items.count(), 80)
        for i in range(count):
            text = (await items.nth(i).inner_text()).strip()
            if "%" not in text or len(text) > 400:
                continue
            blocks.append({"plan_name": None, "title": "", "text": text})

        base_domestic = 0.3
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
            reward_unit="台新 Point(信用卡)",
            notes="透過 Playwright 爬取台新 @GoGo 卡頁面並自動解析回饋與上限。",
            source_type=source_type,
            rules=rules,
        )
