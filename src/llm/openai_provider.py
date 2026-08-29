"""OpenAI implementation of :class:`LLMProvider`."""

from __future__ import annotations

import json
import time
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from ..utils.config import openai_key, openai_model
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


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        super().__init__()
        self.model = model or openai_model()
        self._key = api_key or openai_key()
        self._client = None
        self.usage.model = self.model
        self.usage.provider = self.name

    @property
    def available(self) -> bool:
        if not self._key:
            return False
        try:
            import openai  # noqa: F401
        except ImportError:
            return False
        return True

    def _get_client(self):
        if self._client is None:
            if not self.available:
                raise LLMUnavailable("OPENAI_API_KEY is not set (or the openai package is missing).")
            import openai

            self._client = openai.OpenAI(api_key=self._key)
        return self._client

    def analyze(self, system: str, prompt: str, schema: type[T], *, max_tokens: int = 8000) -> T:
        client = self._get_client()
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": f"{prompt}\n\n{self._schema_instruction(schema)}"},
        ]

        for attempt in (1, 2):
            raw = self._call(client, messages, max_tokens)
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
                    raise LLMFailure(f"The model returned schema-invalid output twice:\n{detail}") from exc
                messages = [
                    *messages,
                    {"role": "assistant", "content": raw[:4000]},
                    {"role": "user", "content": REPAIR_PREFIX + detail},
                ]
        raise LLMFailure("unreachable")  # pragma: no cover

    def _call(self, client, messages: list[dict], max_tokens: int) -> str:
        import openai

        delay = 2.0
        last: Exception | None = None
        for attempt in range(1, TRANSIENT_RETRIES + 1):
            try:
                response = client.chat.completions.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    messages=messages,
                    response_format={"type": "json_object"},
                )
            except openai.AuthenticationError as exc:
                raise LLMUnavailable(f"OpenAI rejected the API key: {exc}") from exc
            except openai.PermissionDeniedError as exc:
                raise LLMUnavailable(f"This key cannot reach model {self.model}: {exc}") from exc
            except openai.NotFoundError as exc:
                raise LLMUnavailable(f"Model {self.model} was not found: {exc}") from exc
            except (
                openai.RateLimitError,
                openai.APIConnectionError,
                openai.APITimeoutError,
            ) as exc:
                last = exc
            except openai.APIStatusError as exc:
                if exc.status_code and exc.status_code >= 500:
                    last = exc
                else:
                    raise LLMFailure(f"OpenAI API error {exc.status_code}: {exc}") from exc
            else:
                self.usage.add(_normalise_usage(getattr(response, "usage", None)))
                return response.choices[0].message.content or ""

            if attempt < TRANSIENT_RETRIES:
                _log.warning("transient OpenAI failure; retrying in %.0fs", delay)
                time.sleep(delay)
                delay *= 2

        raise LLMFailure(f"OpenAI did not respond after {TRANSIENT_RETRIES} attempts: {last}")


class _Usage:
    """OpenAI reports prompt/completion tokens; the shared accounting wants input/output."""

    def __init__(self, input_tokens: int = 0, output_tokens: int = 0) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


def _normalise_usage(usage) -> _Usage:
    if usage is None:
        return _Usage()
    return _Usage(
        input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
        output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
    )
