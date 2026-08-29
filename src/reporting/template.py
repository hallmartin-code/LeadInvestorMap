"""The blank document template.

``blank_map()`` is a fully-placeholdered :class:`LeadInvestorMap`: no company, no
investors, no scores - only the structure, the field slots, and the fixed vocabularies
each slot may draw from. Rendering it through the ordinary renderer produces the canonical
one-pager template, which is why the template can never drift from what the application
actually emits.

It also exercises every conditional zone at once - a Tier 1 and a Tier 2 candidate, a
verified and an unverified lead history, all three lead-confidence bands, every outreach
phase, the disqualification list, the gaps table, a company objection and the fallback
structures - so the template shows every state the layout can enter, including states that
never co-occur in a real analysis.

Values that come from a fixed vocabulary (tiers, relationship stages, confidence bands,
disqualification reasons) are shown as their real vocabulary terms rather than as
placeholders, because those terms *are* the template: an analysis may only ever print one
of them.
"""

from __future__ import annotations

from .. import models as M
from ..models.analysis import (
    Disqualification,
    FallbackStructure,
    Gap,
    HighestPullCommitment,
    LeadInvestorMap,
    MomentumStep,
    OutreachPhase,
    OutreachSequence,
    RunMetadata,
    ShortlistEntry,
)
from ..models.company import Company, Objection
from ..models.evidence import Confidence, EvidenceStatus, Fact, SourceRef, SourceType
from ..models.investor import (
    ConflictLevel,
    DiligenceStage,
    DisqualificationReason,
    Fit,
    FundStatus,
    Investor,
    InvestorType,
    LeadConfidence,
    LeadHistoryEntry,
    PortfolioConflict,
    QualificationResult,
    Relationship,
    SignalValue,
    Tier,
)
from ..models.round import LeadRequirement, Round

PLACEHOLDER_PAGE = 1
"""Page or slide number on every template citation.

It exists so the template demonstrates the source-reference format ("deck p./sl. 1"). It
is a format marker, not a reference to any real page.
"""

_QUOTE = "[VERBATIM SENTENCE FROM THE CITED PAGE OR SLIDE, MAX 400 CHARS]"


def _source(source_type: SourceType = SourceType.PITCH_DECK, name: str = "[SOURCE FILENAME]") -> SourceRef:
    return SourceRef(
        source_type=source_type,
        source_name=name,
        page_or_slide=PLACEHOLDER_PAGE,
        source_text=_QUOTE,
    )


def _fact(claim: str, placeholder: str, numeric: float | None = None) -> Fact:
    """A verified, sourced fact slot. Real runs fill value and numeric_value."""
    return Fact.from_document(claim, placeholder, _source(), numeric_value=numeric)


# --- company and round ---------------------------------------------------------------------


def _company() -> Company:
    company = Company(
        name=_fact("Company name", "[COMPANY NAME]"),
        one_liner=_fact("Company one-liner", "[ONE-LINE DESCRIPTION OF THE BUSINESS, MAX 140 CHARACTERS]"),
        sector=_fact("Sector", "[SECTOR]"),
        sub_sector=_fact("Sub-sector", "[SUB-SECTOR]"),
        business_model=_fact("Business model", "[BUSINESS MODEL]"),
        market=_fact("Market", "[MARKET DESCRIPTION]"),
        stage=_fact("Company stage", "[COMPANY STAGE]"),
        location=_fact("Location", "[HEADQUARTERS]"),
        fundraising_status=_fact("Fundraising status", "[FUNDRAISING STATUS]"),
        keywords=["[KEYWORD 1]", "[KEYWORD 2]", "[KEYWORD 3]"],
        named_competitors=["[COMPETITOR NAMED IN THE DECK]"],
    )
    company.traction = [_fact("Traction", "[TRACTION FACT WITH A NUMBER, AS STATED IN THE DECK]")]
    company.key_risks = [_fact("Stated risk", "[RISK THE DECK ITSELF ACKNOWLEDGES]")]
    company.investor_weaknesses = [
        _fact("Investor-visible weakness", "[GAP AN INVESTOR WOULD NOTICE IN THIS DECK]")
    ]
    company.objections = [
        Objection(
            category="[OBJECTION CATEGORY]",
            objection="[OBJECTION NAMING A FIGURE OR STATED GAP]",
            evidence="[DECK CONTENT, OR THE ABSENCE, BEHIND IT]",
            source_ref=f"p./sl. {PLACEHOLDER_PAGE}",
            severity="high",
        )
    ]
    return company


