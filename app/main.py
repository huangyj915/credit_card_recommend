"""FastAPI application entrypoint serving both API endpoints and the static web UI."""

from collections import deque
from contextlib import asynccontextmanager
import hashlib
import hmac
import logging
import os
from pathlib import Path
import secrets
import time
from typing import Deque, Dict, List, Optional
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.catalog import (
    discover_bank_cards_via_playwright,
    list_bank_catalog,
    list_cards_for_bank,
)
from app.db import get_card_by_slug, init_db, list_cards, list_scrape_logs, upsert_card
from app.i18n import (
    get_localized_channels,
    normalize_lang,
    t_backend,
    translate_card_out,
    translate_scrape_log,
)
from app.models import (
    AdminLoginRequest,
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
from app.scrapers.manager import ScraperBusyError, list_available_scrapers, run_scrapers
from app.seed_data import ensure_seed_data

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

ADMIN_SESSION_COOKIE = "cc_admin_session"
ADMIN_SESSION_TTL_SECONDS = 8 * 60 * 60
_PLACEHOLDER_ADMIN_TOKEN = "change-me-to-a-strong-password"
_STRICT_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "frame-ancestors 'none'"
)


class _SlidingWindowRateLimiter:
    """Simple in-memory per-IP sliding window rate limiter."""

    def __init__(self, max_requests: int, window_seconds: int = 60, max_keys: int = 4096) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._hits: Dict[str, Deque[float]] = {}

    def allow(self, key: str) -> bool:
        if self.max_requests <= 0:
            return True
        now = time.monotonic()
        cutoff = now - self.window_seconds
        bucket = self._hits.get(key)
        if bucket is None:
            if len(self._hits) >= self.max_keys:
                self._prune(cutoff)
            bucket = deque()
            self._hits[key] = bucket
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= self.max_requests:
            return False
        bucket.append(now)
        return True

    def _prune(self, cutoff: float) -> None:
        stale = [k for k, q in self._hits.items() if not q or q[-1] <= cutoff]
        for k in stale:
            del self._hits[k]
        if len(self._hits) >= self.max_keys:
            self._hits.clear()


def _client_ip(request: Request) -> str:
    return request.client.host if request.client and request.client.host else "unknown"


def _is_https_request(request: Request) -> bool:
    proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    return request.url.scheme == "https" or proto == "https"


