"""File dispatch and input-bundle assembly.

The user hands over a deck plus a pile of supporting material. This module works out what
each file is, reads it with the right parser, and collects failures as warnings so that
one bad file never takes down the run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..models.evidence import SourceType, Warning
from ..utils.logging import get_logger
from .docx_parser import parse_docx
from .pdf_parser import parse_pdf
from .ppt_parser import parse_pptx
from .spreadsheet_parser import parse_spreadsheet
from .text_parser import parse_text
from .types import ParsedDocument, UnreadableFile, UnsupportedFile

_log = get_logger()

DECK_EXTENSIONS = {".pdf", ".ppt", ".pptx"}
SPREADSHEET_EXTENSIONS = {".csv", ".xlsx", ".xlsm"}
DOC_EXTENSIONS = {".docx"}
TEXT_EXTENSIONS = {".txt", ".md"}

SUPPORTED_EXTENSIONS = DECK_EXTENSIONS | SPREADSHEET_EXTENSIONS | DOC_EXTENSIONS | TEXT_EXTENSIONS

#: Filename hints used to guess what a supporting file is when the user has not said.
_ROLE_HINTS: tuple[tuple[SourceType, tuple[str, ...]], ...] = (
    (SourceType.CRM_EXPORT, ("crm", "pipedrive", "hubspot", "salesforce", "affinity", "export")),
    (SourceType.INVESTOR_LIST, ("investor", "target", "prospect", "pipeline", "list", "tracker")),
    (SourceType.MEETING_NOTES, ("meeting", "notes", "call", "minutes", "conversation")),
    (SourceType.INVESTOR_RESEARCH, ("research", "profile", "fund", "memo")),
    (SourceType.DILIGENCE_DOC, ("diligence", "dd", "dataroom", "data room")),
)


@dataclass
class InputBundle:
    """Every document read for one run, split by role."""

    deck: ParsedDocument | None = None
    supporting: list[ParsedDocument] = field(default_factory=list)
    warnings: list[Warning] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)

    @property
    def all_documents(self) -> list[ParsedDocument]:
        return ([self.deck] if self.deck else []) + list(self.supporting)

    @property
    def file_names(self) -> list[str]:
        return [d.name for d in self.all_documents]

    def documents_of(self, *source_types: SourceType) -> list[ParsedDocument]:
        wanted = set(source_types)
        return [d for d in self.all_documents if d.source_type in wanted]

    def spreadsheets(self) -> list[ParsedDocument]:
        return [d for d in self.all_documents if d.kind == "spreadsheet"]


def classify_role(path: Path, default: SourceType = SourceType.INVESTOR_RESEARCH) -> SourceType:
    """Guess a supporting file's role from its name and extension."""
    stem = path.stem.lower()
    for source_type, hints in _ROLE_HINTS:
        if any(hint in stem for hint in hints):
            if source_type in {SourceType.CRM_EXPORT, SourceType.INVESTOR_LIST}:
                if path.suffix.lower() not in SPREADSHEET_EXTENSIONS:
                    continue
            return source_type
    if path.suffix.lower() in SPREADSHEET_EXTENSIONS:
        return SourceType.INVESTOR_LIST
    if path.suffix.lower() in TEXT_EXTENSIONS:
        return SourceType.MEETING_NOTES
    return default


def load_document(path: str | Path, source_type: SourceType | None = None) -> ParsedDocument:
    """Read one file with the parser its extension calls for."""
    path = Path(path)
    if not path.exists():
        raise UnreadableFile(f"{path} does not exist.")
    if path.stat().st_size == 0:
        raise UnreadableFile(f"{path.name} is empty.")

    suffix = path.suffix.lower()
    role = source_type or classify_role(path)

    if suffix == ".pdf":
        return parse_pdf(path, role)
    if suffix in {".ppt", ".pptx"}:
        return parse_pptx(path, role)
    if suffix in SPREADSHEET_EXTENSIONS:
        return parse_spreadsheet(path, role)
    if suffix in DOC_EXTENSIONS:
        return parse_docx(path, role)
    if suffix in TEXT_EXTENSIONS:
        return parse_text(path, role)

    raise UnsupportedFile(
        f"{path.name}: {suffix or 'no extension'} is not supported. "
        f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
    )


def load_bundle(
    deck_path: str | Path | None,
    supporting_paths: list[str | Path] | None = None,
    roles: dict[str, SourceType] | None = None,
) -> InputBundle:
    """Read a deck plus supporting files, surviving individual failures."""
    bundle = InputBundle()
    roles = roles or {}

    if deck_path:
        try:
            bundle.deck = load_document(deck_path, SourceType.PITCH_DECK)
            bundle.warnings.extend(bundle.deck.warnings)
        except (UnsupportedFile, UnreadableFile) as exc:
            bundle.failed.append((str(deck_path), str(exc)))
            bundle.warnings.append(
                Warning(
                    severity="error",
                    stage="ingestion",
                    message=f"The pitch deck could not be read: {exc}",
                )
            )

    for path in supporting_paths or []:
        key = str(path)
        try:
            document = load_document(path, roles.get(key))
            bundle.supporting.append(document)
            bundle.warnings.extend(document.warnings)
        except (UnsupportedFile, UnreadableFile) as exc:
            bundle.failed.append((key, str(exc)))
            bundle.warnings.append(
                Warning(
                    severity="warning",
                    stage="ingestion",
                    message=f"Skipped {Path(key).name}: {exc}",
                    detail="The rest of the analysis continued without this file.",
                )
            )
        except Exception as exc:  # pragma: no cover - defensive
            _log.exception("unexpected failure reading %s", key)
            bundle.failed.append((key, str(exc)))
            bundle.warnings.append(
                Warning(
                    severity="warning",
                    stage="ingestion",
                    message=f"Skipped {Path(key).name} after an unexpected error: {exc}",
                )
            )

    return bundle
