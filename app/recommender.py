"""Credit card reward calculation & single/multi-card recommendation engine."""

from typing import Dict, List, Optional, Tuple

from app.channels import CHANNEL_MAP
from app.i18n import (
    get_channel_label,
    normalize_lang,
    t_backend,
    translate_annual_fee,
    translate_bank_name,
    translate_card_name,
    translate_plan_name,
    translate_reward_unit,
    translate_rule_conditions,
)
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

OVERSEAS_FEE_RATE = 0.015


def _base_rate_for_channel(card: CardOut, channel_code: str) -> float:
    if channel_code == "overseas":
        return card.base_rate_foreign
    return card.base_rate_domestic


def _append_note(existing: str, extra: str, lang: str) -> str:
    if not extra:
        return existing
    sep = "; " if lang == "en" else "；"
    return f"{existing}{sep}{extra}" if existing else extra


def _format_fee_amount(fee: float) -> str:
    return f"{fee:,.0f}" if fee.is_integer() else f"{fee:,.2f}"


def _evaluate_rule(
    card: CardOut,
    rule: Optional[RewardRuleOut],
    channel_code: str,
    spend_ntd: float,
    total_card_spend: float,
    lang: Optional[str] = None,
    apply_cap: bool = True,
) -> ChannelBreakdown:
    resolved_lang = normalize_lang(lang)
    channel_label = get_channel_label(channel_code, resolved_lang)
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
            note=t_backend("base_rate_note", resolved_lang),
        )

    applied_plan = translate_plan_name(rule.plan_name, resolved_lang)

    # Check minimum monthly spend requirement against total card spend
    if rule.min_spend_ntd is not None and total_card_spend < rule.min_spend_ntd:
        raw_reward = round(spend_ntd * (base_rate / 100.0), 2)
        return ChannelBreakdown(
            channel_code=channel_code,
            channel_label=channel_label,
            spend_ntd=spend_ntd,
            applied_rate=base_rate,
            applied_plan=applied_plan,
            raw_reward_ntd=raw_reward,
            actual_reward_ntd=raw_reward,
            cap_ntd=rule.monthly_cap_ntd,
            cap_reached=False,
            note=t_backend(
                "min_spend_note",
                resolved_lang,
                min_spend=f"{int(rule.min_spend_ntd):,}",
                base_rate=base_rate,
            ),
        )

    raw_cond = rule.conditions or ""
    note_truncated = len(raw_cond) >= 115 or raw_cond.endswith(("…", "..."))

    base_reward = spend_ntd * (base_rate / 100.0)
    if rule.cap_applies_to == "bonus":
        bonus_rate = max(0.0, rule.rate - base_rate)
        raw_bonus = spend_ntd * (bonus_rate / 100.0)
        raw_reward = round(base_reward + raw_bonus, 2)
    else:
        raw_reward = round(spend_ntd * (rule.rate / 100.0), 2)

    actual_reward = raw_reward
    cap_reached = False
    note = translate_rule_conditions(
        raw_cond,
        resolved_lang,
        channel_code=channel_code,
        rate=rule.rate,
        monthly_cap_ntd=rule.monthly_cap_ntd,
        min_spend_ntd=rule.min_spend_ntd,
        payment_methods=rule.payment_methods,
    )

    if apply_cap and rule.monthly_cap_ntd is not None:
        if rule.cap_applies_to == "bonus":
            bonus_rate = max(0.0, rule.rate - base_rate)
            raw_bonus = spend_ntd * (bonus_rate / 100.0)
            if raw_bonus > rule.monthly_cap_ntd:
                cap_reached = True
                actual_reward = round(base_reward + rule.monthly_cap_ntd, 2)
                cap_msg = t_backend(
                    "bonus_cap_reached_note",
                    resolved_lang,
                    cap=f"{int(rule.monthly_cap_ntd):,}",
                    base_rate=base_rate,
                )
                note = _append_note(note, cap_msg, resolved_lang)
        elif raw_reward > rule.monthly_cap_ntd:
            cap_reached = True
            if rule.rate > 0:
                max_capped_spend = rule.monthly_cap_ntd / (rule.rate / 100.0)
                excess_spend = max(0.0, spend_ntd - max_capped_spend)
                excess_base_reward = excess_spend * (base_rate / 100.0)
                actual_reward = round(rule.monthly_cap_ntd + excess_base_reward, 2)
            else:
                actual_reward = round(rule.monthly_cap_ntd, 2)
            cap_msg = t_backend(
                "cap_reached_note",
                resolved_lang,
                cap=f"{int(rule.monthly_cap_ntd):,}",
                base_rate=base_rate,
            )
            note = _append_note(note, cap_msg, resolved_lang)

    return ChannelBreakdown(
        channel_code=channel_code,
        channel_label=channel_label,
        spend_ntd=spend_ntd,
        applied_rate=rule.rate,
        applied_plan=applied_plan,
        raw_reward_ntd=raw_reward,
        actual_reward_ntd=actual_reward,
        cap_ntd=rule.monthly_cap_ntd,
        cap_reached=cap_reached,
        note=note,
        note_truncated=note_truncated,
    )


