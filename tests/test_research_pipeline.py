"""Public research with a stubbed backend and a stubbed model.

These exercise the path that would otherwise only run against the live internet: search
results in, validated claims out, and nothing that cannot point at a page that was
actually retrieved.
"""

from __future__ import annotations

import pytest

from src.llm.base import LLMFailure, LLMProvider
from src.llm.schemas import ResearchExtraction
from src.models.evidence import Confidence
from src.models.investor import FundStatus
from src.research import investor_research
from src.research.investor_research import SearchResult, research_investor, run_research
from tests.factories import make_company, make_investor

RESULTS = [
    SearchResult(
        title="Northlight leads Vessl Dx Series A",
        url="https://reuters.com/northlight-vessl",
        snippet="Northlight Diagnostics Fund led the $8M Series A.",
        published="2025-06-01",
    ),
    SearchResult(
        title="Northlight Fund II",
        url="https://northlight.vc/fund-ii",
        snippet="We invest $2M-$4M at Seed and Series A in diagnostics.",
        published="2025-02-01",
    ),
]


class _StubProvider(LLMProvider):
    name = "stub"

    def __init__(self, extraction: ResearchExtraction | Exception):
        super().__init__()
        self.extraction = extraction
        self.prompts: list[str] = []

    @property
    def available(self) -> bool:
        return True

    def analyze(self, system, prompt, schema, *, max_tokens=8000):
        self.prompts.append(prompt)
        if isinstance(self.extraction, Exception):
            raise self.extraction
        return self.extraction


@pytest.fixture
def research_on(monkeypatch):
    monkeypatch.setenv("ENABLE_PUBLIC_RESEARCH", "true")
    monkeypatch.setenv("RESEARCH_BACKEND", "brave")
    monkeypatch.setenv("BRAVE_API_KEY", "test-key")
    monkeypatch.setattr(investor_research, "search", lambda query, limit=6: list(RESULTS))


def _extraction(**overrides) -> ResearchExtraction:
    payload = {
        "investor_name": "Northlight Diagnostics Fund",
        "leads_rounds": True,
        "lead_history": [
            {
                "company": "Vessl Dx",
                "round_label": "Series A",
                "role": "led",
                "year": "2025",
                "source_text": "Northlight led the $8M Series A.",
            }
        ],
        "check_size_text": "$2M-$4M",
        "stage_focus": "Seed, Series A",
        "sector_focus": "diagnostics",
        "fund_status_text": "Fund II is actively deploying",
        "portfolio_companies": ["Vessl Dx"],
        "claims": [
            {
                "claim": "Northlight led the Vessl Dx Series A in 2025",
                "source_url": "https://reuters.com/northlight-vessl",
                "source_title": "Reuters",
                "source_date": "2025-06-01",
                "confidence": "HIGH",
            }
        ],
    }
    payload.update(overrides)
    return ResearchExtraction.model_validate(payload)


def test_research_folds_validated_claims_into_the_investor(research_on):
    investor = make_investor("Northlight Diagnostics Fund", check=(None, None), lead_history=[])
    provider = _StubProvider(_extraction())

    claims, notes = research_investor(investor, make_company(), provider)

    assert len(claims) == 1
    assert investor.has_verified_lead_history
    assert investor.estimated_check_max == 4_000_000
    assert investor.fund_status == FundStatus.ACTIVE
    assert any(s.source_url for s in investor.sources)
    assert investor.research_claims


def test_the_prompt_only_offers_retrieved_pages(research_on):
    provider = _StubProvider(_extraction())
    research_investor(make_investor("Northlight Diagnostics Fund"), make_company(), provider)
    prompt = provider.prompts[0]
    assert "https://reuters.com/northlight-vessl" in prompt
    assert "https://northlight.vc/fund-ii" in prompt


def test_a_claim_citing_an_unretrieved_page_is_dropped(research_on):
    extraction = _extraction(
        claims=[
            {
                "claim": "Northlight has $500M under management",
                "source_url": "https://invented.example/page",
                "source_title": "Nowhere",
                "confidence": "HIGH",
            }
        ]
    )
    investor = make_investor("Northlight Diagnostics Fund", check=(None, None))
    claims, notes = research_investor(investor, make_company(), _StubProvider(extraction))

    assert claims == []
    assert any("not among the sources retrieved" in note for note in notes)
    # With no surviving claim, nothing was written onto the investor.
    assert investor.estimated_check_max is None


def test_participation_from_research_is_not_lead_history(research_on):
    extraction = _extraction(
        leads_rounds=None,
        lead_history=[
            {
                "company": "Inflammatix",
                "round_label": "Series C",
                "role": "participated",
                "year": "2024",
                "source_text": "took part in the round",
            }
        ],
    )
    investor = make_investor("Northlight Diagnostics Fund", lead_history=[])
    research_investor(investor, make_company(), _StubProvider(extraction))
    assert not investor.has_verified_lead_history


def test_research_does_not_overwrite_stronger_existing_evidence(research_on):
    investor = make_investor("Northlight Diagnostics Fund", check=(9_000_000, 12_000_000))
    research_investor(investor, make_company(), _StubProvider(_extraction()))
    assert investor.estimated_check_max == 12_000_000  # the supplied document wins


def test_stale_research_is_downgraded(research_on):
    extraction = _extraction(
        claims=[
            {
                "claim": "Northlight closed Fund I",
                "source_url": "https://reuters.com/northlight-vessl",
                "source_title": "Reuters",
                "source_date": "2018-01-01",
                "confidence": "HIGH",
            }
        ]
    )
    claims, notes = research_investor(
        make_investor("Northlight Diagnostics Fund"), make_company(), _StubProvider(extraction)
    )
    assert claims[0].confidence == Confidence.LOW
    assert any("STALE" in note for note in notes)


def test_one_failing_investor_does_not_end_the_run(research_on):
    investors = [make_investor("Alpha Capital"), make_investor("Beta Capital")]
    provider = _StubProvider(LLMFailure("model exploded"))

    outcome = run_research(investors, make_company(), provider)

    assert outcome.enabled is True
    assert outcome.claims == []
    assert any("rejected or downgraded" in w.message for w in outcome.warnings)


def test_no_search_results_produces_no_claims(research_on, monkeypatch):
    monkeypatch.setattr(investor_research, "search", lambda query, limit=6: [])
    claims, notes = research_investor(
        make_investor("Unknown Fund"), make_company(), _StubProvider(_extraction())
    )
    assert claims == []
    assert any("No search results" in note for note in notes)


def test_research_prioritises_prospects_with_unknown_evidence(research_on):
    known = make_investor("Known Fund", check=(2e6, 4e6), lead_history=[("X", "Series A", "led")])
    unknown = make_investor("Unknown Fund", check=(None, None), lead_history=[])
    provider = _StubProvider(_extraction())

    outcome = run_research([known, unknown], make_company(), provider, limit=1)
    assert outcome.researched == ["Unknown Fund"]
