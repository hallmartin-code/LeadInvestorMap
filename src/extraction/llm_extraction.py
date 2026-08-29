"""The model-assisted half of extraction.

Each function here is a thin, failure-tolerant wrapper: it calls the provider, converts
the validated response into domain objects, and returns ``None`` on any failure so the
caller can fall back to the rule-based result. A model failure degrades the analysis and
adds a warning; it never stops the run and never produces a fabricated value.
"""

from __future__ import annotations

from ..ingestion.types import ParsedDocument
from ..llm.base import LLMFailure, LLMProvider, LLMUnavailable
from ..llm.prompts import (
    COMPANY_PROMPT,
    COMPANY_SYSTEM,
    INVESTOR_PROMPT,
    INVESTOR_SYSTEM,
    NARRATIVE_PROMPT,
    NARRATIVE_SYSTEM,
    OBJECTION_PROMPT,
    OBJECTION_SYSTEM,
    truncate_context,
)
from ..llm.schemas import (
    CompanyExtraction,
    ExtractedInvestor,
    ExtractedValue,
    InvestorExtraction,
    NarrativeExtraction,
    ObjectionExtraction,
)
from ..models.company import Company, Objection
from ..models.evidence import Confidence, EvidenceStatus, Fact, SourceRef
from ..models.investor import (
    DiligenceStage,
    Investor,
    InvestorType,
    LeadHistoryEntry,
    Relationship,
)
from ..models.round import Round
from ..utils.logging import get_logger
from ..utils.money import format_money, parse_money, parse_money_range
from ..utils.text import squeeze, truncate
from .investor_extractor import (
    _classify_fund_status,
    _classify_relationship,
    _classify_status,
    _classify_type,
    _stated_dependencies,
)

_log = get_logger()


def _fact(
    value: ExtractedValue | None, claim: str, document: ParsedDocument, *, numeric: bool = False
) -> Fact:
    """Turn one extracted value into a Fact, preserving its page reference."""
    if (
        value is None
        or not value.value
        or str(value.value).strip().lower()
        in {
            "null",
            "none",
            "n/a",
            "not provided",
            "unknown",
        }
    ):
        return Fact.missing(claim)

    source = SourceRef(
        source_type=document.source_type,
        source_name=document.name,
        page_or_slide=value.page_or_slide,
        source_text=truncate(value.source_text, 400),
    )
    text = squeeze(str(value.value))
    numeric_value = parse_money(text) if numeric else None
    if numeric and numeric_value is not None:
        text = format_money(numeric_value)

    if value.inferred or not value.source_text.strip():
        fact = Fact.inferred(
            claim,
            text,
            "INFERRED from deck content; not stated outright."
            if value.inferred
            else "No supporting quotation was returned; treat as unverified.",
            [source],
        )
        fact.numeric_value = numeric_value
        if not value.inferred:
            fact.status = EvidenceStatus.UNVERIFIED
        return fact

    return Fact.from_document(
        claim,
        text,
        source,
        numeric_value=numeric_value,
        confidence=Confidence.HIGH if value.source_text else Confidence.MEDIUM,
    )


def extract_company_and_round(
    provider: LLMProvider, deck: ParsedDocument
) -> tuple[Company, Round, list[str]] | None:
    """Model pass over the deck. Returns None when the provider cannot be used."""
    if not provider.available:
        return None
    try:
        result = provider.analyze(
            COMPANY_SYSTEM,
            COMPANY_PROMPT.format(deck_text=truncate_context(deck.text)),
            CompanyExtraction,
            max_tokens=8000,
        )
    except (LLMUnavailable, LLMFailure) as exc:
        _log.warning("company extraction failed: %s", exc)
        return None

    company = Company(
        name=_fact(result.company_name, "Company name", deck),
        one_liner=_fact(result.one_liner, "Company one-liner", deck),
        sector=_fact(result.sector, "Sector", deck),
        sub_sector=_fact(result.sub_sector, "Sub-sector", deck),
        business_model=_fact(result.business_model, "Business model", deck),
        market=_fact(result.market, "Market", deck),
        stage=_fact(result.company_stage, "Company stage", deck),
        location=_fact(result.location, "Location", deck),
        fundraising_status=_fact(result.fundraising_status, "Fundraising status", deck),
        keywords=[squeeze(k) for k in result.keywords if squeeze(k)],
        named_competitors=[squeeze(c) for c in result.named_competitors if squeeze(c)],
    )
    company.traction = [_fact(v, "Traction", deck) for v in result.traction if v.value]
    company.key_risks = [_fact(v, "Stated risk", deck) for v in result.key_risks if v.value]
    company.investor_weaknesses = [
        _fact(v, "Investor-visible weakness", deck) for v in result.investor_weaknesses if v.value
    ]

    round_ = Round(
        stage=_fact(result.round_stage, "Round stage", deck),
        raise_amount=_fact(result.raise_amount, "Round size", deck, numeric=True),
        instrument=_fact(result.instrument, "Instrument", deck),
        pre_money=_fact(result.pre_money, "Pre-money valuation", deck, numeric=True),
        post_money=_fact(result.post_money, "Post-money valuation", deck, numeric=True),
        safe_cap=_fact(result.safe_cap, "Valuation cap", deck, numeric=True),
        committed=_fact(result.committed, "Amount committed", deck, numeric=True),
        circled=_fact(result.circled, "Amount circled", deck, numeric=True),
        target_close=_fact(result.target_close, "Target close", deck),
        investor_count=_fact(result.investor_count, "Investor count", deck),
    )

    return company, round_, [squeeze(n) for n in result.existing_investors if squeeze(n)]


