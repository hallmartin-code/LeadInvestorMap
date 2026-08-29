"""Provider-independent LLM interface.

Every provider takes the same thing - a system prompt, a user prompt, and a Pydantic
schema - and returns a validated instance of that schema. Prose parsing is never used.
When a provider cannot produce valid output twice in a row it raises, and the caller
falls back to rule-based extraction rather than accepting invented content.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from ..utils.logging import get_logger

_log = get_logger()

T = TypeVar("T", bound=BaseModel)


class LLMUnavailable(Exception):
    """No credentials, no client, or the provider is deliberately switched off."""


class LLMFailure(Exception):
    """The provider was reachable but could not be made to return usable output."""


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0
    model: str = ""
    provider: str = ""
    notes: list[str] = field(default_factory=list)

    def add(self, usage_obj) -> None:
        self.input_tokens += int(getattr(usage_obj, "input_tokens", 0) or 0)
        self.output_tokens += int(getattr(usage_obj, "output_tokens", 0) or 0)
        self.calls += 1

    def as_dict(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "notes": self.notes,
        }


REPAIR_PREFIX = (
    "Your previous response did not satisfy the required schema. Return corrected JSON "
    "only, fixing exactly these problems and inventing nothing new:\n"
)


def format_validation_errors(exc: ValidationError, limit: int = 12) -> str:
    lines = []
    for error in exc.errors()[:limit]:
        location = ".".join(str(part) for part in error["loc"])
        lines.append(f"- {location}: {error['msg']}")
    return "\n".join(lines)


def extract_json_block(text: str) -> str:
    """Pull the JSON object out of a response that may be fenced or prefaced."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("```", 2)[1]
        if stripped.lower().startswith("json"):
            stripped = stripped[4:]
        stripped = stripped.strip()
        if stripped.endswith("```"):
            stripped = stripped[:-3].strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        return stripped[start : end + 1]
    return stripped


class LLMProvider(ABC):
    """The interface every provider implements."""

    name: str = "base"

    def __init__(self) -> None:
        self.usage = Usage(provider=self.name)

    @property
    @abstractmethod
    def available(self) -> bool:
        """Whether this provider can actually be called right now."""

    @abstractmethod
    def analyze(self, system: str, prompt: str, schema: type[T], *, max_tokens: int = 8000) -> T:
        """Return a validated instance of ``schema``, or raise."""

    # -- shared helpers ----------------------------------------------------------------

    def _validate(self, raw_text: str, schema: type[T]) -> T:
        payload = json.loads(extract_json_block(raw_text))
        return schema.model_validate(payload)

    def _schema_instruction(self, schema: type[BaseModel]) -> str:
        return (
            "Respond with a single JSON object and nothing else. It must validate against "
            "this JSON Schema:\n"
            f"{json.dumps(schema.model_json_schema(), indent=2)}"
        )


class NullProvider(LLMProvider):
    """Used when no model is configured. Every call raises so callers fall back."""

    name = "local"

    @property
    def available(self) -> bool:
        return False

    def analyze(self, system: str, prompt: str, schema: type[T], *, max_tokens: int = 8000) -> T:
        raise LLMUnavailable("No LLM provider is configured. The analysis ran on rule-based extraction only.")
