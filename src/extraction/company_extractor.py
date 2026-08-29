"""Company fact extraction from the deck.

The rule-based path here is intentionally modest: it takes the company name from the
title slide, keywords from word frequency, and traction from lines that contain
checkable numbers. Anything richer is the model's job, and if no model is configured the
one-pager simply shows less rather than showing invention.
"""

from __future__ import annotations

import re
from collections import Counter

from ..ingestion.types import ParsedDocument
from ..models.company import Company
from ..models.evidence import Confidence, Fact
from ..utils.text import squeeze, truncate

_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "our",
    "we",
    "are",
    "that",
    "this",
    "from",
    "has",
    "have",
    "will",
    "can",
    "its",
    "their",
    "they",
    "them",
    "you",
    "your",
    "all",
    "not",
    "but",
    "was",
    "were",
    "been",
    "being",
    "into",
    "over",
    "than",
    "then",
    "there",
    "these",
    "those",
    "who",
    "what",
    "when",
    "where",
    "which",
    "while",
    "more",
    "most",
    "each",
    "other",
    "such",
    "only",
    "also",
    "any",
    "one",
    "two",
    "three",
    "new",
    "per",
    "via",
    "out",
    "how",
    "why",
    "use",
    "used",
    "using",
    "based",
    "million",
    "billion",
    "market",
    "company",
    "solution",
    "product",
    "platform",
    "team",
    "customers",
    "series",
    "seed",
    "round",
    "raise",
    "raising",
    "investors",
    "investor",
    "valuation",
    "pre",
    "post",
    "money",
    "close",
    "closing",
    "slide",
    "page",
}

SECTOR_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Healthcare / Life Sciences": (
        "clinical",
        "patient",
        "patients",
        "therapeutic",
        "diagnostic",
        "fda",
        "biotech",
        "pharma",
        "medical",
        "disease",
        "treatment",
        "trial",
        "hospital",
        "physician",
        "drug",
        "oncology",
        "sepsis",
        "device",
        "reimbursement",
        "payer",
        "payor",
    ),
    "Enterprise Software / SaaS": (
        "saas",
        "enterprise",
        "workflow",
        "dashboard",
        "integration",
        "api",
        "subscription",
        "seats",
        "arr",
        "mrr",
        "churn",
        "onboarding",
        "deployment",
    ),
    "Fintech": (
        "payments",
        "lending",
        "banking",
        "credit",
        "underwriting",
        "compliance",
        "kyc",
        "transaction",
        "fintech",
        "insurance",
        "wallet",
    ),
    "Climate / Energy": (
        "carbon",
        "emissions",
        "renewable",
        "solar",
        "battery",
        "grid",
        "climate",
        "energy",
        "decarbon",
        "hydrogen",
    ),
    "Industrial / Hardware": (
        "manufacturing",
        "factory",
        "hardware",
        "sensor",
        "robotics",
        "supply chain",
        "logistics",
        "throughput",
        "assembly",
    ),
    "Consumer": (
        "consumer",
        "app",
        "retail",
        "brand",
        "marketplace",
        "subscribers",
        "dtc",
        "engagement",
        "creators",
    ),
    "AI / Data Infrastructure": (
        "model",
        "inference",
        "training",
        "dataset",
        "llm",
        "machine learning",
        "algorithm",
        "data infrastructure",
        "embedding",
    ),
}

BUSINESS_MODEL_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bsaas\b|\bsubscription\b|\barr\b|\bmrr\b", "Subscription / SaaS"),
    (r"\blicens(?:e|ing)\b|\broyalt(?:y|ies)\b", "Licensing / Royalty"),
    (r"\bper[- ]test\b|\bper[- ]use\b|\bper[- ]procedure\b|\breagent\b", "Per-use / Consumable"),
    (r"\bmarketplace\b|\btake rate\b|\bcommission\b", "Marketplace"),
    (r"\bhardware\b\s+(?:sales|revenue)|\bdevice sales\b", "Hardware sales"),
    (r"\btransaction fee\b|\binterchange\b", "Transaction fees"),
    (
        r"\bpartnership\b.{0,30}\bmilestone\b|\bupfront\b.{0,30}\bmilestone\b",
        "Partnership / Milestone",
    ),
)

TRACTION_MARKERS = (
    "revenue",
    "arr",
    "mrr",
    "customers",
    "pilot",
    "pilots",
    "users",
    "bookings",
    "loi",
    "letters of intent",
    "contracts",
    "grant",
    "granted",
    "patent",
    "fda",
    "ce mark",
    "clearance",
    "approval",
    "enrolled",
    "sites",
    "partnership",
    "signed",
    "waitlist",
    "retention",
    "churn",
    "gross margin",
    "published",
    "peer-reviewed",
)

RISK_MARKERS = (
    "risk",
    "risks",
    "challenge",
    "uncertain",
    "dependent on",
    "no assurance",
    "forward-looking",
    "mitigation",
    "regulatory approval required",
)


