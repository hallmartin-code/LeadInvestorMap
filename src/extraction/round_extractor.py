"""Round parameter extraction.

Two paths feed one result: a rule-based reader that always runs, and an optional model
pass. They are merged by :func:`merge_round`, which keeps the better-supported value and
marks genuine disagreements CONFLICTING rather than silently picking a winner. User input
overrides both and is labelled USER PROVIDED.
"""

from __future__ import annotations

import re

from ..ingestion.types import ParsedDocument
from ..models.evidence import Confidence, EvidenceStatus, Fact, SourceRef
from ..models.round import Instrument, Round
from ..utils.money import format_money, parse_money
from ..utils.text import squeeze

_MONEY = r"(?:US\$|USD|\$)\s?\d[\d,]*(?:\.\d+)?\s?(?:mm|bn|[kmb])?"

STAGE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bpre[-\s]?seed\b", "Pre-Seed"),
    (r"\bseed\s+extension\b", "Seed Extension"),
    (r"\bseed\s+round\b|\bseed\b", "Seed"),
    (r"\bseries\s+a[-\s]?1\b", "Series A-1"),
    (r"\bseries\s+a\b", "Series A"),
    (r"\bseries\s+b\b", "Series B"),
    (r"\bseries\s+c\b", "Series C"),
    (r"\bseries\s+d\b", "Series D"),
    (r"\bbridge\s+(?:round|financing|note)\b", "Bridge"),
    (r"\bgrowth\s+round\b", "Growth"),
)

INSTRUMENT_PATTERNS: tuple[tuple[str, Instrument], ...] = (
    (r"\bconvertible\s+note[s]?\b|\bconv(?:ertible)?\s+debt\b", Instrument.CONVERTIBLE_NOTE),
    (
        r"\bsafe\b(?!\s*(?:harbou?r|guard))|\bsimple\s+agreement\s+for\s+future\s+equity\b",
        Instrument.SAFE,
    ),
    (
        r"\bpriced\s+(?:equity|round)\b|\bpreferred\s+(?:stock|shares|equity)\b|"
        r"\bseries\s+[a-d]\s+preferred\b|\bequity\s+round\b",
        Instrument.PRICED_EQUITY,
    ),
)

RAISE_PATTERNS = (
    rf"(?:rais(?:e|ing|ed)|seeking|raise\s+of|round\s+size|total\s+raise|target\s+raise)\D{{0,24}}({_MONEY})",
    rf"({_MONEY})\s+(?:series\s+[a-d]|seed|pre[-\s]?seed)\s+(?:round|financing)?",
    rf"({_MONEY})\s+(?:round|raise|financing)\b",
)

COMMITTED_PATTERNS = (
    rf"({_MONEY})\s+(?:already\s+)?(?:committed|closed|subscribed|secured|in\s+hand|hard[-\s]circled)",
    rf"(?:committed|closed|subscribed|secured|commitments?\s+of|hard[-\s]circled)\D{{0,24}}({_MONEY})",
)

CIRCLED_PATTERNS = (
    rf"({_MONEY})\s+(?:soft[-\s]?circled|circled|verbally\s+committed|indicated)",
    rf"(?:soft[-\s]?circled|circled|verbal\s+commitments?|indications?\s+of\s+interest)\D{{0,24}}({_MONEY})",
)

PRE_MONEY_PATTERNS = (
    rf"({_MONEY})\s+pre[-\s]?money",
    rf"pre[-\s]?money\s+(?:valuation\s+)?(?:of\s+)?({_MONEY})",
)

POST_MONEY_PATTERNS = (
    rf"({_MONEY})\s+post[-\s]?money",
    rf"post[-\s]?money\s+(?:valuation\s+)?(?:of\s+)?({_MONEY})",
)

CAP_PATTERNS = (
    rf"(?:valuation\s+)?cap\s+(?:of\s+)?({_MONEY})",
    rf"({_MONEY})\s+(?:valuation\s+)?cap\b",
)

