"""Provider error handling: bad keys, rate limits, timeouts and malformed output.

The clients are stubbed, so these run offline. What is being checked is that a network
problem produces a clear failure and a fallback, never a fabricated analysis.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from src.extraction.llm_extraction import (
    extract_company_and_round,
    extract_investors_llm,
    generate_objections,
)
from src.ingestion.loader import load_document
from src.llm.anthropic_provider import AnthropicProvider
from src.llm.base import LLMFailure, LLMUnavailable
from src.llm.openai_provider import OpenAIProvider, _normalise_usage
from src.models.evidence import SourceType


class _Schema(BaseModel):
    value: str


class _Block:
    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text


class _Response:
    def __init__(self, text: str, stop_reason: str = "end_turn") -> None:
        self.content = [_Block(text)]
        self.stop_reason = stop_reason
        self.usage = type("U", (), {"input_tokens": 100, "output_tokens": 50})()


class _Messages:
    def __init__(self, script) -> None:
        self.script = list(script)
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _Client:
    def __init__(self, script) -> None:
        self.messages = _Messages(script)


def _provider(script) -> AnthropicProvider:
    provider = AnthropicProvider(model="test-model", api_key="test-key")
    provider._client = _Client(script)
    return provider


def test_valid_output_is_parsed_and_counted():
    provider = _provider([_Response('{"value": "ok"}')])
    assert provider.analyze("system", "prompt", _Schema).value == "ok"
    assert provider.usage.input_tokens == 100
    assert provider.usage.calls == 1


def test_invalid_output_is_repaired_once():
    provider = _provider([_Response("sorry, no json here"), _Response('{"value": "fixed"}')])
    assert provider.analyze("system", "prompt", _Schema).value == "fixed"
    assert provider.usage.notes  # the retry is recorded, not hidden


def test_invalid_twice_fails_loudly():
    provider = _provider([_Response("nope"), _Response("still nope")])
    with pytest.raises(LLMFailure):
        provider.analyze("system", "prompt", _Schema)


def test_a_refusal_is_reported():
    provider = _provider([_Response('{"value": "x"}', stop_reason="refusal")])
    with pytest.raises(LLMFailure):
        provider.analyze("system", "prompt", _Schema)


def test_rate_limits_are_retried_then_surrendered(monkeypatch):
    import anthropic

    monkeypatch.setattr("src.llm.anthropic_provider.time.sleep", lambda seconds: None)

    class _Rate(anthropic.RateLimitError):
        def __init__(self):
            pass  # bypass the SDK constructor, we only need the type

    provider = _provider([_Rate(), _Rate(), _Response('{"value": "eventually"}')])
    assert provider.analyze("s", "p", _Schema).value == "eventually"

    provider = _provider([_Rate(), _Rate(), _Rate()])
    with pytest.raises(LLMFailure) as excinfo:
        provider.analyze("s", "p", _Schema)
    assert "did not respond" in str(excinfo.value)


def test_a_missing_key_is_unavailable_not_fatal(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    provider = AnthropicProvider(model="test-model", api_key=None)
    assert provider.available is False
    with pytest.raises(LLMUnavailable):
        provider.analyze("s", "p", _Schema)


def test_openai_usage_is_normalised():
    usage = type("U", (), {"prompt_tokens": 30, "completion_tokens": 12})()
    normalised = _normalise_usage(usage)
    assert (normalised.input_tokens, normalised.output_tokens) == (30, 12)
    assert _normalise_usage(None).input_tokens == 0


def test_openai_without_a_key_is_unavailable(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert OpenAIProvider(api_key=None).available is False


def test_extraction_falls_back_when_the_model_fails(deck_path, notes_path):
    provider = _provider([_Response("garbage"), _Response("more garbage")])
    deck = load_document(deck_path, SourceType.PITCH_DECK)

    assert extract_company_and_round(provider, deck) is None

    provider = _provider([_Response("garbage"), _Response("more garbage")])
    notes = load_document(notes_path, SourceType.MEETING_NOTES)
    assert extract_investors_llm(provider, [notes]) is None


def test_a_model_pass_that_returns_nothing_useful_is_not_treated_as_fact(deck_path):
    from src.models.company import Company
    from src.models.round import Round

    empty = '{"company_name": {"value": null}, "raise_amount": {"value": null}}'
    provider = _provider([_Response(empty)])
    deck = load_document(deck_path, SourceType.PITCH_DECK)

    company, round_, existing = extract_company_and_round(provider, deck)
    assert isinstance(company, Company) and isinstance(round_, Round)
    assert company.name.display() == "NOT PROVIDED"
    assert round_.raise_amount.display() == "NOT PROVIDED"
    assert existing == []


def test_ungrounded_objections_are_discarded(deck_path):
    from tests.factories import make_company, make_round

    payload = (
        '{"objections": ['
        '{"category": "valuation", "objection": "The price feels high", "evidence": "", '
        '"severity": "high"},'
        '{"category": "team gaps", "objection": "No VP Commercial named", '
        '"evidence": "Slide 9 lists an open VP Commercial role", "severity": "medium"}'
        "]}"
    )
    provider = _provider([_Response(payload)])
    deck = load_document(deck_path, SourceType.PITCH_DECK)

    objections = generate_objections(provider, make_company(), make_round(), deck)
    assert [o.category for o in objections] == ["team gaps"]
