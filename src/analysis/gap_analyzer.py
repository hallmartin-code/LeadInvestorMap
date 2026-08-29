"""Pipeline gaps, structural risks, and fallback round structures.

Each gap states its consequence, because "no specialist funds" is an observation and
"nothing on this list can price a Series A in this sector" is a decision. Fallbacks are
only offered where the pipeline actually indicates one; a healthy lead pipeline gets no
fallback section.
"""

from __future__ import annotations

from ..models.analysis import FallbackStructure, Gap
from ..models.company import Company
from ..models.investor import (
    ConflictLevel,
    DiligenceStage,
    FundStatus,
    Investor,
    LeadConfidence,
    Relationship,
    Tier,
)
from ..models.round import LeadRequirement, Round
from ..utils.dates import parse_date, today
from ..utils.money import format_money


def analyse_gaps(
    investors: list[Investor],
    round_: Round,
    requirement: LeadRequirement,
    company: Company,
) -> list[Gap]:
    gaps: list[Gap] = []
    active = [i for i in investors if i.is_active_prospect]
    leads = [i for i in active if i.tier == Tier.POTENTIAL_LEAD]
    co_leads = [i for i in active if i.tier == Tier.CO_LEAD]

    if not active:
        gaps.append(
            Gap(
                gap="No investor prospects were found in the supplied materials.",
                consequence="There is no pipeline to sequence; the map cannot advise on outreach.",
                suggested_addition="Supply an investor target list or CRM export.",
                severity="high",
            )
        )
        return gaps

    # 1. Capacity to write the lead cheque.
    if requirement.is_known:
        capable = [
            i
            for i in active
            if i.estimated_check_max is not None
            and i.estimated_check_max >= (requirement.lead_check_min or 0)
        ]
        unknown_capacity = [i for i in active if i.estimated_check_max is None]
        if not capable:
            gaps.append(
                Gap(
                    gap=(f"No prospect has evidenced capacity for the {requirement.display()} lead cheque."),
                    consequence="The round cannot be priced by anyone currently in the pipeline.",
                    suggested_addition=(
                        f"Add funds that write {format_money(requirement.lead_check_min)}+ initial "
                        "cheques at this stage."
                    ),
                    severity="high",
                )
            )
        elif len(capable) < 3:
            gaps.append(
                Gap(
                    gap=(
                        f"Only {len(capable)} prospect(s) can write "
                        f"{format_money(requirement.lead_check_min)}+."
                    ),
                    consequence="No competitive tension on price; a single pass resets the process.",
                    suggested_addition="Add 3-5 further funds with matching cheque capacity.",
                    severity="high",
                )
            )
        if len(unknown_capacity) >= max(3, len(active) // 2):
            gaps.append(
                Gap(
                    gap=f"Cheque size is unknown for {len(unknown_capacity)} of {len(active)} prospects.",
                    consequence="Lead capability cannot be tested for most of the pipeline.",
                    suggested_addition="Confirm typical initial cheque before allocating founder time.",
                    severity="medium",
                )
            )

    # 2. Lead capability overall.
    if not leads and not co_leads:
        gaps.append(
            Gap(
                gap="No prospect qualifies as a lead or co-lead on the evidence available.",
                consequence="The round has no route to a price; every conversation waits on someone else.",
                suggested_addition=(
                    "Add specialist funds with verified lead history at this stage, or plan a "
                    "fallback structure."
                ),
                severity="high",
            )
        )
    elif not leads:
        gaps.append(
            Gap(
                gap=f"Only partial leads identified ({len(co_leads)} co-lead candidates).",
                consequence="A co-lead pairing must be constructed; neither party will price alone.",
                suggested_addition="Identify one fund able to underwrite the full lead cheque.",
                severity="high",
            )
        )

    # 3. Dependence on another lead.
    dependent = [i for i in active if "Lead investor secured" in i.dependencies]
    if active and len(dependent) >= len(active) * 0.6:
        gaps.append(
            Gap(
                gap=f"{len(dependent)} of {len(active)} prospects require a lead to be in place.",
                consequence="Pipeline momentum is entirely gated on one commitment.",
                suggested_addition="Prioritise lead conversion before any further follower outreach.",
                severity="high",
            )
        )

    # 4. Relationship temperature of the lead candidates.
    cold_leads = [i for i in (leads + co_leads) if i.relationship_strength <= Relationship.WEAK_CONNECTION]
    if (leads or co_leads) and len(cold_leads) == len(leads + co_leads):
        gaps.append(
            Gap(
                gap="Every lead candidate is a cold relationship.",
                consequence="Expect 6-10 weeks of relationship-building before any term discussion.",
                suggested_addition="Map warm introduction paths through existing investors and advisers.",
                severity="high",
            )
        )

    # 5. Concentration in strategic capital.
    strategics = [i for i in active if i.tier == Tier.STRATEGIC_VALIDATOR]
    if active and len(strategics) >= len(active) * 0.4:
        gaps.append(
            Gap(
                gap=f"{len(strategics)} of {len(active)} prospects are strategic or corporate investors.",
                consequence=(
                    "Strategic-heavy rounds price slowly and can deter institutional leads on "
                    "governance grounds."
                ),
                suggested_addition="Add institutional funds that price rounds at this stage.",
                severity="medium",
            )
        )

    # 6. Sector specialists.
    specialists = [i for i in active if i.sector_fit.value == "STRONG"]
    if company.sector.is_known and not specialists:
        gaps.append(
            Gap(
                gap=f"No prospect has a verified focus in {company.sector.display()}.",
                consequence="Diligence will be slower and conviction lower without sector fluency.",
                suggested_addition=f"Add funds with a stated {company.sector.display()} thesis.",
                severity="medium",
            )
        )

    # 7. Timeline against the close.
    close = parse_date(round_.target_close.value)
    if close is not None:
        weeks = (close - today()).days / 7.0
        blocked = [i for i in (leads + co_leads) if i.timeline_compatible is False]
        if weeks < 8 and (leads or co_leads):
            gaps.append(
                Gap(
                    gap=(
                        f"Target close is {round_.target_close.display()} - about "
                        f"{max(0, int(weeks))} weeks away."
                    ),
                    consequence="Shorter than a normal institutional lead process from first meeting.",
                    suggested_addition="Prioritise prospects already past partner meeting, or move the date.",
                    severity="high",
                )
            )
        elif blocked:
            gaps.append(
                Gap(
                    gap=f"{len(blocked)} lead candidate(s) cannot realistically close by the target date.",
                    consequence="Either the date moves or those candidates come off the critical path.",
                    suggested_addition="Re-baseline the close date against the slowest necessary process.",
                    severity="medium",
                )
            )

    # 8. Fund status.
    impaired = [
        i
        for i in active
        if i.fund_status in {FundStatus.BETWEEN_FUNDS, FundStatus.FOLLOW_ON_ONLY, FundStatus.INACTIVE}
    ]
    if impaired:
        names = ", ".join(i.investor_name for i in impaired[:3])
        gaps.append(
            Gap(
                gap=f"{len(impaired)} prospect(s) are between funds or follow-on only ({names}).",
                consequence="These names cannot make new platform investments in this window.",
                suggested_addition="Replace with funds that have closed a fund recently.",
                severity="medium",
            )
        )

    # 9. Conflicts.
    conflicted = [i for i in active if i.conflict_level in {ConflictLevel.HIGH, ConflictLevel.MODERATE}]
    if conflicted:
        gaps.append(
            Gap(
                gap=f"{len(conflicted)} prospect(s) carry a possible portfolio conflict.",
                consequence="Diligence may end abruptly, and information shared may reach a competitor.",
                suggested_addition="Clear the conflict explicitly before sharing sensitive material.",
                severity="medium",
            )
        )

    # 10. Valuation expectation.
    if round_.valuation_display == "NOT PROVIDED" and (leads or co_leads):
        gaps.append(
            Gap(
                gap="No valuation or cap has been established for the round.",
                consequence="Lead candidates cannot self-select, so time is spent on mismatched funds.",
                suggested_addition="Set a target valuation range before phase 2 outreach.",
                severity="medium",
            )
        )

    order = {"high": 0, "medium": 1, "low": 2}
    gaps.sort(key=lambda g: order.get(g.severity, 3))
    return gaps


def evaluate_fallbacks(
    investors: list[Investor], round_: Round, requirement: LeadRequirement
) -> list[FallbackStructure]:
    """Fallback structures, offered only where the pipeline indicates one is needed."""
    active = [i for i in investors if i.is_active_prospect]
    strong_leads = [
        i
        for i in active
        if i.tier == Tier.POTENTIAL_LEAD and i.lead_confidence in {LeadConfidence.HIGH, LeadConfidence.MEDIUM}
    ]
    if strong_leads:
        return []

    structures: list[FallbackStructure] = []
    total = round_.raise_amount.numeric_value
    committed = round_.committed.numeric_value or 0.0
    remaining = requirement.remaining_raise

    # Party round.
    meaningful = [
        i
        for i in active
        if i.estimated_check_max is not None
        and requirement.is_known
        and i.estimated_check_max >= (requirement.lead_check_min or 0) * 0.25
    ]
    if len(meaningful) >= 3:
        structures.append(
            FallbackStructure(
                structure="Party round",
                viability="VIABLE",
                capital_required=format_money(remaining) if remaining else "NOT PROVIDED",
                primary_risk=(
                    "No investor owns the price or the governance, which makes the next round harder to lead."
                ),
                milestone_required="Agreed terms the company sets itself, plus a credible anchor.",
                effect_on_next_round="Series A/B leads will scrutinise the absence of a prior lead.",
                rationale=(f"{len(meaningful)} prospects can each write a meaningful, non-leading cheque."),
            )
        )

    # Strategic-led.
    strategics = [
        i
        for i in active
        if i.tier == Tier.STRATEGIC_VALIDATOR and i.relationship_strength >= Relationship.FIRST_MEETING
    ]
    if strategics:
        structures.append(
            FallbackStructure(
                structure="Strategic-led round",
                viability="POSSIBLE",
                capital_required=format_money(remaining) if remaining else "NOT PROVIDED",
                primary_risk=(
                    "Strategic terms (rights of first refusal, exclusivity) can deter future financial leads."
                ),
                milestone_required="Commercial agreement or pilot with the strategic partner.",
                effect_on_next_round="Signals validation but narrows the acquirer set.",
                rationale=f"{strategics[0].investor_name} is engaged and past a first meeting.",
            )
        )

    # Extension of the existing financing.
    existing = [i for i in investors if i.current_diligence_stage == DiligenceStage.COMMITTED]
    if existing:
        structures.append(
            FallbackStructure(
                structure="Extension of the existing round",
                viability="POSSIBLE",
                capital_required=(format_money(committed * 0.5) if committed else "NOT PROVIDED"),
                primary_risk="Existing holders absorb more dilution and may decline to re-up.",
                milestone_required="Evidence that the milestone gap is small and time-bound.",
                effect_on_next_round="Preserves optionality but signals a failed external process.",
                rationale=f"{len(existing)} investor(s) are already committed.",
            )
        )

    # Bridge.
    if total:
        structures.append(
            FallbackStructure(
                structure="Bridge to the next inflection",
                viability="POSSIBLE",
                capital_required=f"{format_money(total * 0.3)} (approx. 30% of the target raise)",
                primary_risk="Dilution and a harder story if the milestone slips again.",
                milestone_required="One value-inflecting result that changes the lead conversation.",
                effect_on_next_round="Raises the bar for the next round but buys time to earn a lead.",
                rationale="No credible lead identified; a smaller raise to a clear milestone is the "
                "conventional alternative.",
            )
        )

    return structures
