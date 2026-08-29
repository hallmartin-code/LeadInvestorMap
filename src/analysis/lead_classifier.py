"""Fit assessment, the ten-point lead test, and six-tier classification.

The load-bearing decision in this application is Tier 1 versus everything else, because a
follower mistaken for a lead can stall a raise for a quarter. Tier 1 therefore requires
positive evidence on the criteria that actually determine whether a fund can price a
round - not prestige, not fund size, and not enthusiasm.
"""

from __future__ import annotations

import re

from ..models.company import Company
from ..models.evidence import Confidence, EvidenceStatus
from ..models.investor import (
    ConflictLevel,
    DiligenceStage,
    DisqualificationReason,
    Fit,
    FundStatus,
    Investor,
    InvestorType,
    QualificationResult,
    Relationship,
    SignalValue,
    Tier,
)
from ..models.round import LeadRequirement, Round
from ..utils.config import CO_LEAD_FRACTION, FILL_CHECK_FRACTION
from ..utils.dates import parse_date, today
from ..utils.money import format_money
from ..utils.text import squeeze

# --- stage vocabulary --------------------------------------------------------------------

_STAGE_ORDER = ["pre-seed", "seed", "series a", "series b", "series c", "series d", "growth"]

#: Words that appear in every thesis and so prove nothing about sector fit.
_GENERIC_SECTOR_WORDS = {
    "stated",
    "focus",
    "company",
    "market",
    "markets",
    "platform",
    "solution",
    "solutions",
    "technology",
    "technologies",
    "product",
    "products",
    "business",
    "model",
    "early",
    "stage",
    "venture",
    "ventures",
    "capital",
    "investments",
    "investing",
    "sector",
    "industry",
    "global",
    "based",
    "driven",
    "enabled",
    "first",
    "founder",
    "founders",
    "matched",
    "portfolio",
}

_STAGE_ALIASES: tuple[tuple[str, str], ...] = (
    (r"pre[-\s]?seed", "pre-seed"),
    (r"\bseed\b", "seed"),
    (r"series\s*a", "series a"),
    (r"\ba\s+round\b", "series a"),
    (r"series\s*b", "series b"),
    (r"\bb\s+round\b", "series b"),
    (r"series\s*c", "series c"),
    (r"series\s*d", "series d"),
    (r"\bgrowth\b|\blate[-\s]stage\b", "growth"),
    (r"\bearly[-\s]stage\b", "seed"),
)


def canonical_stage(text: str | None) -> str | None:
    if not text:
        return None
    low = squeeze(text).lower()
    for pattern, label in _STAGE_ALIASES:
        if re.search(pattern, low):
            return label
    return None


def stage_distance(investor_stage: str, round_stage: str) -> int | None:
    if investor_stage not in _STAGE_ORDER or round_stage not in _STAGE_ORDER:
        return None
    return _STAGE_ORDER.index(investor_stage) - _STAGE_ORDER.index(round_stage)


# --- fit ----------------------------------------------------------------------------------


def assess_stage_fit(investor: Investor, round_: Round) -> Investor:
    """Compare the investor's stated ENTRY stages with this round's stage.

    A portfolio company that has since reached Series A says nothing about where the fund
    enters, so only stated entry stages and lead history rounds are used.
    """
    round_stage = canonical_stage(round_.stage.value)
    if round_stage is None:
        investor.stage_fit = Fit.UNKNOWN
        investor.stage_fit_detail = (
            investor.stage_fit_detail or "Round stage not established; stage fit cannot be tested."
        )
        return investor

    declared = [canonical_stage(s) for s in investor.entry_stages]
    declared = [s for s in declared if s]

    if not declared:
        # Lead history is the next best evidence of where they actually enter.
        history = [canonical_stage(e.round_label) for e in investor.lead_evidence_entries]
        declared = [s for s in history if s]
        if declared:
            investor.stage_fit_detail = (
                investor.stage_fit_detail
                or f"Entry stage inferred from lead history: {', '.join(sorted(set(declared)))}"
            )

    if not declared:
        investor.stage_fit = Fit.UNKNOWN
        investor.stage_fit_detail = investor.stage_fit_detail or "No stated entry stage."
        return investor

    distances = [stage_distance(s, round_stage) for s in declared]
    distances = [d for d in distances if d is not None]
    if not distances:
        investor.stage_fit = Fit.UNKNOWN
        return investor

    closest = min(distances, key=abs)
    if closest == 0:
        investor.stage_fit = Fit.STRONG
    elif abs(closest) == 1:
        investor.stage_fit = Fit.PARTIAL
    else:
        investor.stage_fit = Fit.MISMATCH
    if not investor.stage_fit_detail:
        investor.stage_fit_detail = f"Stated entry: {', '.join(sorted(set(declared)))}"
    return investor


