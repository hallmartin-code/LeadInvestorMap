"""Company-specific investor objections.

The model writes these when one is configured. This rule-based path is the fallback, and
it only produces an objection when the deck gives it something to point at - either a
statement or a conspicuous absence. Nothing here is generic venture boilerplate that
would read the same for any company.
"""

from __future__ import annotations

import re

from ..ingestion.types import ParsedDocument
from ..models.company import Company, Objection
from ..models.investor import Investor, Tier
from ..models.round import LeadRequirement, Round
from ..utils.money import format_money
from ..utils.text import squeeze, truncate

_REVENUE_MARKERS = ("revenue", "arr", "mrr", "bookings", "sales of", "recurring")
_CUSTOMER_MARKERS = (
    "customers",
    "clients",
    "accounts",
    "pilots",
    "deployments",
    "hospitals",
    "sites",
)
_MOAT_MARKERS = ("patent", "ip", "trade secret", "proprietary", "exclusiv", "moat", "defensib")
_REGULATORY_MARKERS = (
    "fda",
    "ce mark",
    "regulatory",
    "clearance",
    "510(k)",
    "pma",
    "approval",
    "ema",
)
_REIMBURSEMENT_MARKERS = ("reimbursement", "cpt", "payer", "payor", "coverage", "cms")
_BURN_MARKERS = ("burn", "runway", "months of cash", "cash out")
_TEAM_MARKERS = ("ceo", "cto", "founder", "vp ", "head of", "chief")
_COMPETITION_MARKERS = ("competitor", "competition", "competitive", "landscape")


def generate_objections_rule_based(
    company: Company, round_: Round, deck: ParsedDocument | None
) -> list[Objection]:
    text = deck.text if deck is not None else ""
    if not text.strip():
        # Every objection below is grounded in what the deck says or conspicuously omits.
        # With no deck there is no omission to point at, and inventing one would be the
        # boilerplate this module exists to avoid.
        return []
    low = text.lower()
    objections: list[Objection] = []

    def add(category: str, objection: str, evidence: str, severity: str = "medium") -> None:
        if evidence.strip():
            objections.append(
                Objection(
                    category=category,
                    objection=squeeze(objection),
                    evidence=truncate(evidence, 200),
                    severity=severity,
                )
            )

    # Revenue: absence is the evidence, and it is stated as an absence.
    revenue_line = _first_line_with(text, _REVENUE_MARKERS, require_digit=True)
    if not revenue_line and text:
        add(
            "insufficient revenue",
            "No revenue figure appears anywhere in the deck, so a lead cannot underwrite "
            "commercial traction.",
            "No line containing a revenue, ARR or bookings figure was found in the deck.",
            "high",
        )
    elif revenue_line:
        amount = _amount_in(revenue_line)
        if amount is not None and round_.raise_amount.numeric_value:
            if amount < round_.raise_amount.numeric_value * 0.15:
                add(
                    "insufficient revenue",
                    f"Revenue of {format_money(amount)} is small relative to a "
                    f"{round_.raise_amount.display()} raise, inviting a valuation challenge.",
                    revenue_line,
                    "high",
                )

    # Customer concentration.
    customer_line = _first_line_with(text, _CUSTOMER_MARKERS, require_digit=True)
    if customer_line:
        count = _small_count_in(customer_line)
        if count is not None and count <= 5:
            add(
                "customer concentration",
                f"Only {count} customers or pilots are disclosed, leaving repeatable go-to-market unproven.",
                customer_line,
                "high",
            )

    # Defensibility.
    if text and not any(marker in low for marker in _MOAT_MARKERS):
        add(
            "weak defensibility",
            "The deck does not address patents, exclusivity or any other barrier to imitation.",
            "No patent, IP or defensibility language was found anywhere in the deck.",
            "high",
        )

    # Regulatory pathway, only raised where the deck itself shows a regulated product.
    if any(marker in low for marker in _REGULATORY_MARKERS):
        pathway = _first_line_with(text, ("510(k)", "pma", "de novo", "ind", "nda", "pathway"))
        if not pathway:
            add(
                "regulatory risk",
                "Regulatory language appears but no specific pathway or timeline is identified.",
                _first_line_with(text, _REGULATORY_MARKERS) or "",
                "high",
            )
        if not any(marker in low for marker in _REIMBURSEMENT_MARKERS):
            add(
                "reimbursement risk",
                "A regulated product is described but reimbursement or payer coverage is not addressed.",
                "No reimbursement, payer or coverage discussion was found in the deck.",
            )

    # Runway against the milestone.
    burn_line = _first_line_with(text, _BURN_MARKERS, require_digit=True)
    if burn_line:
        months = _months_in(burn_line)
        if months is not None and months <= 12:
            add(
                "short runway",
                f"Stated runway of {months} months leaves little margin if the round slips.",
                burn_line,
                "high",
            )
    elif round_.raise_amount.is_known and text:
        add(
            "high burn",
            "The deck states a raise but no burn rate or runway, so use of proceeds cannot be "
            "tested against the milestone.",
            "No burn or runway figure was found in the deck.",
        )

    # Competition.
    if text and not any(marker in low for marker in _COMPETITION_MARKERS):
        add(
            "competition",
            "No competitive landscape is presented, so the differentiation claim is untested.",
            "No competitor or competitive-landscape content was found in the deck.",
        )

    # Valuation.
    if round_.valuation_display == "NOT PROVIDED" and round_.raise_amount.is_known:
        add(
            "valuation",
            f"A {round_.raise_amount.display()} raise is described with no valuation or cap, so "
            "price cannot be assessed.",
            "No pre-money, post-money or cap figure was found in the deck.",
            "high",
        )

    # Team gaps.
    if text and not any(marker in low for marker in _TEAM_MARKERS):
        add(
            "team gaps",
            "No named executive team appears in the deck, leaving execution capacity unassessable.",
            "No CEO, CTO or founder title was found in the deck.",
        )

    for weakness in company.investor_weaknesses[:3]:
        if weakness.is_known:
            add(
                "unclear product-market fit",
                str(weakness.value),
                weakness.sources[0].source_text if weakness.sources else str(weakness.value),
            )

    return objections[:7]