# The prefix is case-insensitive; the date group is not, so that "October 2026" is
# matched as a month name rather than any stray capitalised word.
CLOSE_PATTERNS = (
    r"(?i:target(?:ed)?\s+clos(?:e|ing)|first\s+clos(?:e|ing)|final\s+clos(?:e|ing)|"
    r"clos(?:e|ing)\s+(?:date|target|expected))\D{0,20}?"
    r"([A-Z][a-z]{2,9}\s+\d{4}|Q[1-4]\s*\d{4}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})",
    r"(?i:clos(?:e|es|ing))\s+(?:in\s+|by\s+|on\s+)([A-Z][a-z]{2,9}\s+\d{4}|Q[1-4]\s*\d{4})",
    r"(?i:clos(?:e|es|ing))\s*[:,-]?\s*(Q[1-4]\s*\d{4}|[A-Z][a-z]{2,9}\s+\d{4})",
)


def extract_round_rule_based(document: ParsedDocument) -> Round:
    """Read round parameters from deck text with regular expressions only."""
    round_ = Round()
    if document is None:
        return round_

    stage_hits: list[tuple[str, SourceRef]] = []
    instrument_hits: list[tuple[str, SourceRef]] = []

    for segment in document.segments:
        text = segment.full_text()
        if not text:
            continue
        flat = squeeze(text)
        low = flat.lower()

        for pattern, label in STAGE_PATTERNS:
            match = re.search(pattern, low)
            if match:
                stage_hits.append((label, _ref(document, segment.index, _window(flat, match))))
                break

        for pattern, instrument in INSTRUMENT_PATTERNS:
            match = re.search(pattern, low)
            if match:
                instrument_hits.append(
                    (instrument.value, _ref(document, segment.index, _window(flat, match)))
                )
                break

        _apply_money(round_, "raise_amount", RAISE_PATTERNS, flat, document, segment.index, "Round size")
        _apply_money(
            round_,
            "committed",
            COMMITTED_PATTERNS,
            flat,
            document,
            segment.index,
            "Amount committed",
        )
        _apply_money(round_, "circled", CIRCLED_PATTERNS, flat, document, segment.index, "Amount circled")
        _apply_money(
            round_,
            "pre_money",
            PRE_MONEY_PATTERNS,
            flat,
            document,
            segment.index,
            "Pre-money valuation",
        )
        _apply_money(
            round_,
            "post_money",
            POST_MONEY_PATTERNS,
            flat,
            document,
            segment.index,
            "Post-money valuation",
        )
        _apply_money(round_, "safe_cap", CAP_PATTERNS, flat, document, segment.index, "Valuation cap")

        for pattern in CLOSE_PATTERNS:
            match = re.search(pattern, flat)
            if match and not round_.target_close.is_known:
                round_.target_close = Fact.from_document(
                    "Target close",
                    squeeze(match.group(1)),
                    _ref(document, segment.index, _window(flat, match)),
                    confidence=Confidence.MEDIUM,
                )
                break

    if stage_hits:
        label, ref = _most_common(stage_hits)
        round_.stage = Fact.from_document("Round stage", label, ref, confidence=Confidence.MEDIUM)
    if instrument_hits:
        label, ref = _most_common(instrument_hits)
        round_.instrument = Fact.from_document("Instrument", label, ref, confidence=Confidence.MEDIUM)
    elif round_.safe_cap.is_known:
        round_.instrument = Fact.inferred(
            "Instrument",
            Instrument.SAFE.value,
            "ASSUMPTION - inferred from the presence of a valuation cap; requires verification.",
            round_.safe_cap.sources,
        )

    return round_


