"""PDF ingestion: text by page, tables where they exist, image-only pages flagged.

pdfplumber is the primary reader because it also gives table structure; PyMuPDF is the
fallback for files pdfplumber refuses. Neither is asked to guess at scanned content -
a page with almost no machine-readable text is reported, not silently skipped.
"""

from __future__ import annotations

from pathlib import Path

from ..models.evidence import SourceType, Warning
from ..utils.config import IMAGE_PAGE_CHAR_THRESHOLD
from ..utils.logging import get_logger
from ..utils.text import clean
from .types import ParsedDocument, Segment, UnreadableFile

_log = get_logger()


def parse_pdf(path: str | Path, source_type: SourceType = SourceType.PITCH_DECK) -> ParsedDocument:
    path = Path(path)
    doc = ParsedDocument(path=path, name=path.name, source_type=source_type, kind="deck")

    segments, warnings, meta = _read_with_pdfplumber(path)
    if segments is None:
        segments, warnings, meta = _read_with_pymupdf(path)
    if segments is None:
        raise UnreadableFile(f"{path.name} could not be opened. It may be corrupt or password-protected.")

    doc.segments = segments
    doc.warnings = warnings
    doc.metadata = meta

    image_pages = [s.index for s in segments if s.image_only]
    if image_pages:
        preview = ", ".join(str(i) for i in image_pages[:8])
        more = "..." if len(image_pages) > 8 else ""
        doc.warnings.append(
            Warning(
                severity="warning",
                stage="ingestion",
                message=(
                    f"Possible image-only content on page(s) {preview}{more} of {path.name} - "
                    "manual verification recommended."
                ),
                detail="These pages yielded little or no machine-readable text.",
            )
        )
    if doc.total_chars == 0:
        doc.warnings.append(
            Warning(
                severity="error",
                stage="ingestion",
                message=f"No machine-readable text found in {path.name}.",
                detail="The file is probably a scan or an image-only export.",
            )
        )
    return doc


def _read_with_pdfplumber(path: Path):
    try:
        import pdfplumber
    except ImportError:  # pragma: no cover - dependency is declared
        return None, [], {}

    segments: list[Segment] = []
    warnings: list[Warning] = []
    meta: dict = {}
    try:
        with pdfplumber.open(str(path)) as pdf:
            meta = {"pages": len(pdf.pages), "reader": "pdfplumber"}
            for number, page in enumerate(pdf.pages, start=1):
                text = ""
                tables: list[list[list[str]]] = []
                try:
                    text = clean(page.extract_text() or "")
                except Exception as exc:
                    warnings.append(
                        Warning(
                            severity="warning",
                            stage="ingestion",
                            message=f"Text extraction failed on page {number} of {path.name}.",
                            detail=str(exc),
                        )
                    )
                try:
                    for table in page.extract_tables() or []:
                        rows = [[clean(cell) if cell else "" for cell in row] for row in table]
                        if any(any(cell for cell in row) for row in rows):
                            tables.append(rows)
                except Exception:
                    # Table detection is best-effort; the page text still stands.
                    pass
                segment = Segment(index=number, text=text, kind="page", tables=tables)
                segment.image_only = segment.char_count < IMAGE_PAGE_CHAR_THRESHOLD
                segments.append(segment)
    except Exception as exc:
        message = str(exc).lower()
        if "password" in message or "encrypt" in message:
            raise UnreadableFile(f"{path.name} is password-protected. Supply an unlocked copy.") from exc
        _log.debug("pdfplumber failed on %s: %s", path.name, exc)
        return None, [], {}
    return segments, warnings, meta


def _read_with_pymupdf(path: Path):
    try:
        import fitz  # PyMuPDF
    except ImportError:  # pragma: no cover - dependency is declared
        return None, [], {}

    segments: list[Segment] = []
    try:
        with fitz.open(str(path)) as pdf:
            if getattr(pdf, "needs_pass", False):
                raise UnreadableFile(f"{path.name} is password-protected. Supply an unlocked copy.")
            for number, page in enumerate(pdf, start=1):
                text = clean(page.get_text("text") or "")
                segment = Segment(index=number, text=text, kind="page")
                segment.image_only = segment.char_count < IMAGE_PAGE_CHAR_THRESHOLD
                segments.append(segment)
    except UnreadableFile:
        raise
    except Exception as exc:
        _log.debug("PyMuPDF failed on %s: %s", path.name, exc)
        return None, [], {}
    return segments, [], {"pages": len(segments), "reader": "pymupdf"}