def _apply_shared_cap_groups(
    card: CardOut,
    chosen_items: List[Tuple[str, float, Optional[RewardRuleOut], ChannelBreakdown]],
    total_spend: float,
    resolved_lang: str,
) -> None:
    """Apply shared monthly cap across channels belonging to the same cap_group."""
    groups: Dict[Tuple[str, str], List[Tuple[str, float, RewardRuleOut, ChannelBreakdown]]] = {}
    for ch_code, spend_ntd, rule, bd in chosen_items:
        if rule is None or not rule.cap_group or rule.monthly_cap_ntd is None:
            continue
        if rule.min_spend_ntd is not None and total_spend < rule.min_spend_ntd:
            continue
        groups.setdefault((rule.cap_group, rule.cap_applies_to), []).append(
            (ch_code, spend_ntd, rule, bd)
        )

    for (_, cap_mode), entries in groups.items():
        if len(entries) <= 1:
            # Single active channel in this group: apply its individual cap normally
            if len(entries) == 1:
                ch_code, spend_ntd, rule, bd = entries[0]
                capped_bd = _evaluate_rule(
                    card, rule, ch_code, spend_ntd, total_spend, lang=resolved_lang, apply_cap=True
                )
                bd.actual_reward_ntd = capped_bd.actual_reward_ntd
                bd.cap_reached = capped_bd.cap_reached
                bd.note = capped_bd.note
            continue

        group_cap = min(r.monthly_cap_ntd for _, _, r, _ in entries if r.monthly_cap_ntd is not None)
        cappable_list: List[float] = []
        priorities: List[float] = []
        for ch_code, spend_ntd, rule, _ in entries:
            base_rate = _base_rate_for_channel(card, ch_code)
            if cap_mode == "bonus":
                bonus_rate = max(0.0, rule.rate - base_rate)
                cappable = spend_ntd * (bonus_rate / 100.0)
                prio = round(bonus_rate, 6)
            else:
                cappable = spend_ntd * (rule.rate / 100.0)
                prio = round((rule.rate - base_rate) / rule.rate if rule.rate > 0 else 0.0, 6)
            cappable_list.append(cappable)
            priorities.append(prio)

        total_cappable = sum(cappable_list)
        if total_cappable <= group_cap + 1e-9:
            continue

        # Allocate group_cap in descending priority order; proportional split on tied priorities
        remaining_cap = group_cap
        allocated = [0.0] * len(entries)
        for prio in sorted(set(priorities), reverse=True):
            tier_indices = [i for i, p in enumerate(priorities) if p == prio]
            tier_demand = sum(cappable_list[i] for i in tier_indices)
            if tier_demand <= 0:
                continue
            if remaining_cap >= tier_demand:
                for i in tier_indices:
                    allocated[i] = cappable_list[i]
                remaining_cap -= tier_demand
            else:
                ratio = remaining_cap / tier_demand if tier_demand > 0 else 0.0
                for i in tier_indices:
                    allocated[i] = cappable_list[i] * ratio
                remaining_cap = 0.0
                break

        note_key = (
            "shared_bonus_cap_reached_note"
            if cap_mode == "bonus"
            else "shared_cap_reached_note"
        )
        for idx, (ch_code, spend_ntd, rule, bd) in enumerate(entries):
            base_rate = _base_rate_for_channel(card, ch_code)
            alloc_cap = allocated[idx]
            if cap_mode == "bonus":
                base_reward = spend_ntd * (base_rate / 100.0)
                bd.actual_reward_ntd = round(base_reward + alloc_cap, 2)
            else:
                if rule.rate > 0:
                    capped_spend = alloc_cap / (rule.rate / 100.0)
                    excess_spend = max(0.0, spend_ntd - capped_spend)
                    bd.actual_reward_ntd = round(alloc_cap + excess_spend * (base_rate / 100.0), 2)
                else:
                    bd.actual_reward_ntd = round(alloc_cap, 2)
            bd.cap_reached = True
            cap_msg = t_backend(
                note_key,
                resolved_lang,
                cap=f"{int(group_cap):,}",
                base_rate=base_rate,
            )
            bd.note = _append_note(bd.note, cap_msg, resolved_lang)


