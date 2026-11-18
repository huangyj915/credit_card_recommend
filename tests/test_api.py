"""End-to-end FastAPI endpoint tests."""

from fastapi.testclient import TestClient

from app.catalog import extract_card_candidates_from_links
from app.db import upsert_directory_cards
from app.main import create_app


def test_api_flow(tmp_path):
    db_path = tmp_path / "api_test.db"
    app = create_app(db_path=db_path)

    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json() == {"status": "ok"}

        channels = client.get("/api/channels")
        assert channels.status_code == 200
        assert len(channels.json()) >= 8

        cards = client.get("/api/cards")
        assert cards.status_code == 200
        cards_json = cards.json()
        assert len(cards_json) >= 6
        assert all(c["last_updated"] for c in cards_json)

        rec = client.post(
            "/api/recommend",
            json={"monthly_spending": {"ecommerce": 5000, "dining": 4000}},
        )
        assert rec.status_code == 200
        data = rec.json()
        assert data["total_spend_ntd"] == 9000.0
        assert len(data["recommendations"]) >= 6
        assert all(r["last_updated"] for r in data["recommendations"])
        assert data["combo"] is not None

        page = client.get("/")
        assert page.status_code == 200
        assert "台灣信用卡回饋比較" in page.text

        custom_bad = client.post(
            "/api/scrape/custom",
            json={"card_name": "測試卡", "official_url": "http://127.0.0.1:8000", "mode": "live"},
        )
        assert custom_bad.status_code == 200
        assert custom_bad.json()["results"][0]["status"] == "error"

        custom_builtin = client.post(
            "/api/scrape/custom",
            json={"card_name": "CUBE 卡", "mode": "demo_html"},
        )
        assert custom_builtin.status_code == 200
        assert custom_builtin.json()["results"][0]["status"] == "success"
        assert custom_builtin.json()["results"][0]["card_slug"] == "cathay-cube"

        banks = client.get("/api/banks")
        assert banks.status_code == 200
        banks_json = banks.json()
        assert len(banks_json) >= 15
        assert any(b["bank_code"] == "cathay" for b in banks_json)

        upsert_directory_cards(
            "dbs",
            "星展銀行",
            [{"card_name": "星展飛行世界商務卡", "official_url": "https://www.dbs.com.tw/example"}],
            db_path=db_path,
        )
        dbs_cards = client.get("/api/banks/dbs/cards")
        assert dbs_cards.status_code == 200
        dbs_names = [c["card_name"] for c in dbs_cards.json()]
        assert "星展 eco 永續卡" in dbs_names
        assert "星展飛行世界商務卡" in dbs_names

        cathay_cards = client.get("/api/banks/cathay/cards")
        assert cathay_cards.status_code == 200
        cube_entry = next(c for c in cathay_cards.json() if c["card_name"] == "CUBE 卡")
        assert cube_entry["in_db"] is True

        missing_bank = client.get("/api/banks/unknown-bank/cards")
        assert missing_bank.status_code == 404


def test_extract_card_candidates_from_links():
    candidates = extract_card_candidates_from_links(
        [
            ("信用卡首頁", "/home"),
            ("申辦信用卡", "/apply"),
            ("熱門卡片", ""),
            ("推薦卡片", ""),
            ("掛失信用卡", "/reportlostcard.html"),
            ("卡友登錄專區", "/promotion"),
            ("卡友理財服務", "/loan.html"),
            ("小樹點(信用卡)", "/bonus.html"),
            ("CUBE 簽帳金融卡", "/debit/cube"),
            ("您知道這些卡片已經升級為CUBE卡了嗎？", ""),
            ("亞洲萬里通聯名卡 早刷這張，換里出發", "/asia-miles"),
            ("星展 eco 永續卡", "/cards/eco"),
            ("星展eco永續信用卡", "/cards/eco-dup"),
            ("星展饗樂生活卡", "/cards/live"),
            ("星展花旗停發卡", "/cards/old", ""),
            ("某舊聯名卡", "/cards/legacy", "已停發信用卡 停止申辦"),
            ("另一張停辦卡", "/cards/discontinued/abc", ""),
        ],
        "https://www.dbs.com.tw/personal-zh/cards/",
        require_url=True,
    )
    names = [c["card_name"] for c in candidates]
    assert names == ["星展 eco 永續卡", "星展饗樂生活卡"]
    assert candidates[0]["official_url"] == "https://www.dbs.com.tw/cards/eco"


def test_discontinued_cards_excluded_from_catalog_and_custom_scrape(tmp_path):
    db_path = tmp_path / "discontinued_test.db"
    app = create_app(db_path=db_path)

    with TestClient(app) as client:
        upsert_directory_cards(
            "fubon",
            "台北富邦",
            [{"card_name": "富邦舊卡（已停發）", "official_url": "https://www.fubon.com/old"}],
            db_path=db_path,
        )
        fubon_names = [c["card_name"] for c in client.get("/api/banks/fubon/cards").json()]
        assert "數位生活卡" not in fubon_names
        assert "富邦舊卡（已停發）" not in fubon_names

        res = client.post(
            "/api/scrape/custom",
            json={"card_name": "數位生活卡（已停發）", "mode": "live"},
        )
        assert res.status_code == 200
        item = res.json()["results"][0]
        assert item["status"] == "warning"
        assert "停發" in item["message"]
