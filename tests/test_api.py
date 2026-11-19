"""End-to-end FastAPI endpoint tests."""

import asyncio
import socket

from fastapi.testclient import TestClient
import pytest

from app.catalog import extract_card_candidates_from_links, normalize_card_query
from app.db import get_connection, init_db, list_directory_cards, replace_directory_cards, upsert_directory_cards
from app.main import create_app
from app.scrapers.base import ScraperHttpStatusError, summarize_scraper_error, validate_public_http_url
from app.scrapers.manager import get_playwright_semaphore


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

        too_large = client.post(
            "/api/recommend",
            json={"monthly_spending": {"ecommerce": 10000000}},
        )
        assert too_large.status_code == 422

        negative_spend = client.post(
            "/api/recommend",
            json={"monthly_spending": {"ecommerce": -100}},
        )
        assert negative_spend.status_code == 422

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

        assert normalize_card_query("玉山ＵBear信用卡") == normalize_card_query("玉山 U Bear 卡")
        assert normalize_card_query("滙豐 Live+ 現金回饋卡") == normalize_card_query("匯豐 Live+ 現金回饋卡")
        esun_names = [c["card_name"] for c in client.get("/api/banks/esun/cards").json()]
        assert "玉山熊本熊卡" in esun_names
        assert sum("bear" in normalize_card_query(n) for n in esun_names) == 1


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


def test_admin_token_and_public_readonly_modes(tmp_path):
    # 1. Admin token + disabled docs mode
    admin_app = create_app(
        db_path=tmp_path / "admin.db",
        admin_token="secret-pw",
        disable_docs=True,
    )
    with TestClient(admin_app) as client:
        cfg = client.get("/api/config").json()
        assert cfg == {
            "admin_protected": True,
            "public_readonly": False,
            "docs_enabled": False,
        }
        assert client.get("/docs").status_code == 404
        assert client.post("/api/recommend", json={"monthly_spending": {"dining": 1000}}).status_code == 200

        assert client.post("/api/scrape", json={"bank_codes": ["cathay"], "mode": "demo_html"}).status_code == 403
        assert (
            client.post(
                "/api/scrape",
                json={"bank_codes": ["cathay"], "mode": "demo_html"},
                headers={"X-Admin-Token": "wrong"},
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/scrape/custom",
                json={"card_name": "CUBE 卡", "mode": "demo_html"},
            ).status_code
            == 403
        )
        assert client.post("/api/banks/fubon/discover").status_code == 403

        ok_res = client.post(
            "/api/scrape",
            json={"bank_codes": ["cathay"], "mode": "demo_html"},
            headers={"X-Admin-Token": "secret-pw"},
        )
        assert ok_res.status_code == 200
        assert ok_res.json()["results"][0]["status"] == "success"

    # 2. Pure public readonly mode
    ro_app = create_app(db_path=tmp_path / "readonly.db", public_readonly=True)
    with TestClient(ro_app) as client:
        assert client.get("/api/config").json()["public_readonly"] is True
        assert client.post("/api/recommend", json={"monthly_spending": {"dining": 1000}}).status_code == 200
        assert client.post("/api/scrape", json={"bank_codes": ["cathay"], "mode": "demo_html"}).status_code == 403


def test_security_validations_dns_and_api_bounds(tmp_path, monkeypatch):
    # DNS resolution pointing to private/loopback IP must be blocked
    def fake_getaddrinfo(host, port, type=0):
        if host == "rebind.example.com":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.8", 443))]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    assert validate_public_http_url("https://rebind.example.com/card")[0] is False
    assert validate_public_http_url("http://[::ffff:127.0.0.1]/admin")[0] is False
    assert validate_public_http_url("https://public.example.com/card")[0] is True

    app = create_app(db_path=tmp_path / "sec_test.db")
    with TestClient(app) as client:
        # scrape-logs limit validation
        assert client.get("/api/scrape-logs?limit=0").status_code == 422
        assert client.get("/api/scrape-logs?limit=201").status_code == 422
        assert client.get("/api/scrape-logs?limit=5").status_code == 200

        # POST /api/cards official_url scheme, card_slug, and channel_code validation
        bad_url = client.post(
            "/api/cards",
            json={
                "bank_name": "測試銀行",
                "card_name": "XSS 卡",
                "card_slug": "xss-card",
                "official_url": "javascript:alert(1)",
            },
        )
        assert bad_url.status_code == 422

        bad_slug = client.post(
            "/api/cards",
            json={
                "bank_name": "測試銀行",
                "card_name": "Slug 卡",
                "card_slug": "../bad slug!",
            },
        )
        assert bad_slug.status_code == 422

        bad_channel = client.post(
            "/api/cards",
            json={
                "bank_name": "測試銀行",
                "card_name": "Channel 卡",
                "card_slug": "valid-slug",
                "rules": [
                    {
                        "channel_code": "invalid_channel",
                        "channel_label": "無效通路",
                        "rate": 2.0,
                    }
                ],
            },
        )
        assert bad_channel.status_code == 422

        # rules max_length=100 boundary
        too_many_rules = client.post(
            "/api/cards",
            json={
                "bank_name": "測試銀行",
                "card_name": "規則超量卡",
                "card_slug": "too-many-rules",
                "rules": [
                    {
                        "channel_code": "general",
                        "channel_label": "一般國內消費",
                        "rate": 1.0,
                    }
                    for _ in range(101)
                ],
            },
        )
        assert too_many_rules.status_code == 422