def _evaluate_card_for_plan(
    card: CardOut,
    spending: Dict[str, float],
    active_plan: Optional[str],
    preferred_payment: Optional[str],
    lang: Optional[str] = None,
    total_spend_override: Optional[float] = None,
    deduct_overseas_fee: bool = False,
) -> Tuple[float, List[ChannelBreakdown]]:
    resolved_lang = normalize_lang(lang)
    total_spend = (
        total_spend_override if total_spend_override is not None else sum(spending.values())
    )
    chosen_items: List[Tuple[str, float, Optional[RewardRuleOut], ChannelBreakdown]] = []

    for channel_code, spend_ntd in spending.items():
        if spend_ntd <= 0:
            continue

        candidates = [
            r
            for r in card.rules
            if r.channel_code == channel_code
            and (r.plan_name is None or r.plan_name == active_plan)
        ]

        best_rule: Optional[RewardRuleOut] = None
        best_bd: Optional[ChannelBreakdown] = None
        for rule in candidates:
            # Evaluate without cap_group cap first if part of a cap_group; individual caps still guide selection
            bd = _evaluate_rule(
                card, rule, channel_code, spend_ntd, total_spend, lang=resolved_lang, apply_cap=True
            )
            if best_bd is None:
                best_bd = bd
                best_rule = rule
            elif bd.actual_reward_ntd > best_bd.actual_reward_ntd:
                best_bd = bd
                best_rule = rule
            elif (
                bd.actual_reward_ntd == best_bd.actual_reward_ntd
                and preferred_payment
                and preferred_payment in rule.payment_methods
            ):
                best_bd = bd
                best_rule = rule

        if best_bd is None:
            best_bd = _evaluate_rule(
                card, None, channel_code, spend_ntd, total_spend, lang=resolved_lang
            )
        elif best_rule is not None and best_rule.cap_group and best_rule.monthly_cap_ntd is not None:
            # Re-evaluate uncapped so _apply_shared_cap_groups can distribute the group cap across channels
            best_bd = _evaluate_rule(
                card,
                best_rule,
                channel_code,
                spend_ntd,
                total_spend,
                lang=resolved_lang,
                apply_cap=False,
            )

        chosen_items.append((channel_code, spend_ntd, best_rule, best_bd))

    _apply_shared_cap_groups(card, chosen_items, total_spend, resolved_lang)

    breakdowns: List[ChannelBreakdown] = []
    for channel_code, spend_ntd, _, bd in chosen_items:
        if deduct_overseas_fee and channel_code == "overseas" and spend_ntd > 0:
            fee = round(spend_ntd * OVERSEAS_FEE_RATE, 2)
            bd.actual_reward_ntd = round(bd.actual_reward_ntd - fee, 2)
            fee_msg = t_backend(
                "overseas_fee_note", resolved_lang, fee=_format_fee_amount(fee)
            )
            bd.note = _append_note(bd.note, fee_msg, resolved_lang)
        breakdowns.append(bd)

    total_reward = round(sum(b.actual_reward_ntd for b in breakdowns), 2)
    return total_reward, breakdowns


