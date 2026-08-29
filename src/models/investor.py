"""The normalised investor record.

One object per prospect, whatever it was assembled from - a CRM export row, a line in a
target list, a paragraph of meeting notes, or public research. Everything that could
influence the tier decision is stored here alongside the evidence for it.
"""

from __future__ import annotations

from enum import Enum, IntEnum
from typing import ClassVar

from pydantic import BaseModel, Field

from ..utils.money import format_money_range
from .evidence import Confidence, EvidenceStatus, Fact, SourceRef


class InvestorType(str, Enum):
    VC = "Venture Fund"
    MICRO_VC = "Micro VC"
    GROWTH = "Growth Fund"
    CORPORATE = "Corporate / CVC"
    STRATEGIC = "Strategic"
    FAMILY_OFFICE = "Family Office"
    ANGEL = "Angel"
    ANGEL_GROUP = "Angel Group"
    SYNDICATE = "Syndicate / SPV"
    ACCELERATOR = "Accelerator"
    GOVERNMENT = "Government / Grant"
    CROSSOVER = "Crossover"
    UNKNOWN = "Unknown"

    @property
    def is_institutional(self) -> bool:
        return self in {
            InvestorType.VC,
            InvestorType.MICRO_VC,
            InvestorType.GROWTH,
            InvestorType.CROSSOVER,
        }

    @property
    def is_strategic(self) -> bool:
        return self in {InvestorType.CORPORATE, InvestorType.STRATEGIC}

    @property
    def is_individual_or_pooled(self) -> bool:
        return self in {
            InvestorType.ANGEL,
            InvestorType.ANGEL_GROUP,
            InvestorType.FAMILY_OFFICE,
            InvestorType.SYNDICATE,
        }


class Tier(IntEnum):
    POTENTIAL_LEAD = 1
    CO_LEAD = 2
    STRATEGIC_VALIDATOR = 3
    FOLLOW_ON = 4
    ANGEL_FAMILY_SYNDICATE = 5
    FILL_THE_ROUND = 6

    @property
    def label(self) -> str:
        return {
            1: "POTENTIAL LEAD",
            2: "CO-LEAD / PARTIAL",
            3: "STRATEGIC VALIDATOR",
            4: "FOLLOW-ON",
            5: "ANGEL / FO / SYNDICATE",
            6: "FILL THE ROUND",
        }[int(self)]

    @property
    def short_label(self) -> str:
        return {
            1: "T1 LEAD",
            2: "T2 CO-LEAD",
            3: "T3 STRATEGIC",
            4: "T4 FOLLOW",
            5: "T5 ANGEL/FO",
            6: "T6 FILL",
        }[int(self)]


class Relationship(IntEnum):
    COLD = 0
    WEAK_CONNECTION = 1
    WARM_INTRO_AVAILABLE = 2
    INTRO_MADE = 3
    FIRST_MEETING = 4
    PARTNER_ENGAGEMENT = 5
    ACTIVE_DILIGENCE = 6
    VERBAL_INTEREST = 7
    VERBAL_COMMITMENT = 8
    COMMITTED = 9

    @property
    def label(self) -> str:
        return {
            0: "COLD",
            1: "WEAK CONNECTION",
            2: "WARM INTRO AVAILABLE",
            3: "INTRO MADE",
            4: "FIRST MEETING",
            5: "PARTNER ENGAGEMENT",
            6: "ACTIVE DILIGENCE",
            7: "VERBAL INTEREST",
            8: "VERBAL COMMITMENT",
            9: "COMMITTED",
        }[int(self)]

    @property
    def short_label(self) -> str:
        return {
            0: "COLD",
            1: "WEAK",
            2: "INTRO AVAIL",
            3: "INTRO MADE",
            4: "MEETING",
            5: "PARTNER",
            6: "DD",
            7: "VERBAL INT",
            8: "VERBAL",
            9: "COMMITTED",
        }[int(self)]


class DiligenceStage(str, Enum):
    COLD = "COLD"
    INTRO_AVAILABLE = "INTRO AVAILABLE"
    INTRO_MADE = "INTRO MADE"
    FIRST_MEETING = "FIRST MEETING"
    FOLLOW_UP = "FOLLOW-UP"
    PARTNER_MEETING = "PARTNER MEETING"
    DILIGENCE = "DILIGENCE"
    TERM_DISCUSSION = "TERM DISCUSSION"
    VERBAL = "VERBAL"
    COMMITTED = "COMMITTED"
    PASS = "PASS"