def assess_sector_fit(investor: Investor, company: Company) -> Investor:
    """Match stated sector focus and relevant portfolio against the company's own terms."""
    terms = [t for t in company.sector_terms() if len(t) >= 4]
    # Only stated focus, portfolio and researched claims count. Free-text notes are
    # excluded because "no life sciences investments identified" would otherwise read as
    # a life-sciences match.
    haystack = " ".join(
        filter(
            None,
            [
                investor.sector_fit_detail,
                " ".join(investor.supporting_portfolio_companies),
                " ".join(investor.research_claims),
            ],
        )
    ).lower()
    # Holding this company is not evidence of a sector thesis, so its own name is removed
    # from the text being matched - rather than from the terms, which would delete a real
    # sector word for a company called, say, "Helios Diagnostics".
    own_name = company.display_name.strip().lower()
    if own_name and own_name != "company not identified":
        haystack = haystack.replace(own_name, " ")

    if not haystack.strip():
        investor.sector_fit = Fit.UNKNOWN
        investor.sector_fit_detail = investor.sector_fit_detail or "No stated sector focus."
        return investor
    if not terms:
        investor.sector_fit = Fit.UNKNOWN
        return investor

    # Whole phrases rarely appear verbatim - a company in "medical diagnostics" meets a
    # fund investing in "diagnostics, medical devices" - so significant words count too.
    phrase_hits = [t for t in terms if t in haystack]
    tokens = {
        word for term in terms for word in re.findall(r"[a-z]{5,}", term) if word not in _GENERIC_SECTOR_WORDS
    }
    token_hits = sorted(t for t in tokens if t in haystack)
    stated_focus = "stated focus" in haystack

    if phrase_hits or len(token_hits) >= 2:
        investor.sector_fit = Fit.STRONG
    elif token_hits:
        investor.sector_fit = Fit.PARTIAL
    elif stated_focus:
        investor.sector_fit = Fit.WEAK
    else:
        investor.sector_fit = Fit.UNKNOWN

    hits = phrase_hits or token_hits

    if hits and "matched" not in investor.sector_fit_detail:
        detail = f"Matched: {', '.join(hits[:4])}"
        investor.sector_fit_detail = (
            f"{investor.sector_fit_detail}. {detail}".strip(". ") if investor.sector_fit_detail else detail
        )
    return investor


# --- cheque size ---------------------------------------------------------------------------


def assess_check_capacity(investor: Investor, requirement: LeadRequirement) -> Investor:
    """Can they write the lead cheque this round needs? Unknown stays unknown."""
    if not requirement.is_known:
        investor.can_write_full_lead_check = None
        return investor
    if investor.estimated_check_max is None:
        investor.can_write_full_lead_check = None
        return investor
    investor.can_write_full_lead_check = investor.estimated_check_max >= (requirement.lead_check_min or 0)
    return investor


# --- timeline --------------------------------------------------------------------------------

