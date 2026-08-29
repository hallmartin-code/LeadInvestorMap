"""Investor prospect extraction.

Three sources feed the prospect list:

* spreadsheet rows (target lists, CRM exports) - the most structured, read directly;
* free text (meeting notes, research documents) - read by the model where one is
  configured, and by pattern matching otherwise;
* the deck itself - existing investors named on the cap table.

Whatever the source, the rules are the same: lead history requires explicit lead wording,
cheque size is only what someone actually stated, and a relationship is only as warm as
the material says it is.
"""

from __future__ import annotations

import re

from ..ingestion.types import ParsedDocument, TableRow
from ..models.evidence import Confidence, EvidenceStatus, SourceRef, SourceType
from ..models.investor import (
    DiligenceStage,
    FundStatus,
    Investor,
    InvestorType,
    LeadHistoryEntry,
    Relationship,
)
from ..utils.logging import get_logger
from ..utils.money import parse_money, parse_money_range
from ..utils.text import squeeze, truncate
from .normalizer import deduplicate

_log = get_logger()

# --- vocabulary -------------------------------------------------------------------------

TYPE_KEYWORDS: tuple[tuple[str, InvestorType], ...] = (
    ("micro vc", InvestorType.MICRO_VC),
    ("micro-vc", InvestorType.MICRO_VC),
    ("pre-seed fund", InvestorType.MICRO_VC),
    ("growth equity", InvestorType.GROWTH),
    ("growth fund", InvestorType.GROWTH),
    ("crossover", InvestorType.CROSSOVER),
    ("corporate venture", InvestorType.CORPORATE),
    ("cvc", InvestorType.CORPORATE),
    ("corporate", InvestorType.CORPORATE),
    ("strategic", InvestorType.STRATEGIC),
    ("family office", InvestorType.FAMILY_OFFICE),
    ("angel group", InvestorType.ANGEL_GROUP),
    ("angel network", InvestorType.ANGEL_GROUP),
    ("angel", InvestorType.ANGEL),
    ("syndicate", InvestorType.SYNDICATE),
    ("spv", InvestorType.SYNDICATE),
    ("accelerator", InvestorType.ACCELERATOR),
    ("incubator", InvestorType.ACCELERATOR),
    ("grant", InvestorType.GOVERNMENT),
    ("government", InvestorType.GOVERNMENT),
    ("sovereign", InvestorType.GOVERNMENT),
    ("venture fund", InvestorType.VC),
    ("venture capital", InvestorType.VC),
    ("vc", InvestorType.VC),
)

NAME_TYPE_HINTS: tuple[tuple[str, InvestorType], ...] = (
    ("angels", InvestorType.ANGEL_GROUP),
    ("angel group", InvestorType.ANGEL_GROUP),
    ("family office", InvestorType.FAMILY_OFFICE),
    ("syndicate", InvestorType.SYNDICATE),
    ("ventures", InvestorType.VC),
    ("venture partners", InvestorType.VC),
    ("capital", InvestorType.VC),
    ("partners", InvestorType.VC),
)

#: Relationship wording -> level. Ordered strongest first so "verbal commitment" is not
#: read as merely "verbal interest".
RELATIONSHIP_PATTERNS: tuple[tuple[str, Relationship], ...] = (
    # "Fund IV closed in 2025" is not a commitment to this round, so the strongest level
    # needs commitment wording rather than any use of "closed" or "signed".
    (
        r"\bcommitted\b(?!\s+capital)|\bwired\b|signed (?:the )?(?:docs|documents|spa)",
        Relationship.COMMITTED,
    ),
    (r"verbal commitment|committed verbally|soft commit", Relationship.VERBAL_COMMITMENT),
    (r"verbal interest|expressed interest|indicated interest", Relationship.VERBAL_INTEREST),
    (r"\bdiligence\b|\bdd\b|data room|reference calls", Relationship.ACTIVE_DILIGENCE),
    (
        r"partner meeting|full partnership|partner engagement|met the partnership",
        Relationship.PARTNER_ENGAGEMENT,
    ),
    (r"first meeting|met with|call held|initial call|second meeting", Relationship.FIRST_MEETING),
    (r"intro(?:duction)? made|introduced|forwarded the deck|email sent", Relationship.INTRO_MADE),
    (
        r"warm intro|intro available|can introduce|will introduce|offered to introduce",
        Relationship.WARM_INTRO_AVAILABLE,
    ),
    (
        r"second[- ]degree|linkedin connection|knows of us|weak connection",
        Relationship.WEAK_CONNECTION,
    ),
    (r"\bcold\b|no relationship|not contacted", Relationship.COLD),
)

