"""FastAPI application entrypoint serving both API endpoints and the static web UI."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.channels import CHANNELS
from app.db import get_card_by_slug, init_db, list_cards, list_scrape_logs, upsert_card
from app.models import (
    CardIn,
    CardOut,
    CustomScrapeRequest,
    RecommendRequest,
    RecommendResponse,
    ScrapeRequest,
    ScrapeResponse,
)
from app.recommender import recommend_cards
from app.scrapers.custom import scrape_custom_card
from app.scrapers.manager import list_available_scrapers, run_scrapers
from app.seed_data import ensure_seed_data

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"


def create_app(db_path: Optional[Path] = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        init_db(db_path)
        ensure_seed_data(db_path)
        yield

    application = FastAPI(
        title="台灣信用卡回饋比較與通路推薦系統",
        description="使用 Python + FastAPI + Playwright 打造的個人化信用卡推薦網站",
        version="0.1.0",
        lifespan=lifespan,
    )

    application.state.db_path = db_path

    @application.middleware("http")
    async def disable_static_cache(request: Request, call_next):
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response

    if STATIC_DIR.exists():
        application.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @application.get("/", include_in_schema=False)
    async def index():
        index_file = STATIC_DIR / "index.html"
        if not index_file.exists():
            raise HTTPException(status_code=404, detail="Frontend index.html not found")
        return FileResponse(str(index_file))

    @application.get("/api/health")
    def health() -> Dict[str, str]:
        return {"status": "ok"}

    @application.get("/api/channels")
    def get_channels() -> List[Dict[str, str]]:
        return CHANNELS

    @application.get("/api/cards", response_model=List[CardOut])
    def get_cards() -> List[CardOut]:
        return list_cards(application.state.db_path)

    @application.get("/api/cards/{card_slug}", response_model=CardOut)
    def get_card(card_slug: str) -> CardOut:
        card = get_card_by_slug(card_slug, application.state.db_path)
        if card is None:
            raise HTTPException(status_code=404, detail="Card not found")
        return card

    @application.post("/api/cards", response_model=CardOut)
    def create_or_update_card(card: CardIn) -> CardOut:
        return upsert_card(card, application.state.db_path)

    @application.post("/api/recommend", response_model=RecommendResponse)
    def recommend(request: RecommendRequest) -> RecommendResponse:
        cards = list_cards(application.state.db_path)
        return recommend_cards(cards, request)

    @application.get("/api/scrapers")
    def get_scrapers() -> List[Dict[str, str]]:
        return list_available_scrapers()

    @application.get("/api/scrape-logs")
    def get_scrape_logs(limit: int = 20) -> List[dict]:
        return list_scrape_logs(limit=limit, db_path=application.state.db_path)

    @application.post("/api/scrape", response_model=ScrapeResponse)
    async def trigger_scrape(request: ScrapeRequest) -> ScrapeResponse:
        if request.mode not in ("live", "demo_html"):
            raise HTTPException(status_code=400, detail="mode must be 'live' or 'demo_html'")
        results = await run_scrapers(
            bank_codes=request.bank_codes,
            mode=request.mode,
            db_path=application.state.db_path,
        )
        return ScrapeResponse(mode=request.mode, results=results)

    @application.post("/api/scrape/custom", response_model=ScrapeResponse)
    async def trigger_custom_scrape(request: CustomScrapeRequest) -> ScrapeResponse:
        if request.mode not in ("live", "demo_html"):
            raise HTTPException(status_code=400, detail="mode must be 'live' or 'demo_html'")
        if not request.card_name.strip():
            raise HTTPException(status_code=400, detail="card_name must not be empty")
        result = await scrape_custom_card(
            card_name=request.card_name,
            bank_name=request.bank_name,
            official_url=request.official_url,
            mode=request.mode,
            db_path=application.state.db_path,
        )
        return ScrapeResponse(mode=request.mode, results=[result])

    return application


app = create_app()
