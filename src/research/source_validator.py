"""Validation of research claims before they are allowed near the analysis.

A search snippet is not evidence. Every claim that survives this module carries a URL
that was actually returned by the search, and claims are ranked by how authoritative the
domain is. Anything that fails is dropped with a reason, not quietly downgraded.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from ..models.evidence import Confidence, ResearchClaim

#: Rough source hierarchy from section 30 of the specification.
DOMAIN_TIERS: tuple[tuple[int, tuple[str, ...]], ...] = (
    (1, ("sec.gov", "edgar.sec.gov", "ec.europa.eu", "gov.uk", "fca.org.uk")),
    (2, ("crunchbase.com", "pitchbook.com", "dealroom.co", "cbinsights.com")),
    (
        3,
        (
            "reuters.com",
            "bloomberg.com",
            "wsj.com",
            "ft.com",
            "axios.com",
            "techcrunch.com",
            "fiercebiotech.com",
            "endpts.com",
            "statnews.com",
            "businesswire.com",
            "prnewswire.com",
            "globenewswire.com",
        ),
    ),
)

#: Domains whose content is user-generated or promotional and cannot carry a claim alone.
WEAK_DOMAINS = (
    "linkedin.com",
    "twitter.com",
    "x.com",
    "medium.com",
    "substack.com",
    "reddit.com",
    "facebook.com",
    "quora.com",
    "wikipedia.org",
)


def domain_of(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    return netloc[4:] if netloc.startswith("www.") else netloc


def source_rank(url: str, investor_name: str = "") -> int:
    """Lower is better. 0 is the investor's own site; 9 is unranked."""
    domain = domain_of(url)
    if not domain:
        return 9
    if investor_name:
        slug = re.sub(r"[^a-z0-9]", "", investor_name.lower())
        bare = re.sub(r"[^a-z0-9]", "", domain.split(".")[0])
        if slug and bare and (bare in slug or slug.startswith(bare)):
            return 0
    for tier, domains in DOMAIN_TIERS:
        if any(domain == d or domain.endswith("." + d) for d in domains):
            return tier
    if any(domain == d or domain.endswith("." + d) for d in WEAK_DOMAINS):
        return 8
    return 5


def is_weak(url: str) -> bool:
    domain = domain_of(url)
    return any(domain == d or domain.endswith("." + d) for d in WEAK_DOMAINS)


def validate_claims(
    claims: list[ResearchClaim], allowed_urls: set[str], investor_name: str = ""
) -> tuple[list[ResearchClaim], list[str]]:
    """Keep only claims whose URL came from the search results. Returns (kept, rejected)."""
    kept: list[ResearchClaim] = []
    rejected: list[str] = []

    normalised = {url.rstrip("/") for url in allowed_urls}
    for claim in claims:
        url = (claim.source_url or "").strip()
        if not url:
            rejected.append(f"'{claim.claim[:70]}' - no source URL")
            continue
        if url.rstrip("/") not in normalised:
            rejected.append(f"'{claim.claim[:70]}' - URL was not among the sources retrieved")
            continue
        if is_weak(url) and claim.confidence == Confidence.HIGH:
            claim.confidence = Confidence.MEDIUM
        kept.append(claim)

    kept.sort(key=lambda c: source_rank(c.source_url, investor_name))
    return kept, rejected


def detect_conflicts(claims: list[ResearchClaim]) -> list[str]:
    """Flag claims that contradict each other on the same subject."""
    conflicts: list[str] = []
    lead_yes = [c for c in claims if re.search(r"\bleads?\b|\bled\b", c.claim, re.IGNORECASE)]
    lead_no = [
        c for c in claims if re.search(r"does not lead|never leads|follow[- ]on only", c.claim, re.IGNORECASE)
    ]
    if lead_yes and lead_no:
        conflicts.append(
            "Sources disagree on lead behaviour: "
            f"{domain_of(lead_yes[0].source_url)} vs {domain_of(lead_no[0].source_url)}."
        )
        for claim in lead_yes + lead_no:
            claim.conflicts_with = [c.source_url for c in (lead_yes + lead_no) if c is not claim][:3]
    return conflicts
