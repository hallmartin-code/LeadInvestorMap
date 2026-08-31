"""What must stay true of how this app is deployed.

The web app has no access gate: anyone with the URL can run an analysis, and every
analysis spends API credit. That is a deliberate choice, so what is left to protect is the
credential itself - it must never be baked into an image or committed to the repository.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_the_key_is_not_baked_into_the_image():
    """The Dockerfile must never carry a credential."""
    for name in ("Dockerfile", "Procfile", "railway.json", ".streamlit/config.toml"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "sk-ant-" not in text
        assert "ANTHROPIC_API_KEY=" not in text


def test_dotenv_is_ignored_by_git_and_docker():
    assert ".env" in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()


def test_no_password_gate_survives_anywhere():
    """Removing the gate means removing it everywhere, not leaving a variable that lies."""
    for name in ("app.py", "src/utils/config.py", ".env.example", ".streamlit/config.toml"):
        assert "APP_PASSWORD" not in (ROOT / name).read_text(encoding="utf-8"), name
