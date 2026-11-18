"""Tests for Playwright scraper text parsing and demo HTML Chromium extraction."""

import asyncio

from app.db import init_db, list_cards
from app.scrapers.base import (
    check_page_discontinued,
    detect_channels_from_text,
    detect_discontinued_in_page_fields,
    extract_monthly_cap,
    extract_percentage,
)
from app.scrapers.custom import (
    _score_candidate_url,
    match_builtin_scraper_code,
    match_existing_card,
    parse_generic_card_page,
    unwrap_search_result_url,
    validate_public_http_url,
)
from app.scrapers.manager import _launch_browser, run_scrapers
from app.seed_data import ensure_seed_data
from playwright.async_api import async_playwright


def test_text_parsers():
    assert extract_percentage("指定網購最高 3.5% 回饋") == 3.5
    assert extract_monthly_cap("每月加碼回饋上限 1,500 元") == 1500.0
    assert extract_monthly_cap("上限300點") == 300.0
    assert "ecommerce" in detect_channels_from_text("蝦皮、momo 網購電商")
    assert "overseas" in detect_channels_from_text("日韓海外實體消費")


def test_playwright_demo_html_scrape(tmp_path):
    db_path = tmp_path / "scrape_test.db"
    init_db(db_path)

    results = asyncio.run(
        run_scrapers(["cathay", "esun", "taishin"], mode="demo_html", db_path=db_path)
    )
    assert len(results) == 3
    assert all(r.status == "success" for r in results)
    assert all(r.rules_count > 0 for r in results)

    cards = list_cards(db_path)
    assert len(cards) == 3
    assert all(c.source_type == "scraped" for c in cards)
    cube = next(c for c in cards if c.card_slug == "cathay-cube")
    assert any(r.plan_name == "趣旅行" and r.rate == 3.0 for r in cube.rules)


def test_custom_scraper_helpers_and_generic_parser(tmp_path):
    db_path = tmp_path / "custom_test.db"
    init_db(db_path)
    ensure_seed_data(db_path)

    assert validate_public_http_url("https://www.dbs.com.tw/personal-zh/cards/eco")[0] is True
    assert validate_public_http_url("http://127.0.0.1:8000")[0] is False
    assert validate_public_http_url("file:///etc/passwd")[0] is False

    bing_wrapped = "https://www.bing.com/ck/a?!&&p=123&u=a1aHR0cHM6Ly93d3cuZnVib24uY29tL2JhbmtpbmcvcGVyc29uYWwvY3JlZGl0X2NhcmQvYWxsX2NhcmQvb3BlbnBvc3NpYmxlL29wZW5wb3NzaWJsZS5odG0&ntb=1"
    assert (
        unwrap_search_result_url(bing_wrapped)
        == "https://www.fubon.com/banking/personal/credit_card/all_card/openpossible/openpossible.htm"
    )
    assert _score_candidate_url("https://www.card.rakuten.com.tw/auth/", "樂天 Panda J 卡", "樂天信用卡會員服務: 登入") < 0
    assert _score_candidate_url("https://www.card.rakuten.com.tw/corp/product/", "樂天 Panda J 卡", "樂天 Panda J 卡國內 3% 回饋") > 0

    assert match_builtin_scraper_code("國泰 CUBE") == "cathay"
    assert match_builtin_scraper_code("U Bear 信用卡") == "esun"
    matched = match_existing_card("富邦 J 卡", db_path=db_path)
    assert matched is not None
    assert matched.card_slug == "fubon-j"

    async def _run_generic():
        sample_html = """
        <!doctype html>
        <html lang="zh-Hant">
        <head><title>星展 eco 永續卡 | 星展銀行</title></head>
        <body>
          <p>國內一般消費享 1.2% 現金積點回饋無上限</p>
          <div class="benefit">海外日本韓國消費最高 5% 回饋，每月上限 1,000 元</div>
          <div class="benefit">Uber Eats、foodpanda 外送平台享 3% 回饋</div>
        </body>
        </html>
        """
        async with async_playwright() as p:
            browser = await _launch_browser(p)
            page = await browser.new_page()
            await page.set_content(sample_html, wait_until="domcontentloaded")
            card_in = await parse_generic_card_page(
                page=page,
                card_name="eco 永續卡",
                official_url="https://www.dbs.com.tw/personal-zh/cards/eco",
            )
            await browser.close()
            return card_in

    parsed = asyncio.run(_run_generic())
    assert parsed.bank_name == "星展銀行"
    assert parsed.base_rate_domestic == 1.2
    assert parsed.source_type == "scraped"
    assert any(r.channel_code == "overseas" and r.rate == 5.0 and r.monthly_cap_ntd == 1000.0 for r in parsed.rules)
    assert any(r.channel_code == "delivery" and r.rate == 3.0 for r in parsed.rules)


def test_discontinued_page_detection():
    # Active card with a footer link mentioning 停發卡專區 must NOT false-positive
    assert (
        detect_discontinued_in_page_fields(
            title="CUBE 信用卡 | 國泰世華銀行",
            heading_text="CUBE 卡介紹",
            badge_text="熱門推薦",
            body_text="一般消費 0.3% 回饋。頁尾導覽：常見問題 | 停發卡專區 | 聯絡我們",
            url="https://www.cathaybk.com.tw/cards/cube/",
        )
        is None
    )

    # Discontinued card page must be detected
    assert (
        detect_discontinued_in_page_fields(
            title="數位生活卡 | 台北富邦",
            heading_text="數位生活卡",
            badge_text="",
            body_text="親愛的卡友您好，本卡已於 2025/01/01 起停止受理新卡申辦。",
            url="https://www.fubon.com/cards/digital/",
        )
        is not None
    )

    async def _check_dom():
        html = """
        <!doctype html>
        <html lang="zh-Hant">
        <head><title>測試卡（已停發）</title></head>
        <body><h1>測試停發卡</h1><p>本卡已停發，僅提供既有卡友查詢。</p></body>
        </html>
        """
        async with async_playwright() as p:
            browser = await _launch_browser(p)
            page = await browser.new_page()
            await page.set_content(html, wait_until="domcontentloaded")
            reason = await check_page_discontinued(page, "https://example.com/card")
            await browser.close()
            return reason

    assert asyncio.run(_check_dom()) is not None