_TIME_TO_TERM_SHEET_WEEKS = {
    DiligenceStage.COLD: 16,
    DiligenceStage.INTRO_AVAILABLE: 15,
    DiligenceStage.INTRO_MADE: 13,
    DiligenceStage.FIRST_MEETING: 11,
    DiligenceStage.FOLLOW_UP: 10,
    DiligenceStage.PARTNER_MEETING: 8,
    DiligenceStage.DILIGENCE: 6,
    DiligenceStage.TERM_DISCUSSION: 3,
    DiligenceStage.VERBAL: 2,
    DiligenceStage.COMMITTED: 0,
    DiligenceStage.PASS: 99,
}


def assess_timeline(investor: Investor, round_: Round) -> Investor:
    """Estimate weeks to a term sheet from process position, and test it against the close.

    The estimate is a planning heuristic, labelled as such wherever it is displayed. Where
    no target close date exists, compatibility stays unknown rather than assumed.
    """
    weeks = _TIME_TO_TERM_SHEET_WEEKS.get(investor.current_diligence_stage, 16)
    if investor.investment_committee and "weekly" not in (investor.investment_committee or "").lower():
        weeks += 2
    investor.estimated_time_to_term_sheet = (
        "committed" if weeks == 0 else f"~{weeks} weeks (estimated from process position)"
    )

    close = parse_date(round_.target_close.value)
    if close is None:
        investor.timeline_compatible = None
        return investor
    weeks_available = (close - today()).days / 7.0
    investor.timeline_compatible = weeks_available >= weeks
    return investor


# --- signal -----------------------------------------------------------------------------------


def assess_signal_value(investor: Investor, all_investors: list[Investor]) -> Investor:
    """Signal is the ability to move other investors on THIS list, not general fame.

    Downstream names are only recorded where another prospect's own material says it is
    waiting for a lead - never invented from reputation.
    """
    waiting = [
        other.investor_name
        for other in all_investors
        if other.investor_name != investor.investor_name
        and ("Lead investor secured" in other.stated_dependencies or other.leads_rounds_stated is False)
    ]

    lead_evidence = investor.has_verified_lead_history
    institutional = investor.investor_type.is_institutional
    strategic = investor.investor_type.is_strategic

    if lead_evidence and institutional and waiting:
        investor.signal_value = SignalValue.VERY_HIGH if len(waiting) >= 3 else SignalValue.HIGH
        investor.signal_rationale = (
            f"Verified lead history and {len(waiting)} prospect(s) on this list state they need a "
            "lead in place."
        )
        investor.investors_influenced = waiting[:6]
    elif strategic and investor.relationship_strength >= Relationship.FIRST_MEETING:
        investor.signal_value = SignalValue.HIGH
        investor.signal_rationale = (
            "Strategic validation of the technology or market, which institutional investors can price off."
        )
        investor.investors_influenced = waiting[:4]
    elif lead_evidence and institutional:
        investor.signal_value = SignalValue.MEDIUM
        investor.signal_rationale = (
            "Verified lead history, but no listed prospect states it is waiting on a lead."
        )
    elif institutional:
        investor.signal_value = SignalValue.LOW
        investor.signal_rationale = "Institutional but no verified lead behaviour."
    else:
        investor.signal_value = SignalValue.UNKNOWN
        investor.signal_rationale = "Insufficient evidence to judge downstream influence."
    return investor


# --- the ten-point test --------------------------------------------------------------------------


