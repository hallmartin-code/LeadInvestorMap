"""The complete analysis object - the thing that is serialised to JSON and rendered."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..utils.dates import iso_today
from .company import Company
from .evidence import SourceRef, Warning
from .investor import DisqualificationReason, Investor, LeadConfidence
from .round import LeadRequirement, Round


class ShortlistEntry(BaseModel):
    """One shortlisted lead candidate, with the case for and against."""

    rank: int
    investor_name: str
    lead_confidence: LeadConfidence
    check_display: str
    why_they_can_lead: str
    why_they_fit: str
    key_obstacle: str
    what_must_go_right: str
    required_next_step: str
    next_step_owner: str
    relationship: str
    lead_evidence: str
    score: float | None = None


class Disqualification(BaseModel):
    investor_name: str
    reasons: list[DisqualificationReason] = Field(default_factory=list)
    detail: str = ""

    def display(self) -> str:
        reason = ", ".join(r.value for r in self.reasons) if self.reasons else "NOT A LEAD"
        return f"{self.investor_name} - {reason}"


class MomentumStep(BaseModel):
    step: int
    investor_name: str
    event: str
    effect: str
    basis: str = ""


class HighestPullCommitment(BaseModel):
    investor_name: str | None = None
    rationale: str = ""
    downstream_investors: list[str] = Field(default_factory=list)
    confidence: str = "LOW"


class OutreachPhase(BaseModel):
    phase: str
    objective: str
    investors: list[str] = Field(default_factory=list)
    notes: str = ""


class OutreachSequence(BaseModel):
    phase_1: OutreachPhase
    phase_2: OutreachPhase
    phase_3: OutreachPhase
    phase_4: OutreachPhase
    hold_back: OutreachPhase


class Gap(BaseModel):
    gap: str
    consequence: str
    suggested_addition: str = ""
    severity: str = "medium"  # high | medium | low


class FallbackStructure(BaseModel):
    structure: str
    viability: str  # VIABLE | POSSIBLE | NOT INDICATED
    capital_required: str
    primary_risk: str
    milestone_required: str
    effect_on_next_round: str
    rationale: str = ""


class RunMetadata(BaseModel):
    generated_date: str = Field(default_factory=iso_today)
    llm_provider: str = "none"
    llm_model: str = ""
    public_research_enabled: bool = False
    research_backend: str = "none"
    input_files: list[str] = Field(default_factory=list)
    token_usage: dict = Field(default_factory=dict)
    app_version: str = "1.0.0"


class LeadInvestorMap(BaseModel):
    """Top-level analysis object (section 39 of the specification)."""

    company: Company = Field(default_factory=Company)
    round: Round = Field(default_factory=Round)
    lead_requirement: LeadRequirement = Field(default_factory=LeadRequirement)
    prospects: list[Investor] = Field(default_factory=list)
    lead_shortlist: list[ShortlistEntry] = Field(default_factory=list)
    highest_pull_commitment: HighestPullCommitment = Field(default_factory=HighestPullCommitment)
    momentum_sequence: list[MomentumStep] = Field(default_factory=list)
    disqualified_as_leads: list[Disqualification] = Field(default_factory=list)
    outreach_sequence: OutreachSequence | None = None
    gaps_and_risks: list[Gap] = Field(default_factory=list)
    fallback_structures: list[FallbackStructure] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)
    warnings: list[Warning] = Field(default_factory=list)
    metadata: RunMetadata = Field(default_factory=RunMetadata)

    # -- helpers ---------------------------------------------------------------------

    def prospect(self, name: str) -> Investor | None:
        low = name.strip().lower()
        for investor in self.prospects:
            if investor.investor_name.strip().lower() == low:
                return investor
        return None

    def by_tier(self, tier: int) -> list[Investor]:
        return [p for p in self.prospects if p.tier is not None and int(p.tier) == tier]

    def add_warning(
        self, message: str, *, severity: str = "warning", stage: str = "", detail: str | None = None
    ) -> None:
        self.warnings.append(Warning(message=message, severity=severity, stage=stage, detail=detail))

    def collect_sources(self) -> list[SourceRef]:
        """Every distinct source behind the analysis, for the companion sources file."""
        collected: list[SourceRef] = []
        seen: set[tuple] = set()

        def add(source: SourceRef) -> None:
            key = (
                source.source_type,
                source.source_name,
                source.page_or_slide,
                source.source_url,
                source.source_text[:80],
            )
            if key not in seen:
                seen.add(key)
                collected.append(source)

        for fact in (
            self.company.name,
            self.company.one_liner,
            self.company.sector,
            self.company.sub_sector,
            self.company.business_model,
            self.company.market,
            self.company.stage,
            self.company.location,
            self.company.fundraising_status,
            self.round.stage,
            self.round.raise_amount,
            self.round.instrument,
            self.round.pre_money,
            self.round.post_money,
            self.round.safe_cap,
            self.round.committed,
            self.round.circled,
            self.round.target_close,
            self.round.investor_count,
        ):
            for source in fact.sources:
                add(source)
        for group in (
            self.company.traction,
            self.company.key_risks,
            self.company.investor_weaknesses,
        ):
            for fact in group:
                for source in fact.sources:
                    add(source)
        for investor in self.prospects:
            for source in investor.sources:
                add(source)
            for entry in investor.lead_history:
                if entry.source:
                    add(entry.source)
            for conflict in investor.portfolio_conflicts:
                if conflict.source:
                    add(conflict.source)
        for source in self.sources:
            add(source)
        return collected
