"""Momentum analysis: whose commitment actually moves the round.

The sequence is built only from prospects in the supplied materials, and a downstream
link is only drawn where that second investor's own record says it is waiting on a lead.
No relationship between two funds is ever asserted on reputation alone.
"""

from __future__ import annotations

from ..models.analysis import HighestPullCommitment, MomentumStep
from ..models.investor import DiligenceStage, Investor, Relationship, SignalValue, Tier
from ..utils.text import truncate

_SIGNAL_WEIGHT = {
    SignalValue.VERY_HIGH: 30.0,
    SignalValue.HIGH: 22.0,
    SignalValue.MEDIUM: 12.0,
    SignalValue.LOW: 5.0,
    SignalValue.UNKNOWN: 6.0,
}


def identify_highest_pull(investors: list[Investor]) -> HighestPullCommitment:
    """The one commitment with the greatest downstream effect on this specific pipeline."""
    candidates = [
        investor
        for investor in investors
        if investor.is_active_prospect
        and investor.tier in {Tier.POTENTIAL_LEAD, Tier.CO_LEAD, Tier.STRATEGIC_VALIDATOR}
    ]
    if not candidates:
        return HighestPullCommitment(
            rationale=(
                "No prospect in the supplied materials has both lead capability and downstream "
                "influence. Pipeline pull cannot be established."
            ),
            confidence="INSUFFICIENT EVIDENCE",
        )

    def pull(investor: Investor) -> float:
        score = (investor.lead_score or 0) * 0.5
        score += _SIGNAL_WEIGHT.get(investor.signal_value, 6.0)
        score += min(len(investor.investors_influenced), 6) * 4.0
        # Proximity matters: an investor already in diligence can commit sooner.
        score += int(investor.relationship_strength) * 1.5
        if investor.tier == Tier.POTENTIAL_LEAD:
            score += 10.0
        return score

    best = max(candidates, key=pull)
    downstream = list(best.investors_influenced)

    if best.has_verified_lead_history and downstream:
        confidence = "HIGH"
    elif best.has_verified_lead_history or downstream:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    rationale_bits = []
    if best.has_verified_lead_history:
        rationale_bits.append(f"verified lead history ({best.lead_history_display(1)})")
    else:
        rationale_bits.append("lead history NOT VERIFIED")
    if downstream:
        rationale_bits.append(f"{len(downstream)} prospect(s) on this list state they need a lead in place")
    if best.relationship_strength >= Relationship.FIRST_MEETING:
        rationale_bits.append(f"already at {best.relationship_strength.label.lower()}")

    return HighestPullCommitment(
        investor_name=best.investor_name,
        rationale=truncate("; ".join(rationale_bits) + ".", 240),
        downstream_investors=downstream[:6],
        confidence=confidence,
    )