STATUS_PATTERNS: tuple[tuple[str, DiligenceStage], ...] = (
    (r"\bpass(?:ed)?\b|declined|not interested", DiligenceStage.PASS),
    (
        r"\bcommitted\b(?!\s+capital)|\bwired\b|closed (?:the )?(?:round|investment)",
        DiligenceStage.COMMITTED,
    ),
    (r"verbal", DiligenceStage.VERBAL),
    (r"term sheet|terms discussion|term discussion|negotiat", DiligenceStage.TERM_DISCUSSION),
    (r"diligence|\bdd\b|data room", DiligenceStage.DILIGENCE),
    (r"partner meeting|partnership meeting|full partner", DiligenceStage.PARTNER_MEETING),
    (r"follow[- ]?up|second meeting|follow on call", DiligenceStage.FOLLOW_UP),
    (r"first meeting|intro call|initial meeting|meeting held", DiligenceStage.FIRST_MEETING),
    (r"intro made|introduced|reached out|contacted", DiligenceStage.INTRO_MADE),
    (r"intro available|warm intro|can introduce", DiligenceStage.INTRO_AVAILABLE),
    (r"\bcold\b|not contacted|no contact", DiligenceStage.COLD),
)

FUND_STATUS_PATTERNS: tuple[tuple[str, FundStatus], ...] = (
    (r"between funds|raising fund|fund ?[ivx0-9]+ closing|no dry powder", FundStatus.BETWEEN_FUNDS),
    (r"follow[- ]?on only|reserves only|no new investments", FundStatus.FOLLOW_ON_ONLY),
    (r"\binactive\b|wound down|stopped investing|dormant", FundStatus.INACTIVE),
    (r"slow deployment|deploying slowly|conserving capital|slowed", FundStatus.SLOW_DEPLOYMENT),
    (
        r"actively deploying|actively investing|deploying fund|new fund closed|fresh fund",
        FundStatus.ACTIVE,
    ),
    (r"\bactive\b", FundStatus.LIKELY_ACTIVE),
)

#: Explicit lead wording. Anything softer is participation.
LEAD_ROLE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bco[- ]?led\b", "co-led"),
    (r"(?<![\w-])led\b(?!\s+by)", "led"),
    (r"\bpriced\s+(?:the\s+)?round\b", "priced"),
    (r"\blead\s+investor\b", "lead investor"),
    (r"\btook\s+(?:a\s+)?board\s+seat\b|\bboard\s+seat\b", "board seat"),
)

# "lead" on its own is not a claim about lead behaviour - "needs a lead in place" says the
# opposite - so the positive pattern requires the verb, and negatives are checked first.
LEADS_ROUNDS_YES = re.compile(
    r"\b(leads rounds|will lead|can lead|happy to lead|prefers to lead|"
    r"often leads|always leads|leads deals|is the lead|lead investor)\b",
    re.IGNORECASE,
)
LEADS_ROUNDS_NO = re.compile(
    r"\b(never leads|does not lead|did not lead|doesn't lead|didn't lead|"
    r"follows only|follower|only follows|non-lead|will not lead|won't lead|"
    r"need(?:s|ed)? an? lead|requires? an? lead|wants? an? lead in place|rarely leads)\b",
    re.IGNORECASE,
)