def extract_company_rule_based(document: ParsedDocument | None) -> Company:
    company = Company()
    if document is None:
        return company

    full_text = document.text
    if not full_text.strip():
        return company

    name = _company_name(document)
    if name:
        company.name = Fact.from_document(
            "Company name",
            name,
            document.source_ref(document.segments[0].index if document.segments else 1, name),
            confidence=Confidence.MEDIUM,
        )

    first = document.segments[0] if document.segments else None
    if first is not None:
        lines = [ln for ln in first.full_text().splitlines() if squeeze(ln)]
        for line in lines[1:4]:
            text = squeeze(line)
            if 20 <= len(text) <= 160:
                company.one_liner = Fact.from_document(
                    "Company one-liner",
                    text,
                    document.source_ref(first.index, text),
                    confidence=Confidence.LOW,
                )
                break

    sector, hits = _classify_sector(full_text)
    if sector:
        company.sector = Fact.inferred(
            "Sector",
            sector,
            f"ASSUMPTION - inferred from deck vocabulary ({', '.join(hits[:4])}).",
            [document.source_ref(None, ", ".join(hits[:6]))],
        )

    low = full_text.lower()
    for pattern, label in BUSINESS_MODEL_PATTERNS:
        match = re.search(pattern, low)
        if match:
            segment_index, context = _locate(document, match.group(0))
            company.business_model = Fact.inferred(
                "Business model",
                label,
                "ASSUMPTION - inferred from deck terminology; requires verification.",
                [document.source_ref(segment_index, context)],
            )
            break

    company.keywords = _keywords(full_text)
    company.traction = _traction(document)
    company.key_risks = _risks(document)
    company.named_competitors = _competitors(document, exclude=name)
    return company


def _company_name(document: ParsedDocument) -> str:
    if not document.segments:
        return ""
    first = document.segments[0]
    if first.title and 2 <= len(first.title) <= 60:
        return squeeze(first.title)
    for line in first.full_text().splitlines():
        text = squeeze(line)
        if 2 <= len(text) <= 60 and not text.lower().startswith(
            ("confidential", "private", "draft", "presentation")
        ):
            return text
    stem = document.path.stem
    stem = re.sub(r"[-_]+", " ", stem)
    stem = re.sub(r"(?i)\b(deck|pitch|investor|presentation|final|v\d+(\.\d+)*|\d{4}|copy)\b", " ", stem)
    return squeeze(stem)


def _classify_sector(text: str) -> tuple[str, list[str]]:
    low = text.lower()
    scores: dict[str, list[str]] = {}
    for sector, terms in SECTOR_KEYWORDS.items():
        hits = [t for t in terms if t in low]
        if hits:
            scores[sector] = hits
    if not scores:
        return "", []
    best = max(scores, key=lambda s: len(scores[s]))
    if len(scores[best]) < 3:
        return "", []
    return best, scores[best]


def _keywords(text: str, limit: int = 12) -> list[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z-]{3,}", text.lower())
    counts = Counter(w for w in words if w not in _STOPWORDS)
    return [word for word, count in counts.most_common(limit) if count > 1]


def _traction(document: ParsedDocument) -> list[Fact]:
    facts: list[Fact] = []
    seen: set[str] = set()
    for segment in document.segments:
        for line in segment.full_text().splitlines():
            text = squeeze(line)
            if not (20 <= len(text) <= 220):
                continue
            low = text.lower()
            if not any(marker in low for marker in TRACTION_MARKERS):
                continue
            if not re.search(r"\d", text):
                continue
            key = low[:60]
            if key in seen:
                continue
            seen.add(key)
            facts.append(
                Fact.from_document(
                    "Traction",
                    truncate(text, 200),
                    document.source_ref(segment.index, text),
                    confidence=Confidence.MEDIUM,
                )
            )
            if len(facts) >= 12:
                return facts
    return facts


def _risks(document: ParsedDocument) -> list[Fact]:
    facts: list[Fact] = []
    for segment in document.segments:
        for line in segment.full_text().splitlines():
            text = squeeze(line)
            if not (20 <= len(text) <= 220):
                continue
            if any(marker in text.lower() for marker in RISK_MARKERS):
                facts.append(
                    Fact.from_document(
                        "Stated risk",
                        truncate(text, 200),
                        document.source_ref(segment.index, text),
                        confidence=Confidence.MEDIUM,
                    )
                )
            if len(facts) >= 8:
                return facts
    return facts


#: Capitalised words that appear on a competition slide without naming a competitor.
_NOT_A_COMPETITOR = {
    "competitors",
    "competition",
    "competitive",
    "landscape",
    "our",
    "we",
    "the",
    "they",
    "slide",
    "page",
    "confidential",
    "series",
    "and",
    "vs",
}


def _strip_stopwords(name: str) -> str:
    """Drop leading and trailing non-name words, so a slide title does not join a name."""
    words = name.split(" ")
    while words and words[0].lower() in _NOT_A_COMPETITOR:
        words.pop(0)
    while words and words[-1].lower() in _NOT_A_COMPETITOR:
        words.pop()
    return " ".join(words)


def _competitors(document: ParsedDocument, exclude: str = "") -> list[str]:
    """Capitalised names on a competition slide, minus the company's own name.

    Without the exclusion the deck footer turns the company into its own competitor, and
    every existing investor is then flagged as a portfolio conflict.
    """
    names: list[str] = []
    own = squeeze(exclude).lower()
    for segment in document.segments:
        text = segment.full_text()
        if "competit" not in text.lower():
            continue
        for match in re.finditer(r"\b([A-Z][A-Za-z0-9&.'-]{2,}(?:\s+[A-Z][A-Za-z0-9&.'-]+){0,2})\b", text):
            name = _strip_stopwords(squeeze(match.group(1)))
            low = name.lower()
            if not name or low in _NOT_A_COMPETITOR or len(name) < 3:
                continue
            if own and (low == own or low in own or own in low):
                continue
            if name not in names:
                names.append(name)
    return names[:12]


def _locate(document: ParsedDocument, needle: str) -> tuple[int | None, str]:
    hits = document.find(needle)
    if hits:
        segment, line = hits[0]
        return segment.index, line
    return None, needle
