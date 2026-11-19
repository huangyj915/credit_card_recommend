"""Pydantic schemas for credit cards, reward rules, recommendations, and scraping."""

import math
import re
from typing import Dict, List, Literal, Optional
from urllib.parse import urlparse
from pydantic import BaseModel, Field, field_validator

from app.channels import CHANNEL_MAP

MAX_CHANNEL_SPEND_NTD = 9_999_999.0
_CARD_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")


class RewardRuleIn(BaseModel):
    channel_code: str = Field(..., description="Standardized channel code")
    channel_label: str = Field(..., description="Human-readable channel label")
    plan_name: Optional[str] = Field(None, description="Optional switchable plan name")
    rate: float = Field(..., ge=0.0, le=100.0, description="Reward rate percentage, e.g. 3.0")
    monthly_cap_ntd: Optional[float] = Field(
        None, ge=0.0, description="Monthly reward cap in NTD (None = unlimited)"
    )
    cap_group: Optional[str] = Field(
        None, description="Optional shared monthly cap group identifier across multiple channels"
    )
    cap_applies_to: Literal["total", "bonus"] = Field(
        default="total",
        description="Whether monthly_cap_ntd caps 'total' reward or 'bonus' reward above base_rate",
    )
    min_spend_ntd: Optional[float] = Field(
        None, ge=0.0, description="Minimum monthly card spend required to unlock this rate"
    )
    payment_methods: List[str] = Field(default_factory=list)
    conditions: str = Field(default="")

    @field_validator("channel_code")
    @classmethod
    def validate_channel_code(cls, v: str) -> str:
        cleaned = (v or "").strip()
        if cleaned not in CHANNEL_MAP:
            raise ValueError(f"Invalid channel_code: '{v}'")
        return cleaned


class RewardRuleOut(RewardRuleIn):
    id: int
    card_id: int


class CardIn(BaseModel):
    bank_name: str
    card_name: str
    card_slug: str
    official_url: str = ""
    annual_fee: str = "免年費（達成條件）"
    base_rate_domestic: float = Field(default=0.3, ge=0.0, le=100.0)
    base_rate_foreign: float = Field(default=0.3, ge=0.0, le=100.0)
    reward_unit: str = "現金回饋 / 點數"
    notes: str = ""
    source_type: str = "seed"
    rules: List[RewardRuleIn] = Field(default_factory=list, max_length=100)

    @field_validator("card_slug")
    @classmethod
    def validate_card_slug(cls, v: str) -> str:
        cleaned = (v or "").strip()
        if not _CARD_SLUG_RE.fullmatch(cleaned):
            raise ValueError(
                "card_slug must be 1-80 lowercase alphanumeric, hyphen, or underscore characters"
            )
        return cleaned

    @field_validator("official_url")
    @classmethod
    def validate_official_url(cls, v: str) -> str:
        cleaned = (v or "").strip()
        if not cleaned:
            return ""
        parsed = urlparse(cleaned)
        if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
            raise ValueError("official_url must be a valid http:// or https:// URL")
        return cleaned


class CardOut(BaseModel):
    id: int
    bank_name: str
    card_name: str
    card_slug: str
    official_url: str
    annual_fee: str
    base_rate_domestic: float
    base_rate_foreign: float
    reward_unit: str
    notes: str
    source_type: str
    last_updated: str
    rules: List[RewardRuleOut] = Field(default_factory=list)


class RecommendRequest(BaseModel):
    monthly_spending: Dict[str, float] = Field(
        default_factory=dict,
        description="Mapping from channel_code to monthly NTD spending",
    )
    preferred_payment: Optional[str] = Field(
        None, description="Optional preferred payment method filter/note"
    )
    only_no_min_spend: bool = Field(
        False, description="If true, exclude cards with minimum spend requirements"
    )
    max_combo_cards: Optional[int] = Field(
        None, ge=1, le=10, description="Optional max number of cards in multi-card combo"
    )
    deduct_overseas_fee: bool = Field(
        False, description="If true, deduct 1.5% foreign transaction fee from overseas rewards"
    )
    lang: Optional[str] = Field(
        None, description="Optional response language ('zh-TW' or 'en')"
    )

    @field_validator("monthly_spending")
    @classmethod
    def validate_monthly_spending_bounds(cls, v: Dict[str, float]) -> Dict[str, float]:
        for channel, amount in v.items():
            if amount is None:
                continue
            if math.isnan(amount) or math.isinf(amount) or amount < 0 or amount > MAX_CHANNEL_SPEND_NTD:
                raise ValueError(
                    f"Monthly spending for '{channel}' must be between 0 and {int(MAX_CHANNEL_SPEND_NTD):,} NTD"
                )
        return v


