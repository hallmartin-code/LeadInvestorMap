"""Lead candidate scoring and shortlisting.

The weighted score exists to order the shortlist and to band it HIGH / MEDIUM / LOW. The
number itself is never shown, because a 68.4 would imply a precision the underlying
evidence does not have. Unknown evidence scores at a neutral-to-low value rather than at
zero or at full marks: absence of proof is neither a pass nor a disqualification.
"""

from __future__ import annotations

from ..models.analysis import ShortlistEntry
from ..models.company import Company
from ..models.investor import (
    ConflictLevel,
    Fit,
    FundStatus,
    Investor,
    LeadConfidence,
    Relationship,
    SignalValue,
    Tier,
)
from ..models.round import LeadRequirement, Round
from ..utils.config import (
    LEAD_CONFIDENCE_HIGH,
    LEAD_CONFIDENCE_MEDIUM,
    LEAD_SCORE_WEIGHTS,
    SHORTLIST_FLOOR,
    SHORTLIST_MAX,
)
from ..utils.money import format_money
from ..utils.text import truncate

_STAGE_SCORES = {
    Fit.STRONG: 100.0,
    Fit.PARTIAL: 60.0,
    Fit.UNKNOWN: 35.0,
    Fit.WEAK: 20.0,
    Fit.MISMATCH: 0.0,
}
_SECTOR_SCORES = {
    Fit.STRONG: 100.0,
    Fit.PARTIAL: 65.0,
    Fit.UNKNOWN: 35.0,
    Fit.WEAK: 25.0,
    Fit.MISMATCH: 0.0,
}
_FUND_SCORES = {
    FundStatus.ACTIVE: 100.0,
    FundStatus.LIKELY_ACTIVE: 80.0,
    FundStatus.UNKNOWN: 40.0,
    FundStatus.SLOW_DEPLOYMENT: 30.0,
    FundStatus.FOLLOW_ON_ONLY: 10.0,
    FundStatus.BETWEEN_FUNDS: 5.0,
    FundStatus.INACTIVE: 0.0,
}
_SIGNAL_SCORES = {
    SignalValue.VERY_HIGH: 100.0,
    SignalValue.HIGH: 80.0,
    SignalValue.MEDIUM: 55.0,
    SignalValue.LOW: 30.0,
    SignalValue.UNKNOWN: 35.0,
}
_CONFLICT_SCORES = {
    ConflictLevel.NONE: 100.0,
    ConflictLevel.LOW: 80.0,
    ConflictLevel.UNKNOWN: 50.0,
    ConflictLevel.MODERATE: 30.0,
    ConflictLevel.HIGH: 0.0,
}


def score_investor(investor: Investor, requirement: LeadRequirement) -> dict[str, float]:
    """Per-dimension 0-100 scores. Kept in the JSON so a ranking can be audited."""
    breakdown: dict[str, float] = {}

    # Lead history: named, sourced examples beat a stated willingness to lead.
    if investor.has_verified_lead_history:
        named = [e for e in investor.lead_evidence_entries if e.company != "unnamed company"]
        breakdown["lead_history"] = 100.0 if len(named) >= 2 else (85.0 if named else 60.0)
    elif investor.leads_rounds_stated is True:
        breakdown["lead_history"] = 40.0
    elif investor.leads_rounds_stated is False:
        breakdown["lead_history"] = 0.0
    else:
        breakdown["lead_history"] = 15.0

    # Cheque size against the estimated lead requirement.
    if not requirement.is_known or investor.estimated_check_max is None:
        breakdown["check_size_fit"] = 35.0
    else:
        needed_low = requirement.lead_check_min or 0.0
        needed_high = requirement.lead_check_max or needed_low
        capacity = investor.estimated_check_max
        if capacity >= needed_high:
            breakdown["check_size_fit"] = 100.0
        elif capacity >= needed_low:
            breakdown["check_size_fit"] = 80.0
        elif needed_low > 0 and capacity >= needed_low * 0.5:
            breakdown["check_size_fit"] = 45.0
        else:
            breakdown["check_size_fit"] = 10.0

    breakdown["stage_fit"] = _STAGE_SCORES.get(investor.stage_fit, 35.0)
    breakdown["sector_fit"] = _SECTOR_SCORES.get(investor.sector_fit, 35.0)
    breakdown["active_deployment"] = _FUND_SCORES.get(investor.fund_status, 40.0)
    breakdown["relationship_strength"] = min(100.0, int(investor.relationship_strength) / 9 * 100)
    if investor.warm_intro_verified and investor.relationship_strength < Relationship.INTRO_MADE:
        breakdown["relationship_strength"] = max(breakdown["relationship_strength"], 35.0)

    if investor.timeline_compatible is True:
        breakdown["timeline_compatibility"] = 100.0
    elif investor.timeline_compatible is False:
        breakdown["timeline_compatibility"] = 10.0
    else:
        breakdown["timeline_compatibility"] = 50.0

    breakdown["signal_value"] = _SIGNAL_SCORES.get(investor.signal_value, 35.0)
    breakdown["conflict_risk"] = _CONFLICT_SCORES.get(investor.conflict_level, 50.0)
    return breakdown


def weighted_score(breakdown: dict[str, float]) -> float:
    return round(sum(breakdown.get(key, 0.0) * weight for key, weight in LEAD_SCORE_WEIGHTS.items()), 1)