def run_lead_test(
    investor: Investor, round_: Round, requirement: LeadRequirement, company: Company
) -> list[QualificationResult]:
    """Score the ten lead criteria. Each is PASS, FAIL or UNKNOWN with its reason."""
    results: list[QualificationResult] = []

    def add(criterion: str, verdict: str, detail: str) -> None:
        results.append(QualificationResult(criterion=criterion, verdict=verdict, detail=detail))

    # 1. Cheque-size fit
    if investor.can_write_full_lead_check is True:
        add(
            "Check-size fit",
            "PASS",
            f"Stated cheque up to {format_money(investor.estimated_check_max)} covers the "
            f"{requirement.display()} lead requirement.",
        )
    elif investor.can_write_full_lead_check is False:
        add(
            "Check-size fit",
            "FAIL",
            f"Stated cheque tops out at {format_money(investor.estimated_check_max)}; the lead "
            f"requirement is {requirement.display()}.",
        )
    else:
        add(
            "Check-size fit",
            "UNKNOWN",
            "No stated cheque size, or no lead requirement to test against.",
        )

    # 2. Stage fit
    if investor.stage_fit == Fit.STRONG:
        add("Stage fit", "PASS", investor.stage_fit_detail or "Enters at this stage.")
    elif investor.stage_fit in {Fit.MISMATCH, Fit.WEAK}:
        add(
            "Stage fit",
            "FAIL",
            investor.stage_fit_detail or "Entry stage does not match this round.",
        )
    elif investor.stage_fit == Fit.PARTIAL:
        add("Stage fit", "UNKNOWN", investor.stage_fit_detail or "Adjacent stage; needs confirming.")
    else:
        add("Stage fit", "UNKNOWN", "Entry stage not established.")

    # 3. Sector fit
    if investor.sector_fit == Fit.STRONG:
        add("Sector fit", "PASS", investor.sector_fit_detail or "Sector focus matches.")
    elif investor.sector_fit in {Fit.MISMATCH, Fit.WEAK}:
        add(
            "Sector fit",
            "FAIL",
            investor.sector_fit_detail or "Stated focus does not cover this sector.",
        )
    elif investor.sector_fit == Fit.PARTIAL:
        add("Sector fit", "UNKNOWN", investor.sector_fit_detail or "Partial sector overlap.")
    else:
        add("Sector fit", "UNKNOWN", "Sector focus not established.")

    # 4. Evidence of leading comparable rounds
    if investor.has_verified_lead_history:
        add("Lead history", "PASS", investor.lead_history_display())
    elif investor.leads_rounds_stated is True:
        add(
            "Lead history",
            "UNKNOWN",
            "States that it leads rounds, but no named led round was evidenced.",
        )
    elif investor.leads_rounds_stated is False:
        add("Lead history", "FAIL", "Material states this investor does not lead.")
    else:
        add("Lead history", "FAIL", "NOT VERIFIED - participation is not evidence of leading.")

    # 5. Ownership fit
    if investor.ownership_expectation:
        add("Ownership fit", "UNKNOWN", f"Stated expectation: {investor.ownership_expectation}.")
    else:
        add("Ownership fit", "UNKNOWN", "Ownership expectation not publicly verified.")

    # 6. Governance / board behaviour
    if investor.board_expectation:
        add("Governance fit", "PASS", investor.board_expectation)
    elif any("board seat" in e.role for e in investor.lead_history):
        add("Governance fit", "PASS", "Has taken a board seat in a financing it led.")
    else:
        add("Governance fit", "UNKNOWN", "Board behaviour not established.")

    # 7. Active deployment
    if investor.fund_status.is_deploying:
        add("Active deployment", "PASS", f"Fund status: {investor.fund_status.value}.")
    elif investor.fund_status in {
        FundStatus.BETWEEN_FUNDS,
        FundStatus.INACTIVE,
        FundStatus.FOLLOW_ON_ONLY,
        FundStatus.SLOW_DEPLOYMENT,
    }:
        add("Active deployment", "FAIL", f"Fund status: {investor.fund_status.value}.")
    else:
        add("Active deployment", "UNKNOWN", "Current deployment activity not established.")

    # 8. Portfolio conflict
    if investor.conflict_level == ConflictLevel.HIGH:
        add(
            "Portfolio conflict",
            "FAIL",
            "; ".join(c.rationale for c in investor.portfolio_conflicts[:2]),
        )
    elif investor.conflict_level == ConflictLevel.MODERATE:
        add("Portfolio conflict", "UNKNOWN", "Possible conflict flagged in the material.")
    elif investor.conflict_level == ConflictLevel.NONE:
        add("Portfolio conflict", "PASS", "No competing portfolio company identified.")
    else:
        add("Portfolio conflict", "UNKNOWN", "Portfolio not established.")

    # 9. Relationship accessibility
    if investor.relationship_strength >= Relationship.FIRST_MEETING:
        add("Relationship access", "PASS", investor.relationship_strength.label)
    elif investor.relationship_strength >= Relationship.WARM_INTRO_AVAILABLE:
        add(
            "Relationship access",
            "PASS" if investor.warm_intro_verified else "UNKNOWN",
            investor.warm_intro_path or investor.relationship_strength.label,
        )
    else:
        add(
            "Relationship access",
            "FAIL",
            f"Relationship is {investor.relationship_strength.label}.",
        )

    # 10. Ability to close within the round timeline
    if investor.timeline_compatible is True:
        add("Timeline fit", "PASS", investor.estimated_time_to_term_sheet or "")
    elif investor.timeline_compatible is False:
        add(
            "Timeline fit",
            "FAIL",
            f"{investor.estimated_time_to_term_sheet} exceeds the window to {round_.target_close.display()}.",
        )
    else:
        add("Timeline fit", "UNKNOWN", "No target close date to test against.")

    return results


