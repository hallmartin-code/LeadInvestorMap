"""Structured response schemas.

Every field an extraction model may fill is optional and defaults to "not found". The
models are told to leave a field null rather than guess, and the schema makes that the
easy path.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExtractedValue(BaseModel):
    """A single extracted value with its location in the source document."""

    value: str | None = Field(
        default=None, description="Verbatim or lightly normalised value. Null if not present."
    )
    page_or_slide: int | None = Field(default=None, description="Page or slide number the value came from.")
    source_text: str = Field(default="", description="The exact sentence or fragment supporting the value.")
    inferred: bool = Field(
        default=False,
        description="True when the value is a reading of the material rather than a stated fact.",
    )


class CompanyExtraction(BaseModel):
    """Company and round facts read from the deck."""

    company_name: ExtractedValue = Field(default_factory=ExtractedValue)
    one_liner: ExtractedValue = Field(default_factory=ExtractedValue)
    sector: ExtractedValue = Field(default_factory=ExtractedValue)
    sub_sector: ExtractedValue = Field(default_factory=ExtractedValue)
    business_model: ExtractedValue = Field(default_factory=ExtractedValue)
    market: ExtractedValue = Field(default_factory=ExtractedValue)
    company_stage: ExtractedValue = Field(default_factory=ExtractedValue)
    location: ExtractedValue = Field(default_factory=ExtractedValue)
    fundraising_status: ExtractedValue = Field(default_factory=ExtractedValue)

    round_stage: ExtractedValue = Field(default_factory=ExtractedValue)
    raise_amount: ExtractedValue = Field(default_factory=ExtractedValue)
    instrument: ExtractedValue = Field(default_factory=ExtractedValue)
    pre_money: ExtractedValue = Field(default_factory=ExtractedValue)
    post_money: ExtractedValue = Field(default_factory=ExtractedValue)
    safe_cap: ExtractedValue = Field(default_factory=ExtractedValue)
    committed: ExtractedValue = Field(default_factory=ExtractedValue)
    circled: ExtractedValue = Field(default_factory=ExtractedValue)
    target_close: ExtractedValue = Field(default_factory=ExtractedValue)
    investor_count: ExtractedValue = Field(default_factory=ExtractedValue)

    traction: list[ExtractedValue] = Field(
        default_factory=list, description="Concrete traction facts stated in the deck."
    )
    key_risks: list[ExtractedValue] = Field(
        default_factory=list, description="Risks the deck itself acknowledges."
    )
    investor_weaknesses: list[ExtractedValue] = Field(
        default_factory=list,
        description="Weaknesses an investor would notice, each tied to deck content.",
    )
    named_competitors: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(
        default_factory=list, description="6-12 terms describing what this company does."
    )
    existing_investors: list[str] = Field(
        default_factory=list, description="Investors already on the cap table per the deck."
    )


class ExtractedLeadHistory(BaseModel):
    company: str
    round_label: str = ""
    role: str = Field(
        default="participated",
        description="Must be one of: led, co-led, priced, board seat, participated. "
        "Use 'participated' unless the source explicitly states a lead role.",
    )
    year: str | None = None
    source_text: str = ""


class ExtractedInvestor(BaseModel):
    """One investor prospect found in the supplied materials."""

    investor_name: str
    aliases: list[str] = Field(default_factory=list)
    investor_type: str | None = Field(
        default=None,
        description="Venture Fund, Micro VC, Growth Fund, Corporate / CVC, Strategic, "
        "Family Office, Angel, Angel Group, Syndicate / SPV, Accelerator, "
        "Government / Grant, Crossover, or null.",
    )
    check_size_text: str | None = Field(
        default=None, description="Cheque size exactly as stated in the source, e.g. '$1-3M'."
    )
    stage_focus: str | None = None
    sector_focus: str | None = None
    leads_rounds_stated: bool | None = Field(
        default=None,
        description="True only when the source explicitly says this investor leads rounds.",
    )
    lead_history: list[ExtractedLeadHistory] = Field(default_factory=list)
    portfolio_companies: list[str] = Field(default_factory=list)
    relationship_text: str | None = Field(
        default=None, description="Relationship or introduction path exactly as described."
    )
    warm_intro_path: str | None = None
    status_text: str | None = Field(default=None, description="Process status as described.")
    fund_status_text: str | None = None
    contact: str | None = None
    stated_dependencies: list[str] = Field(
        default_factory=list,
        description="Conditions the investor themselves stated, e.g. 'wants a lead in place'.",
    )
    committed_amount: str | None = None
    notes: str = ""
    source_page_or_slide: int | None = None
    source_text: str = ""


class InvestorExtraction(BaseModel):
    investors: list[ExtractedInvestor] = Field(default_factory=list)


class GeneratedObjection(BaseModel):
    category: str
    objection: str = Field(description="One or two sentences, specific to this company.")
    evidence: str = Field(description="The deck content that creates this objection.")
    source_ref: str = Field(default="", description="Page or slide reference.")
    severity: str = Field(default="medium", description="high, medium or low.")


class ObjectionExtraction(BaseModel):
    objections: list[GeneratedObjection] = Field(default_factory=list)


class InvestorNarrative(BaseModel):
    """Short narrative lines for one shortlisted lead candidate."""

    investor_name: str
    why_they_can_lead: str = ""
    why_they_fit: str = ""
    key_obstacle: str = ""
    what_must_go_right: str = ""


class NarrativeExtraction(BaseModel):
    narratives: list[InvestorNarrative] = Field(default_factory=list)


class ResearchExtraction(BaseModel):
    """What a research pass concluded about one investor from cited pages."""

    investor_name: str
    leads_rounds: bool | None = None
    lead_history: list[ExtractedLeadHistory] = Field(default_factory=list)
    check_size_text: str | None = None
    stage_focus: str | None = None
    sector_focus: str | None = None
    fund_status_text: str | None = None
    latest_fund: str | None = None
    portfolio_companies: list[str] = Field(default_factory=list)
    claims: list["ResearchClaimOut"] = Field(default_factory=list)


class ResearchClaimOut(BaseModel):
    claim: str
    source_url: str = Field(description="Must be one of the URLs supplied in the prompt.")
    source_title: str = ""
    source_date: str | None = None
    confidence: str = "MEDIUM"


ResearchExtraction.model_rebuild()