# --- spreadsheet path --------------------------------------------------------------------


def investors_from_rows(document: ParsedDocument) -> list[Investor]:
    """Build one investor per data row of a target list or CRM export."""
    investors: list[Investor] = []
    for row in document.rows:
        name = _row_name(row)
        if not name:
            continue
        source = SourceRef(
            source_type=document.source_type,
            source_name=document.name,
            page_or_slide=row.row_number,
            source_text=truncate(
                "; ".join(f"{k}: {v}" for k, v in row.values.items() if not k.islower() or True),
                400,
            ),
        )
        investor = Investor(investor_name=name)
        investor.add_source(source)

        type_text = row.get("investor_type")
        investor.investor_type = _classify_type(f"{type_text} {name}", explicit=type_text)

        check_text = row.get("check_size")
        if check_text:
            low, high = parse_money_range(check_text)
            if low is not None or high is not None:
                investor.estimated_check_min = low
                investor.estimated_check_max = high or low
                investor.check_size_status = EvidenceStatus.UNVERIFIED
                investor.check_size_confidence = Confidence.MEDIUM

        if row.get("stage_focus"):
            investor.entry_stages = [
                s.strip() for s in re.split(r"[,/;]| and ", row.get("stage_focus")) if s.strip()
            ]
            investor.stage_fit_detail = f"Stated focus: {row.get('stage_focus')}"
        if row.get("sector_focus"):
            investor.sector_fit_detail = f"Stated focus: {row.get('sector_focus')}"
            investor.notes = f"{investor.notes} Sector focus: {row.get('sector_focus')}.".strip()

        leads_text = row.get("leads_rounds")
        investor.leads_rounds_stated = _parse_leads_flag(leads_text)

        lead_history_text = row.get("lead_history")
        if lead_history_text:
            investor.lead_history.extend(_lead_entries_from_text(lead_history_text, source))

        portfolio = row.get("portfolio")
        if portfolio:
            investor.supporting_portfolio_companies = [
                p.strip() for p in re.split(r"[,;]", portfolio) if p.strip()
            ]

        relationship_text = " ".join(x for x in (row.get("relationship"), row.get("notes")) if x)
        if relationship_text:
            level, detail = _classify_relationship(relationship_text)
            investor.relationship_strength = level
            investor.relationship_detail = detail or squeeze(relationship_text)[:160]
        if row.get("relationship"):
            path = row.get("relationship")
            if "->" in path or "-->" in path or "via" in path.lower() or "through" in path.lower():
                investor.warm_intro_path = squeeze(path)
                investor.warm_intro_verified = True

        status_text = " ".join(x for x in (row.get("status"), row.get("notes")) if x)
        if status_text:
            investor.current_diligence_stage = _classify_status(status_text)

        fund_status_text = " ".join(x for x in (row.get("fund_status"), row.get("notes")) if x)
        if fund_status_text:
            investor.fund_status = _classify_fund_status(fund_status_text)
            investor.deployment_status = investor.fund_status.value
        if row.get("fund_status"):
            vintage = re.search(r"(19|20)\d{2}", row.get("fund_status"))
            if vintage:
                investor.fund_vintage = vintage.group(0)

        if row.get("aum"):
            investor.fund_size = parse_money(row.get("aum"))

        if row.get("contact"):
            investor.decision_champion = squeeze(row.get("contact"))
        if row.get("next_step"):
            investor.required_next_step = squeeze(row.get("next_step"))
        if row.get("owner"):
            investor.next_step_owner = squeeze(row.get("owner"))
        if row.get("committed"):
            investor.amount_committed = parse_money(row.get("committed"))
        if row.get("notes"):
            investor.notes = f"{investor.notes} {squeeze(row.get('notes'))}".strip()
            investor.stated_dependencies.extend(_stated_dependencies(row.get("notes")))

        investor.confidence = Confidence.MEDIUM
        investors.append(investor)
    return investors


