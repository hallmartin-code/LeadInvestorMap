"""Evidence handling, freshness, public-research validation, and the LLM abstraction."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import BaseModel

from src.llm.base import (
    LLMFailure,
    LLMProvider,
    LLMUnavailable,
    NullProvider,
    extract_json_block,
)
from src.llm.factory import get_provider
from src.models.evidence import (
    Confidence,
    EvidenceStatus,
    Fact,
    Freshness,
    ResearchClaim,
    SourceRef,
    SourceType,
)
from src.research.freshness import apply_freshness, downgrade_for_age
from src.research.investor_research import run_research
from src.research.source_validator import detect_conflicts, source_rank, validate_claims
from src.utils.dates import freshness_label
from src.utils.validation import assert_no_unsourced_verification, downgrade_unsourced
from tests.factories import make_company, make_investor

# --- evidence ---------------------------------------------------------------------------------


def test_a_missing_fact_reads_not_provided():
    fact = Fact.missing("Round size")
    assert not fact.is_known
    assert fact.display() == "NOT PROVIDED"
    assert fact.confidence == Confidence.INSUFFICIENT


def test_user_facts_are_labelled_user_provided():
    fact = Fact.from_user("Round size", "$6M", 6_000_000)
    assert fact.status == EvidenceStatus.USER_PROVIDED
    assert fact.display(with_status=True).endswith("(USER PROVIDED)")
    assert fact.sources[0].source_type == SourceType.USER_INPUT


def test_inference_is_never_silently_promoted():
    fact = Fact.inferred("Instrument", "SAFE", "ASSUMPTION - inferred from a valuation cap.")
    assert fact.status == EvidenceStatus.INFERRED
    assert fact.confidence == Confidence.LOW
    assert "ASSUMPTION" in fact.note


def test_verified_without_a_source_is_downgraded():
    fact = Fact(claim="x", value="y", status=EvidenceStatus.VERIFIED, confidence=Confidence.HIGH)
    problems = assert_no_unsourced_verification([fact])
    assert problems

    downgrade_unsourced(fact)
    assert fact.status == EvidenceStatus.INFERRED
    assert fact.confidence == Confidence.LOW


def test_conflicting_facts_keep_both_sources():
    a = Fact.from_document("Round size", "$6M", SourceRef(source_type=SourceType.PITCH_DECK, page_or_slide=4))
    b = Fact.from_document("Round size", "$8M", SourceRef(source_type=SourceType.PITCH_DECK, page_or_slide=9))
    merged = a.conflict_with(b)
    assert merged.status == EvidenceStatus.CONFLICTING
    assert len(merged.sources) == 2
    assert "$8M" in merged.note


# --- freshness --------------------------------------------------------------------------------


def test_freshness_labels_track_the_current_date():
    today = date(2026, 8, 29)
    assert freshness_label("2026-03-01", now=today) == "CURRENT"
    assert freshness_label("2025-02-01", now=today) == "RECENT"
    assert freshness_label("2021-01-01", now=today) == "STALE"
    assert freshness_label(None) == "UNKNOWN"


def test_the_year_is_not_hard_coded():
    """Freshness is relative to the run date, so the same source ages over time."""
    source_date = "2024-06-01"
    assert freshness_label(source_date, now=date(2024, 9, 1)) == "CURRENT"
    assert freshness_label(source_date, now=date(2025, 9, 1)) == "RECENT"
    assert freshness_label(source_date, now=date(2027, 9, 1)) == "STALE"


def test_stale_evidence_cannot_support_high_confidence():
    assert downgrade_for_age(Confidence.HIGH, Freshness.STALE) == Confidence.LOW
    assert downgrade_for_age(Confidence.HIGH, Freshness.UNKNOWN) == Confidence.MEDIUM
    assert downgrade_for_age(Confidence.HIGH, Freshness.CURRENT) == Confidence.HIGH


def test_apply_freshness_reports_what_it_downgraded():
    claim = ResearchClaim(
        claim="Fund V closed",
        investor_name="Old Fund",
        source_url="https://example.com/a",
        source_date="2019-01-01",
        confidence=Confidence.HIGH,
    )
    notes = apply_freshness([claim])
    assert claim.confidence == Confidence.LOW
    assert notes and "STALE" in notes[0]


def test_deck_sources_are_current_by_default():
    source = SourceRef(source_type=SourceType.PITCH_DECK, source_name="deck.pdf", page_or_slide=1)
    assert source.freshness == Freshness.CURRENT


# --- research validation -----------------------------------------------------------------------


def test_claims_without_a_retrieved_url_are_rejected():
    claims = [
        ResearchClaim(claim="Led a round", source_url="https://real.example/a"),
        ResearchClaim(claim="Invented", source_url="https://made-up.example/b"),
    ]
    kept, rejected = validate_claims(claims, {"https://real.example/a"})
    assert [c.claim for c in kept] == ["Led a round"]
    assert rejected and "not among the sources retrieved" in rejected[0]


def test_weak_domains_cannot_carry_high_confidence():
    claim = ResearchClaim(
        claim="Partner says they lead",
        source_url="https://www.linkedin.com/posts/x",
        confidence=Confidence.HIGH,
    )
    kept, _ = validate_claims([claim], {"https://www.linkedin.com/posts/x"})
    assert kept[0].confidence == Confidence.MEDIUM


def test_source_ranking_prefers_primary_sources():
    assert source_rank("https://www.sec.gov/edgar/x") < source_rank("https://techcrunch.com/x")
    assert source_rank("https://northlight.vc/team", "Northlight Ventures") == 0
    assert source_rank("https://reddit.com/r/vc") > source_rank("https://reuters.com/x")


def test_contradictory_sources_are_flagged():
    claims = [
        ResearchClaim(claim="Meridian led the Series A", source_url="https://a.example/1"),
        ResearchClaim(claim="Meridian does not lead rounds", source_url="https://b.example/2"),
    ]
    conflicts = detect_conflicts(claims)
    assert conflicts
    assert claims[0].conflicts_with


def test_research_is_off_by_default_and_says_so():
    outcome = run_research([make_investor("Any Fund")], make_company(), NullProvider())
    assert outcome.enabled is False
    assert outcome.claims == []
    assert any("disabled" in w.message for w in outcome.warnings)


def test_research_without_a_backend_key_does_not_invent(monkeypatch):
    monkeypatch.setenv("ENABLE_PUBLIC_RESEARCH", "true")
    monkeypatch.setenv("RESEARCH_BACKEND", "brave")
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)

    outcome = run_research([make_investor("Any Fund")], make_company(), NullProvider())
    assert outcome.enabled is False
    assert outcome.claims == []
    assert any("no API key" in w.message for w in outcome.warnings)


def test_research_claim_requires_a_url():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ResearchClaim(claim="No source for this")


# --- LLM abstraction -----------------------------------------------------------------------------


class _Schema(BaseModel):
    value: str


class _FlakyProvider(LLMProvider):
    """Returns invalid output once, then valid output."""

    name = "flaky"

    def __init__(self, responses):
        super().__init__()
        self.responses = list(responses)
        self.calls = 0

    @property
    def available(self) -> bool:
        return True

    def analyze(self, system, prompt, schema, *, max_tokens=8000):
        for _ in range(2):
            self.calls += 1
            raw = self.responses.pop(0)
            try:
                return self._validate(raw, schema)
            except Exception:
                continue
        raise LLMFailure("invalid twice")


def test_json_is_extracted_from_a_fenced_response():
    assert extract_json_block('```json\n{"value": "x"}\n```') == '{"value": "x"}'
    assert extract_json_block('Here you go: {"value": "x"} - hope that helps') == '{"value": "x"}'


def test_a_schema_failure_is_retried_once_then_raised():
    provider = _FlakyProvider(["not json", '{"value": "ok"}'])
    assert provider.analyze("s", "p", _Schema).value == "ok"
    assert provider.calls == 2

    doomed = _FlakyProvider(["nope", "still nope"])
    with pytest.raises(LLMFailure):
        doomed.analyze("s", "p", _Schema)


def test_missing_credentials_give_an_unavailable_provider_not_a_crash(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    provider = get_provider("anthropic")
    assert provider.available is False

    local = get_provider("local")
    assert local.available is False
    with pytest.raises(LLMUnavailable):
        local.analyze("s", "p", _Schema)


def test_an_unknown_provider_falls_back_to_rule_based():
    assert get_provider("something-else").name == "local"


def test_api_keys_are_never_hard_coded():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "src"
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "sk-ant-api" not in text
        assert "sk-proj-" not in text
