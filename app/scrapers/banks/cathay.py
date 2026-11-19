"""Playwright scraper for Cathay United Bank (國泰世華 CUBE 卡)."""

from typing import Dict, List, Optional
from playwright.async_api import Page

from app.models import CardIn
from app.scrapers.base import (
    BaseBankScraper,
    build_rules_from_blocks,
    collect_dom_text_blocks,
    extract_percentage,
)


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

        # 1. Try structured plan sections first in a single IPC call (supports hidden tab panels)
        structured = await page.evaluate(
            """() => {
                const sections = Array.from(document.querySelectorAll("section.cube-plan, [data-plan]"));
                const out = [];
                for (const sec of sections) {
                    if (sec.closest("header, nav, footer")) continue;
                    const planAttr = (sec.getAttribute("data-plan") || "").trim();
                    const headingText = (sec.querySelector("h2, h3")?.textContent || "").replace(/\\s+/g, " ").trim();
                    const planName = planAttr || headingText || null;
                    const items = Array.from(sec.querySelectorAll(".benefit-item, li, p"));
                    if (items.length > 0) {
                        for (const item of items) {
                            const txt = (item.innerText || item.textContent || "").replace(/\\s+/g, " ").trim();
                            if (txt.includes("%")) {
                                out.push({ plan_name: planName, title: planName || "", text: txt });
                            }
                        }
                    } else {
                        const txt = (sec.innerText || sec.textContent || "").replace(/\\s+/g, " ").trim();
                        if (txt) {
                            out.push({ plan_name: planName, title: planName || "", text: txt });
                        }
                    }
                }
                return out;
            }"""
        )
        blocks.extend(structured)

        # 2. Fallback generic DOM scanning for live bank pages with dynamic classes
        if not blocks:
            raw_texts = await collect_dom_text_blocks(
                page,
                "section, article, li, [class*='benefit'], [class*='card']",
                max_items=80,
            )
            known_plans = ["玩數位", "樂饗購", "趣旅行", "集精選", "慶生月"]
            for text in raw_texts:
                detected_plan = next((p for p in known_plans if p in text), None)
                blocks.append({"plan_name": detected_plan, "title": "", "text": text})

        base_domestic = 0.3
        base_text = await page.evaluate(
            "() => (document.querySelector('.base-rate')?.innerText || document.querySelector('.base-rate')?.textContent || '').trim()"
        )
        if base_text:
            parsed_base = extract_percentage(base_text)
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