class _TemplateRound(Round):
    """A Round whose derived field shows its slot rather than arithmetic on placeholders."""

    @property
    def remaining(self) -> Fact:
        return Fact(
            claim="Remaining allocation",
            value="[$ REMAINING]",
            status=EvidenceStatus.INFERRED,
            confidence=Confidence.MEDIUM,
            note="Derived: total raise less stated commitments.",
        )


class _TemplateRequirement(LeadRequirement):
    """A LeadRequirement that displays its slot rather than a computed range."""

    def display(self) -> str:
        return "[$ MIN-$ MAX]"


def _round() -> Round:
    return _TemplateRound(
        stage=_fact("Round stage", "[STAGE]"),
        raise_amount=_fact("Round size", "[$ RAISE]", 0.0),
        instrument=_fact("Instrument", "[INSTRUMENT]"),
        pre_money=_fact("Pre-money valuation", "[$ PRE-MONEY]", 0.0),
        safe_cap=Fact.missing("Valuation cap"),
        committed=_fact("Amount committed", "[$ COMMITTED]", 0.0),
        circled=_fact("Amount circled", "[$ CIRCLED]", 0.0),
        target_close=_fact("Target close", "[TARGET CLOSE]"),
        investor_count=Fact.missing("Investor count"),
    )


def _requirement() -> LeadRequirement:
    return _TemplateRequirement(
        remaining_raise=0.0,
        lead_check_min=0.0,
        lead_check_max=0.0,
        basis="[$ RAISE less $ COMMITTED = $ REMAINING]",
        confidence=Confidence.MEDIUM,
        status=EvidenceStatus.INFERRED,
        assumptions=["[STATED ASSUMPTION BEHIND THE ESTIMATE]"],
    )


# --- prospects ------------------------------------------------------------------------------