def _apply_money(
    round_: Round,
    field: str,
    patterns: tuple[str, ...],
    flat: str,
    document: ParsedDocument,
    segment_index: int,
    claim: str,
) -> None:
    existing: Fact = getattr(round_, field)
    for pattern in patterns:
        match = re.search(pattern, flat, re.IGNORECASE)
        if not match:
            continue
        amount = parse_money(match.group(1))
        if amount is None:
            continue
        found = Fact.from_document(
            claim,
            format_money(amount),
            _ref(document, segment_index, _window(flat, match)),
            numeric_value=amount,
            confidence=Confidence.MEDIUM,
        )
        if not existing.is_known:
            setattr(round_, field, found)
        elif (
            existing.numeric_value is not None
            and abs((existing.numeric_value or 0) - amount) > 1.0
            and existing.status != EvidenceStatus.CONFLICTING
        ):
            setattr(round_, field, existing.conflict_with(found))
        return


def _window(text: str, match: re.Match, width: int = 130) -> str:
    start = max(0, match.start() - width // 2)
    end = min(len(text), match.end() + width // 2)
    return text[start:end].strip()


def _ref(document: ParsedDocument, index: int, text: str) -> SourceRef:
    return document.source_ref(index, text)


def _most_common(hits: list[tuple[str, SourceRef]]) -> tuple[str, SourceRef]:
    counts: dict[str, int] = {}
    for label, _ in hits:
        counts[label] = counts.get(label, 0) + 1
    best = max(counts, key=lambda k: counts[k])
    for label, ref in hits:
        if label == best:
            return label, ref
    return hits[0]  # pragma: no cover


def merge_round(primary: Round, secondary: Round) -> Round:
    """Merge two readings of the round. ``primary`` wins ties; disagreements are flagged."""
    merged = primary.model_copy(deep=True)
    for field in (
        "stage",
        "raise_amount",
        "instrument",
        "pre_money",
        "post_money",
        "safe_cap",
        "committed",
        "circled",
        "target_close",
        "investor_count",
    ):
        a: Fact = getattr(merged, field)
        b: Fact = getattr(secondary, field)
        if not b.is_known:
            continue
        if not a.is_known:
            setattr(merged, field, b)
            continue
        if a.status == EvidenceStatus.USER_PROVIDED:
            continue
        if _values_agree(a, b):
            # Same reading from two independent passes: keep one, keep both sources.
            combined = a.model_copy(deep=True)
            combined.sources = [*a.sources, *b.sources]
            combined.confidence = Confidence.HIGH
            setattr(merged, field, combined)
        else:
            setattr(merged, field, a.conflict_with(b))
    return merged


def _values_agree(a: Fact, b: Fact) -> bool:
    if a.numeric_value is not None and b.numeric_value is not None:
        return abs(a.numeric_value - b.numeric_value) < max(1.0, a.numeric_value * 0.02)
    return squeeze(str(a.value)).lower() == squeeze(str(b.value)).lower()


def apply_user_overrides(round_: Round, overrides: dict) -> Round:
    """User-entered values beat everything, and are labelled USER PROVIDED."""
    updated = round_.model_copy(deep=True)
    money_fields = {
        "raise_amount": "Round size",
        "committed": "Amount committed",
        "circled": "Amount circled",
        "pre_money": "Pre-money valuation",
        "post_money": "Post-money valuation",
        "safe_cap": "Valuation cap",
    }
    text_fields = {
        "stage": "Round stage",
        "instrument": "Instrument",
        "target_close": "Target close",
        "investor_count": "Investor count",
    }

    for field, claim in money_fields.items():
        raw = overrides.get(field)
        if raw in (None, "", 0):
            continue
        amount = parse_money(raw)
        if amount is None:
            continue
        setattr(updated, field, Fact.from_user(claim, format_money(amount), numeric_value=amount))

    for field, claim in text_fields.items():
        raw = overrides.get(field)
        if raw in (None, ""):
            continue
        setattr(updated, field, Fact.from_user(claim, squeeze(str(raw))))

    return updated