def build_momentum_sequence(
    investors: list[Investor], highest_pull: HighestPullCommitment
) -> list[MomentumStep]:
    """A short, evidence-linked chain: who commits, and what that unlocks."""
    steps: list[MomentumStep] = []
    if not highest_pull.investor_name:
        return steps

    by_name = {i.investor_name: i for i in investors}
    anchor = by_name.get(highest_pull.investor_name)
    if anchor is None:
        return steps

    # The anchor is described as what it actually is. Calling a strategic validator a
    # lead here would contradict its own disqualification a few centimetres away.
    if anchor.tier == Tier.POTENTIAL_LEAD:
        event, effect = "commits as lead", "Prices the round and sets terms."
    elif anchor.tier == Tier.CO_LEAD:
        event, effect = (
            "commits as co-lead",
            "Anchors part of the round; a pricing partner is still required.",
        )
    else:
        event, effect = (
            "commits as strategic anchor",
            "Validates the technology or market, but does not price the round.",
        )

    steps.append(
        MomentumStep(
            step=1,
            investor_name=anchor.investor_name,
            event=event,
            effect=effect,
            basis=anchor.lead_history_display(1),
        )
    )

    # Prospects that explicitly need a lead move next, closest to a decision first.
    waiting = [
        investor
        for investor in investors
        if investor.investor_name != anchor.investor_name
        and investor.is_active_prospect
        # Already-committed money cannot be unlocked by a lead - it is in.
        and investor.current_diligence_stage != DiligenceStage.COMMITTED
        and investor.fund_status.value not in {"BETWEEN FUNDS", "INACTIVE"}
        and investor.conflict_level.value != "HIGH"
        and (
            "Lead investor secured" in investor.stated_dependencies
            or "Lead investor secured" in investor.dependencies
        )
    ]
    # Institutional money moves the next investor; an angel group committing after a
    # lead is expected and tells other investors nothing.
    waiting.sort(
        key=lambda i: (
            0 if i.investor_type.is_institutional or i.investor_type.is_strategic else 1,
            -int(i.relationship_strength),
        )
    )

    if waiting:
        first = waiting[0]
        steps.append(
            MomentumStep(
                step=2,
                investor_name=first.investor_name,
                event="enters diligence",
                effect="Stated dependency on a lead is satisfied.",
                basis="Stated dependency: lead investor secured.",
            )
        )

    strategics = [
        investor
        for investor in investors
        if investor.tier == Tier.STRATEGIC_VALIDATOR
        and investor.is_active_prospect
        and investor.investor_name != anchor.investor_name
    ]
    strategics.sort(key=lambda i: -int(i.relationship_strength))
    if strategics:
        steps.append(
            MomentumStep(
                step=len(steps) + 1,
                investor_name=strategics[0].investor_name,
                event="validates the sector",
                effect="Commercial or technical validation for remaining institutions.",
                basis=strategics[0].signal_rationale or "Strategic investor.",
            )
        )

    fillers = [
        investor
        for investor in investors
        if investor.tier in {Tier.ANGEL_FAMILY_SYNDICATE, Tier.FILL_THE_ROUND}
        and investor.is_active_prospect
        and investor.current_diligence_stage != DiligenceStage.COMMITTED
        and investor.fund_status.value not in {"BETWEEN FUNDS", "INACTIVE"}
    ]
    remaining_followers = [i for i in waiting[1:]]
    tail = remaining_followers + fillers
    if tail:
        names = ", ".join(i.investor_name for i in tail[:3])
        steps.append(
            MomentumStep(
                step=len(steps) + 1,
                investor_name=names,
                event="fill remaining allocation",
                effect="Round completes.",
                basis=f"{len(tail)} prospect(s) available for allocation.",
            )
        )

    return steps


def momentum_path_line(steps: list[MomentumStep]) -> str:
    """One-line rendering for the PDF, e.g. "A commits > B diligence > C validates"."""
    if not steps:
        return "No evidence-supported momentum path could be built from the supplied prospects."
    parts = [f"{s.investor_name} {s.event}" for s in steps]
    return "  >  ".join(parts)


def next_step_defaults(investor: Investor) -> tuple[str, str]:
    """The single next action for a prospect that does not already have one.

    Derived from where the relationship actually is, so the founder gets one instruction
    per investor rather than a list of possibilities.
    """
    if investor.required_next_step:
        return investor.required_next_step, investor.next_step_owner or "CEO"

    stage = investor.current_diligence_stage
    if stage == DiligenceStage.PASS:
        return "No action - passed on the round", "-"
    if investor.relationship_strength >= Relationship.VERBAL_COMMITMENT:
        return "Convert verbal commitment to signed documents", "CEO"
    if stage in {DiligenceStage.TERM_DISCUSSION, DiligenceStage.VERBAL}:
        return "Request explicit lead interest and proposed terms", "CEO"
    if stage == DiligenceStage.DILIGENCE:
        return "Complete outstanding diligence requests", "CEO"
    if stage == DiligenceStage.PARTNER_MEETING:
        return "Follow up for partner-meeting outcome", "CEO"
    if stage in {DiligenceStage.FIRST_MEETING, DiligenceStage.FOLLOW_UP}:
        return "Schedule partner meeting", "CEO"
    if stage == DiligenceStage.INTRO_MADE:
        return "Convert introduction into a first meeting", "CEO"
    if investor.warm_intro_path:
        return f"Secure introduction via {truncate(investor.warm_intro_path, 60)}", "Board member"
    if investor.relationship_strength >= Relationship.WARM_INTRO_AVAILABLE:
        return "Activate available warm introduction", "Existing investor"
    if investor.estimated_check_max is None:
        return "Confirm check-size capacity before investing time", "TEN Capital"
    return "Identify a warm introduction path before outreach", "TEN Capital"


def apply_next_steps(investors: list[Investor]) -> list[Investor]:
    for investor in investors:
        step, owner = next_step_defaults(investor)
        investor.required_next_step = step
        investor.next_step_owner = owner or "CEO"
    return investors