def extract_investors_llm(provider: LLMProvider, documents: list[ParsedDocument]) -> list[Investor] | None:
    """Model pass over supporting material. Returns None when unusable."""
    if not provider.available or not documents:
        return None

    blocks = []
    for document in documents:
        blocks.append(f"### FILE: {document.name} ({document.source_type.value})\n{document.text}")
    material = truncate_context("\n\n".join(blocks))
    if not material.strip():
        return None

    try:
        result = provider.analyze(
            INVESTOR_SYSTEM,
            INVESTOR_PROMPT.format(material_text=material),
            InvestorExtraction,
            max_tokens=12000,
        )
    except (LLMUnavailable, LLMFailure) as exc:
        _log.warning("investor extraction failed: %s", exc)
        return None

    by_name = {d.name: d for d in documents}
    investors: list[Investor] = []
    for extracted in result.investors:
        investor = _investor_from_extraction(extracted, documents, by_name)
        if investor is not None:
            investors.append(investor)
    return investors


def _investor_from_extraction(
    extracted: ExtractedInvestor, documents: list[ParsedDocument], by_name: dict
) -> Investor | None:
    name = squeeze(extracted.investor_name)
    if not name:
        return None

    document = documents[0]
    source = SourceRef(
        source_type=document.source_type,
        source_name=document.name,
        page_or_slide=extracted.source_page_or_slide,
        source_text=truncate(extracted.source_text, 400),
    )

    investor = Investor(investor_name=name, confidence=Confidence.MEDIUM)
    investor.aliases = [squeeze(a) for a in extracted.aliases if squeeze(a)]
    investor.add_source(source)

    if extracted.investor_type:
        try:
            investor.investor_type = InvestorType(extracted.investor_type)
        except ValueError:
            investor.investor_type = _classify_type(f"{extracted.investor_type} {name}")
    else:
        investor.investor_type = _classify_type(f"{extracted.notes} {name}")

    if extracted.check_size_text:
        low, high = parse_money_range(extracted.check_size_text)
        if low is not None or high is not None:
            investor.estimated_check_min = low
            investor.estimated_check_max = high or low
            investor.check_size_status = EvidenceStatus.UNVERIFIED
            investor.check_size_confidence = Confidence.MEDIUM

    if extracted.stage_focus:
        investor.entry_stages = [s.strip() for s in extracted.stage_focus.split(",") if s.strip()]
        investor.stage_fit_detail = f"Stated focus: {squeeze(extracted.stage_focus)}"
    if extracted.sector_focus:
        investor.sector_fit_detail = f"Stated focus: {squeeze(extracted.sector_focus)}"

    investor.leads_rounds_stated = extracted.leads_rounds_stated
    for entry in extracted.lead_history:
        investor.lead_history.append(
            LeadHistoryEntry(
                company=squeeze(entry.company) or "unnamed company",
                round_label=squeeze(entry.round_label),
                role=squeeze(entry.role) or "participated",
                year=entry.year,
                source=SourceRef(
                    source_type=source.source_type,
                    source_name=source.source_name,
                    page_or_slide=extracted.source_page_or_slide,
                    source_text=truncate(entry.source_text or extracted.source_text, 300),
                ),
                confidence=Confidence.MEDIUM,
            )
        )

    investor.supporting_portfolio_companies = [
        squeeze(p) for p in extracted.portfolio_companies if squeeze(p)
    ]

    if extracted.relationship_text:
        level, detail = _classify_relationship(extracted.relationship_text)
        investor.relationship_strength = level
        investor.relationship_detail = detail or squeeze(extracted.relationship_text)[:160]
    if extracted.warm_intro_path:
        investor.warm_intro_path = squeeze(extracted.warm_intro_path)
        investor.warm_intro_verified = True
        if investor.relationship_strength < Relationship.WARM_INTRO_AVAILABLE:
            investor.relationship_strength = Relationship.WARM_INTRO_AVAILABLE

    if extracted.status_text:
        investor.current_diligence_stage = _classify_status(extracted.status_text)
        if investor.current_diligence_stage == DiligenceStage.COLD and extracted.relationship_text:
            investor.current_diligence_stage = _classify_status(extracted.relationship_text)

    if extracted.fund_status_text:
        investor.fund_status = _classify_fund_status(extracted.fund_status_text)
        investor.deployment_status = investor.fund_status.value

    if extracted.contact:
        investor.decision_champion = squeeze(extracted.contact)
    if extracted.committed_amount:
        investor.amount_committed = parse_money(extracted.committed_amount)

    investor.stated_dependencies = [squeeze(d) for d in extracted.stated_dependencies if squeeze(d)]
    if extracted.notes:
        investor.notes = truncate(extracted.notes, 300)
        for dependency in _stated_dependencies(extracted.notes):
            if dependency not in investor.stated_dependencies:
                investor.stated_dependencies.append(dependency)

    return investor