# --- tiering ---------------------------------------------------------------------------------------


def classify(investor: Investor, round_: Round, requirement: LeadRequirement, company: Company) -> Investor:
    """Assign exactly one tier, with the reasons recorded on the investor."""
    investor.qualification = run_lead_test(investor, round_, requirement, company)
    verdicts = {q.criterion: q.verdict for q in investor.qualification}

    investor.lead_history_confidence = _lead_history_confidence(investor)
    investor.disqualification_reasons = _disqualifications(investor, round_, requirement, verdicts)

    if investor.current_diligence_stage == DiligenceStage.PASS:
        investor.tier = Tier.FOLLOW_ON if investor.investor_type.is_institutional else Tier.FILL_THE_ROUND
        investor.tier_rationale = "Has passed on the round."
        return investor

    if _qualifies_as_lead(investor, verdicts):
        investor.tier = Tier.POTENTIAL_LEAD
        investor.tier_rationale = (
            f"Verified lead history ({investor.lead_history_display(1)}), cheque capacity for the "
            f"{requirement.display()} lead requirement, and no disqualifying fit or conflict issue."
        )
        return investor

    if _qualifies_as_co_lead(investor, requirement, verdicts):
        investor.tier = Tier.CO_LEAD
        investor.tier_rationale = (
            "Can anchor a substantial part of the round but the evidence does not support "
            "pricing and underwriting it alone."
        )
        return investor

    if investor.investor_type.is_strategic:
        investor.tier = Tier.STRATEGIC_VALIDATOR
        investor.tier_rationale = (
            "Strategic or corporate investor: validation and commercial leverage rather than "
            "round leadership."
        )
        return investor

    if investor.investor_type.is_institutional:
        investor.tier = Tier.FOLLOW_ON
        reason = (
            "Material states this investor does not lead."
            if investor.leads_rounds_stated is False
            else "No verified lead history."
        )
        investor.tier_rationale = f"Institutional participant. {reason} Requires lead in place."
        if "Lead investor secured" not in investor.dependencies:
            investor.dependencies.insert(0, "Lead investor secured")
        return investor

    if investor.investor_type.is_individual_or_pooled or investor.investor_type in {
        InvestorType.ACCELERATOR,
        InvestorType.GOVERNMENT,
    }:
        if _is_fill_the_round(investor, round_):
            investor.tier = Tier.FILL_THE_ROUND
            investor.tier_rationale = (
                "Small cheque with limited pricing, signalling or governance influence; useful for "
                "completing allocation."
            )
        else:
            investor.tier = Tier.ANGEL_FAMILY_SYNDICATE
            investor.tier_rationale = (
                "Angel, family office or syndicate capital; no evidence of institutional lead behaviour."
            )
        return investor

    if _is_fill_the_round(investor, round_):
        investor.tier = Tier.FILL_THE_ROUND
        investor.tier_rationale = "Cheque size is small relative to the round; allocation filler."
    else:
        investor.tier = Tier.FOLLOW_ON
        investor.tier_rationale = (
            "Insufficient evidence of lead behaviour; treated as a participant until proven otherwise."
        )
        if "Lead investor secured" not in investor.dependencies:
            investor.dependencies.insert(0, "Lead investor secured")
    return investor


