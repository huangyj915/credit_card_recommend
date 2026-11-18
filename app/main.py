"""FastAPI application entrypoint serving both API endpoints and the static web UI."""

from contextlib import asynccontextmanager
import hmac
import os
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.catalog import (
    discover_bank_cards_via_playwright,
    list_bank_catalog,
    list_cards_for_bank,
)
from app.channels import CHANNELS
from app.db import get_card_by_slug, init_db, list_cards, list_scrape_logs, upsert_card
from app.models import (
    BankCardCatalogItem,
    BankCatalogItem,
    BankDiscoverResponse,
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


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def create_app(
    db_path: Optional[Path] = None,
    admin_token: Optional[str] = None,
    public_readonly: Optional[bool] = None,
    disable_docs: Optional[bool] = None,
) -> FastAPI:
    resolved_token = (
        os.getenv("ADMIN_TOKEN", "").strip() if admin_token is None else admin_token.strip()
    )
    resolved_readonly = (
        _env_flag("PUBLIC_READONLY", False) if public_readonly is None else public_readonly
    )
    resolved_disable_docs = (
        _env_flag("DISABLE_DOCS", False) if disable_docs is None else disable_docs
    )

    def require_admin_write(
        x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
    ) -> None:
        if resolved_token:
            provided = (x_admin_token or "").strip()
            if not provided or not hmac.compare_digest(provided, resolved_token):
                raise HTTPException(
                    status_code=403,
                    detail="需要正確的管理員密碼（X-Admin-Token）才能執行寫入或爬蟲操作。",
                )
            return
        if resolved_readonly:
            raise HTTPException(
                status_code=403,
                detail="目前為公開唯讀展示模式，已停用卡片寫入與 Playwright 爬蟲。",
            )

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
        docs_url=None if resolved_disable_docs else "/docs",
        redoc_url=None if resolved_disable_docs else "/redoc",
        openapi_url=None if resolved_disable_docs else "/openapi.json",
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

    @application.get("/api/config")
    def get_config() -> Dict[str, bool]:
        return {
            "admin_protected": bool(resolved_token),
            "public_readonly": bool(resolved_readonly and not resolved_token),
            "docs_enabled": not resolved_disable_docs,
        }

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

    @application.post("/api/cards", response_model=CardOut, dependencies=[Depends(require_admin_write)])
    def create_or_update_card(card: CardIn) -> CardOut:
        return upsert_card(card, application.state.db_path)

    @application.post("/api/recommend", response_model=RecommendResponse)
    def recommend(request: RecommendRequest) -> RecommendResponse:
        cards = list_cards(application.state.db_path)
        return recommend_cards(cards, request)

    @application.get("/api/scrapers")
    def get_scrapers() -> List[Dict[str, str]]:
        return list_available_scrapers()

    @application.get("/api/banks", response_model=List[BankCatalogItem])
    def get_banks() -> List[BankCatalogItem]:
        return list_bank_catalog(db_path=application.state.db_path)

    @application.get("/api/banks/{bank_code}/cards", response_model=List[BankCardCatalogItem])
    def get_bank_cards(bank_code: str) -> List[BankCardCatalogItem]:
        cards = list_cards_for_bank(bank_code, db_path=application.state.db_path)
        if cards is None:
            raise HTTPException(status_code=404, detail="Bank not found")
        return cards

    @application.post(
        "/api/banks/{bank_code}/discover",
        response_model=BankDiscoverResponse,
        dependencies=[Depends(require_admin_write)],
    )
    async def discover_bank_cards(bank_code: str) -> BankDiscoverResponse:
        result = await discover_bank_cards_via_playwright(
            bank_code,
            db_path=application.state.db_path,
        )
        if result is None:
            raise HTTPException(status_code=404, detail="Bank not found")
        return result

    @application.get("/api/scrape-logs")
    def get_scrape_logs(limit: int = 20) -> List[dict]:
        return list_scrape_logs(limit=limit, db_path=application.state.db_path)

    @application.post("/api/scrape", response_model=ScrapeResponse, dependencies=[Depends(require_admin_write)])
    async def trigger_scrape(request: ScrapeRequest) -> ScrapeResponse:
        if request.mode not in ("live", "demo_html"):
            raise HTTPException(status_code=400, detail="mode must be 'live' or 'demo_html'")
        results = await run_scrapers(
            bank_codes=request.bank_codes,
            mode=request.mode,
            db_path=application.state.db_path,
        )
        return ScrapeResponse(mode=request.mode, results=results)

    @application.post(
        "/api/scrape/custom",
        response_model=ScrapeResponse,
        dependencies=[Depends(require_admin_write)],
    )
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
