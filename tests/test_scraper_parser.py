"""Tests for Playwright scraper text parsing and demo HTML Chromium extraction."""

import asyncio

from app.db import init_db, list_cards
from app.scrapers.base import (
    detect_channels_from_text,
    extract_monthly_cap,
    extract_percentage,
)
from app.scrapers.manager import run_scrapers


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