def evaluate_card(
    card: CardOut,
    spending: Dict[str, float],
    preferred_payment: Optional[str] = None,
    lang: Optional[str] = None,
    deduct_overseas_fee: bool = False,
) -> CardRecommendation:
    resolved_lang = normalize_lang(lang)
    total_spend = round(sum(v for v in spending.values() if v > 0), 2)
    plan_names = sorted({r.plan_name for r in card.rules if r.plan_name})

    if plan_names:
        best_plan: Optional[str] = None
        best_reward = float("-inf")
        best_breakdowns: List[ChannelBreakdown] = []
        for plan in plan_names:
            reward, bds = _evaluate_card_for_plan(
                card,
                spending,
                plan,
                preferred_payment,
                lang=resolved_lang,
                deduct_overseas_fee=deduct_overseas_fee,
            )
            if reward > best_reward:
                best_reward = reward
                best_plan = plan
                best_breakdowns = bds
    else:
        best_plan = None
        best_reward, best_breakdowns = _evaluate_card_for_plan(
            card,
            spending,
            None,
            preferred_payment,
            lang=resolved_lang,
            deduct_overseas_fee=deduct_overseas_fee,
        )

    effective_rate = round((best_reward / total_spend) * 100.0, 2) if total_spend > 0 else 0.0
    highlights = [
        t_backend(
            "highlight_item",
            resolved_lang,
            channel_label=b.channel_label,
            rate=b.applied_rate,
            reward=f"{b.actual_reward_ntd:.0f}",
        )
        for b in sorted(best_breakdowns, key=lambda x: x.actual_reward_ntd, reverse=True)
        if b.applied_rate >= 2.0 and b.spend_ntd > 0
    ][:3]

    return CardRecommendation(
        card_id=card.id,
        bank_name=translate_bank_name(card.bank_name, resolved_lang),
        card_name=translate_card_name(card.card_name, resolved_lang),
        card_slug=card.card_slug,
        official_url=card.official_url,
        annual_fee=translate_annual_fee(card.annual_fee, resolved_lang),
        reward_unit=translate_reward_unit(card.reward_unit, resolved_lang),
        source_type=card.source_type,
        last_updated=card.last_updated,
        recommended_plan=translate_plan_name(best_plan, resolved_lang),
        total_spend_ntd=total_spend,
        total_reward_ntd=best_reward,
        effective_rate_pct=effective_rate,
        matched_highlights=highlights,
        breakdown=best_breakdowns,
    )


def _score_combo_assignment(
    cards: List[CardOut],
    spending: Dict[str, float],
    assignment: Dict[str, int],
    plans: Dict[int, Optional[str]],
    preferred_payment: Optional[str],
    deduct_overseas_fee: bool,
    resolved_lang: str,
) -> Tuple[float, Dict[str, Tuple[CardOut, ChannelBreakdown]]]:
    """Evaluate a multi-card combo assignment using card-level cap groups, plans, and min_spend."""
    by_card: Dict[int, Dict[str, float]] = {}
    for ch_code, card_idx in assignment.items():
        amt = spending.get(ch_code, 0.0)
        if amt > 0:
            by_card.setdefault(card_idx, {})[ch_code] = amt

    total_reward = 0.0
    breakdowns_by_channel: Dict[str, Tuple[CardOut, ChannelBreakdown]] = {}
    for card_idx, card_spend in by_card.items():
        card = cards[card_idx]
        reward, bds = _evaluate_card_for_plan(
            card,
            card_spend,
            plans.get(card_idx),
            preferred_payment,
            lang=resolved_lang,
            deduct_overseas_fee=deduct_overseas_fee,
        )
        total_reward += reward
        for bd in bds:
            breakdowns_by_channel[bd.channel_code] = (card, bd)

    return round(total_reward, 2), breakdowns_by_channel


