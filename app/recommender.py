"""Credit card reward calculation & single/multi-card recommendation engine."""

from typing import Dict, List, Optional, Tuple

from app.channels import CHANNEL_MAP
from app.models import (
    CardOut,
    CardRecommendation,
    ChannelBreakdown,
    ComboAllocation,
    ComboRecommendation,
    RecommendRequest,
    RecommendResponse,
    RewardRuleOut,
)


def _base_rate_for_channel(card: CardOut, channel_code: str) -> float:
    if channel_code == "overseas":
        return card.base_rate_foreign
    return card.base_rate_domestic


def _evaluate_rule(
    card: CardOut,
    rule: Optional[RewardRuleOut],
    channel_code: str,
    spend_ntd: float,
    total_card_spend: float,
) -> ChannelBreakdown:
    channel_info = CHANNEL_MAP.get(channel_code, {"label": channel_code})
    channel_label = channel_info["label"]
    base_rate = _base_rate_for_channel(card, channel_code)

    if rule is None:
        raw_reward = round(spend_ntd * (base_rate / 100.0), 2)
        return ChannelBreakdown(
            channel_code=channel_code,
            channel_label=channel_label,
            spend_ntd=spend_ntd,
            applied_rate=base_rate,
            applied_plan=None,
            raw_reward_ntd=raw_reward,
            actual_reward_ntd=raw_reward,
            cap_ntd=None,
            cap_reached=False,
            note="適用基本消費回饋",
        )

    # Check minimum monthly spend requirement
    if rule.min_spend_ntd is not None and total_card_spend < rule.min_spend_ntd:
        raw_reward = round(spend_ntd * (base_rate / 100.0), 2)
        return ChannelBreakdown(
            channel_code=channel_code,
            channel_label=channel_label,
            spend_ntd=spend_ntd,
            applied_rate=base_rate,
            applied_plan=rule.plan_name,
            raw_reward_ntd=raw_reward,
            actual_reward_ntd=raw_reward,
            cap_ntd=rule.monthly_cap_ntd,
            cap_reached=False,
            note=f"未達低消門檻 NT${int(rule.min_spend_ntd):,}，改計基本回饋 {base_rate}%",
        )

    raw_reward = round(spend_ntd * (rule.rate / 100.0), 2)
    actual_reward = raw_reward
    cap_reached = False
    note = rule.conditions or ""

    if rule.monthly_cap_ntd is not None and raw_reward > rule.monthly_cap_ntd:
        # Up to the cap earns rule.rate; remaining spend falls back to base_rate
        cap_reached = True
        if rule.rate > 0:
            max_capped_spend = rule.monthly_cap_ntd / (rule.rate / 100.0)
            excess_spend = max(0.0, spend_ntd - max_capped_spend)
            excess_base_reward = excess_spend * (base_rate / 100.0)
            actual_reward = round(rule.monthly_cap_ntd + excess_base_reward, 2)
        else:
            actual_reward = round(rule.monthly_cap_ntd, 2)
        cap_msg = f"已達月回饋上限 NT${int(rule.monthly_cap_ntd):,}（超過部分以基本回饋 {base_rate}% 計）"
        note = f"{note}；{cap_msg}" if note else cap_msg

    return ChannelBreakdown(
        channel_code=channel_code,
        channel_label=channel_label,
        spend_ntd=spend_ntd,
        applied_rate=rule.rate,
        applied_plan=rule.plan_name,
        raw_reward_ntd=raw_reward,
        actual_reward_ntd=actual_reward,
        cap_ntd=rule.monthly_cap_ntd,
        cap_reached=cap_reached,
        note=note,
    )


def _evaluate_card_for_plan(
    card: CardOut,
    spending: Dict[str, float],
    active_plan: Optional[str],
    preferred_payment: Optional[str],
) -> Tuple[float, List[ChannelBreakdown]]:
    total_spend = sum(spending.values())
    breakdowns: List[ChannelBreakdown] = []

    for channel_code, spend_ntd in spending.items():
        if spend_ntd <= 0:
            continue

        # Candidate rules: always include plan-agnostic rules + rules matching active_plan
        candidates = [
            r
            for r in card.rules
            if r.channel_code == channel_code
            and (r.plan_name is None or r.plan_name == active_plan)
        ]

        # If user specified a preferred payment method, slightly prefer rules mentioning it when rates tie
        best_bd: Optional[ChannelBreakdown] = None
        for rule in candidates:
            bd = _evaluate_rule(card, rule, channel_code, spend_ntd, total_spend)
            if best_bd is None:
                best_bd = bd
            elif bd.actual_reward_ntd > best_bd.actual_reward_ntd:
                best_bd = bd
            elif (
                bd.actual_reward_ntd == best_bd.actual_reward_ntd
                and preferred_payment
                and preferred_payment in rule.payment_methods
            ):
                best_bd = bd

        if best_bd is None:
            best_bd = _evaluate_rule(card, None, channel_code, spend_ntd, total_spend)

        breakdowns.append(best_bd)

    total_reward = round(sum(b.actual_reward_ntd for b in breakdowns), 2)
    return total_reward, breakdowns