def band(score: float, investor: Investor) -> LeadConfidence:
    """Convert a score into the band shown on the page.

    HIGH is gated on verified lead history regardless of score: a fund can look excellent
    on every other axis and still have no evidence it has ever priced a round.
    """
    if investor.tier not in {Tier.POTENTIAL_LEAD, Tier.CO_LEAD}:
        return LeadConfidence.NOT_A_LEAD
    blocked = (
        investor.fund_status in {FundStatus.BETWEEN_FUNDS, FundStatus.INACTIVE, FundStatus.FOLLOW_ON_ONLY}
        or investor.conflict_level == ConflictLevel.HIGH
    )
    if blocked:
        return LeadConfidence.LOW
    if (
        score >= LEAD_CONFIDENCE_HIGH
        and investor.has_verified_lead_history
        and investor.timeline_compatible is not False
    ):
        return LeadConfidence.HIGH
    if score >= LEAD_CONFIDENCE_MEDIUM:
        return LeadConfidence.MEDIUM
    return LeadConfidence.LOW


def rank(investors: list[Investor], requirement: LeadRequirement) -> list[Investor]:
    """Score every prospect and set the lead-confidence band."""
    for investor in investors:
        breakdown = score_investor(investor, requirement)
        investor.lead_score_breakdown = breakdown
        investor.lead_score = weighted_score(breakdown)
        investor.lead_confidence = band(investor.lead_score, investor)
    return investors


def build_shortlist(
    investors: list[Investor],
    requirement: LeadRequirement,
    round_: Round,
    company: Company,
    narratives: dict[str, dict] | None = None,
) -> list[ShortlistEntry]:
    """The 5-8 most credible lead candidates - or fewer, when fewer clear the bar."""
    candidates = [
        investor
        for investor in investors
        if investor.tier in {Tier.POTENTIAL_LEAD, Tier.CO_LEAD}
        and investor.is_active_prospect
        and (investor.lead_score or 0) >= SHORTLIST_FLOOR
    ]
    candidates.sort(key=lambda i: (i.tier != Tier.POTENTIAL_LEAD, -(i.lead_score or 0), i.investor_name))
    candidates = candidates[:SHORTLIST_MAX]

    entries: list[ShortlistEntry] = []
    for index, investor in enumerate(candidates, start=1):
        narrative = (narratives or {}).get(investor.investor_name.lower(), {})
        entries.append(
            ShortlistEntry(
                rank=index,
                investor_name=investor.investor_name,
                lead_confidence=investor.lead_confidence,
                check_display=investor.check_display(),
                why_they_can_lead=narrative.get("why_they_can_lead")
                or _why_they_can_lead(investor, requirement),
                why_they_fit=narrative.get("why_they_fit") or _why_they_fit(investor, company),
                key_obstacle=narrative.get("key_obstacle") or _key_obstacle(investor, round_),
                what_must_go_right=narrative.get("what_must_go_right") or _what_must_go_right(investor),
                required_next_step=investor.required_next_step,
                next_step_owner=investor.next_step_owner,
                relationship=investor.relationship_strength.short_label,
                lead_evidence=investor.lead_history_display(1),
                score=investor.lead_score,
            )
        )
    return entries


def _why_they_can_lead(investor: Investor, requirement: LeadRequirement) -> str:
    if investor.has_verified_lead_history:
        evidence = investor.lead_history_display(1)
        capacity = (
            f"cheque to {format_money(investor.estimated_check_max)}"
            if investor.estimated_check_max is not None
            else "cheque size NOT VERIFIED"
        )
        return truncate(f"Led before: {evidence}; {capacity}.", 150)
    if investor.leads_rounds_stated is True:
        return truncate(
            "States it leads rounds, but no named led round is evidenced - lead history NOT VERIFIED.",
            150,
        )
    return "Lead history NOT VERIFIED; treated as a partial lead only."


def _why_they_fit(investor: Investor, company: Company) -> str:
    bits = []
    if investor.stage_fit != Fit.UNKNOWN:
        bits.append(f"stage {investor.stage_fit.value.lower()}")
    if investor.sector_fit != Fit.UNKNOWN:
        bits.append(f"sector {investor.sector_fit.value.lower()}")
    if investor.supporting_portfolio_companies:
        bits.append(f"portfolio incl. {investor.supporting_portfolio_companies[0]}")
    if not bits:
        return "Fit NOT VERIFIED from the supplied material."
    return truncate("Fit: " + ", ".join(bits) + ".", 150)


def _key_obstacle(investor: Investor, round_: Round) -> str:
    if investor.conflict_level in {ConflictLevel.HIGH, ConflictLevel.MODERATE}:
        return truncate(
            f"Possible portfolio conflict: {investor.portfolio_conflicts[0].company}."
            if investor.portfolio_conflicts
            else "Possible portfolio conflict flagged.",
            150,
        )
    if investor.can_write_full_lead_check is False:
        return "Cheque capacity is below the estimated lead requirement."
    if investor.relationship_strength <= Relationship.WEAK_CONNECTION:
        return "Relationship is cold; no verified route in."
    if investor.timeline_compatible is False:
        return f"Process is unlikely to conclude by {round_.target_close.display()}."
    if investor.fund_status in {FundStatus.SLOW_DEPLOYMENT, FundStatus.UNKNOWN}:
        return "Current deployment capacity is not established."
    if not investor.has_verified_lead_history:
        return "No verified lead history - lead intent must be tested directly."
    return "No single blocking obstacle identified in the supplied material."


def _what_must_go_right(investor: Investor) -> str:
    if investor.dependencies:
        return truncate(investor.dependencies[0], 150)
    if investor.stated_dependencies:
        return truncate(investor.stated_dependencies[0], 150)
    if investor.relationship_strength < Relationship.FIRST_MEETING:
        return "Convert the introduction into a partner-level meeting."
    return "Move from interest to a priced proposal with named terms."
