"""Phased outreach sequencing.

A raise is not a mail merge. The sequence is built so the narrative is tested on
investors the company can afford to lose, the best lead candidates are approached once
the pitch has survived contact, signal-sensitive investors are engaged only after
momentum exists, and allocation is filled last. Prospects that would be wasted now are
explicitly held back.
"""

from __future__ import annotations

from ..models.analysis import OutreachPhase, OutreachSequence
from ..models.investor import (
    ConflictLevel,
    DiligenceStage,
    FundStatus,
    Investor,
    LeadConfidence,
    Relationship,
    Tier,
)

_PHASE_1_MAX = 5
_PHASE_2_MAX = 6


def build_sequence(investors: list[Investor]) -> OutreachSequence:
    # Money already committed needs no outreach, and a fund that cannot deploy is not a
    # sequencing problem - both would only dilute the founder's time.
    active = [
        i
        for i in investors
        if i.is_active_prospect
        and i.current_diligence_stage != DiligenceStage.COMMITTED
        and i.fund_status not in {FundStatus.BETWEEN_FUNDS, FundStatus.INACTIVE}
    ]

    leads = [i for i in active if i.tier in {Tier.POTENTIAL_LEAD, Tier.CO_LEAD}]
    leads.sort(key=lambda i: -(i.lead_score or 0))

    strategics = [i for i in active if i.tier == Tier.STRATEGIC_VALIDATOR]
    followers = [i for i in active if i.tier == Tier.FOLLOW_ON]
    fillers = [i for i in active if i.tier in {Tier.ANGEL_FAMILY_SYNDICATE, Tier.FILL_THE_ROUND}]

    # Phase 1 calibration: credible enough to give a real read, not so important that
    # burning them would cost the round. Anyone already in a live process is excluded -
    # you do not restart a conversation that has advanced.
    calibration = [
        i
        for i in leads
        # A Tier 1 candidate is never calibration fodder: you get one first impression
        # from the funds that can actually price the round.
        if i.tier != Tier.POTENTIAL_LEAD
        and i.lead_confidence in {LeadConfidence.MEDIUM, LeadConfidence.LOW}
        and i.current_diligence_stage
        in {DiligenceStage.COLD, DiligenceStage.INTRO_AVAILABLE, DiligenceStage.INTRO_MADE}
        and i.conflict_level != ConflictLevel.HIGH
    ]
    calibration += [
        i
        for i in followers
        if i.relationship_strength >= Relationship.WARM_INTRO_AVAILABLE
        and i.conflict_level != ConflictLevel.HIGH
        and i not in calibration
    ]
    calibration = calibration[:_PHASE_1_MAX]

    # Phase 2 conversion: the strongest lead candidates, plus anyone already advanced.
    conversion = [i for i in leads if i not in calibration]
    conversion.sort(
        key=lambda i: (
            -int(i.current_diligence_stage in {DiligenceStage.DILIGENCE, DiligenceStage.PARTNER_MEETING}),
            -(i.lead_score or 0),
        )
    )
    conversion = conversion[:_PHASE_2_MAX]

    # Phase 3 signal leverage: strategics and followers that react to a lead.
    signal = [i for i in strategics if i not in conversion]
    signal += [i for i in followers if i not in calibration and _needs_lead(i)]

    # Phase 4 completion: angels, family offices, syndicates, small cheques.
    completion = [i for i in fillers] + [i for i in followers if i not in calibration and i not in signal]

    # Held back: prospects where contact now is actively counterproductive rather than
    # merely early. A cold lead candidate is not held back - phase 2 is exactly when it
    # should be approached, after phase 1 has tested the pitch.
    hold_back = [
        i
        for i in active
        if i.tier == Tier.STRATEGIC_VALIDATOR and i.relationship_strength <= Relationship.WEAK_CONNECTION
    ]
    # A fund holding a named competitor sees whatever is sent to it. Hold until the
    # conflict is cleared in writing, whatever else it looks like on paper.
    hold_back += [i for i in active if i.conflict_level == ConflictLevel.HIGH and i not in hold_back]

    conversion = [i for i in conversion if i not in hold_back]
    signal = [i for i in signal if i not in hold_back]
    completion = [i for i in completion if i not in hold_back]

    return OutreachSequence(
        phase_1=OutreachPhase(
            phase="PHASE 1 - CALIBRATION",
            objective="Test the narrative and surface objections on replaceable conversations.",
            investors=_names(calibration),
            notes="Approach now. Expect to change materials before phase 2."
            if calibration
            else "No suitable calibration targets identified in the supplied list.",
        ),
        phase_2=OutreachPhase(
            phase="PHASE 2 - LEAD CONVERSION",
            objective="Generate partner meetings and a competitive process for the lead.",
            investors=_names(conversion),
            notes="Approach once phase 1 objections are answered."
            if conversion
            else "No credible lead candidates identified - see fallback structures.",
        ),
        phase_3=OutreachPhase(
            phase="PHASE 3 - SIGNAL LEVERAGE",
            objective="Activate strategics and re-engage followers once lead momentum exists.",
            investors=_names(signal),
            notes="Trigger: a lead in term discussion.",
        ),
        phase_4=OutreachPhase(
            phase="PHASE 4 - ROUND COMPLETION",
            objective="Fill remaining allocation with angels, family offices and syndicates.",
            investors=_names(completion),
            notes="Trigger: lead terms agreed.",
        ),
        hold_back=OutreachPhase(
            phase="HOLD BACK",
            objective="Do not approach until lead momentum exists - one shot each.",
            investors=_names(hold_back),
            notes="Cold approaches here spend the best names on an untested pitch."
            if hold_back
            else "Nothing is being held back.",
        ),
    )


def _needs_lead(investor: Investor) -> bool:
    return (
        "Lead investor secured" in investor.stated_dependencies
        or "Lead investor secured" in investor.dependencies
        or investor.leads_rounds_stated is False
    )


def _names(investors: list[Investor]) -> list[str]:
    seen: list[str] = []
    for investor in investors:
        if investor.investor_name not in seen:
            seen.append(investor.investor_name)
    return seen


def derive_dependencies(investors: list[Investor], has_credible_lead: bool) -> list[Investor]:
    """Fill in analyst-inferred dependencies, kept distinct from investor-stated ones."""
    for investor in investors:
        inferred: list[str] = []

        if investor.tier in {Tier.FOLLOW_ON, Tier.ANGEL_FAMILY_SYNDICATE, Tier.FILL_THE_ROUND}:
            inferred.append("Lead investor secured")
        if investor.tier == Tier.CO_LEAD and not has_credible_lead:
            inferred.append("Co-lead partner identified")
        if investor.relationship_strength <= Relationship.WEAK_CONNECTION:
            inferred.append("Warm introduction path established")
        if investor.estimated_check_max is None:
            inferred.append("Check-size capacity confirmed")
        if investor.investment_committee:
            inferred.append("IC approval")
        if investor.conflict_level.value in {"MODERATE", "HIGH"}:
            inferred.append("Portfolio conflict cleared")

        for dependency in investor.stated_dependencies:
            if dependency not in investor.dependencies:
                investor.dependencies.append(dependency)
        for dependency in inferred:
            if dependency not in investor.dependencies:
                investor.dependencies.append(dependency)
    return investors