def evaluate_card(
    card: CardOut,
    spending: Dict[str, float],
    preferred_payment: Optional[str] = None,
) -> CardRecommendation:
    total_spend = round(sum(v for v in spending.values() if v > 0), 2)
    plan_names = sorted({r.plan_name for r in card.rules if r.plan_name})

    if plan_names:
        best_plan: Optional[str] = None
        best_reward = -1.0
        best_breakdowns: List[ChannelBreakdown] = []
        for plan in plan_names:
            reward, bds = _evaluate_card_for_plan(card, spending, plan, preferred_payment)
            if reward > best_reward:
                best_reward = reward
                best_plan = plan
                best_breakdowns = bds
    else:
        best_plan = None
        best_reward, best_breakdowns = _evaluate_card_for_plan(
            card, spending, None, preferred_payment
        )

    effective_rate = round((best_reward / total_spend) * 100.0, 2) if total_spend > 0 else 0.0
    highlights = [
        f"{b.channel_label} {b.applied_rate}%（省 NT${b.actual_reward_ntd:.0f}）"
        for b in sorted(best_breakdowns, key=lambda x: x.actual_reward_ntd, reverse=True)
        if b.applied_rate >= 2.0 and b.spend_ntd > 0
    ][:3]

    return CardRecommendation(
        card_id=card.id,
        bank_name=card.bank_name,
        card_name=card.card_name,
        card_slug=card.card_slug,
        official_url=card.official_url,
        annual_fee=card.annual_fee,
        reward_unit=card.reward_unit,
        source_type=card.source_type,
        recommended_plan=best_plan,
        total_spend_ntd=total_spend,
        total_reward_ntd=best_reward,
        effective_rate_pct=effective_rate,
        matched_highlights=highlights,
        breakdown=best_breakdowns,
    )


def _compute_combo(
    cards: List[CardOut],
    spending: Dict[str, float],
    best_single_reward: float,
) -> Optional[ComboRecommendation]:
    total_spend = round(sum(v for v in spending.values() if v > 0), 2)
    if total_spend <= 0 or not cards:
        return None

    allocations: List[ComboAllocation] = []
    for channel_code, spend_ntd in spending.items():
        if spend_ntd <= 0:
            continue
        channel_label = CHANNEL_MAP.get(channel_code, {"label": channel_code})["label"]

        best_choice: Optional[Tuple[CardOut, ChannelBreakdown]] = None
        for card in cards:
            # Evaluate each rule or base rate independently for this channel
            candidate_rules = [r for r in card.rules if r.channel_code == channel_code]
            if not candidate_rules:
                bd = _evaluate_rule(card, None, channel_code, spend_ntd, spend_ntd)
                if best_choice is None or bd.actual_reward_ntd > best_choice[1].actual_reward_ntd:
                    best_choice = (card, bd)
            else:
                for rule in candidate_rules:
                    bd = _evaluate_rule(card, rule, channel_code, spend_ntd, spend_ntd)
                    if best_choice is None or bd.actual_reward_ntd > best_choice[1].actual_reward_ntd:
                        best_choice = (card, bd)

        if best_choice is not None:
            chosen_card, bd = best_choice
            allocations.append(
                ComboAllocation(
                    channel_code=channel_code,
                    channel_label=channel_label,
                    spend_ntd=spend_ntd,
                    card_slug=chosen_card.card_slug,
                    bank_name=chosen_card.bank_name,
                    card_name=chosen_card.card_name,
                    plan_name=bd.applied_plan,
                    applied_rate=bd.applied_rate,
                    reward_ntd=bd.actual_reward_ntd,
                )
            )

    combo_reward = round(sum(a.reward_ntd for a in allocations), 2)
    effective_rate = round((combo_reward / total_spend) * 100.0, 2) if total_spend > 0 else 0.0
    selected_cards: List[str] = []
    for a in allocations:
        label = f"{a.bank_name} {a.card_name}"
        if label not in selected_cards:
            selected_cards.append(label)

    return ComboRecommendation(
        total_spend_ntd=total_spend,
        total_reward_ntd=combo_reward,
        effective_rate_pct=effective_rate,
        gain_over_best_single_ntd=round(max(0.0, combo_reward - best_single_reward), 2),
        selected_cards=selected_cards,
        allocations=allocations,
    )


def recommend_cards(cards: List[CardOut], request: RecommendRequest) -> RecommendResponse:
    cleaned_spending = {
        k: float(v)
        for k, v in request.monthly_spending.items()
        if k in CHANNEL_MAP and v is not None and float(v) > 0
    }
    total_spend = round(sum(cleaned_spending.values()), 2)

    filtered_cards = cards
    if request.only_no_min_spend:
        filtered_cards = [
            c
            for c in cards
            if not any(r.min_spend_ntd and r.min_spend_ntd > 0 for r in c.rules)
        ]

    recommendations = [
        evaluate_card(card, cleaned_spending, request.preferred_payment)
        for card in filtered_cards
    ]
    recommendations.sort(key=lambda r: (r.total_reward_ntd, r.effective_rate_pct), reverse=True)

    best_single = recommendations[0].total_reward_ntd if recommendations else 0.0
    combo = _compute_combo(filtered_cards, cleaned_spending, best_single)

    return RecommendResponse(
        total_spend_ntd=total_spend,
        recommendations=recommendations,
        combo=combo,
    )
