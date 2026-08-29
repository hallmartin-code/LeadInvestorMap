"""Plain text and markdown ingestion, used for pasted meeting notes."""

from __future__ import annotations

from pathlib import Path

from ..models.evidence import SourceType, Warning
from ..utils.text import clean
from .types import ParsedDocument, Segment, UnreadableFile


def parse_text(path: str | Path, source_type: SourceType = SourceType.MEETING_NOTES) -> ParsedDocument:
    path = Path(path)
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            content = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:  # pragma: no cover - latin-1 always decodes
        raise UnreadableFile(f"{path.name} could not be decoded as text.")

    return _document_from_string(content, name=path.name, path=path, source_type=source_type)


def parse_text_content(
    content: str, name: str = "pasted notes", source_type: SourceType = SourceType.MEETING_NOTES
) -> ParsedDocument:
    """Same treatment for text typed straight into the UI."""
    return _document_from_string(content, name=name, path=Path(name), source_type=source_type)


def _document_from_string(content: str, *, name: str, path: Path, source_type: SourceType) -> ParsedDocument:
    doc = ParsedDocument(path=path, name=name, source_type=source_type)
    blocks = [b for b in clean(content).split("\n\n") if b.strip()]
    if not blocks:
        doc.warnings.append(Warning(severity="info", stage="ingestion", message=f"{name} contained no text."))
        doc.segments = [Segment(index=1, kind="section", text="")]
        return doc

    for index, block in enumerate(blocks, start=1):
        lines = block.splitlines()
        title = lines[0].strip("# ").strip() if lines and len(lines[0]) < 90 else ""
        doc.segments.append(Segment(index=index, kind="section", text=block, title=title))
    doc.metadata = {"blocks": len(doc.segments)}
    return doc
