"""Common containers produced by every parser.

A parser's job is to hand back text with its location intact - page 7, slide 3, row 12 of
sheet "Pipeline" - so that every downstream claim can point back at something a human can
open and check. Content that could not be extracted is reported as a warning rather than
being dropped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..models.evidence import SourceRef, SourceType, Warning
from ..utils.text import squeeze


@dataclass
class Segment:
    """One page, slide, sheet or section of a document."""

    index: int
    text: str = ""
    kind: str = "page"  # page | slide | sheet | section
    title: str = ""
    notes: str = ""
    tables: list[list[list[str]]] = field(default_factory=list)
    image_only: bool = False

    @property
    def char_count(self) -> int:
        return len(self.text.strip())

    def table_text(self) -> str:
        lines: list[str] = []
        for table in self.tables:
            for row in table:
                cells = [squeeze(c) for c in row if squeeze(c)]
                if cells:
                    lines.append(" | ".join(cells))
        return "\n".join(lines)

    def full_text(self) -> str:
        parts = [self.text.strip()]
        table_text = self.table_text()
        if table_text:
            parts.append(table_text)
        if self.notes.strip():
            parts.append(f"[speaker notes] {self.notes.strip()}")
        return "\n".join(p for p in parts if p)


@dataclass
class TableRow:
    """A normalised row from a spreadsheet or CRM export."""

    sheet: str
    row_number: int
    values: dict[str, str]

    def get(self, *keys: str, default: str = "") -> str:
        for key in keys:
            if key in self.values and str(self.values[key]).strip():
                return str(self.values[key]).strip()
        return default


@dataclass
class ParsedDocument:
    """Everything one input file yielded."""

    path: Path
    name: str
    source_type: SourceType
    kind: str = "document"  # document | deck | spreadsheet
    segments: list[Segment] = field(default_factory=list)
    rows: list[TableRow] = field(default_factory=list)
    headers: list[str] = field(default_factory=list)
    warnings: list[Warning] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def text(self) -> str:
        blocks = []
        for segment in self.segments:
            body = segment.full_text()
            if body:
                label = f"[{segment.kind} {segment.index}]"
                if segment.title:
                    label += f" {segment.title}"
                blocks.append(f"{label}\n{body}")
        return "\n\n".join(blocks)

    @property
    def total_chars(self) -> int:
        return sum(s.char_count for s in self.segments)

    def source_ref(self, segment_index: int | None = None, text: str = "") -> SourceRef:
        return SourceRef(
            source_type=self.source_type,
            source_name=self.name,
            page_or_slide=segment_index,
            source_text=squeeze(text)[:400],
        )

    def find(self, needle: str) -> list[tuple[Segment, str]]:
        """Locate a string across segments, returning (segment, matching line)."""
        hits: list[tuple[Segment, str]] = []
        low = needle.lower()
        for segment in self.segments:
            for line in segment.full_text().splitlines():
                if low in line.lower():
                    hits.append((segment, squeeze(line)))
        return hits


class UnsupportedFile(Exception):
    """The file extension is not one this application can read."""


class UnreadableFile(Exception):
    """The file is the right type but could not be opened (corrupt, encrypted, empty)."""
