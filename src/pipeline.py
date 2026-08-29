"""End-to-end orchestration: files in, one-page map out.

The order matters. Round parameters come first because the lead requirement is derived
from them and every investor is then judged against that requirement. Extraction is
rule-based with an optional model pass layered on top - never the other way round, so a
missing API key degrades the output rather than emptying it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .analysis.gap_analyzer import analyse_gaps, evaluate_fallbacks
from .analysis.lead_classifier import classify_all
from .analysis.lead_ranker import build_shortlist, rank
from .analysis.momentum_analyzer import (
    apply_next_steps,
    build_momentum_sequence,
    identify_highest_pull,
)
from .analysis.objection_analyzer import (
    add_lead_commitment_objection,
    attach_objections_to_investors,
    generate_objections_rule_based,
)
from .analysis.outreach_sequencer import build_sequence, derive_dependencies
from .extraction.company_extractor import extract_company_rule_based
from .extraction.investor_extractor import extract_investors
from .extraction.llm_extraction import (
    extract_company_and_round,
    extract_investors_llm,
    generate_narratives,
    generate_objections,
)
from .extraction.normalizer import deduplicate
from .extraction.round_extractor import (
    apply_user_overrides,
    extract_round_rule_based,
    merge_round,
)
from .ingestion.loader import InputBundle, load_bundle
from .llm.base import LLMProvider
from .llm.factory import get_provider
from .models.analysis import Disqualification, LeadInvestorMap, RunMetadata
from .models.company import Company
from .models.evidence import Confidence, SourceType
from .models.investor import DiligenceStage, Investor, Relationship, Tier
from .models.round import Round, estimate_lead_requirement
from .notifications.emailer import EmailOutcome, send_analysis_email
from .reporting.csv_exporter import export_csv
from .reporting.json_exporter import export_json, export_sources
from .reporting.pdf_generator import render
from .research.investor_research import run_research
from .utils.config import (
    MIN_TOTAL_CHARS,
    EmailSettings,
    enable_public_research,
    output_dir,
    research_backend,
)
from .utils.logging import get_logger
from .utils.text import squeeze
from .utils.validation import downgrade_unsourced

_log = get_logger()


@dataclass
class PipelineOptions:
    """Everything the caller can vary for one run."""

    deck_path: str | Path | None = None
    supporting_paths: list[str | Path] = field(default_factory=list)
    roles: dict[str, SourceType] = field(default_factory=dict)
    round_overrides: dict = field(default_factory=dict)
    use_llm: bool = True
    provider_name: str | None = None
    public_research: bool | None = None
    output_directory: Path | None = None
    output_stem: str | None = None
    write_csv: bool = True
    send_email: bool = True
    email_to: str | None = None


@dataclass
class PipelineResult:
    analysis: LeadInvestorMap
    pdf_path: Path | None = None
    json_path: Path | None = None
    sources_path: Path | None = None
    csv_path: Path | None = None
    render_dropped: list[str] = field(default_factory=list)
    overflow: float = 0.0
    email: EmailOutcome = field(default_factory=EmailOutcome)


def run(options: PipelineOptions) -> PipelineResult:
    """Read the inputs, build the analysis, write the outputs."""
    analysis = analyse(options)
    return write_outputs(analysis, options)


# --- analysis ------------------------------------------------------------------------------


def analyse(options: PipelineOptions) -> LeadInvestorMap:
    analysis = LeadInvestorMap()
    provider = get_provider(options.provider_name) if options.use_llm else get_provider("local")

    bundle = load_bundle(options.deck_path, options.supporting_paths, options.roles)
    analysis.warnings.extend(bundle.warnings)
    analysis.metadata = RunMetadata(
        llm_provider=provider.name if provider.available else "none (rule-based)",
        llm_model=getattr(provider, "model", ""),
        public_research_enabled=bool(
            options.public_research if options.public_research is not None else enable_public_research()
        ),
        research_backend=research_backend(),
        input_files=bundle.file_names,
    )

    if bundle.deck is None:
        analysis.add_warning(
            "No readable pitch deck was supplied; company and round facts will be mostly NOT PROVIDED.",
            severity="error",
            stage="ingestion",
        )
    elif bundle.deck.total_chars < MIN_TOTAL_CHARS:
        analysis.add_warning(
            f"The deck yielded only {bundle.deck.total_chars} characters of text; it is probably "
            "image-based. Round parameters may be missing.",
            severity="error",
            stage="ingestion",
        )

    company, round_ = _extract_company_and_round(analysis, bundle, provider, options)
    analysis.company = company
    analysis.round = round_
    analysis.lead_requirement = estimate_lead_requirement(round_)

    if not round_.raise_amount.is_known:
        analysis.add_warning(
            "Round size could not be established, so the lead cheque requirement is NOT PROVIDED "
            "and cheque-size fit cannot be tested.",
            severity="warning",
            stage="extraction",
        )

    prospects = _extract_prospects(analysis, bundle, provider)
    analysis.prospects = prospects

    if not prospects:
        analysis.add_warning(
            "No investor prospects were found. Supply a target list, CRM export or investor notes "
            "to get a lead map.",
            severity="error",
            stage="extraction",
        )

    # Optional public research, before classification so it can inform the tiering.
    if analysis.metadata.public_research_enabled and prospects:
        outcome = run_research(prospects, company, provider)
        analysis.warnings.extend(outcome.warnings)
        analysis.metadata.public_research_enabled = outcome.enabled
        for claim in outcome.claims:
            analysis.sources.append(claim.to_source_ref())

    classify_all(prospects, round_, analysis.lead_requirement, company)
    rank(prospects, analysis.lead_requirement)

    has_credible_lead = any(p.tier == Tier.POTENTIAL_LEAD and p.is_active_prospect for p in prospects)
    derive_dependencies(prospects, has_credible_lead)
    apply_next_steps(prospects)

    objections = _objections(analysis, bundle, provider)
    objections = add_lead_commitment_objection(objections, prospects, round_, analysis.lead_requirement)
    analysis.company.objections = objections
    attach_objections_to_investors(prospects, objections)

    narratives = None
    shortlist_preview = build_shortlist(prospects, analysis.lead_requirement, round_, company)
    if provider.available and shortlist_preview:
        narratives = generate_narratives(
            provider, company, round_, [_candidate_context(analysis, e) for e in shortlist_preview]
        )
        if narratives is None:
            analysis.add_warning(
                "Candidate narratives fell back to rule-based text after a model failure.",
                severity="info",
                stage="analysis",
            )
    analysis.lead_shortlist = build_shortlist(
        prospects, analysis.lead_requirement, round_, company, narratives
    )

    analysis.highest_pull_commitment = identify_highest_pull(prospects)
    analysis.momentum_sequence = build_momentum_sequence(prospects, analysis.highest_pull_commitment)
    analysis.disqualified_as_leads = _disqualifications(prospects)
    analysis.outreach_sequence = build_sequence(prospects)
    analysis.gaps_and_risks = analyse_gaps(prospects, round_, analysis.lead_requirement, company)
    analysis.fallback_structures = evaluate_fallbacks(prospects, round_, analysis.lead_requirement)
    analysis.sources.extend(analysis.collect_sources())

    _final_checks(analysis, provider)
    if provider.available:
        analysis.metadata.token_usage = provider.usage.as_dict()
    return analysis


def _extract_company_and_round(
    analysis: LeadInvestorMap, bundle: InputBundle, provider: LLMProvider, options: PipelineOptions
) -> tuple[Company, Round]:
    deck = bundle.deck
    company = extract_company_rule_based(deck)
    round_ = extract_round_rule_based(deck) if deck is not None else Round()

    if deck is not None and provider.available:
        result = extract_company_and_round(provider, deck)
        if result is None:
            analysis.add_warning(
                "The model pass over the deck failed; company and round facts come from "
                "rule-based extraction only.",
                severity="warning",
                stage="extraction",
            )
        else:
            llm_company, llm_round, existing_investors = result
            company = _merge_company(llm_company, company)
            round_ = merge_round(llm_round, round_)
            for name in existing_investors:
                analysis.sources.append(deck.source_ref(None, f"Deck names {name} as an existing investor"))
            company.keywords = company.keywords or extract_company_rule_based(deck).keywords

    if options.round_overrides:
        round_ = apply_user_overrides(round_, options.round_overrides)

    conflicting = [
        name
        for name in ("raise_amount", "committed", "pre_money", "post_money", "safe_cap", "stage")
        if getattr(round_, name).status.value == "CONFLICTING"
    ]
    if conflicting:
        analysis.add_warning(
            f"Conflicting values found for: {', '.join(conflicting)}. Both readings are kept in the "
            "JSON and the field is marked CONFLICTING.",
            severity="warning",
            stage="extraction",
        )
    return company, round_


def _merge_company(primary: Company, secondary: Company) -> Company:
    merged = primary.model_copy(deep=True)
    for field_name in (
        "name",
        "one_liner",
        "sector",
        "sub_sector",
        "business_model",
        "market",
        "stage",
        "location",
        "fundraising_status",
    ):
        if not getattr(merged, field_name).is_known:
            setattr(merged, field_name, getattr(secondary, field_name))
    for field_name in ("traction", "key_risks", "investor_weaknesses"):
        if not getattr(merged, field_name):
            setattr(merged, field_name, getattr(secondary, field_name))
    merged.keywords = merged.keywords or secondary.keywords
    for name in secondary.named_competitors:
        if name not in merged.named_competitors:
            merged.named_competitors.append(name)
    return merged


def _extract_prospects(
    analysis: LeadInvestorMap, bundle: InputBundle, provider: LLMProvider
) -> list[Investor]:
    rule_based, merge_notes = extract_investors(bundle.supporting, bundle.deck)
    for note in merge_notes:
        analysis.add_warning(note, severity="info", stage="extraction")

    combined = list(rule_based)
    text_documents = [d for d in bundle.supporting if d.kind != "spreadsheet"]
    if provider.available and text_documents:
        from_model = extract_investors_llm(provider, text_documents)
        if from_model is None:
            analysis.add_warning(
                "The model pass over supporting documents failed; prospects come from pattern matching only.",
                severity="warning",
                stage="extraction",
            )
        else:
            combined.extend(from_model)

    deduped, notes = deduplicate(combined)
    for note in notes:
        analysis.add_warning(note, severity="info", stage="extraction")

    unnamed = [i for i in deduped if not squeeze(i.investor_name)]
    if unnamed:
        analysis.add_warning(
            f"{len(unnamed)} record(s) had no investor name and were dropped.",
            severity="warning",
            stage="extraction",
        )
    return [i for i in deduped if squeeze(i.investor_name)]


def _objections(analysis: LeadInvestorMap, bundle: InputBundle, provider: LLMProvider):
    company, round_, deck = analysis.company, analysis.round, bundle.deck
    if provider.available and deck is not None:
        generated = generate_objections(provider, company, round_, deck)
        if generated:
            return generated
        analysis.add_warning(
            "Objection generation fell back to rule-based analysis.",
            severity="info",
            stage="analysis",
        )
    return generate_objections_rule_based(company, round_, deck)


def _candidate_context(analysis: LeadInvestorMap, entry) -> dict:
    investor = analysis.prospect(entry.investor_name)
    if investor is None:
        return {"investor_name": entry.investor_name}
    return {
        "investor_name": investor.investor_name,
        "tier": investor.tier.label if investor.tier else "",
        "check_range": investor.check_display(),
        "lead_evidence": investor.lead_history_display(3),
        "leads_rounds_stated": investor.leads_rounds_stated,
        "stage_fit": f"{investor.stage_fit.value} - {investor.stage_fit_detail}",
        "sector_fit": f"{investor.sector_fit.value} - {investor.sector_fit_detail}",
        "portfolio": ", ".join(investor.supporting_portfolio_companies[:5]),
        "fund_status": investor.fund_status.value,
        "relationship": investor.relationship_strength.label,
        "warm_intro_path": investor.warm_intro_path,
        "diligence_stage": investor.current_diligence_stage.value,
        "conflict": investor.conflict_level.value,
        "dependencies": "; ".join(investor.dependencies[:3]),
        "timeline": investor.estimated_time_to_term_sheet,
    }


def _disqualifications(investors: list[Investor]) -> list[Disqualification]:
    """Everyone who must not be treated as a lead, most consequential first."""
    entries: list[Disqualification] = []
    for investor in investors:
        # Tier 1 and 2 appear in the candidate table with their obstacle stated there;
        # listing a shortlisted co-lead as "disqualified" would contradict the page.
        if investor.tier in {Tier.POTENTIAL_LEAD, Tier.CO_LEAD}:
            continue
        if not investor.disqualification_reasons:
            continue
        entries.append(
            Disqualification(
                investor_name=investor.investor_name,
                reasons=investor.disqualification_reasons[:3],
                detail=investor.tier_rationale,
            )
        )

    def priority(entry: Disqualification) -> tuple:
        # Names a founder is most likely to over-rate come first: institutions and
        # strategics before small cheques.
        investor = next((i for i in investors if i.investor_name == entry.investor_name), None)
        tier_value = int(investor.tier) if investor and investor.tier else 9
        relationship = int(investor.relationship_strength) if investor else 0
        return (tier_value, -relationship, entry.investor_name)

    entries.sort(key=priority)
    return entries


def _final_checks(analysis: LeadInvestorMap, provider: LLMProvider) -> None:
    """Enforce the hallucination controls one last time, in code."""
    for fact in (
        analysis.company.name,
        analysis.company.one_liner,
        analysis.company.sector,
        analysis.round.stage,
        analysis.round.raise_amount,
        analysis.round.instrument,
        analysis.round.committed,
        analysis.round.target_close,
    ):
        downgrade_unsourced(fact)

    for investor in analysis.prospects:
        for entry in investor.lead_history:
            if entry.is_lead_evidence and entry.source is None and entry.confidence == Confidence.HIGH:
                entry.confidence = Confidence.LOW
        if investor.warm_intro_verified and not investor.warm_intro_path:
            investor.warm_intro_verified = False
        if (
            investor.relationship_strength >= Relationship.WARM_INTRO_AVAILABLE
            and not investor.warm_intro_path
            and not investor.relationship_detail
        ):
            investor.relationship_strength = Relationship.WEAK_CONNECTION

    unresearched = [
        i.investor_name for i in analysis.prospects if i.estimated_check_max is None and i.is_active_prospect
    ]
    if unresearched:
        analysis.add_warning(
            f"Cheque size is NOT VERIFIED for {len(unresearched)} prospect(s): "
            f"{', '.join(unresearched[:6])}"
            + (f" (+{len(unresearched) - 6})" if len(unresearched) > 6 else ""),
            severity="info",
            stage="analysis",
        )

    if not provider.available:
        analysis.add_warning(
            "No LLM was configured for this run. Extraction was rule-based, so narrative detail is "
            "reduced; nothing was inferred to compensate.",
            severity="info",
            stage="analysis",
        )

    passed = [i for i in analysis.prospects if i.current_diligence_stage == DiligenceStage.PASS]
    if passed:
        analysis.add_warning(
            f"{len(passed)} prospect(s) have passed and are excluded from sequencing: "
            f"{', '.join(i.investor_name for i in passed[:5])}",
            severity="info",
            stage="analysis",
        )


# --- outputs ---------------------------------------------------------------------------------


def write_outputs(analysis: LeadInvestorMap, options: PipelineOptions) -> PipelineResult:
    directory = Path(options.output_directory or output_dir())
    directory.mkdir(parents=True, exist_ok=True)

    stem = options.output_stem or _slug(analysis.company.display_name)
    pdf_path = directory / f"{stem}_lead_investor_map.pdf"
    json_path = directory / f"{stem}_lead_investor_map.json"
    sources_path = directory / f"{stem}_lead_investor_map_sources.json"
    csv_path = directory / f"{stem}_lead_investor_map.csv"

    result = PipelineResult(analysis=analysis)

    try:
        render_result = render(analysis, pdf_path)
        result.pdf_path = render_result.path
        result.render_dropped = render_result.dropped
        result.overflow = render_result.overflow
        if render_result.dropped:
            analysis.add_warning(
                "Content was compressed to keep the map to one page: " + "; ".join(render_result.dropped),
                severity="info",
                stage="render",
            )
    except Exception as exc:  # a render failure must not destroy the analysis
        _log.exception("PDF rendering failed")
        analysis.add_warning(
            f"The PDF could not be rendered: {exc}. The JSON analysis was still written.",
            severity="error",
            stage="render",
        )

    result.sources_path = export_sources(analysis, sources_path)
    if options.write_csv:
        result.csv_path = export_csv(analysis, csv_path)

    # Email before the main JSON is written, so the JSON records what happened to the
    # notification rather than describing a run that had not finished when it was saved.
    result.email = _send_email(analysis, result, options)

    result.json_path = export_json(analysis, json_path)
    return result


def _send_email(analysis: LeadInvestorMap, result: PipelineResult, options: PipelineOptions) -> EmailOutcome:
    """Notify, then record the outcome. A failed send is a warning, never an exception."""
    if not options.send_email:
        return EmailOutcome(skipped="email disabled for this run")

    extras = [path for path in (result.csv_path,) if path]
    settings = EmailSettings.from_env()
    if settings.attach_json and result.sources_path:
        extras.append(result.sources_path)

    outcome = send_analysis_email(
        analysis,
        result.pdf_path,
        to=options.email_to or "",
        config=settings,
        extra_attachments=extras,
    )

    if outcome.sent:
        analysis.add_warning(outcome.summary(), severity="info", stage="email")
    elif outcome.skipped:
        analysis.add_warning(outcome.summary(), severity="info", stage="email")
    else:
        analysis.add_warning(
            f"{outcome.summary()} The analysis and its files were produced normally.",
            severity="warning",
            stage="email",
        )
    return outcome


def _slug(name: str) -> str:
    import re

    slug = re.sub(r"[^A-Za-z0-9]+", "_", squeeze(name)).strip("_")
    return (slug or "company")[:48]
