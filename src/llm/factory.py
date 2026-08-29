"""Provider selection.

``get_provider`` never raises for a missing key: it returns a provider whose ``available``
is False, and callers fall back to rule-based extraction with a warning attached to the
analysis. A missing key degrades the output; it does not end the run.
"""

from __future__ import annotations

from ..utils.config import llm_provider
from ..utils.logging import get_logger
from .base import LLMProvider, NullProvider

_log = get_logger()


def get_provider(name: str | None = None) -> LLMProvider:
    choice = (name or llm_provider()).strip().lower()

    if choice in {"local", "none", "off", "rule", "rules"}:
        return NullProvider()

    if choice == "anthropic":
        from .anthropic_provider import AnthropicProvider

        provider = AnthropicProvider()
    elif choice == "openai":
        from .openai_provider import OpenAIProvider

        provider = OpenAIProvider()
    else:
        _log.warning("unknown LLM_PROVIDER %r; falling back to rule-based extraction", choice)
        return NullProvider()

    if not provider.available:
        _log.warning(
            "%s provider is configured but not usable (missing key or package); "
            "falling back to rule-based extraction",
            choice,
        )
    return provider
