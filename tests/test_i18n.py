"""Tests for backend and frontend internationalization (zh-TW and en)."""

import re

from fastapi.testclient import TestClient

from app.db import log_scrape, upsert_card
from app.main import create_app
from app.models import CardIn, RewardRuleIn

CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")


def test_api_i18n_endpoints(tmp_path):
    db_path = tmp_path / "i18n_test.db"
    app = create_app(db_path=db_path)

    with TestClient(app) as client:
        # 1. Channels default (zh-TW) vs English (en)
        ch_zh = client.get("/api/channels").json()
        ch_en = client.get("/api/channels?lang=en").json()
        assert ch_zh[0]["label"] == "超商消費"
        assert ch_en[0]["label"] == "Convenience Stores"
        assert len(ch_zh) == len(ch_en)

        # 2. Cards localization
        cards_en = client.get("/api/cards?lang=en").json()
        cube_en = next(c for c in cards_en if c["card_slug"] == "cathay-cube")
        assert cube_en["bank_name"] == "Cathay United Bank"
        assert cube_en["card_name"] == "CUBE Card"
        assert any(r["plan_name"] == "Fun Travel" for r in cube_en["rules"])
        assert cube_en["rules"][0]["channel_label"] != ""

        single_en = client.get("/api/cards/cathay-cube?lang=en").json()
        assert single_en["card_name"] == "CUBE Card"

        # 3. Recommendation calculations match across languages while text is localized
        rec_zh = client.post(
            "/api/recommend",
            json={"monthly_spending": {"overseas": 20000, "travel": 10000, "ecommerce": 5000}},
        ).json()
        rec_en = client.post(
            "/api/recommend?lang=en",
            json={"monthly_spending": {"overseas": 20000, "travel": 10000, "ecommerce": 5000}},
        ).json()

        assert rec_zh["total_spend_ntd"] == rec_en["total_spend_ntd"] == 35000.0
        cube_rec_zh = next(r for r in rec_zh["recommendations"] if r["card_slug"] == "cathay-cube")
        cube_rec_en = next(r for r in rec_en["recommendations"] if r["card_slug"] == "cathay-cube")
        assert cube_rec_zh["total_reward_ntd"] == cube_rec_en["total_reward_ntd"]
        assert cube_rec_zh["recommended_plan"] == "趣旅行"
        assert cube_rec_en["recommended_plan"] == "Fun Travel"
        assert any("Save NT$" in h for h in cube_rec_en["matched_highlights"])
        assert rec_en["combo"]["allocations"][0]["channel_label"] in {
            "Overseas Spending",
            "Travel & Lodging",
            "Online Shopping",
        }

        # 4. Banks & scrapers localization
        banks_en = client.get("/api/banks?lang=en").json()
        cathay_bank = next(b for b in banks_en if b["bank_code"] == "cathay")
        assert cathay_bank["bank_name"] == "Cathay United Bank"

        cathay_cards_en = client.get("/api/banks/cathay/cards?lang=en").json()
        assert any(c["card_name"] == "CUBE Card" for c in cathay_cards_en)

        scrapers_en = client.get("/api/scrapers?lang=en").json()
        assert any(s["bank_name"] == "Cathay United Bank" and s["card_name"] == "CUBE Card" for s in scrapers_en)

        # 5. Custom scrape canonicalizes English card names back to built-in scraper
        custom_en = client.post(
            "/api/scrape/custom?lang=en",
            json={"card_name": "CUBE Card", "bank_name": "Cathay United Bank", "mode": "demo_html"},
        )
        assert custom_en.status_code == 200
        item = custom_en.json()["results"][0]
        assert item["status"] == "success"
        assert item["card_slug"] == "cathay-cube"
        assert "Playwright" in item["message"]

        # 6. HTML includes language switcher and i18n.js
        page = client.get("/")
        assert page.status_code == 200
        assert "/static/i18n.js" in page.text
        assert 'data-lang="en"' in page.text


def test_admin_errors_i18n(tmp_path):
    app = create_app(db_path=tmp_path / "admin_i18n.db", admin_token="secret")
    with TestClient(app) as client:
        res_en = client.post(
            "/api/scrape?lang=en",
            json={"bank_codes": ["cathay"], "mode": "demo_html"},
        )
        assert res_en.status_code == 403
        assert "X-Admin-Token" in res_en.json()["detail"]
        assert "admin password" in res_en.json()["detail"].lower()

        res_header = client.post(
            "/api/scrape",
            json={"bank_codes": ["cathay"], "mode": "demo_html"},
            headers={"X-Lang": "en"},
        )
        assert res_header.status_code == 403
        assert "admin password" in res_header.json()["detail"].lower()