def add_lead_commitment_objection(
    objections: list[Objection],
    investors: list[Investor],
    round_: Round,
    requirement: LeadRequirement,
) -> list[Objection]:
    """The objection every prospect raises when no lead exists yet."""
    has_lead = any(
        investor.tier == Tier.POTENTIAL_LEAD and investor.is_active_prospect for investor in investors
    )
    committed = round_.committed.numeric_value or 0.0
    total = round_.raise_amount.numeric_value

    if not has_lead:
        share = f" ({format_money(committed)} of {format_money(total)} committed)" if total else ""
        objections.insert(
            0,
            Objection(
                category="insufficient lead commitment",
                objection=(
                    "No prospect on the current list qualifies as a lead on the evidence "
                    f"available{share}, so every institutional conversation stalls on price."
                ),
                evidence=(
                    f"{len(investors)} prospects analysed; none met the lead test on cheque size, "
                    "lead history and stage fit together."
                ),
                severity="high",
            ),
        )
    return objections[:7]


def attach_objections_to_investors(investors: list[Investor], objections: list[Objection]) -> None:
    """Give each prospect the objections most likely to matter to them.

    A follower that needs a lead cares about lead commitment; a strategic cares about
    commercial validation. The mapping is coarse on purpose - it is a prompt for the
    founder, not a prediction.
    """
    by_category = {o.category: o for o in objections}
    for investor in investors:
        relevant: list[str] = []
        if investor.tier in {Tier.FOLLOW_ON, Tier.ANGEL_FAMILY_SYNDICATE, Tier.FILL_THE_ROUND}:
            if "insufficient lead commitment" in by_category:
                relevant.append(by_category["insufficient lead commitment"].objection)
        if investor.tier in {Tier.POTENTIAL_LEAD, Tier.CO_LEAD}:
            for category in ("valuation", "insufficient revenue", "customer concentration"):
                if category in by_category:
                    relevant.append(by_category[category].objection)
        if investor.tier == Tier.STRATEGIC_VALIDATOR:
            for category in ("regulatory risk", "reimbursement risk", "competition"):
                if category in by_category:
                    relevant.append(by_category[category].objection)
        investor.likely_objections = [truncate(o, 180) for o in relevant[:3]]


# --- helpers ------------------------------------------------------------------------------


def _first_line_with(text: str, markers, require_digit: bool = False) -> str:
    for line in text.splitlines():
        flat = squeeze(line)
        if not flat or len(flat) > 240:
            continue
        low = flat.lower()
        if any(marker in low for marker in markers):
            if require_digit and not re.search(r"\d", flat):
                continue
            return flat
    return ""


def _amount_in(line: str):
    from ..utils.money import parse_money

    return parse_money(line)


def _small_count_in(line: str) -> int | None:
    words = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
    }
    low = line.lower()
    for word, value in words.items():
        if re.search(rf"\b{word}\b", low):
            return value
    match = re.search(r"\b(\d{1,3})\s+(?:enterprise\s+)?(?:customers|clients|pilots|sites|accounts)", low)
    if match:
        return int(match.group(1))
    return None


def _months_in(line: str) -> int | None:
    match = re.search(r"\b(\d{1,2})\s*(?:-|\s)?\s*month", line.lower())
    return int(match.group(1)) if match else None
