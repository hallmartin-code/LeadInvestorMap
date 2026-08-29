"""Date handling. The current date is always read at runtime - never hard-coded."""

from __future__ import annotations

import re
from datetime import date, datetime

from .config import FRESHNESS_CURRENT_MONTHS, FRESHNESS_RECENT_MONTHS

_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def today() -> date:
    """Current date. Indirected through a function so tests can monkeypatch it."""
    return date.today()


def iso_today() -> str:
    return today().isoformat()


def parse_date(raw: str | None) -> date | None:
    """Best-effort parse of dates seen in decks, CRM exports and web pages."""
    if not raw:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if isinstance(raw, (date, datetime)):  # pragma: no cover - defensive
        return raw if isinstance(raw, date) else raw.date()

    for fmt in (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%Y/%m/%d",
        "%d-%b-%Y",
        "%b %d, %Y",
        "%B %d, %Y",
    ):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    # "October 2026", "Oct 2026", "Q4 2026", "2026"
    m = re.search(r"([A-Za-z]{3,9})\s+(\d{4})", text)
    if m and m.group(1)[:3].lower() in _MONTHS:
        return date(int(m.group(2)), _MONTHS[m.group(1)[:3].lower()], 1)
    m = re.search(r"[Qq]([1-4])\s*[- ]?\s*(\d{4})", text)
    if m:
        quarter_end_month = int(m.group(1)) * 3
        return date(int(m.group(2)), quarter_end_month, 1)
    m = re.fullmatch(r"(19|20)\d{2}", text)
    if m:
        return date(int(text), 1, 1)
    return None


def months_between(earlier: date, later: date) -> int:
    return (later.year - earlier.year) * 12 + (later.month - earlier.month)


def freshness_label(source_date: str | date | None, *, now: date | None = None) -> str:
    """CURRENT (<12mo) / RECENT (12-24mo) / STALE (>24mo) / UNKNOWN."""
    parsed = source_date if isinstance(source_date, date) else parse_date(source_date)
    if parsed is None:
        return "UNKNOWN"
    now = now or today()
    age = months_between(parsed, now)
    if age < 0:
        return "CURRENT"
    if age < FRESHNESS_CURRENT_MONTHS:
        return "CURRENT"
    if age <= FRESHNESS_RECENT_MONTHS:
        return "RECENT"
    return "STALE"


def format_month_year(value: date | None) -> str:
    return value.strftime("%b %Y") if value else "NOT PROVIDED"