def generate_objections(
    provider: LLMProvider, company: Company, round_: Round, deck: ParsedDocument
) -> list[Objection] | None:
    if not provider.available:
        return None
    company_context = "\n".join(
        [
            f"Name: {company.name.display()}",
            f"One-liner: {company.one_liner.display()}",
            f"Sector: {company.sector.display()}",
            f"Business model: {company.business_model.display()}",
            "Traction: " + ("; ".join(f.display() for f in company.traction[:8]) or "NOT PROVIDED"),
            "Stated risks: " + ("; ".join(f.display() for f in company.key_risks[:6]) or "NOT PROVIDED"),
        ]
    )
    round_context = "\n".join(
        [
            f"Stage: {round_.stage.display()}",
            f"Raise: {round_.raise_amount.display()}",
            f"Instrument: {round_.instrument.display()}",
            f"Valuation: {round_.valuation_display}",
            f"Committed: {round_.committed.display()}",
            f"Target close: {round_.target_close.display()}",
        ]
    )
    try:
        result = provider.analyze(
            OBJECTION_SYSTEM,
            OBJECTION_PROMPT.format(
                company_context=company_context,
                round_context=round_context,
                deck_text=truncate_context(deck.text, 60_000),
            ),
            ObjectionExtraction,
            max_tokens=4000,
        )
    except (LLMUnavailable, LLMFailure) as exc:
        _log.warning("objection generation failed: %s", exc)
        return None

    objections = [
        Objection(
            category=squeeze(o.category),
            objection=squeeze(o.objection),
            evidence=squeeze(o.evidence),
            source_ref=squeeze(o.source_ref),
            severity=(o.severity or "medium").lower(),
        )
        for o in result.objections
        if squeeze(o.objection)
    ]
    # An objection with no evidence is boilerplate; drop it rather than print it.
    return [o for o in objections if o.is_grounded]


def generate_narratives(
    provider: LLMProvider, company: Company, round_: Round, candidates: list[dict]
) -> dict[str, dict] | None:
    if not provider.available or not candidates:
        return None

    lines = []
    for candidate in candidates:
        lines.append(
            "\n".join(f"{key}: {value}" for key, value in candidate.items() if value not in (None, "", []))
        )
    company_context = (
        f"{company.name.display()} - {company.one_liner.display()} (sector: {company.sector.display()})"
    )
    round_context = (
        f"{round_.stage.display()} / {round_.raise_amount.display()} / "
        f"{round_.instrument.display()} / committed {round_.committed.display()}"
    )
    try:
        result = provider.analyze(
            NARRATIVE_SYSTEM,
            NARRATIVE_PROMPT.format(
                company_context=company_context,
                round_context=round_context,
                candidates="\n\n---\n\n".join(lines),
            ),
            NarrativeExtraction,
            max_tokens=3000,
        )
    except (LLMUnavailable, LLMFailure) as exc:
        _log.warning("narrative generation failed: %s", exc)
        return None

    return {
        squeeze(n.investor_name).lower(): {
            "why_they_can_lead": squeeze(n.why_they_can_lead),
            "why_they_fit": squeeze(n.why_they_fit),
            "key_obstacle": squeeze(n.key_obstacle),
            "what_must_go_right": squeeze(n.what_must_go_right),
        }
        for n in result.narratives
    }