def _qualifies_as_lead(investor: Investor, verdicts: dict[str, str]) -> bool:
    """Tier 1 needs affirmative evidence on the criteria that decide who can price a round."""
    if not investor.has_verified_lead_history:
        return False
    if investor.leads_rounds_stated is False:
        return False
    if not investor.investor_type.is_institutional and investor.investor_type != InvestorType.UNKNOWN:
        return False
    if verdicts.get("Check-size fit") == "FAIL":
        return False
    if verdicts.get("Stage fit") == "FAIL":
        return False
    if verdicts.get("Sector fit") == "FAIL":
        return False
    if verdicts.get("Active deployment") == "FAIL":
        return False
    if investor.conflict_level == ConflictLevel.HIGH:
        return False
    # An unknown cheque size cannot be assumed adequate.
    if investor.can_write_full_lead_check is not True:
        return False
    # A timeline that does not reach the target close is an obstacle to manage, not proof
    # that the fund cannot lead - the close date is the company's aspiration, and treating
    # it as disqualifying would empty Tier 1 whenever a founder sets an ambitious date. It
    # caps lead confidence at MEDIUM instead (see lead_ranker.band).
    return True


def _qualifies_as_co_lead(investor: Investor, requirement: LeadRequirement, verdicts: dict[str, str]) -> bool:
    if investor.conflict_level == ConflictLevel.HIGH:
        return False
    if investor.investor_type.is_strategic:
        return False
    if not (investor.investor_type.is_institutional or investor.investor_type == InvestorType.UNKNOWN):
        return False
    if investor.leads_rounds_stated is False:
        return False
    # A fund that cannot deploy, or invests somewhere else entirely, cannot anchor part of
    # this round however good its lead history looks.
    if verdicts.get("Active deployment") == "FAIL":
        return False
    if verdicts.get("Sector fit") == "FAIL":
        return False
    if verdicts.get("Stage fit") == "FAIL":
        return False

    # Lead signal must be evidenced. A fund that merely says it leads, and enters at a
    # different stage, is a participant here - promoting it would be the exact error this
    # tool exists to prevent.
    if not investor.has_verified_lead_history:
        if investor.leads_rounds_stated is not True or investor.stage_fit != Fit.STRONG:
            return False

    if requirement.is_known and investor.estimated_check_max is not None:
        threshold = (requirement.lead_check_min or 0) * CO_LEAD_FRACTION
        return investor.estimated_check_max >= threshold
    # Lead signal but no cheque evidence: co-lead is the honest placement.
    return True


def _is_fill_the_round(investor: Investor, round_: Round) -> bool:
    total = round_.raise_amount.numeric_value
    if total is None or investor.estimated_check_max is None:
        return False
    return investor.estimated_check_max < total * FILL_CHECK_FRACTION


def _lead_history_confidence(investor: Investor) -> Confidence:
    entries = investor.lead_evidence_entries
    if not entries:
        return Confidence.INSUFFICIENT
    named = [e for e in entries if e.company != "unnamed company"]
    with_sources = [e for e in named if e.source is not None]
    if len(named) >= 2 and with_sources:
        return Confidence.HIGH
    if named and with_sources:
        return Confidence.MEDIUM
    return Confidence.LOW


