"""Small text helpers shared across ingestion, extraction and rendering."""

from __future__ import annotations

import re
import unicodedata

_WS = re.compile(r"[ \t\u00a0]+")
_MULTI_NL = re.compile(r"\n{3,}")


def clean(text: str | None) -> str:
    """Normalise whitespace and unicode punctuation without dropping content."""
    if not text:
        return ""
    value = unicodedata.normalize("NFKC", str(text))
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = (
        value.replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2022", "-")
    )
    value = _WS.sub(" ", value)
    value = _MULTI_NL.sub("\n\n", value)
    return value.strip()


def squeeze(text: str | None) -> str:
    """Collapse all whitespace, including newlines, to single spaces."""
    return re.sub(r"\s+", " ", clean(text)).strip()


def truncate(text: str | None, limit: int, *, ellipsis: str = "...") -> str:
    """Word-boundary truncation."""
    value = squeeze(text)
    if len(value) <= limit:
        return value
    cut = value[: max(0, limit - len(ellipsis))].rsplit(" ", 1)[0]
    return (cut.rstrip(",;:.- ") + ellipsis) if cut else value[:limit]


def first_sentence(text: str | None, hard_cap: int = 180) -> str:
    value = squeeze(text)
    if not value:
        return ""
    for end in (". ", "? ", "! "):
        idx = value.find(end)
        if 0 < idx <= hard_cap:
            return value[: idx + 1].strip()
    if value.endswith((".", "?", "!")) and len(value) <= hard_cap:
        return value
    return truncate(value, hard_cap)


def sentences(text: str | None) -> list[str]:
    value = squeeze(text)
    if not value:
        return []
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", value)
    return [p.strip() for p in parts if p.strip()]


def contains_any(haystack: str | None, needles) -> bool:
    if not haystack:
        return False
    low = haystack.lower()
    return any(str(n).lower() in low for n in needles)


def find_context(text: str, needle: str, window: int = 140) -> str:
    """Return the text surrounding the first occurrence of ``needle``."""
    if not text or not needle:
        return ""
    idx = text.lower().find(needle.lower())
    if idx < 0:
        return ""
    start = max(0, idx - window // 2)
    end = min(len(text), idx + len(needle) + window // 2)
    return squeeze(text[start:end])


def title_case_name(name: str) -> str:
    """Title-case a name while leaving existing internal capitals alone (a16z, TEN)."""
    words = []
    for word in squeeze(name).split(" "):
        if not word:
            continue
        if any(c.isupper() for c in word[1:]) or word.isupper():
            words.append(word)
        else:
            words.append(word[:1].upper() + word[1:])
    return " ".join(words)