class ChannelBreakdown(BaseModel):
    channel_code: str
    channel_label: str
    spend_ntd: float
    applied_rate: float
    applied_plan: Optional[str] = None
    raw_reward_ntd: float
    actual_reward_ntd: float
    cap_ntd: Optional[float] = None
    cap_reached: bool = False
    note: str = ""
    note_truncated: bool = False


class CardRecommendation(BaseModel):
    card_id: int
    bank_name: str
    card_name: str
    card_slug: str
    official_url: str
    annual_fee: str
    reward_unit: str
    source_type: str
    last_updated: str = ""
    recommended_plan: Optional[str] = None
    total_spend_ntd: float
    total_reward_ntd: float
    effective_rate_pct: float
    matched_highlights: List[str] = Field(default_factory=list)
    breakdown: List[ChannelBreakdown] = Field(default_factory=list)


class ComboAllocation(BaseModel):
    channel_code: str
    channel_label: str
    spend_ntd: float
    card_slug: str
    bank_name: str
    card_name: str
    plan_name: Optional[str] = None
    applied_rate: float
    reward_ntd: float


class ComboRecommendation(BaseModel):
    total_spend_ntd: float
    total_reward_ntd: float
    effective_rate_pct: float
    gain_over_best_single_ntd: float
    selected_cards: List[str]
    allocations: List[ComboAllocation]


class RecommendResponse(BaseModel):
    total_spend_ntd: float
    recommendations: List[CardRecommendation]
    combo: Optional[ComboRecommendation] = None


class ScrapeRequest(BaseModel):
    bank_codes: List[str] = Field(
        default_factory=lambda: ["cathay", "esun", "taishin"],
        description="Bank scraper codes to run",
    )
    mode: str = Field(
        default="live",
        description="'live' to scrape official bank URLs with Playwright; 'demo_html' to run Playwright against built-in sample bank HTML",
    )
    lang: Optional[str] = Field(None, description="Optional response language ('zh-TW' or 'en')")


class CustomScrapeRequest(BaseModel):
    card_name: str = Field(..., min_length=1, max_length=100, description="Target credit card name")
    bank_name: Optional[str] = Field(None, max_length=60, description="Optional issuing bank name")
    official_url: Optional[str] = Field(None, max_length=500, description="Optional official card URL")
    mode: str = Field(default="live", description="'live' or 'demo_html'")
    lang: Optional[str] = Field(None, description="Optional response language ('zh-TW' or 'en')")


class ScrapeResultItem(BaseModel):
    bank_code: str
    card_slug: str
    status: str
    message: str
    rules_count: int = 0
    url: str = ""


class ScrapeResponse(BaseModel):
    mode: str
    results: List[ScrapeResultItem]


class BankCardCatalogItem(BaseModel):
    card_name: str
    bank_name: str
    official_url: str = ""
    in_db: bool = False
    card_slug: Optional[str] = None
    source_type: Optional[str] = None
    last_updated: Optional[str] = None
    catalog_source: str = "catalog"


class BankCatalogItem(BaseModel):
    bank_code: str
    bank_name: str
    list_url: str = ""
    card_count: int = 0


class BankDiscoverResponse(BaseModel):
    bank_code: str
    bank_name: str
    status: str
    message: str
    cards: List[BankCardCatalogItem] = Field(default_factory=list)


class AdminLoginRequest(BaseModel):
    token: str = Field(..., min_length=1, max_length=256)