def _prospect(
    name: str,
    tier: Tier,
    *,
    lead_confidence: LeadConfidence,
    verified_lead_history: bool,
    relationship: Relationship,
    diligence: DiligenceStage,
    investor_type: InvestorType = InvestorType.VC,
    fit: Fit = Fit.STRONG,
    conflict: ConflictLevel = ConflictLevel.NONE,
    fund_status: FundStatus = FundStatus.ACTIVE,
    signal: SignalValue = SignalValue.HIGH,
    disqualifications: list[DisqualificationReason] | None = None,
    dependency: str = "[DEPENDENCY BEFORE THEY COMMIT]",
) -> Investor:
    investor = Investor(
        investor_name=name,
        aliases=["[ALIAS, IF THE MATERIAL USES MORE THAN ONE NAME]"],
        investor_type=investor_type,
        tier=tier,
        tier_rationale="[WHY THIS TIER, NOT THE ONE ABOVE]",
        estimated_check_min=0.0,
        estimated_check_max=0.0,
        check_size_status=EvidenceStatus.UNVERIFIED,
        check_size_confidence=Confidence.MEDIUM,
        can_write_full_lead_check=tier == Tier.POTENTIAL_LEAD,
        lead_history_confidence=Confidence.MEDIUM if verified_lead_history else Confidence.INSUFFICIENT,
        leads_rounds_stated=True if verified_lead_history else None,
        stage_fit=fit,
        stage_fit_detail="[STATED ENTRY STAGES]",
        entry_stages=["[ENTRY STAGE]"],
        sector_fit=fit,
        sector_fit_detail="[STATED SECTOR FOCUS]",
        supporting_portfolio_companies=["[RELEVANT PORTFOLIO COMPANY]"],
        conflict_level=conflict,
        fund_vintage="[FUND VINTAGE YEAR]",
        fund_status=fund_status,
        deployment_status=fund_status.value,
        recent_deal_pace="[RECENT DEAL PACE, IF ESTABLISHED]",
        relationship_strength=relationship,
        relationship_detail="[RELATIONSHIP AS DESCRIBED IN THE MATERIAL]",
        warm_intro_path="[FOUNDER > CONNECTOR > PARTNER]",
        warm_intro_verified=True,
        current_diligence_stage=diligence,
        decision_champion="[NAMED CHAMPION, IF ESTABLISHED]",
        partner_meeting_cadence="[CADENCE, IF PUBLICLY VERIFIED]",
        investment_committee="[IC REQUIREMENT, IF PUBLICLY VERIFIED]",
        estimated_time_to_term_sheet="[~N WEEKS (ESTIMATED FROM PROCESS POSITION)]",
        timeline_compatible=True,
        signal_value=signal,
        signal_rationale="[WHY THIS COMMITMENT WOULD OR WOULD NOT MOVE OTHERS]",
        investors_influenced=["[PROSPECT THAT STATES IT NEEDS A LEAD]"],
        ownership_expectation="[OWNERSHIP TARGET, IF VERIFIED]",
        board_expectation="[BOARD EXPECTATION, IF VERIFIED]",
        pro_rata_expectation="[PRO-RATA EXPECTATION, IF VERIFIED]",
        governance_expectation="[GOVERNANCE EXPECTATION, IF VERIFIED]",
        likely_objections=["[OBJECTION THIS INVESTOR IS LIKELY TO RAISE]"],
        required_next_step="[SINGLE NEXT ACTION]",
        next_step_owner="[OWNER]",
        dependencies=[dependency],
        stated_dependencies=["[CONDITION THE INVESTOR THEMSELVES STATED]"],
        lead_score=0.0,
        lead_score_breakdown={key: 0.0 for key in _SCORE_DIMENSIONS},
        lead_confidence=lead_confidence,
        disqualification_reasons=disqualifications or [],
        confidence=Confidence.MEDIUM,
        notes="[FREE-TEXT NOTES CARRIED THROUGH TO THE JSON AND CSV, NOT THE PDF]",
    )
    investor.add_source(_source(SourceType.INVESTOR_LIST, "[INVESTOR LIST FILENAME]"))
    investor.add_source(_source(SourceType.MEETING_NOTES, "[MEETING NOTES FILENAME]"))

    if verified_lead_history:
        investor.lead_history = [
            LeadHistoryEntry(
                company="[PORTFOLIO COMPANY]",
                round_label="[ROUND]",
                role="led",
                year="[YEAR]",
                source=_source(SourceType.INVESTOR_LIST, "[INVESTOR LIST FILENAME]"),
                confidence=Confidence.MEDIUM,
            ),
            LeadHistoryEntry(
                company="[PORTFOLIO COMPANY]",
                round_label="[ROUND]",
                role="co-led",
                year="[YEAR]",
                source=_source(SourceType.INVESTOR_LIST, "[INVESTOR LIST FILENAME]"),
                confidence=Confidence.MEDIUM,
            ),
        ]
    if conflict in {ConflictLevel.MODERATE, ConflictLevel.HIGH}:
        investor.portfolio_conflicts = [
            PortfolioConflict(
                company="[COMPETING PORTFOLIO COMPANY]",
                level=conflict,
                rationale="[WHY THIS IS A CONFLICT, TIED TO A COMPETITOR NAMED IN THE DECK]",
                source=_source(),
            )
        ]

    investor.qualification = [
        QualificationResult(
            criterion=criterion,
            verdict="[PASS | FAIL | UNKNOWN]",
            detail="[THE EVIDENCE, OR THE REASON IT COULD NOT BE TESTED]",
        )
        for criterion in _LEAD_TEST_CRITERIA
    ]
    return investor


_LEAD_TEST_CRITERIA = (
    "Check-size fit",
    "Stage fit",
    "Sector fit",
    "Lead history",
    "Ownership fit",
    "Governance fit",
    "Active deployment",
    "Portfolio conflict",
    "Relationship access",
    "Timeline fit",
)

_SCORE_DIMENSIONS = (
    "lead_history",
    "check_size_fit",
    "stage_fit",
    "sector_fit",
    "active_deployment",
    "relationship_strength",
    "timeline_compatibility",
    "signal_value",
    "conflict_risk",
)


