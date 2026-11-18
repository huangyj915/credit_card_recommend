"""Pydantic schemas for credit cards, reward rules, recommendations, and scraping."""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class RewardRuleIn(BaseModel):
    channel_code: str = Field(..., description="Standardized channel code")
    channel_label: str = Field(..., description="Human-readable channel label")
    plan_name: Optional[str] = Field(None, description="Optional switchable plan name")
    rate: float = Field(..., ge=0.0, le=100.0, description="Reward rate percentage, e.g. 3.0")
    monthly_cap_ntd: Optional[float] = Field(
        None, ge=0.0, description="Monthly reward cap in NTD (None = unlimited)"
    )
    min_spend_ntd: Optional[float] = Field(
        None, ge=0.0, description="Minimum monthly card spend required to unlock this rate"
    )
    payment_methods: List[str] = Field(default_factory=list)
    conditions: str = Field(default="")


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
    rules: List[RewardRuleIn] = Field(default_factory=list)


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
