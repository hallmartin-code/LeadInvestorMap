"""Optional public investor research, off unless explicitly enabled."""

from .freshness import apply_freshness, downgrade_for_age, label
from .investor_research import ResearchOutcome, backend_available, run_research
from .source_validator import detect_conflicts, source_rank, validate_claims

__all__ = [
    "ResearchOutcome",
    "apply_freshness",
    "backend_available",
    "detect_conflicts",
    "downgrade_for_age",
    "label",
    "run_research",
    "source_rank",
    "validate_claims",
]
