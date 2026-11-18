"""End-to-end FastAPI endpoint tests."""

from fastapi.testclient import TestClient

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
