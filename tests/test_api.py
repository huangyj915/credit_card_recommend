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
        assert len(cards.json()) >= 6

        rec = client.post(
            "/api/recommend",
            json={"monthly_spending": {"ecommerce": 5000, "dining": 4000}},
        )
        assert rec.status_code == 200
        data = rec.json()
        assert data["total_spend_ntd"] == 9000.0
        assert len(data["recommendations"]) >= 6
        assert data["combo"] is not None

        page = client.get("/")
        assert page.status_code == 200
        assert "台灣信用卡回饋比較" in page.text
