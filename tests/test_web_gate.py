"""The web app's access gate.

Every analysis spends API credit, so an ungated public URL is a standing bill against the
account. These tests stand in for the browser: a stub Streamlit records what the gate did
and raises on ``stop()``, which is what Streamlit itself does to halt a script run.
"""

from __future__ import annotations

import contextlib

import pytest

from app import _check_password
from src.utils.config import app_password, is_public_deployment


class _Stopped(Exception):
    """Raised by the stub in place of Streamlit's own script-halting exception."""


class _StubStreamlit:
    def __init__(self, typed: str | None = None) -> None:
        self.typed = typed
        self.session_state: dict = {}
        self.errors: list[str] = []
        self.titles: list[str] = []
        self.captions: list[str] = []
        self.markup: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def title(self, message: str) -> None:
        self.titles.append(message)

    def caption(self, message: str) -> None:
        self.captions.append(message)

    def markdown(self, body: str, **_kwargs) -> None:
        self.markup.append(body)

    def container(self, **_kwargs):
        """Streamlit containers are context managers; the stub only needs the protocol."""
        return contextlib.nullcontext()

    def text_input(self, _label: str, **_kwargs) -> str:
        return self.typed or ""

    def stop(self):
        raise _Stopped()


def test_localhost_without_a_password_is_open(monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    assert app_password() is None
    assert is_public_deployment() is False
    assert _check_password(_StubStreamlit()) is True


def test_a_public_deployment_without_a_password_refuses_to_serve(monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")

    stub = _StubStreamlit()
    with pytest.raises(_Stopped):
        _check_password(stub)

    assert stub.errors, "the gate must explain why it refused"
    assert "APP_PASSWORD" in stub.errors[0]
    assert "credit" in stub.errors[0].lower()


def test_the_correct_password_unlocks_and_is_remembered(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "correct horse")
    stub = _StubStreamlit(typed="correct horse")

    assert _check_password(stub) is True
    assert stub.session_state["authenticated"] is True

    # A later rerun does not ask again.
    stub.typed = None
    assert _check_password(stub) is True


def test_a_wrong_password_is_rejected(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "correct horse")
    stub = _StubStreamlit(typed="battery staple")

    with pytest.raises(_Stopped):
        _check_password(stub)
    assert stub.errors == ["Incorrect password."]
    assert "authenticated" not in stub.session_state


def test_an_empty_entry_waits_rather_than_failing(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "correct horse")
    stub = _StubStreamlit(typed="")

    with pytest.raises(_Stopped):
        _check_password(stub)
    assert stub.errors == []  # nothing typed yet is not a failed attempt


def test_whitespace_only_password_counts_as_unset(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "   ")
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    assert app_password() is None
    assert _check_password(_StubStreamlit()) is True


@pytest.mark.parametrize(
    "variable", ["RAILWAY_ENVIRONMENT", "RAILWAY_PROJECT_ID", "RENDER", "FLY_APP_NAME", "DYNO"]
)
def test_hosting_platforms_are_recognised(monkeypatch, variable):
    for name in ("RAILWAY_ENVIRONMENT", "RAILWAY_PROJECT_ID", "RENDER", "FLY_APP_NAME", "DYNO"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(variable, "1")
    assert is_public_deployment() is True


def test_the_key_is_not_baked_into_the_image():
    """The Dockerfile must never carry a credential."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for name in ("Dockerfile", "Procfile", "railway.json", ".streamlit/config.toml"):
        text = (root / name).read_text(encoding="utf-8")
        assert "sk-ant-" not in text
        assert "ANTHROPIC_API_KEY=" not in text


def test_dotenv_is_ignored_by_git_and_docker():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    assert ".env" in (root / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in (root / ".dockerignore").read_text(encoding="utf-8").splitlines()