def _disqualifications(
    investor: Investor, round_: Round, requirement: LeadRequirement, verdicts: dict[str, str]
) -> list[DisqualificationReason]:
    reasons: list[DisqualificationReason] = []

    if investor.current_diligence_stage == DiligenceStage.PASS:
        reasons.append(DisqualificationReason.PASSED)
    if not investor.has_verified_lead_history:
        reasons.append(DisqualificationReason.NO_VERIFIED_LEAD_HISTORY)
    if investor.can_write_full_lead_check is False:
        reasons.append(DisqualificationReason.CHECK_TOO_SMALL)
    if investor.leads_rounds_stated is False or "Lead investor secured" in investor.stated_dependencies:
        reasons.append(DisqualificationReason.REQUIRES_EXISTING_LEAD)
    if verdicts.get("Stage fit") == "FAIL":
        reasons.append(DisqualificationReason.WRONG_STAGE)
    if verdicts.get("Sector fit") == "FAIL":
        reasons.append(DisqualificationReason.WRONG_SECTOR)
    if investor.conflict_level == ConflictLevel.HIGH:
        reasons.append(DisqualificationReason.PORTFOLIO_CONFLICT)
    if investor.fund_status == FundStatus.INACTIVE:
        reasons.append(DisqualificationReason.INACTIVE_FUND)
    if investor.fund_status == FundStatus.BETWEEN_FUNDS:
        reasons.append(DisqualificationReason.BETWEEN_FUNDS)
    if investor.fund_status == FundStatus.FOLLOW_ON_ONLY:
        reasons.append(DisqualificationReason.FOLLOW_ON_ONLY)
    if investor.timeline_compatible is False:
        reasons.append(DisqualificationReason.TIMELINE_TOO_LONG)
    if investor.relationship_strength <= Relationship.WEAK_CONNECTION and not investor.warm_intro_verified:
        reasons.append(DisqualificationReason.RELATIONSHIP_TOO_COLD)
    if investor.investor_type.is_strategic:
        reasons.append(DisqualificationReason.STRATEGIC_ONLY)

    # De-duplicate while preserving the order they were tested in.
    unique: list[DisqualificationReason] = []
    for reason in reasons:
        if reason not in unique:
            unique.append(reason)
    return unique


def classify_all(
    investors: list[Investor], round_: Round, requirement: LeadRequirement, company: Company
) -> list[Investor]:
    """Run fit, conflict, signal and tier assignment across the whole prospect list."""
    from .conflict_analyzer import analyse_conflicts

    for investor in investors:
        analyse_conflicts(investor, company)
        assess_stage_fit(investor, round_)
        assess_sector_fit(investor, company)
        assess_check_capacity(investor, requirement)
        assess_timeline(investor, round_)

    for investor in investors:
        assess_signal_value(investor, investors)

    for investor in investors:
        classify(investor, round_, requirement, company)
        _set_overall_confidence(investor)
    return investors


def _set_overall_confidence(investor: Investor) -> None:
    known = sum(
        1
        for value in (
            investor.estimated_check_max,
            investor.stage_fit != Fit.UNKNOWN or None,
            investor.sector_fit != Fit.UNKNOWN or None,
            investor.fund_status != FundStatus.UNKNOWN or None,
            investor.has_verified_lead_history or None,
        )
        if value
    )
    sourced = len(investor.sources)
    if known >= 4 and sourced >= 2:
        investor.confidence = Confidence.HIGH
    elif known >= 3 or (known >= 2 and sourced >= 2):
        investor.confidence = Confidence.MEDIUM
    elif known >= 1:
        investor.confidence = Confidence.LOW
    else:
        investor.confidence = Confidence.INSUFFICIENT

    if investor.check_size_status == EvidenceStatus.NOT_PROVIDED and investor.confidence == Confidence.HIGH:
        investor.confidence = Confidence.MEDIUM
