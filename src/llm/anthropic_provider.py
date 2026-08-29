"""Anthropic implementation of :class:`LLMProvider`."""

from __future__ import annotations

import json
import time
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from ..utils.config import anthropic_key, anthropic_model
from ..utils.logging import get_logger
from .base import (
    REPAIR_PREFIX,
    LLMFailure,
    LLMProvider,
    LLMUnavailable,
    format_validation_errors,
)

_log = get_logger()
T = TypeVar("T", bound=BaseModel)

TRANSIENT_RETRIES = 3


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        super().__init__()
        self.model = model or anthropic_model()
        self._key = api_key or anthropic_key()
        self._client = None
        self.usage.model = self.model
        self.usage.provider = self.name

    @property
    def available(self) -> bool:
        if not self._key:
            return False
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False
        return True

    def _get_client(self):
        if self._client is None:
            if not self.available:
                raise LLMUnavailable(
                    "ANTHROPIC_API_KEY is not set (or the anthropic package is missing). "
                    "Set it in .env, or run with LLM_PROVIDER=local for rule-based extraction."
                )
            import anthropic

            self._client = anthropic.Anthropic(api_key=self._key)
        return self._client

    def analyze(self, system: str, prompt: str, schema: type[T], *, max_tokens: int = 8000) -> T:
        import anthropic

        client = self._get_client()
        messages = [
            {
                "role": "user",
                "content": f"{prompt}\n\n{self._schema_instruction(schema)}",
            }
        ]

        for attempt in (1, 2):
            raw = self._call(client, anthropic, system, messages, max_tokens)
            try:
                return self._validate(raw, schema)
            except (ValidationError, json.JSONDecodeError) as exc:
                detail = (
                    format_validation_errors(exc)
                    if isinstance(exc, ValidationError)
                    else f"- response was not valid JSON: {exc}"
                )
                _log.warning("model output failed validation (attempt %d): %s", attempt, detail)
                self.usage.notes.append(f"schema validation failure on attempt {attempt}")
                if attempt == 2:
                    raise LLMFailure(
                        "The model returned schema-invalid output twice. Errors on the second "
                        f"attempt:\n{detail}"
                    ) from exc
                messages = [
                    *messages,
                    {"role": "assistant", "content": raw[:4000]},
                    {"role": "user", "content": REPAIR_PREFIX + detail},
                ]
        raise LLMFailure("unreachable")  # pragma: no cover

    def _call(self, client, anthropic, system: str, messages: list[dict], max_tokens: int) -> str:
        delay = 2.0
        last: Exception | None = None
        for attempt in range(1, TRANSIENT_RETRIES + 1):
            try:
                response = client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=messages,
                )
            except anthropic.AuthenticationError as exc:
                raise LLMUnavailable(f"Anthropic rejected the API key: {exc}") from exc
            except anthropic.PermissionDeniedError as exc:
                raise LLMUnavailable(f"This API key cannot reach model {self.model}: {exc}") from exc
            except anthropic.NotFoundError as exc:
                raise LLMUnavailable(
                    f"Model {self.model} was not found. Set ANTHROPIC_MODEL to a model your "
                    f"account can use. ({exc})"
                ) from exc
            except (
                anthropic.RateLimitError,
                anthropic.APIConnectionError,
                anthropic.APITimeoutError,
            ) as exc:
                last = exc
            except anthropic.APIStatusError as exc:
                if exc.status_code and exc.status_code >= 500:
                    last = exc
                else:
                    raise LLMFailure(f"Anthropic API error {exc.status_code}: {exc}") from exc
            else:
                self.usage.add(response.usage)
                if getattr(response, "stop_reason", None) == "refusal":
                    raise LLMFailure("The model declined to analyse this material.")
                return "".join(
                    block.text for block in response.content if getattr(block, "type", "") == "text"
                )

            if attempt < TRANSIENT_RETRIES:
                _log.warning(
                    "transient Anthropic failure (%s); retrying in %.0fs [%d/%d]",
                    type(last).__name__,
                    delay,
                    attempt,
                    TRANSIENT_RETRIES,
                )
                time.sleep(delay)
                delay *= 2

        raise LLMFailure(f"Anthropic did not respond after {TRANSIENT_RETRIES} attempts: {last}")