def test_advanced_security_headers_cookie_auth_rate_limit_and_log_sanitization(tmp_path):
    # 1. Refuse default placeholder ADMIN_TOKEN from .env.example
    with pytest.raises(ValueError):
        create_app(
            db_path=tmp_path / "weak.db",
            admin_token="change-me-to-a-strong-password",
        )

    # 2. Sanitized scraper error summaries never leak raw internal strings
    leaked = RuntimeError("internal secret path /etc/shadow token=abc123")
    summary_zh = summarize_scraper_error(leaked, "zh-TW")
    summary_en = summarize_scraper_error(leaked, "en")
    assert "/etc/shadow" not in summary_zh and "abc123" not in summary_zh
    assert "/etc/shadow" not in summary_en and "abc123" not in summary_en
    assert summarize_scraper_error(ScraperHttpStatusError(403, "Forbidden", "https://bank.tw"), "en") == "HTTP 403"

    # 3. Security headers, HttpOnly cookie login/logout, CSRF protection, admin-protected logs, and rate limiting
    app = create_app(
        db_path=tmp_path / "adv_sec.db",
        admin_token="strong-unique-pass-2026",
        admin_rate_limit=3,
        recommend_rate_limit=2,
    )
    with TestClient(app) as client:
        # Security headers + HSTS when HTTPS
        resp = client.get("/api/health", headers={"X-Forwarded-Proto": "https"})
        assert resp.status_code == 200
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["X-Frame-Options"] == "DENY"
        assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert "default-src 'self'" in resp.headers["Content-Security-Policy"]
        assert "max-age=" in resp.headers["Strict-Transport-Security"]

        # Logs are admin-protected when ADMIN_TOKEN is active
        assert client.get("/api/scrape-logs").status_code == 403
        assert client.get("/api/admin/session").json() == {"authenticated": False}

        # Login sets HttpOnly SameSite=Strict cookie
        login_res = client.post("/api/admin/login", json={"token": "strong-unique-pass-2026"})
        assert login_res.status_code == 200
        assert login_res.json() == {"authenticated": True}
        set_cookie = login_res.headers.get("set-cookie", "").lower()
        assert "cc_admin_session=" in set_cookie
        assert "httponly" in set_cookie
        assert "samesite=strict" in set_cookie

        assert client.get("/api/admin/session").json() == {"authenticated": True}
        assert client.get("/api/scrape-logs").status_code == 200

        # Cookie-authenticated POST without Origin/Referer/X-Requested-With is rejected by CSRF guard
        csrf_fail = client.post(
            "/api/scrape",
            json={"bank_codes": ["cathay"], "mode": "demo_html"},
        )
        assert csrf_fail.status_code == 403

        # With X-Requested-With header, cookie auth succeeds
        csrf_ok = client.post(
            "/api/scrape",
            json={"bank_codes": ["cathay"], "mode": "demo_html"},
            headers={"X-Requested-With": "fetch"},
        )
        assert csrf_ok.status_code == 200
        assert csrf_ok.json()["results"][0]["status"] == "success"

        # Logout clears cookie
        logout_res = client.post("/api/admin/logout", headers={"X-Requested-With": "fetch"})
        assert logout_res.status_code == 200
        assert client.get("/api/admin/session").json() == {"authenticated": False}
        assert client.get("/api/scrape-logs").status_code == 403

        # Recommend rate limiting (limit=2)
        assert client.post("/api/recommend", json={"monthly_spending": {"dining": 1000}}).status_code == 200
        assert client.post("/api/recommend", json={"monthly_spending": {"dining": 1000}}).status_code == 200
        assert client.post("/api/recommend", json={"monthly_spending": {"dining": 1000}}).status_code == 429

        # Admin login rate limiting (already 1 login attempt above; next 2 allowed -> 4th returns 429)
        assert client.post("/api/admin/login", json={"token": "wrong"}).status_code == 403
        assert client.post("/api/admin/login", json={"token": "wrong"}).status_code == 403
        assert client.post("/api/admin/login", json={"token": "wrong"}).status_code == 429


def test_sqlite_wal_atomic_replace_and_429_concurrency_guard(tmp_path):
    db_path = tmp_path / "perf_test.db"
    init_db(db_path)
    with get_connection(db_path) as conn:
        mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        assert mode.lower() == "wal"

    replace_directory_cards(
        "cathay",
        "國泰世華",
        [{"card_name": "測試卡片一", "official_url": "https://www.cathaybk.com.tw/c1"}],
        db_path=db_path,
    )
    replace_directory_cards(
        "cathay",
        "國泰世華",
        [{"card_name": "測試卡片二", "official_url": "https://www.cathaybk.com.tw/c2"}],
        db_path=db_path,
    )
    rows = list_directory_cards("cathay", db_path=db_path)
    assert [r["card_name"] for r in rows] == ["測試卡片二"]

    # Verify concurrent scraper guard returns HTTP 429 immediately when semaphore is locked
    app = create_app(db_path=db_path)
    with TestClient(app) as client:
        async def _check_429():
            sem = get_playwright_semaphore()
            await sem.acquire()
            try:
                from httpx import ASGITransport, AsyncClient

                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://testserver"
                ) as ac:
                    res = await ac.post(
                        "/api/scrape",
                        json={"bank_codes": ["cathay"], "mode": "demo_html"},
                    )
                    assert res.status_code == 429
            finally:
                sem.release()

        asyncio.run(_check_429())