def _row_name(row: TableRow) -> str:
    name = row.get("investor_name")
    if name:
        return squeeze(name)
    # No recognised name column: fall back to the first value that looks like a name.
    for value in row.values.values():
        text = squeeze(str(value))
        if len(text) > 2 and not text.replace(".", "").replace(",", "").isdigit():
            return text
    return ""


# --- free-text path ----------------------------------------------------------------------

#: Investor mentions in prose: a capitalised phrase ending in a fund-ish word. Words like
#: "Bio" or "Labs" are deliberately absent - they name operating companies, and treating
#: them as investors is how a portfolio company ends up in the prospect list.
_TEXT_NAME_RE = re.compile(
    r"\b((?:[A-Z][A-Za-z0-9&.'-]*\s+){0,3}"
    r"(?:Capital|Ventures|Venture Partners|Partners|Fund|Funds|Investments|Angels|"
    r"Angel Group|Angel Network|Family Office|Syndicate|Collective))\b"
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def investors_from_text(document: ParsedDocument) -> list[Investor]:
    """Pattern-based prospect discovery in notes and research documents.

    Attribution is per sentence, to the investor that sentence is *about*. A fund named
    inside someone else's sentence - "Meridian co-led the Nomad Bio Series B" - is a
    portfolio company, not a prospect, and certainly not the owner of that lead history.
    """
    found: dict[str, Investor] = {}

    for segment in document.segments:
        text = segment.full_text()
        if not text:
            continue
        for chunk in _paragraphs(text):
            subject: Investor | None = None
            for sentence in _sentences(chunk):
                name = _subject_name(sentence)
                source = SourceRef(
                    source_type=document.source_type,
                    source_name=document.name,
                    page_or_slide=segment.index,
                    source_text=truncate(sentence, 400),
                )
                if name:
                    investor = found.get(name.lower())
                    if investor is None:
                        investor = Investor(investor_name=name, confidence=Confidence.LOW)
                        found[name.lower()] = investor
                    subject = investor
                if subject is None:
                    continue  # a sentence before any investor has been named
                subject.add_source(source)
                _absorb_sentence(subject, sentence, source, self_name=subject.investor_name)

    return list(found.values())


def _sentences(chunk: str) -> list[str]:
    """Sentences, with each line of a heading-led block kept separate."""
    parts: list[str] = []
    for line in chunk.splitlines():
        line = line.strip()
        if not line:
            continue
        parts.extend(p.strip() for p in _SENTENCE_SPLIT.split(line) if p.strip())
    return parts


def _subject_name(sentence: str) -> str:
    """The investor a sentence is about: a name at its start, or after a bullet/heading.

    A name that appears later in the sentence is being talked about, not talked to, so it
    is not treated as the subject.
    """
    stripped = sentence.lstrip("#*-> \t")
    names = _names_in(stripped)
    if not names:
        return ""
    first = names[0]
    position = stripped.find(first)
    return first if position <= 2 else ""


def _paragraphs(text: str) -> list[str]:
    blocks = [b.strip() for b in re.split(r"\n{2,}", text) if b.strip()]
    out: list[str] = []
    for block in blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        # Bullet lists carry one investor per line; prose is kept whole.
        if len(lines) > 1 and sum(1 for ln in lines if ln.startswith(("-", "*"))) >= len(lines) / 2:
            out.extend(lines)
        else:
            out.append(block)
    return out


def _names_in(chunk: str) -> list[str]:
    names: list[str] = []
    for match in _TEXT_NAME_RE.finditer(chunk):
        name = squeeze(match.group(1))
        name = re.sub(r"^(?:The|A|An|And|But|Our|Their)\s+", "", name)
        if len(name) < 4 or name.lower() in {"capital", "ventures", "partners", "fund", "group"}:
            continue
        if name not in names:
            names.append(name)
    return names


def _absorb_sentence(investor: Investor, chunk: str, source: SourceRef, self_name: str) -> None:
    """Read cheque size, lead wording, relationship and status out of one passage."""
    check = re.search(
        r"(?:cheque|check|ticket|writes?|writing|typical(?:ly)?|allocation|invests?)\D{0,20}"
        r"((?:US\$|USD|\$)\s?\d[\d,.]*\s?(?:mm|bn|[kmb])?(?:\s*(?:-|to)\s*"
        r"(?:US\$|USD|\$)?\s?\d[\d,.]*\s?(?:mm|bn|[kmb])?)?)",
        chunk,
        re.IGNORECASE,
    )
    if check and investor.estimated_check_min is None:
        low_amt, high_amt = parse_money_range(check.group(1))
        if low_amt is not None:
            investor.estimated_check_min = low_amt
            investor.estimated_check_max = high_amt or low_amt
            investor.check_size_status = EvidenceStatus.UNVERIFIED
            investor.check_size_confidence = Confidence.LOW

    for entry in _lead_entries_from_text(chunk, source, exclude=self_name):
        if not any(
            e.company.lower() == entry.company.lower() and e.role == entry.role for e in investor.lead_history
        ):
            investor.lead_history.append(entry)

    if investor.leads_rounds_stated is None:
        stated = _parse_leads_flag(chunk, prose=True)
        if stated is False or (stated is True and not LEADS_ROUNDS_NO.search(chunk)):
            investor.leads_rounds_stated = stated

    level, detail = _classify_relationship(chunk)
    if int(level) > int(investor.relationship_strength):
        investor.relationship_strength = level
        investor.relationship_detail = detail or truncate(chunk, 160)

    intro = re.search(
        r"((?:intro(?:duction)?\s+(?:via|through|from)|via|through|introduced by)\s+[A-Z][\w .'-]{2,40})",
        chunk,
    )
    if intro and not investor.warm_intro_path:
        investor.warm_intro_path = squeeze(intro.group(1)).rstrip(".,;")
        investor.warm_intro_verified = True

    status = _classify_status(chunk)
    order = list(DiligenceStage)
    if order.index(status) > order.index(investor.current_diligence_stage):
        investor.current_diligence_stage = status

    fund_status = _classify_fund_status(chunk)
    if fund_status != FundStatus.UNKNOWN and investor.fund_status == FundStatus.UNKNOWN:
        investor.fund_status = fund_status
        investor.deployment_status = fund_status.value

    if investor.investor_type == InvestorType.UNKNOWN:
        investor.investor_type = _classify_type(f"{chunk} {investor.investor_name}")

    investor.stated_dependencies.extend(
        d for d in _stated_dependencies(chunk) if d not in investor.stated_dependencies
    )

    if not investor.notes:
        investor.notes = truncate(chunk, 240)


# --- deck path ---------------------------------------------------------------------------


def existing_investors_from_deck(document: ParsedDocument) -> list[Investor]:
    """Investors the deck says are already on the cap table."""
    investors: list[Investor] = []
    if document is None:
        return investors

    for segment in document.segments:
        text = segment.full_text()
        if not text:
            continue
        low = text.lower()
        if not any(
            marker in low
            for marker in (
                "existing investor",
                "current investor",
                "our investors",
                "backed by",
                "investors include",
                "cap table",
                "committed to date",
            )
        ):
            continue
        source = SourceRef(
            source_type=SourceType.PITCH_DECK,
            source_name=document.name,
            page_or_slide=segment.index,
            source_text=truncate(text, 400),
        )
        for name in _names_in(text):
            investor = Investor(
                investor_name=name,
                relationship_strength=Relationship.COMMITTED,
                current_diligence_stage=DiligenceStage.COMMITTED,
                confidence=Confidence.MEDIUM,
                notes="Named in the deck as an existing investor.",
            )
            investor.investor_type = _classify_type(name)
            investor.add_source(source)
            investors.append(investor)
    return investors


# --- shared classifiers -------------------------------------------------------------------


def _classify_type(text: str, explicit: str | None = None) -> InvestorType:
    low = (text or "").lower()
    if explicit:
        for keyword, investor_type in TYPE_KEYWORDS:
            if keyword in explicit.lower():
                return investor_type
    for keyword, investor_type in TYPE_KEYWORDS:
        if keyword in low:
            return investor_type
    for keyword, investor_type in NAME_TYPE_HINTS:
        if keyword in low:
            return investor_type
    return InvestorType.UNKNOWN


_BARE_ANSWER = re.compile(r"^\s*(yes|y|true|no|n|false)\b", re.IGNORECASE)


def _parse_leads_flag(text: str | None, *, prose: bool = False) -> bool | None:
    """Read a stated lead behaviour. ``prose=True`` ignores bare yes/no answers.

    A spreadsheet cell reading "No" answers the "leads rounds?" column. The word "no"
    in a sentence of meeting notes answers nothing.
    """
    if not text:
        return None
    value = squeeze(text)
    if not prose:
        bare = _BARE_ANSWER.match(value)
        if bare:
            return bare.group(1).lower() in {"yes", "y", "true"}
    if LEADS_ROUNDS_NO.search(value):
        return False
    if LEADS_ROUNDS_YES.search(value):
        return True
    return None


def _classify_relationship(text: str) -> tuple[Relationship, str]:
    low = squeeze(text).lower()
    for pattern, level in RELATIONSHIP_PATTERNS:
        match = re.search(pattern, low)
        if match:
            return level, truncate(text, 160)
    return Relationship.COLD, ""


def _classify_status(text: str) -> DiligenceStage:
    low = squeeze(text).lower()
    for pattern, stage in STATUS_PATTERNS:
        if re.search(pattern, low):
            return stage
    return DiligenceStage.COLD


def _classify_fund_status(text: str) -> FundStatus:
    low = squeeze(text).lower()
    for pattern, status in FUND_STATUS_PATTERNS:
        if re.search(pattern, low):
            return status
    return FundStatus.UNKNOWN


def _lead_entries_from_text(text: str, source: SourceRef, exclude: str = "") -> list[LeadHistoryEntry]:
    """Find explicit lead statements. Participation wording is deliberately ignored.

    Board seats are treated per the lead-history standard: a board appointment counts only
    where it is attached to a financing already named in the same sentence, never on its
    own and never as a way to invent a company name out of the following words.
    """
    entries: list[LeadHistoryEntry] = []
    flat = squeeze(text)
    for pattern, role in LEAD_ROLE_PATTERNS:
        for match in re.finditer(pattern, flat, re.IGNORECASE):
            sentence = _sentence_around(flat, match.start())
            tail = flat[match.end() : match.end() + 130]
            round_label = ""
            round_match = re.search(
                r"\b((?:series\s+[a-d]|seed|pre-seed|bridge)(?:\s+round)?)\b", tail, re.IGNORECASE
            )
            if round_match:
                round_label = squeeze(round_match.group(1)).title()

            if role == "board seat":
                # Attach to a financing named earlier in the same sentence, or drop it.
                prior = [e for e in entries if e.company != "unnamed company"]
                if not prior or not any(e.company in sentence for e in prior):
                    continue
                company = prior[-1].company
                if any(e.company == company and e.role != "board seat" for e in entries):
                    continue
            else:
                company = _company_after(tail, exclude)

            year_match = re.search(r"\b(20\d{2})\b", tail)
            if not company and not round_label:
                # "leads rounds" with no named deal is a stated behaviour, not history.
                continue
            entries.append(
                LeadHistoryEntry(
                    company=company or "unnamed company",
                    round_label=round_label,
                    role=role if role != "leads rounds" else "led",
                    year=year_match.group(1) if year_match else None,
                    source=source,
                    confidence=Confidence.MEDIUM if company else Confidence.LOW,
                )
            )
    # Deduplicate on (company, role).
    unique: list[LeadHistoryEntry] = []
    for entry in entries:
        if not any(e.company.lower() == entry.company.lower() and e.role == entry.role for e in unique):
            unique.append(entry)
    return unique


def _sentence_around(text: str, position: int) -> str:
    start = max(text.rfind(". ", 0, position), text.rfind("; ", 0, position)) + 1
    end = text.find(". ", position)
    end = len(text) if end < 0 else end
    return text[max(0, start) : end].strip()


#: Capitalised words that start a clause rather than name a company.
_NOT_A_COMPANY = {
    "Series",
    "Seed",
    "The",
    "A",
    "An",
    "In",
    "On",
    "At",
    "And",
    "With",
    "For",
    "Their",
    "Its",
    "Round",
    "Rounds",
    "Warm",
    "Intro",
    "Introduction",
    "They",
    "We",
    "He",
    "She",
    "This",
    "That",
    "It",
    "But",
    "So",
    "Both",
    "Our",
    "Founder",
    "Partner",
    "Board",
}


def _company_after(tail: str, exclude: str = "") -> str:
    """The capitalised name immediately following a lead verb, or nothing."""
    tail = tail.lstrip(" :,-")
    match = re.match(r"(?:the\s+|in\s+|on\s+)?([A-Z][A-Za-z0-9&.'-]*(?:\s+[A-Z][A-Za-z0-9&.'-]*){0,2})", tail)
    if not match:
        return ""
    words = [w for w in squeeze(match.group(1)).split(" ") if w not in _NOT_A_COMPANY]
    name = " ".join(words)
    if not name or len(name) < 3:
        return ""
    if exclude and name.lower() in exclude.lower():
        return ""
    return name


_DEPENDENCY_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"(?:needs?|requires?|wants?|waiting for)\s+a?\s*lead", "Lead investor secured"),
    (r"(?:needs?|requires?|wants?)\s+.{0,30}(?:revenue|arr|bookings)", "Revenue milestone"),
    (
        r"(?:needs?|requires?|wants?)\s+.{0,30}(?:fda|regulatory|clearance|approval)",
        "Regulatory milestone",
    ),
    # "ic" needs word boundaries, or "health economics" becomes an IC dependency.
    (r"(?:needs?|requires?|pending)\s+.{0,30}\b(?:ic|investment committee)\b", "IC approval"),
    (r"(?:needs?|requires?|wants?)\s+.{0,30}(?:data|readout|results)", "Data readout"),
    (
        r"(?:needs?|requires?|wants?)\s+.{0,30}(?:customer|reference|pilot)",
        "Named customer or reference",
    ),
    (r"(?:needs?|requires?|wants?)\s+.{0,30}(?:valuation|price|cap)", "Valuation adjustment"),
    (
        r"(?:once|after|when)\s+.{0,20}(?:round is|minimum|50%|half)\s+.{0,20}(?:subscribed|committed)",
        "Minimum round subscribed",
    ),
    (
        r"(?:needs?|requires?|wants?)\s+.{0,30}(?:partnership|strategic partner)",
        "Strategic partnership",
    ),
)


def _stated_dependencies(text: str) -> list[str]:
    low = squeeze(text).lower()
    found: list[str] = []
    for pattern, label in _DEPENDENCY_PATTERNS:
        if re.search(pattern, low) and label not in found:
            found.append(label)
    return found


# --- orchestration -------------------------------------------------------------------------


def extract_investors(
    documents: list[ParsedDocument], deck: ParsedDocument | None = None
) -> tuple[list[Investor], list[str]]:
    """Collect prospects from every supporting document, then de-duplicate."""
    collected: list[Investor] = []

    for document in documents:
        if document.kind == "spreadsheet":
            collected.extend(investors_from_rows(document))
        else:
            collected.extend(investors_from_text(document))

    if deck is not None:
        collected.extend(existing_investors_from_deck(deck))

    deduped, notes = deduplicate(collected)
    return deduped, notes