class FundStatus(str, Enum):
    ACTIVE = "ACTIVE"
    LIKELY_ACTIVE = "LIKELY ACTIVE"
    SLOW_DEPLOYMENT = "SLOW DEPLOYMENT"
    BETWEEN_FUNDS = "BETWEEN FUNDS"
    FOLLOW_ON_ONLY = "FOLLOW-ON ONLY"
    INACTIVE = "INACTIVE"
    UNKNOWN = "UNKNOWN"

    @property
    def is_deploying(self) -> bool:
        return self in {FundStatus.ACTIVE, FundStatus.LIKELY_ACTIVE}


class ConflictLevel(str, Enum):
    NONE = "NONE IDENTIFIED"
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


class Fit(str, Enum):
    STRONG = "STRONG"
    PARTIAL = "PARTIAL"
    WEAK = "WEAK"
    MISMATCH = "MISMATCH"
    UNKNOWN = "UNKNOWN"


class SignalValue(str, Enum):
    VERY_HIGH = "VERY HIGH"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class LeadConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NOT_A_LEAD = "NOT A LEAD"


class DisqualificationReason(str, Enum):
    NO_VERIFIED_LEAD_HISTORY = "NO VERIFIED LEAD HISTORY"
    CHECK_TOO_SMALL = "CHECK TOO SMALL"
    REQUIRES_EXISTING_LEAD = "REQUIRES EXISTING LEAD"
    WRONG_STAGE = "WRONG STAGE"
    WRONG_SECTOR = "WRONG SECTOR"
    PORTFOLIO_CONFLICT = "PORTFOLIO CONFLICT"
    INACTIVE_FUND = "INACTIVE FUND"
    BETWEEN_FUNDS = "BETWEEN FUNDS"
    TIMELINE_TOO_LONG = "TIMELINE TOO LONG"
    RELATIONSHIP_TOO_COLD = "RELATIONSHIP TOO COLD"
    STRATEGIC_ONLY = "STRATEGIC ONLY"
    FOLLOW_ON_ONLY = "FOLLOW-ON ONLY"
    PASSED = "PASSED ON THE ROUND"


class LeadHistoryEntry(BaseModel):
    """A named instance of this investor leading or co-leading a round.

    Participation is not lead history. ``role`` must be an explicit lead signal for this
    entry to count toward the lead test.
    """

    company: str
    round_label: str = ""
    role: str = "participated"  # led | co-led | priced | board seat | participated
    year: str | None = None
    source: SourceRef | None = None
    confidence: Confidence = Confidence.LOW

    LEAD_ROLES: ClassVar[tuple[str, ...]] = (
        "led",
        "co-led",
        "coled",
        "priced",
        "lead investor",
        "board seat",
    )

    @property
    def is_lead_evidence(self) -> bool:
        role = (self.role or "").strip().lower()
        return any(token in role for token in self.LEAD_ROLES)

    def display(self) -> str:
        parts = [self.company]
        if self.round_label:
            parts.append(self.round_label)
        parts.append(self.role)
        if self.year:
            parts.append(str(self.year))
        return " - ".join(parts)


class PortfolioConflict(BaseModel):
    company: str
    level: ConflictLevel = ConflictLevel.UNKNOWN
    rationale: str = ""
    source: SourceRef | None = None


class QualificationResult(BaseModel):
    """The ten-point lead test. Each criterion is PASS / FAIL / UNKNOWN with a reason."""

    criterion: str
    verdict: str  # PASS | FAIL | UNKNOWN
    detail: str = ""