def test_scraped_cards_and_dynamic_rules_english_i18n(tmp_path):
    db_path = tmp_path / "scraped_i18n.db"
    app = create_app(db_path=db_path)

    with TestClient(app) as client:
        upsert_card(
            CardIn(
                bank_name="台北富邦",
                card_name="福華聯名卡",
                card_slug="custom-e33cf602",
                official_url="https://www.fubon.com/howard",
                annual_fee="依銀行官網公告",
                reward_unit="現金回饋 / 點數",
                notes="透過 Playwright 依使用者指定卡名爬取解析（來源：https://www.fubon.com/howard）。",
                source_type="scraped",
                rules=[
                    RewardRuleIn(
                        channel_code="dining",
                        channel_label="餐飲美食",
                        rate=10.0,
                        payment_methods=["實體/線上刷卡"],
                        conditions="高雄福華 大飯店 住宿：尊爵豪華單/雙床房享住宿定價3.5折+定價10%服務費",
                    ),
                ],
            ),
            db_path=db_path,
        )
        upsert_card(
            CardIn(
                bank_name="星展銀行",
                card_name="星展everyday鈦金卡",
                card_slug="custom-everyday-d4f707be",
                official_url="https://www.dbs.com.tw/everyday",
                annual_fee="依銀行官網公告",
                reward_unit="現金回饋 / 點數",
                notes="透過 Playwright 依使用者指定卡名爬取解析（來源：https://www.dbs.com.tw/everyday）。",
                source_type="scraped",
                rules=[
                    RewardRuleIn(
                        channel_code="general",
                        channel_label="一般國內消費",
                        rate=14.99,
                        payment_methods=["實體/線上刷卡"],
                        conditions="謹慎理財‧信用至上 循環信用利率區間：5.99~14.99% 預借現金手續費",
                    ),
                ],
            ),
            db_path=db_path,
        )
        upsert_card(
            CardIn(
                bank_name="台新銀行",
                card_name="台新 Richart 卡",
                card_slug="custom-richart-73287a9a",
                official_url="https://www.taishinbank.com.tw/richart",
                annual_fee="依銀行官網公告",
                reward_unit="現金回饋 / 點數",
                notes="透過 Playwright 依使用者指定卡名爬取解析（來源：https://www.taishinbank.com.tw/richart）。",
                source_type="scraped",
                rules=[
                    RewardRuleIn(
                        channel_code="convenience_store",
                        channel_label="超商消費",
                        rate=3.8,
                        payment_methods=["台新Pay"],
                        conditions="Pay著刷 3.8% 台新Pay 及 台新Pay+ 綁定支付享 3.8% * 台新Pay｜全家、7-11",
                    ),
                ],
            ),
            db_path=db_path,
        )

        cards_en = client.get("/api/cards?lang=en").json()
        for card in cards_en:
            for field in ("bank_name", "card_name", "annual_fee", "reward_unit", "notes"):
                assert not CJK_RE.search(card[field]), f"{card['card_slug']}.{field} leaked CJK: {card[field]}"
            for rule in card["rules"]:
                assert not CJK_RE.search(rule["channel_label"]), rule
                assert not CJK_RE.search(rule["conditions"]), rule
                if rule["plan_name"]:
                    assert not CJK_RE.search(rule["plan_name"]), rule

        rec_en = client.post(
            "/api/recommend?lang=en",
            json={
                "monthly_spending": {
                    "convenience_store": 2000,
                    "dining": 6000,
                    "general": 2000,
                }
            },
        ).json()
        for rec in rec_en["recommendations"]:
            assert not CJK_RE.search(rec["bank_name"]), rec
            assert not CJK_RE.search(rec["card_name"]), rec
            for bd in rec["breakdown"]:
                assert not CJK_RE.search(bd["channel_label"]), bd
                assert not CJK_RE.search(bd["note"]), bd

        # Historical scrape logs (both zh-TW and en stored) localize cleanly in both directions
        log_scrape(
            "custom",
            "custom-everyday-d4f707be",
            "https://www.dbs.com.tw/everyday",
            "success",
            "成功透過 Playwright 解析並更新「星展銀行 星展everyday鈦金卡」共 1 條通路規則",
            1,
            db_path=db_path,
        )
        log_scrape(
            "custom",
            "custom-richart-73287a9a",
            "",
            "warning",
            "已開啟頁面但未解析出「台新 Richart 卡」的結構化回饋規則（可能因官網改版、JS 動態載入或防爬阻擋），未更動既有資料。",
            0,
            db_path=db_path,
        )
        log_scrape(
            "cathay",
            "cathay-cube",
            "https://www.cathaybk.com.tw",
            "success",
            "Parsed and updated 6 channel rules for 'Cathay United Bank CUBE Card' via Playwright",
            6,
            db_path=db_path,
        )
        logs_en = client.get("/api/scrape-logs?limit=10&lang=en").json()
        assert len(logs_en) == 3
        for item in logs_en:
            assert not CJK_RE.search(item["message"]), item
        assert any("DBS Everyday Titanium Card" in item["message"] for item in logs_en)

        logs_zh = client.get("/api/scrape-logs?limit=10&lang=zh-TW").json()
        assert any("國泰世華 CUBE 卡" in item["message"] for item in logs_zh)

