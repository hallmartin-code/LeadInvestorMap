"""Palette, type scale and page geometry for the one-pager.

Restrained institutional styling: white ground, dark type, hairline rules, one accent.
Every status is carried by a word as well as a tint, so the page survives being printed
in greyscale - which is how most investment committees actually read it.
"""

from __future__ import annotations

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape, letter

from ..utils.config import page_size_name

# --- palette ---------------------------------------------------------------------------

INK = HexColor("#111827")
BODY = HexColor("#1F2937")
MUTED = HexColor("#6B7280")
FAINT = HexColor("#9CA3AF")
RULE = HexColor("#D1D5DB")
HAIRLINE = HexColor("#E5E7EB")
WHITE = HexColor("#FFFFFF")
PAPER = HexColor("#FAFAFA")

NAVY = HexColor("#1F3864")
ACCENT = HexColor("#2E75B6")
BAND = HexColor("#EEF2F7")

POSITIVE_FG = HexColor("#1B5E20")
POSITIVE_BG = HexColor("#E6F0E6")
CAUTION_FG = HexColor("#7A5B00")
CAUTION_BG = HexColor("#FBF3DC")
NEGATIVE_FG = HexColor("#8C1D18")
NEGATIVE_BG = HexColor("#F7E4E2")
NEUTRAL_FG = HexColor("#374151")
NEUTRAL_BG = HexColor("#EFF1F4")

CONFIDENCE_COLORS = {
    "HIGH": (POSITIVE_FG, POSITIVE_BG),
    "MEDIUM": (CAUTION_FG, CAUTION_BG),
    "MED": (CAUTION_FG, CAUTION_BG),
    "LOW": (NEGATIVE_FG, NEGATIVE_BG),
    "NOT A LEAD": (NEUTRAL_FG, NEUTRAL_BG),
    "INSUFFICIENT EVIDENCE": (NEUTRAL_FG, NEUTRAL_BG),
    "UNKNOWN": (NEUTRAL_FG, NEUTRAL_BG),
}

TIER_COLORS = {
    1: (NAVY, HexColor("#DCE6F1")),
    2: (ACCENT, HexColor("#E7F0F8")),
    3: (CAUTION_FG, CAUTION_BG),
    4: (NEUTRAL_FG, NEUTRAL_BG),
    5: (NEUTRAL_FG, NEUTRAL_BG),
    6: (FAINT, HexColor("#F3F4F6")),
}

SEVERITY_COLORS = {
    "high": (NEGATIVE_FG, NEGATIVE_BG),
    "medium": (CAUTION_FG, CAUTION_BG),
    "low": (NEUTRAL_FG, NEUTRAL_BG),
}

# --- type ------------------------------------------------------------------------------

FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
FONT_ITALIC = "Helvetica-Oblique"

TITLE_SIZE = 16.0
SUBTITLE_SIZE = 9.0
SECTION_SIZE = 8.5
BODY_SIZE = 8.0
BODY_SIZE_MIN = 7.5
TILE_LABEL_SIZE = 6.2
TILE_VALUE_SIZE = 10.0
MICRO_SIZE = 6.4
FOOTNOTE_SIZE = 6.6

LEADING_RATIO = 1.22

# --- geometry ---------------------------------------------------------------------------


def page_size() -> tuple[float, float]:
    base = A4 if page_size_name() == "a4" else letter
    return landscape(base)


PAGE_W, PAGE_H = page_size()
MARGIN = 26.0

X0 = MARGIN
X1 = PAGE_W - MARGIN
CONTENT_W = X1 - X0

Y_TOP = PAGE_H - MARGIN
FOOTER_H = 24.0
Y_BOTTOM = MARGIN + FOOTER_H

SECTION_GAP = 7.0
COLUMN_GAP = 12.0

HEADER_H = 34.0
SNAPSHOT_H = 40.0

#: Three-column band under the candidate table.
BAND_COLUMNS = 3