def _verify_csrf_for_cookie_auth(request: Request) -> bool:
    """Validate same-origin or custom X-Requested-With header when using cookie auth."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return True
    origin = (request.headers.get("origin") or "").strip()
    referer = (request.headers.get("referer") or "").strip()
    expected_host = (request.headers.get("host") or request.url.netloc or "").lower()
    if origin:
        parsed_origin = urlparse(origin)
        return (parsed_origin.netloc or "").lower() == expected_host
    if referer:
        parsed_ref = urlparse(referer)
        return (parsed_ref.netloc or "").lower() == expected_host
    return bool((request.headers.get("x-requested-with") or "").strip())


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
    admin_rate_limit: int = 20,
    recommend_rate_limit: int = 120,
    rate_window_seconds: int = 60,
) -> FastAPI:
    resolved_token = (
        os.getenv("ADMIN_TOKEN", "").strip() if admin_token is None else admin_token.strip()
    )
    if resolved_token.lower() == _PLACEHOLDER_ADMIN_TOKEN:
        raise ValueError(
            "ADMIN_TOKEN is still set to the .env.example placeholder; please configure a strong secret."
        )
    if resolved_token and len(resolved_token) < 12:
        logger.warning(
            "ADMIN_TOKEN is shorter than 12 characters; consider using a stronger secret in production."
        )

    resolved_readonly = (
        _env_flag("PUBLIC_READONLY", False) if public_readonly is None else public_readonly
    )
    resolved_disable_docs = (
        _env_flag("DISABLE_DOCS", False) if disable_docs is None else disable_docs
    )

    session_key = hashlib.sha256(
        f"cc-admin:{resolved_token}:{secrets.token_hex(16)}".encode("utf-8")
    ).digest()
    admin_auth_limiter = _SlidingWindowRateLimiter(admin_rate_limit, rate_window_seconds)
    recommend_limiter = _SlidingWindowRateLimiter(recommend_rate_limit, rate_window_seconds)

    def _issue_session_cookie_value() -> str:
        exp = int(time.time()) + ADMIN_SESSION_TTL_SECONDS
        nonce = secrets.token_urlsafe(16)
        payload = f"{exp}.{nonce}"
        sig = hmac.new(session_key, payload.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"{payload}.{sig}"

    def _has_valid_admin_cookie(request: Request) -> bool:
        if not resolved_token:
            return False
        raw = request.cookies.get(ADMIN_SESSION_COOKIE, "")
        parts = raw.split(".")
        if len(parts) != 3:
            return False
        exp_str, nonce, sig = parts
        try:
            exp = int(exp_str)
        except ValueError:
            return False
        if exp < int(time.time()):
            return False
        payload = f"{exp_str}.{nonce}"
        expected = hmac.new(session_key, payload.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected)

    def _enforce_rate_limit(
        limiter: _SlidingWindowRateLimiter,
        request: Request,
        resolved_lang: str,
    ) -> None:
        if not limiter.allow(_client_ip(request)):
            raise HTTPException(
                status_code=429,
                detail=t_backend("rate_limit_exceeded", resolved_lang),
            )

    def require_admin_write(
        request: Request,
        x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
        x_lang: Optional[str] = Header(default=None, alias="X-Lang"),
    ) -> None:
        resolved_lang = normalize_lang(request.query_params.get("lang") or x_lang)
        if resolved_token:
            provided = (x_admin_token or "").strip()
            if provided:
                if hmac.compare_digest(provided, resolved_token):
                    return
                _enforce_rate_limit(admin_auth_limiter, request, resolved_lang)
                raise HTTPException(
                    status_code=403,
                    detail=t_backend("admin_token_required", resolved_lang),
                )
            if _has_valid_admin_cookie(request):
                if not _verify_csrf_for_cookie_auth(request):
                    raise HTTPException(
                        status_code=403,
                        detail=t_backend("csrf_required", resolved_lang),
                    )
                return
            _enforce_rate_limit(admin_auth_limiter, request, resolved_lang)
            raise HTTPException(
                status_code=403,
                detail=t_backend("admin_token_required", resolved_lang),
            )
        if resolved_readonly:
            raise HTTPException(
                status_code=403,
                detail=t_backend("public_readonly", resolved_lang),
            )

    def require_admin_logs_if_protected(
        request: Request,
        x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
        x_lang: Optional[str] = Header(default=None, alias="X-Lang"),
    ) -> None:
        if not resolved_token:
            return
        resolved_lang = normalize_lang(request.query_params.get("lang") or x_lang)
        provided = (x_admin_token or "").strip()
        if provided and hmac.compare_digest(provided, resolved_token):
            return
        if _has_valid_admin_cookie(request):
            return
        raise HTTPException(
            status_code=403,
            detail=t_backend("admin_token_required", resolved_lang),
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
    async def security_and_cache_headers(request: Request, call_next):
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if request.url.path in ("/docs", "/redoc"):
            response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
        else:
            response.headers["Content-Security-Policy"] = _STRICT_CSP
        if _is_https_request(request):
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
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

    @application.get("/api/admin/session")
    def get_admin_session(request: Request) -> Dict[str, bool]:
        return {"authenticated": _has_valid_admin_cookie(request)}

    @application.post("/api/admin/login")
    def admin_login(
        payload: AdminLoginRequest,
        request: Request,
        response: Response,
        lang: Optional[str] = None,
        x_lang: Optional[str] = Header(default=None, alias="X-Lang"),
    ) -> Dict[str, bool]:
        resolved_lang = normalize_lang(lang or x_lang)
        _enforce_rate_limit(admin_auth_limiter, request, resolved_lang)
        if not resolved_token:
            raise HTTPException(status_code=400, detail="Admin token mode is not enabled")
        if not hmac.compare_digest(payload.token.strip(), resolved_token):
            raise HTTPException(
                status_code=403,
                detail=t_backend("admin_token_required", resolved_lang),
            )
        response.set_cookie(
            key=ADMIN_SESSION_COOKIE,
            value=_issue_session_cookie_value(),
            httponly=True,
            samesite="strict",
            secure=_is_https_request(request),
            max_age=ADMIN_SESSION_TTL_SECONDS,
            path="/",
        )
        return {"authenticated": True}

    @application.post("/api/admin/logout")
    def admin_logout(
        request: Request,
        response: Response,
        lang: Optional[str] = None,
        x_lang: Optional[str] = Header(default=None, alias="X-Lang"),
    ) -> Dict[str, bool]:
        resolved_lang = normalize_lang(lang or x_lang)
        if not _verify_csrf_for_cookie_auth(request):
            raise HTTPException(
                status_code=403,
                detail=t_backend("csrf_required", resolved_lang),
            )
        response.delete_cookie(key=ADMIN_SESSION_COOKIE, path="/")
        return {"authenticated": False}

    @application.get("/api/channels")
    def get_channels(lang: Optional[str] = None) -> List[Dict[str, str]]:
        return get_localized_channels(lang)

    @application.get("/api/cards", response_model=List[CardOut])
    def get_cards(lang: Optional[str] = None) -> List[CardOut]:
        cards = list_cards(application.state.db_path)
        return [translate_card_out(c, lang) for c in cards]

    @application.get("/api/cards/{card_slug}", response_model=CardOut)
    def get_card(card_slug: str, lang: Optional[str] = None) -> CardOut:
        card = get_card_by_slug(card_slug, application.state.db_path)
        if card is None:
            raise HTTPException(status_code=404, detail="Card not found")
        return translate_card_out(card, lang)

    @application.post("/api/cards", response_model=CardOut, dependencies=[Depends(require_admin_write)])
    def create_or_update_card(card: CardIn) -> CardOut:
        return upsert_card(card, application.state.db_path)

    @application.post("/api/recommend", response_model=RecommendResponse)
    def recommend(
        request: RecommendRequest,
        http_request: Request,
        lang: Optional[str] = None,
    ) -> RecommendResponse:
        resolved_lang = normalize_lang(lang or request.lang)
        _enforce_rate_limit(recommend_limiter, http_request, resolved_lang)
        cards = list_cards(application.state.db_path)
        return recommend_cards(cards, request, lang=resolved_lang)

    @application.get("/api/scrapers")
    def get_scrapers(lang: Optional[str] = None) -> List[Dict[str, str]]:
        return list_available_scrapers(lang=lang)

    @application.get("/api/banks", response_model=List[BankCatalogItem])
    def get_banks(lang: Optional[str] = None) -> List[BankCatalogItem]:
        return list_bank_catalog(db_path=application.state.db_path, lang=lang)

    @application.get("/api/banks/{bank_code}/cards", response_model=List[BankCardCatalogItem])
    def get_bank_cards(bank_code: str, lang: Optional[str] = None) -> List[BankCardCatalogItem]:
        cards = list_cards_for_bank(bank_code, db_path=application.state.db_path, lang=lang)
        if cards is None:
            raise HTTPException(status_code=404, detail="Bank not found")
        return cards

    @application.post(
        "/api/banks/{bank_code}/discover",
        response_model=BankDiscoverResponse,
        dependencies=[Depends(require_admin_write)],
    )
    async def discover_bank_cards(bank_code: str, lang: Optional[str] = None) -> BankDiscoverResponse:
        try:
            result = await discover_bank_cards_via_playwright(
                bank_code,
                db_path=application.state.db_path,
                lang=lang,
            )
        except ScraperBusyError:
            raise HTTPException(
                status_code=429,
                detail=t_backend("scraper_busy", normalize_lang(lang)),
            )
        if result is None:
            raise HTTPException(status_code=404, detail="Bank not found")
        return result

    @application.get(
        "/api/scrape-logs",
        dependencies=[Depends(require_admin_logs_if_protected)],
    )
    def get_scrape_logs(
        limit: int = Query(default=20, ge=1, le=200),
        lang: Optional[str] = None,
    ) -> List[dict]:
        logs = list_scrape_logs(limit=limit, db_path=application.state.db_path)
        return [translate_scrape_log(item, lang=lang) for item in logs]

    @application.post("/api/scrape", response_model=ScrapeResponse, dependencies=[Depends(require_admin_write)])
    async def trigger_scrape(request: ScrapeRequest, lang: Optional[str] = None) -> ScrapeResponse:
        if request.mode not in ("live", "demo_html"):
            raise HTTPException(status_code=400, detail="mode must be 'live' or 'demo_html'")
        resolved_lang = normalize_lang(lang or request.lang)
        try:
            results = await run_scrapers(
                bank_codes=request.bank_codes,
                mode=request.mode,
                db_path=application.state.db_path,
                lang=resolved_lang,
            )
        except ScraperBusyError:
            raise HTTPException(
                status_code=429,
                detail=t_backend("scraper_busy", resolved_lang),
            )
        return ScrapeResponse(mode=request.mode, results=results)

    @application.post(
        "/api/scrape/custom",
        response_model=ScrapeResponse,
        dependencies=[Depends(require_admin_write)],
    )
    async def trigger_custom_scrape(
        request: CustomScrapeRequest,
        lang: Optional[str] = None,
    ) -> ScrapeResponse:
        if request.mode not in ("live", "demo_html"):
            raise HTTPException(status_code=400, detail="mode must be 'live' or 'demo_html'")
        if not request.card_name.strip():
            raise HTTPException(status_code=400, detail="card_name must not be empty")
        resolved_lang = normalize_lang(lang or request.lang)
        try:
            result = await scrape_custom_card(
                card_name=request.card_name,
                bank_name=request.bank_name,
                official_url=request.official_url,
                mode=request.mode,
                db_path=application.state.db_path,
                lang=resolved_lang,
            )
        except ScraperBusyError:
            raise HTTPException(
                status_code=429,
                detail=t_backend("scraper_busy", resolved_lang),
            )
        return ScrapeResponse(mode=request.mode, results=[result])

    return application


app = create_app()