def _optimize_combo_seed(
    cards: List[CardOut],
    card_plans: List[List[Optional[str]]],
    spending: Dict[str, float],
    channel_order: List[str],
    init_assignment: Dict[str, int],
    init_plans: Dict[int, Optional[str]],
    max_cards: int,
    preferred_payment: Optional[str],
    deduct_overseas_fee: bool,
    resolved_lang: str,
) -> Tuple[float, Dict[str, int], Dict[int, Optional[str]]]:
    assignment = dict(init_assignment)
    plans = dict(init_plans)
    best_reward, _ = _score_combo_assignment(
        cards, spending, assignment, plans, preferred_payment, deduct_overseas_fee, resolved_lang
    )

    for _ in range(15):
        improved = False
        # 1. Try reassigning each channel to any valid (card_idx, plan)
        for ch_code in channel_order:
            orig_card = assignment[ch_code]
            used_cards = set(assignment.values())
            for cand_idx in range(len(cards)):
                if cand_idx not in used_cards and len(used_cards) >= max_cards:
                    # Only replace if orig_card has no other channels
                    if sum(1 for c in assignment.values() if c == orig_card) > 1:
                        continue
                cand_plan_opts = (
                    [plans[cand_idx]]
                    if cand_idx in used_cards and cand_idx in plans
                    else card_plans[cand_idx]
                )
                for cand_plan in cand_plan_opts:
                    if cand_idx == orig_card and plans.get(cand_idx) == cand_plan:
                        continue
                    trial_assign = dict(assignment)
                    trial_assign[ch_code] = cand_idx
                    trial_plans = dict(plans)
                    trial_plans[cand_idx] = cand_plan
                    score, _ = _score_combo_assignment(
                        cards,
                        spending,
                        trial_assign,
                        trial_plans,
                        preferred_payment,
                        deduct_overseas_fee,
                        resolved_lang,
                    )
                    if score > best_reward + 1e-6:
                        best_reward = score
                        assignment = trial_assign
                        plans = trial_plans
                        improved = True

        # 2. Try switching the active plan of each currently used multi-plan card
        for used_idx in sorted(set(assignment.values())):
            if len(card_plans[used_idx]) <= 1:
                continue
            for alt_plan in card_plans[used_idx]:
                if alt_plan == plans.get(used_idx):
                    continue
                trial_plans = dict(plans)
                trial_plans[used_idx] = alt_plan
                score, _ = _score_combo_assignment(
                    cards,
                    spending,
                    assignment,
                    trial_plans,
                    preferred_payment,
                    deduct_overseas_fee,
                    resolved_lang,
                )
                if score > best_reward + 1e-6:
                    best_reward = score
                    plans = trial_plans
                    improved = True

        if not improved:
            break

    return best_reward, assignment, plans


