"""Unit tests for the credit card reward calculation and recommendation engine."""

from app.db import init_db, list_cards, upsert_card
from app.models import CardIn, RecommendRequest, RewardRuleIn
from app.recommender import recommend_cards
from app.seed_data import ensure_seed_data


def test_switchable_plan_selects_best_plan(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    ensure_seed_data(db_path)
    cards = list_cards(db_path)

    # Heavy overseas + travel spending should pick Cathay CUBE "趣旅行"
    resp = recommend_cards(
        cards,
        RecommendRequest(monthly_spending={"overseas": 20000, "travel": 10000}),
    )
    cube = next(r for r in resp.recommendations if r.card_slug == "cathay-cube")
    assert cube.recommended_plan == "趣旅行"
    assert cube.total_reward_ntd == 900.0
    assert cube.last_updated != ""


def test_monthly_cap_and_excess_base_rate(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    upsert_card(
        CardIn(
            bank_name="測試銀行",
            card_name="上限測試卡",
            card_slug="cap-test",
            base_rate_domestic=1.0,
            rules=[
                RewardRuleIn(
                    channel_code="ecommerce",
                    channel_label="網購電商",
                    rate=5.0,
                    monthly_cap_ntd=500.0,
                )
            ],
        ),
        db_path=db_path,
    )
    cards = list_cards(db_path)

    # 20,000 * 5% = 1,000 -> capped at 500 for first 10,000, remaining 10,000 * 1% = 100 -> 600 total
    resp = recommend_cards(cards, RecommendRequest(monthly_spending={"ecommerce": 20000}))
    rec = resp.recommendations[0]
    assert rec.total_reward_ntd == 600.0
    assert rec.breakdown[0].cap_reached is True


def test_min_spend_requirement_fallback(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    upsert_card(
        CardIn(
            bank_name="測試銀行",
            card_name="門檻測試卡",
            card_slug="min-spend-test",
            base_rate_domestic=0.5,
            rules=[
                RewardRuleIn(
                    channel_code="dining",
                    channel_label="餐飲美食",
                    rate=5.0,
                    min_spend_ntd=5000.0,
                )
            ],
        ),
        db_path=db_path,
    )
    cards = list_cards(db_path)

    # Below threshold (2000 < 5000) -> falls back to 0.5% -> 10 NTD
    low_resp = recommend_cards(cards, RecommendRequest(monthly_spending={"dining": 2000}))
    assert low_resp.recommendations[0].total_reward_ntd == 10.0

    # Above threshold (6000 >= 5000) -> gets 5% -> 300 NTD
    high_resp = recommend_cards(cards, RecommendRequest(monthly_spending={"dining": 6000}))
    assert high_resp.recommendations[0].total_reward_ntd == 300.0

    # Exclude cards with min spend when only_no_min_spend=True
    filtered_resp = recommend_cards(
        cards,
        RecommendRequest(monthly_spending={"dining": 6000}, only_no_min_spend=True),
    )
    assert filtered_resp.recommendations == []


def test_multi_card_combo_beats_or_equals_single_card(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    ensure_seed_data(db_path)
    cards = list_cards(db_path)

    resp = recommend_cards(
        cards,
        RecommendRequest(
            monthly_spending={
                "overseas": 10000,
                "delivery": 4000,
                "ecommerce": 5000,
            }
        ),
    )
    assert resp.combo is not None
    best_single = resp.recommendations[0].total_reward_ntd
    assert resp.combo.total_reward_ntd >= best_single
    assert resp.combo.gain_over_best_single_ntd == round(resp.combo.total_reward_ntd - best_single, 2)
