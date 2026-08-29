"""Investor name normalisation and duplicate resolution.

"Andreessen Horowitz", "a16z" and "A16Z" are one investor. "Redwood Capital" and
"Redwood Ventures" are probably two, and merging them would corrupt the analysis, so the
bar for merging is deliberately high: an exact normalised match, a known alias, or one
name being a clean prefix of the other with the same distinctive first word.
"""

from __future__ import annotations

import re
import unicodedata

from ..models.investor import Investor
from ..utils.text import squeeze

#: Suffixes that carry no identity, stripped before comparison.
_LEGAL_SUFFIXES = (
    "llc",
    "l.l.c",
    "lp",
    "l.p",
    "llp",
    "inc",
    "inc.",
    "incorporated",
    "ltd",
    "limited",
    "gmbh",
    "bv",
    "b.v",
    "nv",
    "plc",
    "sa",
    "s.a",
    "ag",
    "pte",
    "co",
    "corp",
    "corporation",
)

#: Words that are common to many fund names and so are weak identity signals.
_GENERIC_WORDS = (
    "capital",
    "ventures",
    "venture",
    "partners",
    "partner",
    "fund",
    "funds",
    "investments",
    "investment",
    "management",
    "group",
    "holdings",
    "advisors",
    "advisers",
    "equity",
    "vc",
    "collective",
    "syndicate",
    "angels",
    "angel",
    "family",
    "office",
)

#: Aliases we treat as authoritative. Everything else must match structurally.
KNOWN_ALIASES: dict[str, str] = {
    "a16z": "andreessen horowitz",
    "andreessen": "andreessen horowitz",
    "gv": "google ventures",
    "ggv": "ggv capital",
    "nea": "new enterprise associates",
    "kpcb": "kleiner perkins",
    "kleiner perkins caufield byers": "kleiner perkins",
    "usv": "union square ventures",
    "svb": "silicon valley bank",
    "jnj": "johnson and johnson",
    "j&j": "johnson and johnson",
    "jjdc": "johnson and johnson innovation",
    "bcv": "bain capital ventures",
    "f-prime": "fprime capital",
    "fprime": "fprime capital",
    "ycombinator": "y combinator",
    "yc": "y combinator",
}


def normalise_name(name: str) -> str:
    """Lower-case, strip punctuation, legal suffixes and the leading 'the'."""
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", squeeze(name)).encode("ascii", "ignore").decode()
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9\s-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if text.startswith("the "):
        text = text[4:]
    words = [w for w in text.split(" ") if w and w.rstrip(".") not in _LEGAL_SUFFIXES]
    text = " ".join(words)
    return KNOWN_ALIASES.get(text, text)


def identity_key(name: str) -> str:
    """The comparison key: normalised name with generic fund words removed.

    Kept separate from :func:`normalise_name` so that "Redwood Capital" and "Redwood
    Ventures" both reduce to "redwood" for a *candidate* match, which is then confirmed
    or rejected by :func:`same_investor`.
    """
    normalised = normalise_name(name)
    words = [w for w in normalised.split(" ") if w not in _GENERIC_WORDS]
    return " ".join(words) if words else normalised


