"""The screen chrome.

Two things must stay true: the page never claims a capability the application lacks, and
money is never mangled on its way to the browser.
"""

from __future__ import annotations

import re
from pathlib import Path

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
    """Supporting material is anything the loader reads that is not a slide deck.

    PDF appears in both slots: a deck arrives as one, and so do research and diligence
    documents. Only .ppt and .pptx are deck-only, because nothing else is a presentation.
    """
    advertised = set(theme.support_formats().split())
    supported = {e.lstrip(".") for e in SUPPORTED_EXTENSIONS - {".ppt", ".pptx"}}
    assert advertised == supported
    assert advertised <= {e.lstrip(".") for e in SUPPORTED_EXTENSIONS}


def test_the_uploaders_offer_exactly_what_is_advertised():
    """The type= lists and the sub-line come from one place, so they cannot drift apart."""
    assert set(theme.DECK_TYPES) == set(theme.deck_formats().split())
    assert set(theme.SUPPORT_TYPES) == set(theme.support_formats().split())
    assert set(theme.DECK_TYPES) == {e.lstrip(".") for e in DECK_EXTENSIONS}


def test_the_upload_limit_tracks_configuration(monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_MB", "32")
    assert theme.upload_limit() == "up to 32 MB"


def test_the_upload_limit_prefers_the_live_server_ceiling(monkeypatch):
    """The browser enforces the server's limit, so that number wins over the env var."""
    monkeypatch.setenv("MAX_UPLOAD_MB", "32")
    assert theme.upload_limit(64) == "up to 64 MB"


def test_the_hint_states_the_formats_and_the_ceiling():
    """One sub-line per zone: the formats that zone reads, and the real ceiling."""

    class _Stub:
        def __init__(self) -> None:
            self.captured: list[str] = []

        def markdown(self, body, **_kwargs):
            self.captured.append(body)

    deck = _Stub()
    theme.hint(deck, theme.deck_formats(), 64)
    assert deck.captured and "64 MB" in deck.captured[0]
    for extension in theme.DECK_TYPES:
        assert extension in deck.captured[0]

    support = _Stub()
    theme.hint(support, theme.support_formats(), 64)
    for extension in theme.SUPPORT_TYPES:
        assert extension in support.captured[0]


def test_the_deck_label_names_the_formats_a_deck_arrives_in():
    """The page is fed pitch decks; the label says what a deck may be before it is opened."""
    assert "PDF" in theme.DECK_LABEL
    assert "PowerPoint" in theme.DECK_LABEL
    assert {"pdf", "ppt", "pptx"} <= set(theme.DECK_TYPES)


def test_the_card_selector_is_substituted_into_the_stylesheet():
    """A leftover placeholder would silently unstyle every card on the page."""
    assert "%CARD%" not in theme.CSS
    assert theme.CARD in theme.CSS


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


def test_the_dropzone_dressing_matches_the_labels_the_app_passes():
    """The zone's instruction is drawn by a selector keyed to its aria-label, which is the
    widget label. If the two ever drift, the zone silently loses its instruction."""
    for label in (theme.DECK_LABEL, theme.SUPPORT_LABEL):
        assert f'aria-label="{label}"' in theme.CSS
    app_source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    assert "theme.DECK_LABEL" in app_source
    assert "theme.SUPPORT_LABEL" in app_source
    assert '"Pitch deck - required"' not in app_source, "the label must come from theme"


def test_the_upload_icon_is_embedded_rather_than_fetched():
    """A dropzone icon that depends on the network is a dropzone icon that sometimes
    is not there."""
    assert "data:image/svg+xml," in theme.CSS
    assert "%3Csvg" in theme.CSS
