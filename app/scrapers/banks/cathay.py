"""Playwright scraper for Cathay United Bank (國泰世華 CUBE 卡)."""

from typing import Dict, List, Optional
from playwright.async_api import Page

from app.models import CardIn
from app.scrapers.base import BaseBankScraper, build_rules_from_blocks, extract_percentage


class CathayCubeScraper(BaseBankScraper):
    bank_code = "cathay"
    bank_name = "國泰世華"
    card_name = "CUBE 卡"
    card_slug = "cathay-cube"
    official_url = (
        "https://www.cathaybk.com.tw/cathaybk/personal/product/credit-card/cards/cube/"
    )

    demo_html = """
    <!doctype html>
    <html lang="zh-Hant">
    <head><title>國泰世華 CUBE 卡</title></head>
    <body>
      <main>
        <h1>CUBE 信用卡</h1>
        <p class="base-rate">一般消費享 0.3% 小樹點(信用卡)回饋無上限，海外消費基本 0.3%。</p>
        <section class="cube-plan" data-plan="玩數位">
          <h2>玩數位</h2>
          <div class="benefit-item">蝦皮、momo、PChome、酷澎網購電商享 3% 小樹點無上限</div>
          <div class="benefit-item">LINE Pay、Apple Pay 指定數位網購平台享 3% 回饋</div>
        </section>
        <section class="cube-plan" data-plan="樂饗購">
          <h2>樂饗購</h2>
          <div class="benefit-item">國內餐飲美食、百貨與藥妝享 3% 小樹點無上限</div>
          <div class="benefit-item">Uber Eats、foodpanda 外送平台享 3% 回饋</div>
        </section>
        <section class="cube-plan" data-plan="趣旅行">
          <h2>趣旅行</h2>
          <div class="benefit-item">海外實體消費、機票航空、全球飯店訂房享 3% 小樹點無上限</div>
          <div class="benefit-item">台灣高鐵、Uber 等交通通勤享 3% 回饋</div>
        </section>
        <section class="cube-plan" data-plan="集精選">
          <h2>集精選</h2>
          <div class="benefit-item">7-11、全家超商消費享 2% 小樹點回饋</div>
          <div class="benefit-item">全聯福利中心、家樂福超市量販享 2% 回饋</div>
        </section>
      </main>
    </body>
    </html>
    """

    async def parse_page(self, page: Page, source_type: str = "scraped") -> CardIn:
        blocks: List[Dict[str, Optional[str]]] = []

        # 1. Try structured plan sections first
        plan_sections = page.locator("section.cube-plan, [data-plan]")
        plan_count = await plan_sections.count()
        if plan_count > 0:
            for i in range(plan_count):
                sec = plan_sections.nth(i)
                plan_name = await sec.get_attribute("data-plan")
                if not plan_name:
                    heading = sec.locator("h2, h3").first
                    if await heading.count() > 0:
                        plan_name = (await heading.inner_text()).strip()
                items = sec.locator(".benefit-item, li, p")
                item_count = await items.count()
                if item_count > 0:
                    for j in range(item_count):
                        text = (await items.nth(j).inner_text()).strip()
                        if "%" in text:
                            blocks.append({"plan_name": plan_name, "title": plan_name, "text": text})
                else:
                    text = (await sec.inner_text()).strip()
                    blocks.append({"plan_name": plan_name, "title": plan_name, "text": text})

        # 2. Fallback generic DOM scanning for live bank pages with dynamic classes
        if not blocks:
            candidates = page.locator("section, article, li, [class*='benefit'], [class*='card']")
            count = min(await candidates.count(), 80)
            known_plans = ["玩數位", "樂饗購", "趣旅行", "集精選", "慶生月"]
            for i in range(count):
                text = (await candidates.nth(i).inner_text()).strip()
                if "%" not in text or len(text) > 400:
                    continue
                detected_plan = next((p for p in known_plans if p in text), None)
                blocks.append({"plan_name": detected_plan, "title": "", "text": text})

        base_domestic = 0.3
        base_locator = page.locator(".base-rate").first
        if await base_locator.count() > 0:
            parsed_base = extract_percentage(await base_locator.inner_text())
            if parsed_base is not None:
                base_domestic = parsed_base

        rules = build_rules_from_blocks(blocks)
        return CardIn(
            bank_name=self.bank_name,
            card_name=self.card_name,
            card_slug=self.card_slug,
            official_url=self.official_url,
            annual_fee="首年免年費，電子帳單/任刷12次免年費",
            base_rate_domestic=base_domestic,
            base_rate_foreign=base_domestic,
            reward_unit="小樹點(信用卡)",
            notes="透過 Playwright 爬取國泰世華 CUBE 卡頁面並自動解析方案規則。",
            source_type=source_type,
            rules=rules,
        )
