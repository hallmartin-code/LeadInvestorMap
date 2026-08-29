"""Document ingestion: one parser per format, one loader to dispatch them."""

from .loader import SUPPORTED_EXTENSIONS, InputBundle, classify_role, load_bundle, load_document
from .types import ParsedDocument, Segment, TableRow, UnreadableFile, UnsupportedFile

__all__ = [
    "InputBundle",
    "ParsedDocument",
    "SUPPORTED_EXTENSIONS",
    "Segment",
    "TableRow",
    "UnreadableFile",
    "UnsupportedFile",
    "classify_role",
    "load_bundle",
    "load_document",
]
