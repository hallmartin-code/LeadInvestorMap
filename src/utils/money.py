"""Money parsing and formatting.

Deck text says "$4M", CRM exports say "4,000,000", notes say "USD 750k". All of it has
to land on one number, and anything that cannot be read must stay ``None`` rather than
becoming a guess.
"""

from __future__ import annotations

import re

_MULTIPLIERS = {
    "k": 1_000.0,
    "m": 1_000_000.0,
    "mm": 1_000_000.0,
    "bn": 1_000_000_000.0,
    "b": 1_000_000_000.0,
}

_WORD_MULTIPLIERS = {"thousand": 1_000.0, "million": 1_000_000.0, "billion": 1_000_000_000.0}

_AMOUNT_RE = re.compile(
    r"""(?:(?P<currency>US\$|USD|\$)\s*)?
        (?P<number>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)
        \s*
        (?P<suffix>mm|bn|[kmb])?
        (?:\s*(?P<word>thousand|million|billion))?
    """,
    re.IGNORECASE | re.VERBOSE,
)

# En dash and em dash are written as escapes so the source file stays pure ASCII.
_RANGE_SPLIT = re.compile(r"\s*(?:--|-|" + "\u2013|\u2014" + r"|to|through)\s*", re.IGNORECASE)
_MAGNITUDE_HINT = re.compile(r"(mm|bn|[kmb])\b|thousand|million|billion|,", re.IGNORECASE)
_SUFFIX_ONLY = re.compile(r"(mm|bn|[kmb])\b", re.IGNORECASE)


def parse_money(text: str | float | int | None) -> float | None:
    """Parse the first monetary amount in ``text``. Returns None when unreadable.

    A bare number with no currency marker and no magnitude suffix is only accepted when
    it is large enough to plausibly be an amount (>= 1000), so that "Series 3" or
    "3 partners" is not read as $3.
    """
    if text is None:
        return None
    if isinstance(text, bool):
        return None
    if isinstance(text, (int, float)):
        return float(text)
    raw = str(text).strip()
    if not raw:
        return None

    match = _AMOUNT_RE.search(raw)
    if not match:
        return None

    number = float(match.group("number").replace(",", ""))
    suffix = (match.group("suffix") or "").lower()
    word = (match.group("word") or "").lower()
    currency = match.group("currency")

    if suffix:
        number *= _MULTIPLIERS[suffix]
    elif word:
        number *= _WORD_MULTIPLIERS[word]
    elif not currency and number < 1000:
        return None
    return number


def parse_money_range(text: str | None) -> tuple[float | None, float | None]:
    """Parse "$1M-$3M", "$1-3M", "500k to 2M" into (min, max).

    A bare magnitude on the low side inherits the high side's suffix: "$1-3M" means
    $1M-$3M, not $1-$3M.
    """
    if text is None:
        return (None, None)
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        value = float(text)
        return (value, value)
    raw = str(text).strip()
    if not raw:
        return (None, None)

    parts = _RANGE_SPLIT.split(raw, maxsplit=1)
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        low = parse_money(parts[0])
        high = parse_money(parts[1])
        high_suffix = _SUFFIX_ONLY.search(parts[1])
        if high is not None and high_suffix and not _MAGNITUDE_HINT.search(parts[0]):
            bare = re.search(r"(\d+(?:\.\d+)?)", parts[0])
            if bare:
                low = float(bare.group(1)) * _MULTIPLIERS[high_suffix.group(1).lower()]
        if low is not None and high is not None and low > high:
            low, high = high, low
        return (low, high)

    single = parse_money(raw)
    return (single, single)


def format_money(value: float | None, *, none_text: str = "NOT PROVIDED") -> str:
    """Compact display form: $4.0M, $750K, $1.25B."""
    if value is None:
        return none_text
    magnitude = abs(value)
    if magnitude >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B".replace(".00B", "B")
    if magnitude >= 1_000_000:
        text = f"${value / 1_000_000:.1f}M"
        return text.replace(".0M", "M") if magnitude >= 10_000_000 else text
    if magnitude >= 1_000:
        return f"${value / 1_000:.0f}K"
    return f"${value:,.0f}"


def format_money_range(low: float | None, high: float | None, *, none_text: str = "NOT VERIFIED") -> str:
    if low is None and high is None:
        return none_text
    if low is not None and high is not None:
        if abs(low - high) < 1e-6:
            return format_money(low)
        return f"{format_money(low)}-{format_money(high)}"
    if high is None:
        return f"{format_money(low)}+"
    return f"up to {format_money(high)}"
