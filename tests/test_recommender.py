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
    assert rec.breakdown[0].note_truncated is False


def test_truncated_scraped_rule_sets_note_truncated(tmp_path):
    db_path = tmp_path / "trunc.db"
    init_db(db_path)
    long_cond = "指定網購及行動支付優惠活動說明文字超過一百二十個字元時會於爬蟲階段截斷並加上刪節號提示使用者前往銀行官網查看完整權益內容與排除條款詳情" * 2
    upsert_card(
        CardIn(
            bank_name="測試銀行",
            card_name="截斷測試卡",
            card_slug="trunc-test",
            official_url="https://example.com/card",
            rules=[
                RewardRuleIn(
                    channel_code="ecommerce",
                    channel_label="網購電商",
                    rate=3.0,
                    conditions=long_cond[:120],
                )
            ],
        ),
        db_path=db_path,
    )
    cards = list_cards(db_path)
    resp = recommend_cards(cards, RecommendRequest(monthly_spending={"ecommerce": 1000}))
    assert resp.recommendations[0].breakdown[0].note_truncated is True


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


def test_bonus_cap_and_shared_cap_group(tmp_path):
    db_path = tmp_path / "shared_cap.db"
    init_db(db_path)
    ensure_seed_data(db_path)
    cards = list_cards(db_path)
    ubear = next(c for c in cards if c.card_slug == "esun-ubear")

    # Single channel NT$10,000 on U Bear: 1% base unlimited (100) + 2% bonus exactly at cap (200) = 300
    single_resp = recommend_cards(
        [ubear], RecommendRequest(monthly_spending={"ecommerce": 10000})
    )
    assert single_resp.recommendations[0].total_reward_ntd == 300.0
    assert single_resp.recommendations[0].breakdown[0].cap_reached is False

    # Single channel NT$15,000 on U Bear: 1% base (150) + 2% bonus capped at 200 = 350 (cap reached)
    over_resp = recommend_cards(
        [ubear], RecommendRequest(monthly_spending={"ecommerce": 15000})
    )
    assert over_resp.recommendations[0].total_reward_ntd == 350.0
    assert over_resp.recommendations[0].breakdown[0].cap_reached is True

    # Multiple channels sharing cap_group ("ubear_online"): NT$6,000 + NT$6,000 = NT$12,000
    # Base 1% (120) + shared 2% bonus capped at 200 (not 200*2!) = 320
    multi_resp = recommend_cards(
        [ubear],
        RecommendRequest(monthly_spending={"ecommerce": 6000, "mobile_pay": 6000}),
    )
    rec = multi_resp.recommendations[0]
    assert rec.total_reward_ntd == 320.0
    assert all(b.cap_reached for b in rec.breakdown)


def test_combo_plan_consistency_min_spend_and_max_cards(tmp_path):
    db_path = tmp_path / "combo_edge.db"
    init_db(db_path)
    ensure_seed_data(db_path)

    # Custom card with 5,000 min_spend across two channels (3,000 + 3,000 = 6,000 >= 5,000)
    upsert_card(
        CardIn(
            bank_name="門檻銀行",
            card_name="雙通路低消卡",
            card_slug="combo-min-spend",
            base_rate_domestic=0.5,
            rules=[
                RewardRuleIn(
                    channel_code="dining",
                    channel_label="餐飲美食",
                    rate=8.0,
                    min_spend_ntd=5000.0,
                ),
                RewardRuleIn(
                    channel_code="travel",
                    channel_label="旅遊住宿",
                    rate=8.0,
                    min_spend_ntd=5000.0,
                ),
            ],
        ),
        db_path=db_path,
    )
    cards = list_cards(db_path)

    # 1. Combo must unlock 8% across dining + travel (6,000 >= 5,000) even though each is 3,000 < 5,000
    min_resp = recommend_cards(
        cards, RecommendRequest(monthly_spending={"dining": 3000, "travel": 3000})
    )
    assert min_resp.combo is not None
    assert min_resp.combo.total_reward_ntd == 480.0

    # 2. Single-card CUBE in combo must not use two different plans simultaneously
    cube = next(c for c in cards if c.card_slug == "cathay-cube")
    cube_combo = recommend_cards(
        [cube],
        RecommendRequest(monthly_spending={"ecommerce": 5000, "dining": 5000, "overseas": 5000}),
    )
    assert cube_combo.combo is not None
    used_plans = {a.plan_name for a in cube_combo.combo.allocations if a.plan_name}
    assert len(used_plans) <= 1

    # 3. max_combo_cards=2 caps distinct cards in combo to <= 2
    limited_resp = recommend_cards(
        cards,
        RecommendRequest(
            monthly_spending={
                "overseas": 10000,
                "transport": 5000,
                "ecommerce": 5000,
                "dining": 5000,
            },
            max_combo_cards=2,
        ),
    )
    assert limited_resp.combo is not None
    assert len(limited_resp.combo.selected_cards) <= 2


def test_overseas_fee_deduction(tmp_path):
    db_path = tmp_path / "fx_fee.db"
    init_db(db_path)
    ensure_seed_data(db_path)
    cards = list_cards(db_path)
    fubon_j = next(c for c in cards if c.card_slug == "fubon-j")

    gross = recommend_cards(
        [fubon_j],
        RecommendRequest(monthly_spending={"overseas": 10000}, deduct_overseas_fee=False),
    )
    net = recommend_cards(
        [fubon_j],
        RecommendRequest(monthly_spending={"overseas": 10000}, deduct_overseas_fee=True),
    )
    # 10,000 * 6% = 600 gross; minus 1.5% fee (150) = 450 net
    assert gross.recommendations[0].total_reward_ntd == 600.0
    assert net.recommendations[0].total_reward_ntd == 450.0
    assert "1.5%" in net.recommendations[0].breakdown[0].note
