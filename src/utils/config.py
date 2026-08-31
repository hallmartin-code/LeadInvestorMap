"""Environment, tunables, and branding constants.

Every knob the application reads at runtime lives here. Nothing else in the codebase
should call ``os.getenv`` directly, so that a deployment can be reasoned about from
one file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[2]

# --- branding ------------------------------------------------------------------------

BRAND_NAME = "TEN Capital Network"
PRODUCT_NAME = "LEAD INVESTOR MAP"
FOOTER_NOTE = (
    "Sources: company-provided materials and cited public information. "
    "Unverified or inferred information is explicitly labelled."
)

# --- LLM ------------------------------------------------------------------------------

DEFAULT_ANTHROPIC_MODEL = "claude-opus-5"
DEFAULT_OPENAI_MODEL = "gpt-4o"

#: Approximate list pricing, USD per million tokens, for the optional cost estimate.
PRICE_PER_MTOK = {
    "claude-opus-5": {"input": 5.00, "output": 25.00},
    "gpt-4o": {"input": 2.50, "output": 10.00},
}


def llm_provider() -> str:
    return (os.getenv("LLM_PROVIDER") or "anthropic").strip().lower()


def anthropic_key() -> str | None:
    return (os.getenv("ANTHROPIC_API_KEY") or "").strip() or None


def anthropic_model() -> str:
    return (os.getenv("ANTHROPIC_MODEL") or "").strip() or DEFAULT_ANTHROPIC_MODEL


def openai_key() -> str | None:
    return (os.getenv("OPENAI_API_KEY") or "").strip() or None


def openai_model() -> str:
    return (os.getenv("OPENAI_MODEL") or "").strip() or DEFAULT_OPENAI_MODEL


# --- public research -------------------------------------------------------------------


def _flag(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def enable_public_research() -> bool:
    return _flag("ENABLE_PUBLIC_RESEARCH", False)


def research_backend() -> str:
    return (os.getenv("RESEARCH_BACKEND") or "none").strip().lower()


def brave_key() -> str | None:
    return (os.getenv("BRAVE_API_KEY") or "").strip() or None


def serper_key() -> str | None:
    return (os.getenv("SERPER_API_KEY") or "").strip() or None


def research_max_queries() -> int:
    try:
        return max(1, int(os.getenv("RESEARCH_MAX_QUERIES_PER_INVESTOR") or 3))
    except ValueError:
        return 3


def research_timeout() -> int:
    try:
        return max(5, int(os.getenv("RESEARCH_TIMEOUT_SECONDS") or 20))
    except ValueError:
        return 20


# --- output ----------------------------------------------------------------------------


def output_dir() -> Path:
    raw = (os.getenv("OUTPUT_DIR") or "output").strip()
    path = Path(raw)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def page_size_name() -> str:
    return (os.getenv("PAGE_SIZE") or "letter").strip().lower()


def max_upload_mb() -> int:
    try:
        return max(1, int(os.getenv("MAX_UPLOAD_MB") or 64))
    except ValueError:
        return 64


# --- email notifications ------------------------------------------------------------------

#: Every generation is reported here unless REPORT_EMAIL_TO overrides it.
DEFAULT_REPORT_TO = "Info@tencapital.group"
#: Must be an address on a domain verified in Resend, or delivery fails for everyone
#: except the account owner.
DEFAULT_EMAIL_FROM = "TEN Capital <reports@tencapital.group>"
EMAIL_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class EmailSettings:
    """Everything the emailer needs, resolved once from the environment."""

    api_key: str | None = None
    from_addr: str = DEFAULT_EMAIL_FROM
    default_to: str = DEFAULT_REPORT_TO
    reply_to: str = ""
    enabled: bool = True
    attach_json: bool = False
    timeout: int = EMAIL_TIMEOUT_SECONDS

    @classmethod
    def from_env(cls) -> "EmailSettings":
        return cls(
            api_key=(os.getenv("RESEND_API_KEY") or "").strip() or None,
            from_addr=(os.getenv("RESEND_FROM") or "").strip() or DEFAULT_EMAIL_FROM,
            default_to=(os.getenv("REPORT_EMAIL_TO") or "").strip() or DEFAULT_REPORT_TO,
            reply_to=(os.getenv("RESEND_REPLY_TO") or "").strip(),
            enabled=_flag("ENABLE_EMAIL", True),
            attach_json=_flag("EMAIL_ATTACH_JSON", False),
            timeout=_int_env("EMAIL_TIMEOUT_SECONDS", EMAIL_TIMEOUT_SECONDS),
        )

    @property
    def available(self) -> bool:
        """Whether a send can even be attempted."""
        return bool(self.api_key)


def _int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name) or default))
    except ValueError:
        return default


# --- extraction tunables ---------------------------------------------------------------

#: Below this mean chars/page a PDF page is treated as image-only and flagged.
IMAGE_PAGE_CHAR_THRESHOLD = 60
#: Below this total char count we cannot analyse the deck at all.
MIN_TOTAL_CHARS = 200
#: Cap on document text handed to a model in one call (characters, not tokens).
MAX_CONTEXT_CHARS = 90_000

# --- lead scoring weights (section 24 of the specification) -----------------------------

LEAD_SCORE_WEIGHTS = {
    "lead_history": 0.20,
    "check_size_fit": 0.15,
    "stage_fit": 0.15,
    "sector_fit": 0.10,
    "active_deployment": 0.10,
    "relationship_strength": 0.10,
    "timeline_compatibility": 0.08,
    "signal_value": 0.07,
    "conflict_risk": 0.05,
}

#: Lead-confidence bands applied to the 0-100 weighted score.
LEAD_CONFIDENCE_HIGH = 70.0
LEAD_CONFIDENCE_MEDIUM = 50.0

#: A shortlist is 5-8 names when that many clear the bar - and fewer when they do not.
SHORTLIST_MIN = 5
SHORTLIST_MAX = 8
#: Below this score an investor is never shortlisted, however short the list becomes.
SHORTLIST_FLOOR = 38.0

#: Fraction of the remaining raise a credible lead is expected to cover.
LEAD_CHECK_LOW_FRACTION = 0.40
LEAD_CHECK_HIGH_FRACTION = 0.70
#: A co-lead must be able to cover at least this fraction of the low lead check.
CO_LEAD_FRACTION = 0.45
#: Checks below this fraction of the total raise are fill-the-round money.
FILL_CHECK_FRACTION = 0.05

# --- freshness --------------------------------------------------------------------------

FRESHNESS_CURRENT_MONTHS = 12
FRESHNESS_RECENT_MONTHS = 24


class ExitCode(IntEnum):
    OK = 0
    UNSUPPORTED_FILE = 2
    NO_CONTENT = 3
    API_FAILURE = 4
    BAD_MODEL_OUTPUT = 5
    RENDER_FAILURE = 6
