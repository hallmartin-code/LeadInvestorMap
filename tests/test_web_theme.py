"""The screen chrome.

Two things must stay true: the page never claims a capability the application lacks, and
money is never mangled on its way to the browser.
"""

from __future__ import annotations

import re

from src.ingestion.loader import DECK_EXTENSIONS, SUPPORTED_EXTENSIONS
from src.web import theme


def test_money_is_escaped_before_streamlit_reads_it_as_latex():
    """Streamlit renders $...$ as maths, which turns a cheque range into italic algebra."""
    assert theme.md_safe("$3.4M-$6.0M") == r"\$3.4M-\$6.0M"
    assert theme.md_safe("$12M") == r"\$12M"
    assert theme.md_safe("NOT PROVIDED") == "NOT PROVIDED"
    # Every dollar sign that survives must be escaped, so none can open a maths span.
    escaped = theme.md_safe("$1M-$2M")
    assert all(escaped[i - 1] == chr(92) for i, c in enumerate(escaped) if c == "$")


def test_advertised_deck_formats_match_the_parsers():
    advertised = set(theme.deck_formats().split())
    assert advertised == {e.lstrip(".") for e in DECK_EXTENSIONS}


def test_advertised_support_formats_match_the_parsers():
    advertised = set(theme.support_formats().split())
    supported = {e.lstrip(".") for e in SUPPORTED_EXTENSIONS - DECK_EXTENSIONS}
    assert advertised == supported


def test_the_upload_limit_tracks_configuration(monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_MB", "32")
    assert theme.upload_limit() == "up to 32 MB"


def test_the_disclosure_promises_email_only_when_email_is_on(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.setenv("ENABLE_EMAIL", "true")
    assert "emailed" not in theme.disclosure_html()

    monkeypatch.setenv("RESEND_API_KEY", "re_key")
    assert "emailed" in theme.disclosure_html()
    assert "Info@tencapital.group" in theme.disclosure_html()

    monkeypatch.setenv("ENABLE_EMAIL", "false")
    assert "emailed" not in theme.disclosure_html()


def test_the_disclosure_names_the_configured_recipient(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_key")
    monkeypatch.setenv("ENABLE_EMAIL", "true")
    monkeypatch.setenv("REPORT_EMAIL_TO", "deals@tencapital.group")
    assert "deals@tencapital.group" in theme.disclosure_html()


def test_no_recipient_address_is_hard_coded_in_the_markup():
    """The address must come from configuration, never from the stylesheet or template."""
    address = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    assert not address.search(theme.CSS)
    assert not address.search(theme.BRAND_MARK)


def test_the_stylesheet_carries_no_mojibake():
    """The supplied mockup had encoding artefacts; they must not survive into the app."""
    for blob in (theme.CSS, theme.BRAND_MARK):
        assert "\u00c2" not in blob
        assert "\u00e2" not in blob
        blob.encode("ascii", "strict")


def test_the_brand_mark_is_labelled_for_screen_readers():
    assert 'role="img"' in theme.BRAND_MARK
    assert "aria-label" in theme.BRAND_MARK


def test_body_type_never_drops_below_a_readable_size():
    sizes = [float(m) for m in re.findall(r"font-size:(\d+(?:\.\d+)?)px", theme.CSS)]
    assert sizes and min(sizes) >= 10.0
