"""Optional public investor research.

Off by default. When on, it needs both a search backend and an LLM: the backend supplies
real pages, and the model reads them. Without a backend nothing is fetched and the run
says so - it never falls back to the model's own recollection, which is exactly the
failure this application exists to avoid.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..llm.base import LLMFailure, LLMProvider, LLMUnavailable
from ..llm.prompts import RESEARCH_PROMPT, RESEARCH_SYSTEM
from ..llm.schemas import ResearchExtraction
from ..models.company import Company
from ..models.evidence import Confidence, EvidenceStatus, ResearchClaim, Warning
from ..models.investor import FundStatus, Investor, LeadHistoryEntry
from ..utils.config import (
    brave_key,
    enable_public_research,
    research_backend,
    research_max_queries,
    research_timeout,
    serper_key,
)
from ..utils.dates import iso_today
from ..utils.logging import get_logger
from ..utils.money import parse_money_range
from ..utils.text import squeeze, truncate
from .freshness import apply_freshness
from .source_validator import detect_conflicts, source_rank, validate_claims

_log = get_logger()


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    published: str | None = None


@dataclass
class ResearchOutcome:
    enabled: bool = False
    backend: str = "none"
    claims: list[ResearchClaim] = field(default_factory=list)
    warnings: list[Warning] = field(default_factory=list)
    researched: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)


# --- search backends -----------------------------------------------------------------------


def _search_brave(query: str, limit: int = 6) -> list[SearchResult]:
    import requests

    response = requests.get(
        "https://api.search.brave.com/res/v1/web/search",
        headers={"Accept": "application/json", "X-Subscription-Token": brave_key() or ""},
        params={"q": query, "count": limit},
        timeout=research_timeout(),
    )
    response.raise_for_status()
    payload = response.json()
    results = []
    for item in (payload.get("web", {}) or {}).get("results", [])[:limit]:
        results.append(
            SearchResult(
                title=squeeze(item.get("title", "")),
                url=item.get("url", ""),
                snippet=squeeze(item.get("description", "")),
                published=item.get("age") or item.get("page_age"),
            )
        )
    return results


def _search_serper(query: str, limit: int = 6) -> list[SearchResult]:
    import requests

    response = requests.post(
        "https://google.serper.dev/search",
        headers={"X-API-KEY": serper_key() or "", "Content-Type": "application/json"},
        json={"q": query, "num": limit},
        timeout=research_timeout(),
    )
    response.raise_for_status()
    payload = response.json()
    results = []
    for item in payload.get("organic", [])[:limit]:
        results.append(
            SearchResult(
                title=squeeze(item.get("title", "")),
                url=item.get("link", ""),
                snippet=squeeze(item.get("snippet", "")),
                published=item.get("date"),
            )
        )
    return results


def search(query: str, limit: int = 6) -> list[SearchResult]:
    backend = research_backend()
    if backend == "brave" and brave_key():
        return _search_brave(query, limit)
    if backend == "serper" and serper_key():
        return _search_serper(query, limit)
    return []


def backend_available() -> tuple[bool, str]:
    backend = research_backend()
    if backend == "brave":
        return (bool(brave_key()), "brave")
    if backend == "serper":
        return (bool(serper_key()), "serper")
    return (False, backend)


# --- research ------------------------------------------------------------------------------


def queries_for(investor: Investor, company: Company) -> list[str]:
    name = investor.investor_name
    sector = company.sector.value or ""
    candidates = [
        f'"{name}" led Series A OR "led the round" investment',
        f'"{name}" fund size new fund close',
        f'"{name}" check size initial investment {sector}'.strip(),
        f'"{name}" portfolio {sector}'.strip(),
    ]
    return candidates[: research_max_queries()]


def research_investor(
    investor: Investor, company: Company, provider: LLMProvider
) -> tuple[list[ResearchClaim], list[str]]:
    """Search, then have the model read only what the search actually returned."""
    results: list[SearchResult] = []
    for query in queries_for(investor, company):
        try:
            results.extend(search(query))
        except Exception as exc:
            _log.warning("search failed for %s: %s", investor.investor_name, exc)

    # De-duplicate by URL, best sources first, and cap the context.
    unique: dict[str, SearchResult] = {}
    for result in results:
        if result.url and result.url not in unique:
            unique[result.url] = result
    ordered = sorted(unique.values(), key=lambda r: source_rank(r.url, investor.investor_name))[:10]
    if not ordered:
        return [], [f"No search results returned for {investor.investor_name}."]

    sources_block = "\n\n".join(
        f"URL: {r.url}\nTITLE: {r.title}\nDATE: {r.published or 'unknown'}\nSNIPPET: {r.snippet}"
        for r in ordered
    )
    context = f"{company.name.display()} - {company.one_liner.display()} ({company.sector.display()})"

    try:
        extraction = provider.analyze(
            RESEARCH_SYSTEM,
            RESEARCH_PROMPT.format(
                investor_name=investor.investor_name,
                company_context=context,
                sources=sources_block,
            ),
            ResearchExtraction,
            max_tokens=4000,
        )
    except (LLMUnavailable, LLMFailure) as exc:
        return [], [f"Research read failed for {investor.investor_name}: {exc}"]

    claims = [
        ResearchClaim(
            claim=squeeze(c.claim),
            investor_name=investor.investor_name,
            source_url=c.source_url,
            source_title=squeeze(c.source_title),
            source_date=c.source_date,
            accessed_date=iso_today(),
            confidence=_confidence(c.confidence),
        )
        for c in extraction.claims
        if squeeze(c.claim)
    ]

    kept, rejected = validate_claims(claims, {r.url for r in ordered}, investor.investor_name)
    notes = apply_freshness(kept)
    conflicts = detect_conflicts(kept)

    _apply_extraction(investor, extraction, kept)

    return kept, rejected + notes + conflicts


def _confidence(raw: str) -> Confidence:
    try:
        return Confidence(str(raw).strip().upper())
    except ValueError:
        return Confidence.MEDIUM


def _apply_extraction(
    investor: Investor, extraction: ResearchExtraction, claims: list[ResearchClaim]
) -> None:
    """Fold validated research into the investor record, never overwriting stronger evidence."""
    if not claims:
        return

    sources = [c.to_source_ref() for c in claims]
    for source in sources[:4]:
        investor.add_source(source)
    investor.research_claims.extend(truncate(c.claim, 180) for c in claims[:6])

    for entry in extraction.lead_history:
        role = squeeze(entry.role).lower()
        if not any(token in role for token in ("led", "co-led", "priced", "lead investor", "board seat")):
            continue  # participation is not lead history
        if any(e.company.lower() == squeeze(entry.company).lower() for e in investor.lead_history):
            continue
        investor.lead_history.append(
            LeadHistoryEntry(
                company=squeeze(entry.company) or "unnamed company",
                round_label=squeeze(entry.round_label),
                role=role,
                year=entry.year,
                source=sources[0] if sources else None,
                confidence=Confidence.MEDIUM,
            )
        )

    if extraction.leads_rounds is not None and investor.leads_rounds_stated is None:
        investor.leads_rounds_stated = extraction.leads_rounds

    if extraction.check_size_text and investor.estimated_check_max is None:
        low, high = parse_money_range(extraction.check_size_text)
        if low is not None or high is not None:
            investor.estimated_check_min = low
            investor.estimated_check_max = high or low
            investor.check_size_status = EvidenceStatus.UNVERIFIED
            investor.check_size_confidence = Confidence.LOW

    if extraction.stage_focus and not investor.entry_stages:
        investor.entry_stages = [s.strip() for s in extraction.stage_focus.split(",") if s.strip()]
    if extraction.sector_focus and not investor.sector_fit_detail:
        investor.sector_fit_detail = f"Stated focus: {squeeze(extraction.sector_focus)}"
    if extraction.portfolio_companies:
        for name in extraction.portfolio_companies:
            if squeeze(name) and squeeze(name) not in investor.supporting_portfolio_companies:
                investor.supporting_portfolio_companies.append(squeeze(name))

    if extraction.fund_status_text and investor.fund_status == FundStatus.UNKNOWN:
        from ..extraction.investor_extractor import _classify_fund_status

        status = _classify_fund_status(extraction.fund_status_text)
        if status != FundStatus.UNKNOWN:
            investor.fund_status = status
            investor.deployment_status = f"{status.value} (public research)"
    if extraction.latest_fund and not investor.fund_vintage:
        import re

        year = re.search(r"(19|20)\d{2}", extraction.latest_fund)
        if year:
            investor.fund_vintage = year.group(0)


def run_research(
    investors: list[Investor], company: Company, provider: LLMProvider, limit: int = 12
) -> ResearchOutcome:
    """Research the prospects most worth the spend: lead-capable names first."""
    outcome = ResearchOutcome(backend=research_backend())

    if not enable_public_research():
        outcome.warnings.append(
            Warning(
                severity="info",
                stage="research",
                message="Public research is disabled; investor claims come only from supplied documents.",
            )
        )
        return outcome

    available, backend = backend_available()
    if not available:
        outcome.warnings.append(
            Warning(
                severity="warning",
                stage="research",
                message=(
                    f"Public research is enabled but the '{backend}' backend has no API key. "
                    "No research was performed and no claims were invented."
                ),
            )
        )
        return outcome
    if not provider.available:
        outcome.warnings.append(
            Warning(
                severity="warning",
                stage="research",
                message="Public research needs an LLM to read the sources; none is configured.",
            )
        )
        return outcome

    outcome.enabled = True

    def priority(investor: Investor) -> tuple:
        return (
            0 if investor.estimated_check_max is None else 1,
            0 if not investor.has_verified_lead_history else 1,
            investor.investor_name,
        )

    for investor in sorted(investors, key=priority)[:limit]:
        try:
            claims, notes = research_investor(investor, company, provider)
        except Exception as exc:  # one investor failing must not end the run
            _log.warning("research failed for %s: %s", investor.investor_name, exc)
            outcome.warnings.append(
                Warning(
                    severity="warning",
                    stage="research",
                    message=f"Research failed for {investor.investor_name}: {exc}",
                )
            )
            continue
        outcome.claims.extend(claims)
        outcome.researched.append(investor.investor_name)
        outcome.rejected.extend(notes)

    if outcome.rejected:
        outcome.warnings.append(
            Warning(
                severity="info",
                stage="research",
                message=f"{len(outcome.rejected)} research claim(s) were rejected or downgraded.",
                detail="; ".join(outcome.rejected[:6]),
            )
        )
    return outcome