def same_investor(a: str, b: str) -> bool:
    """Whether two names are confidently the same entity.

    Conservative by design: a shared distinctive word is not enough, because
    "Redwood Capital" and "Redwood Ventures" can be different firms.
    """
    na, nb = normalise_name(a), normalise_name(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if KNOWN_ALIASES.get(na) == nb or KNOWN_ALIASES.get(nb) == na:
        return True

    ka, kb = identity_key(a), identity_key(b)
    if ka and ka == kb:
        # Same distinctive core. Only merge when one name is the other plus generic
        # words - "Helios Ventures" vs "Helios" - not when both add different ones.
        words_a = set(na.split(" "))
        words_b = set(nb.split(" "))
        return words_a <= words_b or words_b <= words_a
    return False


def merge_investors(primary: Investor, secondary: Investor) -> Investor:
    """Fold ``secondary`` into ``primary``, keeping the better-evidenced value.

    Nothing is thrown away: alternative names become aliases and every source is kept.
    """
    merged = primary.model_copy(deep=True)

    for alias in [secondary.investor_name, *secondary.aliases]:
        if alias and not same_name_in(alias, [merged.investor_name, *merged.aliases]):
            merged.aliases.append(alias)

    if merged.investor_type.value == "Unknown" and secondary.investor_type.value != "Unknown":
        merged.investor_type = secondary.investor_type

    for field in (
        "estimated_check_min",
        "estimated_check_max",
        "typical_initial_check",
        "fund_vintage",
        "fund_size",
        "decision_champion",
        "partner_meeting_cadence",
        "investment_committee",
        "estimated_time_to_term_sheet",
        "warm_intro_path",
        "ownership_expectation",
        "board_expectation",
        "pro_rata_expectation",
        "governance_expectation",
        "amount_committed",
        "amount_circled",
    ):
        if getattr(merged, field) in (None, "") and getattr(secondary, field) not in (None, ""):
            setattr(merged, field, getattr(secondary, field))

    for field in ("stage_fit", "sector_fit"):
        if getattr(merged, field).value == "UNKNOWN":
            setattr(merged, field, getattr(secondary, field))
    if merged.fund_status.value == "UNKNOWN":
        merged.fund_status = secondary.fund_status
    if merged.conflict_level.value == "UNKNOWN":
        merged.conflict_level = secondary.conflict_level

    # The furthest-advanced relationship and process state wins: an intro made somewhere
    # is an intro made.
    if int(secondary.relationship_strength) > int(merged.relationship_strength):
        merged.relationship_strength = secondary.relationship_strength
        if secondary.relationship_detail:
            merged.relationship_detail = secondary.relationship_detail
    merged.warm_intro_verified = merged.warm_intro_verified or secondary.warm_intro_verified

    from ..models.investor import DiligenceStage

    order = list(DiligenceStage)
    if order.index(secondary.current_diligence_stage) > order.index(merged.current_diligence_stage):
        merged.current_diligence_stage = secondary.current_diligence_stage

    for entry in secondary.lead_history:
        if not any(
            e.company.lower() == entry.company.lower() and e.role == entry.role for e in merged.lead_history
        ):
            merged.lead_history.append(entry)
    if secondary.leads_rounds_stated and merged.leads_rounds_stated is None:
        merged.leads_rounds_stated = secondary.leads_rounds_stated

    for field in (
        "supporting_portfolio_companies",
        "entry_stages",
        "likely_objections",
        "dependencies",
        "stated_dependencies",
        "investors_influenced",
        "research_claims",
    ):
        existing = getattr(merged, field)
        for value in getattr(secondary, field):
            if value not in existing:
                existing.append(value)

    for conflict in secondary.portfolio_conflicts:
        if not any(c.company.lower() == conflict.company.lower() for c in merged.portfolio_conflicts):
            merged.portfolio_conflicts.append(conflict)

    if not merged.required_next_step and secondary.required_next_step:
        merged.required_next_step = secondary.required_next_step
        merged.next_step_owner = merged.next_step_owner or secondary.next_step_owner

    if secondary.notes and secondary.notes not in merged.notes:
        merged.notes = f"{merged.notes} {secondary.notes}".strip()

    for source in secondary.sources:
        merged.add_source(source)
    return merged


def same_name_in(name: str, pool: list[str]) -> bool:
    return any(normalise_name(name) == normalise_name(other) for other in pool if other)


def deduplicate(investors: list[Investor]) -> tuple[list[Investor], list[str]]:
    """Collapse duplicate records. Returns the survivors and a note per merge performed."""
    result: list[Investor] = []
    notes: list[str] = []
    for investor in investors:
        for index, existing in enumerate(result):
            names = [existing.investor_name, *existing.aliases]
            if any(same_investor(investor.investor_name, name) for name in names):
                result[index] = merge_investors(existing, investor)
                if normalise_name(investor.investor_name) != normalise_name(existing.investor_name):
                    notes.append(f"Merged '{investor.investor_name}' into '{existing.investor_name}'.")
                break
        else:
            result.append(investor)
    return result, notes