def _shortlist_entry(
    rank: int,
    name: str,
    confidence: LeadConfidence,
    verified: bool,
    relationship: Relationship,
) -> ShortlistEntry:
    return ShortlistEntry(
        rank=rank,
        investor_name=name,
        lead_confidence=confidence,
        check_display="[$ MIN-$ MAX]",
        why_they_can_lead=(
            "[CHEQUE CAPACITY + NAMED LEAD EVIDENCE]"
            if verified
            else "[SAY PLAINLY: LEAD HISTORY NOT VERIFIED]"
        ),
        why_they_fit="[STAGE + SECTOR FIT FOR THIS COMPANY]",
        key_obstacle="[BIGGEST OBSTACLE]",
        what_must_go_right="[CONDITION TO COMMIT]",
        required_next_step="[SINGLE NEXT ACTION]",
        next_step_owner="[OWNER]",
        relationship=relationship.short_label,
        lead_evidence="[CO. - ROUND - ROLE - YEAR]" if verified else "NOT VERIFIED",
        score=0.0,
    )


# --- the template ------------------------------------------------------------------------------


def blank_map() -> LeadInvestorMap:
    """A LeadInvestorMap containing only field placeholders and structural markers."""
    analysis = LeadInvestorMap(company=_company(), round=_round(), lead_requirement=_requirement())

    tier_one = _prospect(
        "[LEAD CANDIDATE 1]",
        Tier.POTENTIAL_LEAD,
        lead_confidence=LeadConfidence.HIGH,
        verified_lead_history=True,
        relationship=Relationship.PARTNER_ENGAGEMENT,
        diligence=DiligenceStage.PARTNER_MEETING,
        signal=SignalValue.VERY_HIGH,
    )
    tier_two = _prospect(
        "[LEAD CANDIDATE 2]",
        Tier.CO_LEAD,
        lead_confidence=LeadConfidence.MEDIUM,
        verified_lead_history=True,
        relationship=Relationship.FIRST_MEETING,
        diligence=DiligenceStage.FIRST_MEETING,
        investor_type=InvestorType.MICRO_VC,
        disqualifications=[DisqualificationReason.CHECK_TOO_SMALL],
        dependency="[CO-LEAD PARTNER IDENTIFIED]",
    )
    tier_two_unverified = _prospect(
        "[LEAD CANDIDATE 3]",
        Tier.CO_LEAD,
        lead_confidence=LeadConfidence.LOW,
        verified_lead_history=False,
        relationship=Relationship.INTRO_MADE,
        diligence=DiligenceStage.INTRO_MADE,
        fit=Fit.PARTIAL,
        conflict=ConflictLevel.UNKNOWN,
        signal=SignalValue.MEDIUM,
    )
    strategic = _prospect(
        "[STRATEGIC INVESTOR]",
        Tier.STRATEGIC_VALIDATOR,
        lead_confidence=LeadConfidence.NOT_A_LEAD,
        verified_lead_history=False,
        relationship=Relationship.ACTIVE_DILIGENCE,
        diligence=DiligenceStage.DILIGENCE,
        investor_type=InvestorType.CORPORATE,
        disqualifications=[DisqualificationReason.STRATEGIC_ONLY],
    )
    follower = _prospect(
        "[FOLLOW-ON INVESTOR]",
        Tier.FOLLOW_ON,
        lead_confidence=LeadConfidence.NOT_A_LEAD,
        verified_lead_history=False,
        relationship=Relationship.FIRST_MEETING,
        diligence=DiligenceStage.FIRST_MEETING,
        disqualifications=[
            DisqualificationReason.NO_VERIFIED_LEAD_HISTORY,
            DisqualificationReason.REQUIRES_EXISTING_LEAD,
        ],
        dependency="[LEAD INVESTOR SECURED]",
    )
    conflicted = _prospect(
        "[CONFLICTED INVESTOR]",
        Tier.FOLLOW_ON,
        lead_confidence=LeadConfidence.NOT_A_LEAD,
        verified_lead_history=False,
        relationship=Relationship.INTRO_MADE,
        diligence=DiligenceStage.INTRO_MADE,
        conflict=ConflictLevel.HIGH,
        disqualifications=[DisqualificationReason.PORTFOLIO_CONFLICT],
        dependency="[PORTFOLIO CONFLICT CLEARED]",
    )
    inactive = _prospect(
        "[BETWEEN-FUNDS INVESTOR]",
        Tier.FOLLOW_ON,
        lead_confidence=LeadConfidence.NOT_A_LEAD,
        verified_lead_history=True,
        relationship=Relationship.FOLLOW_UP
        if hasattr(Relationship, "FOLLOW_UP")
        else Relationship.FIRST_MEETING,
        diligence=DiligenceStage.FOLLOW_UP,
        fund_status=FundStatus.BETWEEN_FUNDS,
        disqualifications=[DisqualificationReason.BETWEEN_FUNDS],
    )
    angel = _prospect(
        "[ANGEL / FO / SYNDICATE]",
        Tier.ANGEL_FAMILY_SYNDICATE,
        lead_confidence=LeadConfidence.NOT_A_LEAD,
        verified_lead_history=False,
        relationship=Relationship.VERBAL_INTEREST,
        diligence=DiligenceStage.VERBAL,
        investor_type=InvestorType.ANGEL_GROUP,
        signal=SignalValue.LOW,
        disqualifications=[DisqualificationReason.CHECK_TOO_SMALL],
        dependency="[LEAD INVESTOR SECURED]",
    )
    filler = _prospect(
        "[FILL-THE-ROUND INVESTOR]",
        Tier.FILL_THE_ROUND,
        lead_confidence=LeadConfidence.NOT_A_LEAD,
        verified_lead_history=False,
        relationship=Relationship.WEAK_CONNECTION,
        diligence=DiligenceStage.COLD,
        investor_type=InvestorType.SYNDICATE,
        signal=SignalValue.LOW,
        disqualifications=[DisqualificationReason.CHECK_TOO_SMALL],
        dependency="[LEAD INVESTOR SECURED]",
    )

    analysis.prospects = [
        tier_one,
        tier_two,
        tier_two_unverified,
        strategic,
        follower,
        conflicted,
        inactive,
        angel,
        filler,
    ]

    analysis.lead_shortlist = [
        _shortlist_entry(
            1, tier_one.investor_name, LeadConfidence.HIGH, True, Relationship.PARTNER_ENGAGEMENT
        ),
        _shortlist_entry(2, tier_two.investor_name, LeadConfidence.MEDIUM, True, Relationship.FIRST_MEETING),
        _shortlist_entry(
            3, tier_two_unverified.investor_name, LeadConfidence.LOW, False, Relationship.INTRO_MADE
        ),
    ]

    analysis.highest_pull_commitment = HighestPullCommitment(
        investor_name=tier_one.investor_name,
        rationale="[WHY THIS COMMITMENT MOVES THE ROUND]",
        downstream_investors=[
            "[PROSPECT NEEDING A LEAD]",
            "[PROSPECT NEEDING A LEAD]",
        ],
        confidence="[HIGH | MEDIUM | LOW | INSUFFICIENT EVIDENCE]",
    )
    analysis.momentum_sequence = [
        MomentumStep(
            step=1,
            investor_name=tier_one.investor_name,
            event="commits as lead",
            effect="Prices the round and sets terms.",
            basis="[THE EVIDENCE BEHIND THIS STEP]",
        ),
        MomentumStep(
            step=2,
            investor_name=follower.investor_name,
            event="enters diligence",
            effect="Stated dependency on a lead is satisfied.",
            basis="[STATED DEPENDENCY]",
        ),
        MomentumStep(
            step=3,
            investor_name=strategic.investor_name,
            event="validates the sector",
            effect="Commercial or technical validation for remaining institutions.",
            basis="[BASIS FOR THE VALIDATION CLAIM]",
        ),
        MomentumStep(
            step=4,
            investor_name=f"{angel.investor_name}, {filler.investor_name}",
            event="fill remaining allocation",
            effect="Round completes.",
            basis="[COUNT OF PROSPECTS AVAILABLE FOR ALLOCATION]",
        ),
    ]

    analysis.disqualified_as_leads = [
        Disqualification(
            investor_name=investor.investor_name,
            reasons=investor.disqualification_reasons[:2],
            detail=investor.tier_rationale,
        )
        for investor in (strategic, follower, conflicted, inactive, angel, filler)
    ]

    analysis.outreach_sequence = OutreachSequence(
        phase_1=OutreachPhase(
            phase="PHASE 1 - CALIBRATION",
            objective="Test the narrative and surface objections on replaceable conversations.",
            investors=["[REPLACEABLE PROSPECT]", "[REPLACEABLE PROSPECT]"],
            notes="Approach now. Expect to change materials before phase 2.",
        ),
        phase_2=OutreachPhase(
            phase="PHASE 2 - LEAD CONVERSION",
            objective="Generate partner meetings and a competitive process for the lead.",
            investors=[tier_one.investor_name, tier_two.investor_name],
            notes="Approach once phase 1 objections are answered.",
        ),
        phase_3=OutreachPhase(
            phase="PHASE 3 - SIGNAL LEVERAGE",
            objective="Activate strategics and re-engage followers once lead momentum exists.",
            investors=[strategic.investor_name, follower.investor_name],
            notes="Trigger: a lead in term discussion.",
        ),
        phase_4=OutreachPhase(
            phase="PHASE 4 - ROUND COMPLETION",
            objective="Fill remaining allocation with angels, family offices and syndicates.",
            investors=[angel.investor_name, filler.investor_name],
            notes="Trigger: lead terms agreed.",
        ),
        hold_back=OutreachPhase(
            phase="HOLD BACK",
            objective="Do not approach until lead momentum exists - one shot each.",
            investors=[conflicted.investor_name],
            notes="Cold approaches here spend the best names on an untested pitch.",
        ),
    )

    analysis.gaps_and_risks = [
        Gap(
            gap="[PIPELINE GAP AS A FACT]",
            consequence="[WHAT IT DOES TO THE ROUND]",
            suggested_addition="[CATEGORY TO ADD, OR ACTION]",
            severity="high",
        ),
        Gap(
            gap="[PIPELINE GAP]",
            consequence="[CONSEQUENCE]",
            suggested_addition="[SUGGESTED ADDITION]",
            severity="medium",
        ),
        Gap(
            gap="[PIPELINE GAP]",
            consequence="[CONSEQUENCE]",
            suggested_addition="[SUGGESTED ADDITION]",
            severity="low",
        ),
    ]

    analysis.fallback_structures = [
        FallbackStructure(
            structure="[FALLBACK STRUCTURE]",
            viability="[VIABLE | POSSIBLE | NOT INDICATED]",
            capital_required="[$ CAPITAL REQUIRED]",
            primary_risk="[PRIMARY RISK]",
            milestone_required="[MILESTONE REQUIRED]",
            effect_on_next_round="[EFFECT ON THE NEXT FINANCING]",
            rationale="[WHY THIS PIPELINE INDICATES THIS STRUCTURE]",
        ),
        FallbackStructure(
            structure="[SECOND FALLBACK STRUCTURE]",
            viability="[VIABLE | POSSIBLE | NOT INDICATED]",
            capital_required="[$ CAPITAL REQUIRED]",
            primary_risk="[PRIMARY RISK]",
            milestone_required="[MILESTONE REQUIRED]",
            effect_on_next_round="[EFFECT ON THE NEXT FINANCING]",
            rationale="[RATIONALE]",
        ),
    ]

    analysis.warnings = [
        M.Warning(
            severity="warning",
            stage="[ingestion | extraction | research | analysis | render]",
            message="[PLAIN-LANGUAGE DESCRIPTION OF A DATA PROBLEM THE READER MUST KNOW ABOUT]",
            detail="[SUPPORTING DETAIL, KEPT IN THE JSON]",
        )
    ]

    analysis.metadata = RunMetadata(
        generated_date="[YYYY-MM-DD]",
        llm_provider="[PROVIDER OR 'none (rule-based)']",
        llm_model="[MODEL ID]",
        public_research_enabled=False,
        research_backend="[none | brave | serper]",
        input_files=["[DECK FILENAME]", "[INVESTOR LIST FILENAME]", "[NOTES FILENAME]"],
    )
    analysis.sources = analysis.collect_sources()
    return analysis