class Investor(BaseModel):
    investor_name: str
    aliases: list[str] = Field(default_factory=list)
    investor_type: InvestorType = InvestorType.UNKNOWN
    tier: Tier | None = None
    tier_rationale: str = ""

    # -- cheque size ------------------------------------------------------------------
    estimated_check_min: float | None = None
    estimated_check_max: float | None = None
    typical_initial_check: float | None = None
    check_size_status: EvidenceStatus = EvidenceStatus.NOT_PROVIDED
    check_size_confidence: Confidence = Confidence.INSUFFICIENT
    can_write_full_lead_check: bool | None = None

    # -- lead behaviour ---------------------------------------------------------------
    lead_history: list[LeadHistoryEntry] = Field(default_factory=list)
    lead_history_confidence: Confidence = Confidence.INSUFFICIENT
    leads_rounds_stated: bool | None = None

    # -- fit --------------------------------------------------------------------------
    stage_fit: Fit = Fit.UNKNOWN
    stage_fit_detail: str = ""
    entry_stages: list[str] = Field(default_factory=list)
    sector_fit: Fit = Fit.UNKNOWN
    sector_fit_detail: str = ""
    supporting_portfolio_companies: list[str] = Field(default_factory=list)

    # -- conflict ---------------------------------------------------------------------
    portfolio_conflicts: list[PortfolioConflict] = Field(default_factory=list)
    conflict_level: ConflictLevel = ConflictLevel.UNKNOWN

    # -- fund status ------------------------------------------------------------------
    fund_vintage: str | None = None
    fund_size: float | None = None
    fund_status: FundStatus = FundStatus.UNKNOWN
    deployment_status: str = "UNKNOWN"
    recent_deal_pace: str = "UNKNOWN"

    # -- relationship -----------------------------------------------------------------
    relationship_strength: Relationship = Relationship.COLD
    relationship_detail: str = ""
    warm_intro_path: str | None = None
    warm_intro_verified: bool = False

    # -- process ----------------------------------------------------------------------
    current_diligence_stage: DiligenceStage = DiligenceStage.COLD
    decision_champion: str | None = None
    partner_meeting_cadence: str | None = None
    investment_committee: str | None = None
    estimated_time_to_term_sheet: str | None = None
    timeline_compatible: bool | None = None

    # -- influence --------------------------------------------------------------------
    signal_value: SignalValue = SignalValue.UNKNOWN
    signal_rationale: str = ""
    investors_influenced: list[str] = Field(default_factory=list)

    # -- terms ------------------------------------------------------------------------
    ownership_expectation: str | None = None
    board_expectation: str | None = None
    pro_rata_expectation: str | None = None
    governance_expectation: str | None = None

    # -- deal-specific ----------------------------------------------------------------
    likely_objections: list[str] = Field(default_factory=list)
    required_next_step: str = ""
    next_step_owner: str = ""
    dependencies: list[str] = Field(default_factory=list)
    stated_dependencies: list[str] = Field(default_factory=list)

    # -- scoring ----------------------------------------------------------------------
    lead_score: float | None = None
    lead_score_breakdown: dict = Field(default_factory=dict)
    lead_confidence: LeadConfidence = LeadConfidence.NOT_A_LEAD
    qualification: list[QualificationResult] = Field(default_factory=list)
    disqualification_reasons: list[DisqualificationReason] = Field(default_factory=list)
    disqualification_detail: str = ""

    # -- provenance -------------------------------------------------------------------
    sources: list[SourceRef] = Field(default_factory=list)
    research_claims: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.LOW
    notes: str = ""
    amount_committed: float | None = None
    amount_circled: float | None = None

    # -- derived ----------------------------------------------------------------------

    @property
    def has_verified_lead_history(self) -> bool:
        return any(entry.is_lead_evidence for entry in self.lead_history)

    @property
    def lead_evidence_entries(self) -> list[LeadHistoryEntry]:
        return [e for e in self.lead_history if e.is_lead_evidence]

    def lead_history_display(self, limit: int = 2) -> str:
        entries = self.lead_evidence_entries[:limit]
        if not entries:
            return "NOT VERIFIED"
        return "; ".join(e.display() for e in entries)

    def check_display(self) -> str:
        return format_money_range(self.estimated_check_min, self.estimated_check_max)

    def fit_display(self) -> str:
        return f"Stg {self.stage_fit.value[:4]} / Sec {self.sector_fit.value[:4]}"

    @property
    def is_active_prospect(self) -> bool:
        return self.current_diligence_stage != DiligenceStage.PASS

    @property
    def key_dependency(self) -> str:
        if self.dependencies:
            return self.dependencies[0]
        if self.stated_dependencies:
            return self.stated_dependencies[0]
        return "None identified"

    def add_source(self, source: SourceRef) -> None:
        signature = (
            source.source_type,
            source.source_name,
            source.page_or_slide,
            source.source_url,
        )
        for existing in self.sources:
            if (
                existing.source_type,
                existing.source_name,
                existing.page_or_slide,
                existing.source_url,
            ) == signature:
                return
        self.sources.append(source)


class InvestorFactSheet(BaseModel):
    """Optional per-investor fact bundle kept out of the one-pager but stored in JSON."""

    investor_name: str
    facts: list[Fact] = Field(default_factory=list)