def _compute_combo(
    cards: List[CardOut],
    spending: Dict[str, float],
    best_single_reward: float,
    preferred_payment: Optional[str] = None,
    max_combo_cards: Optional[int] = None,
    deduct_overseas_fee: bool = False,
    lang: Optional[str] = None,
) -> Optional[ComboRecommendation]:
    resolved_lang = normalize_lang(lang)
    active_spending = {k: v for k, v in spending.items() if v > 0}
    total_spend = round(sum(active_spending.values()), 2)
    if total_spend <= 0 or not cards or not active_spending:
        return None

    channel_order = list(active_spending.keys())
    card_plans: List[List[Optional[str]]] = [
        sorted({r.plan_name for r in c.rules if r.plan_name}) or [None] for c in cards
    ]
    max_cards = len(cards)
    if max_combo_cards is not None:
        max_cards = max(1, min(max_combo_cards, len(cards)))

    # Seed 1: Best single (card, plan) — guarantees combo >= best_single_reward
    best_single_idx = 0
    best_single_plan: Optional[str] = card_plans[0][0]
    best_single_score = float("-inf")
    for idx, card in enumerate(cards):
        for plan in card_plans[idx]:
            score, _ = _evaluate_card_for_plan(
                card,
                active_spending,
                plan,
                preferred_payment,
                lang=resolved_lang,
                deduct_overseas_fee=deduct_overseas_fee,
            )
            if score > best_single_score:
                best_single_score = score
                best_single_idx = idx
                best_single_plan = plan

    seeds: List[Tuple[Dict[str, int], Dict[int, Optional[str]]]] = [
        ({ch: best_single_idx for ch in channel_order}, {best_single_idx: best_single_plan})
    ]

    if max_cards > 1:
        # Seed 2: Greedy channel-by-channel (largest spend first) respecting cap_group & max_cards
        greedy_assign: Dict[str, int] = {}
        greedy_plans: Dict[int, Optional[str]] = {}
        for ch_code in sorted(channel_order, key=lambda c: active_spending[c], reverse=True):
            used = set(greedy_assign.values())
            best_step_score = float("-inf")
            best_step_choice: Tuple[int, Optional[str]] = (best_single_idx, best_single_plan)
            partial_spend = {k: active_spending[k] for k in greedy_assign}
            partial_spend[ch_code] = active_spending[ch_code]
            for idx in range(len(cards)):
                if idx not in used and len(used) >= max_cards:
                    continue
                plan_opts = [greedy_plans[idx]] if idx in used else card_plans[idx]
                for plan in plan_opts:
                    trial_assign = dict(greedy_assign)
                    trial_assign[ch_code] = idx
                    trial_plans = dict(greedy_plans)
                    trial_plans[idx] = plan
                    step_score, _ = _score_combo_assignment(
                        cards,
                        partial_spend,
                        trial_assign,
                        trial_plans,
                        preferred_payment,
                        deduct_overseas_fee,
                        resolved_lang,
                    )
                    if step_score > best_step_score:
                        best_step_score = step_score
                        best_step_choice = (idx, plan)
            greedy_assign[ch_code] = best_step_choice[0]
            greedy_plans[best_step_choice[0]] = best_step_choice[1]
        seeds.append((greedy_assign, greedy_plans))

    best_reward = float("-inf")
    best_assignment: Dict[str, int] = seeds[0][0]
    best_plans: Dict[int, Optional[str]] = seeds[0][1]

    for seed_assign, seed_plans in seeds:
        if max_cards == 1:
            score, _ = _score_combo_assignment(
                cards,
                active_spending,
                seed_assign,
                seed_plans,
                preferred_payment,
                deduct_overseas_fee,
                resolved_lang,
            )
            opt_assign, opt_plans = seed_assign, seed_plans
        else:
            score, opt_assign, opt_plans = _optimize_combo_seed(
                cards,
                card_plans,
                active_spending,
                channel_order,
                seed_assign,
                seed_plans,
                max_cards,
                preferred_payment,
                deduct_overseas_fee,
                resolved_lang,
            )
        if score > best_reward:
            best_reward = score
            best_assignment = opt_assign
            best_plans = opt_plans

    combo_reward, breakdowns_by_channel = _score_combo_assignment(
        cards,
        active_spending,
        best_assignment,
        best_plans,
        preferred_payment,
        deduct_overseas_fee,
        resolved_lang,
    )

    allocations: List[ComboAllocation] = []
    for channel_code in channel_order:
        spend_ntd = active_spending[channel_code]
        chosen_card, bd = breakdowns_by_channel[channel_code]
        allocations.append(
            ComboAllocation(
                channel_code=channel_code,
                channel_label=get_channel_label(channel_code, resolved_lang),
                spend_ntd=spend_ntd,
                card_slug=chosen_card.card_slug,
                bank_name=translate_bank_name(chosen_card.bank_name, resolved_lang),
                card_name=translate_card_name(chosen_card.card_name, resolved_lang),
                plan_name=bd.applied_plan,
                applied_rate=bd.applied_rate,
                reward_ntd=bd.actual_reward_ntd,
            )
        )

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


def recommend_cards(
    cards: List[CardOut],
    request: RecommendRequest,
    lang: Optional[str] = None,
) -> RecommendResponse:
    resolved_lang = normalize_lang(lang or request.lang)
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
        evaluate_card(
            card,
            cleaned_spending,
            request.preferred_payment,
            lang=resolved_lang,
            deduct_overseas_fee=request.deduct_overseas_fee,
        )
        for card in filtered_cards
    ]
    recommendations.sort(key=lambda r: (r.total_reward_ntd, r.effective_rate_pct), reverse=True)

    best_single = recommendations[0].total_reward_ntd if recommendations else 0.0
    combo = _compute_combo(
        filtered_cards,
        cleaned_spending,
        best_single,
        preferred_payment=request.preferred_payment,
        max_combo_cards=request.max_combo_cards,
        deduct_overseas_fee=request.deduct_overseas_fee,
        lang=resolved_lang,
    )

    return RecommendResponse(
        total_spend_ntd=total_spend,
        recommendations=recommendations,
        combo=combo,
    )
