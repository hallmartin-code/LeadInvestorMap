"""Portfolio conflict analysis.

Two companies in the same broad sector are not in conflict, and treating them as such
would disqualify exactly the specialist funds most able to lead. A conflict is recorded
only where a portfolio company is a competitor the deck itself names, or where the
supplied material says in words that a conflict exists.
"""

from __future__ import annotations

import re

from ..extraction.normalizer import normalise_name
from ..models.company import Company
from ..models.investor import ConflictLevel, Investor, PortfolioConflict
from ..utils.text import squeeze

_EXPLICIT_CONFLICT = re.compile(
    r"\b(conflict(?:ed|ing)?|competitor|competing|competes with|portfolio clash|"
    r"already backed a competitor)\b",
    re.IGNORECASE,
)

_HARD_CONFLICT = re.compile(
    r"\b(direct competitor|hard conflict|clear conflict|conflicted out|cannot invest)\b",
    re.IGNORECASE,
)


def analyse_conflicts(investor: Investor, company: Company) -> Investor:
    """Set ``conflict_level`` and record the specific companies behind it."""
    competitors = {normalise_name(c): c for c in company.named_competitors if c.strip()}
    portfolio = [p for p in investor.supporting_portfolio_companies if p.strip()]
    conflicts: list[PortfolioConflict] = list(investor.portfolio_conflicts)

    for entry in portfolio:
        key = normalise_name(entry)
        if key and key in competitors:
            conflicts.append(
                PortfolioConflict(
                    company=entry,
                    level=ConflictLevel.HIGH,
                    rationale=(
                        f"{entry} is named as a competitor in the deck and appears in this "
                        "investor's portfolio."
                    ),
                    source=investor.sources[0] if investor.sources else None,
                )
            )

    text = " ".join(filter(None, [investor.notes, investor.sector_fit_detail]))
    if _EXPLICIT_CONFLICT.search(text):
        level = ConflictLevel.HIGH if _HARD_CONFLICT.search(text) else ConflictLevel.MODERATE
        named = _named_after_conflict(text)
        # Only add an unnamed entry when nothing named has already been found, so a single
        # conflict is not reported twice - once with a company and once without.
        if named or not conflicts:
            conflicts.append(
                PortfolioConflict(
                    company=named or "unnamed portfolio company",
                    level=level,
                    rationale=f"Conflict stated in the supplied material: {squeeze(text)[:160]}",
                    source=investor.sources[0] if investor.sources else None,
                )
            )

    investor.portfolio_conflicts = _dedupe(conflicts)

    if investor.portfolio_conflicts:
        order = [ConflictLevel.HIGH, ConflictLevel.MODERATE, ConflictLevel.LOW]
        for level in order:
            if any(c.level == level for c in investor.portfolio_conflicts):
                investor.conflict_level = level
                break
    elif portfolio:
        # We know what they hold and none of it competes with this company.
        investor.conflict_level = ConflictLevel.NONE
    else:
        investor.conflict_level = ConflictLevel.UNKNOWN

    return investor


def _named_after_conflict(text: str) -> str:
    match = re.search(
        r"(?:conflict(?:s|ed)? with|competitor(?: to| of)?|competes with)\s+"
        r"([A-Z][A-Za-z0-9&.'-]*(?:\s+[A-Z][A-Za-z0-9&.'-]*){0,2})",
        text,
    )
    return squeeze(match.group(1)) if match else ""


def _dedupe(conflicts: list[PortfolioConflict]) -> list[PortfolioConflict]:
    seen: dict[str, PortfolioConflict] = {}
    ranking = {
        ConflictLevel.HIGH: 3,
        ConflictLevel.MODERATE: 2,
        ConflictLevel.LOW: 1,
        ConflictLevel.NONE: 0,
        ConflictLevel.UNKNOWN: 0,
    }
    for conflict in conflicts:
        key = normalise_name(conflict.company) or conflict.company.lower()
        existing = seen.get(key)
        if existing is None or ranking[conflict.level] > ranking[existing.level]:
            seen[key] = conflict
    return list(seen.values())
