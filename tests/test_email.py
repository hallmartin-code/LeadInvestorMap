"""Email notifications.

The governing rule under test: **email never breaks an analysis.** Every failure mode
returns an EmailOutcome describing what happened, and the files are produced regardless.
No test here reaches the network - the transport is stubbed in every case.
"""

from __future__ import annotations

import base64
import json

import pytest

from src.notifications.emailer import (
    MAX_ATTACHMENT_BYTES,
    EmailOutcome,
    build_html,
    build_subject,
    build_text,
    parse_recipients,
    send_analysis_email,
)
from src.pipeline import PipelineOptions, run
from src.utils.config import DEFAULT_REPORT_TO, EmailSettings
from tests.test_reporting import build_analysis


class _Response:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class _Transport:
    """Captures the request instead of sending it."""

    def __init__(self, response: _Response | Exception) -> None:
        self.response = response
        self.calls: list[dict] = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


@pytest.fixture
def transport(monkeypatch):
    """Install a stub `requests` module inside the emailer's import site."""

    def install(response):
        stub = _Transport(response)
        import sys
        import types

        module = types.ModuleType("requests")
        module.post = stub.post
        monkeypatch.setitem(sys.modules, "requests", module)
        return stub

    return install


@pytest.fixture
def settings():
    return EmailSettings(
        api_key="re_test_key",
        from_addr="TEN Capital <reports@tencapital.group>",
        default_to=DEFAULT_REPORT_TO,
        enabled=True,
    )


@pytest.fixture
def files(tmp_path):
    pdf = tmp_path / "map.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake one-pager")
    csv = tmp_path / "map.csv"
    csv.write_text("investor_name\nA Fund\n", encoding="utf-8")
    return pdf, csv


# --- recipients -------------------------------------------------------------------------------


def test_the_default_recipient_is_the_ten_capital_inbox():
    assert DEFAULT_REPORT_TO == "Info@tencapital.group"
    assert EmailSettings.from_env().default_to == "Info@tencapital.group"


def test_recipient_lists_are_split_and_validated():
    assert parse_recipients("Info@tencapital.group") == ["Info@tencapital.group"]
    assert parse_recipients("a@b.co, c@d.io; e@f.org") == ["a@b.co", "c@d.io", "e@f.org"]
    assert parse_recipients("not-an-address") == []
    assert parse_recipients("") == []
    assert parse_recipients("good@example.com, broken") == ["good@example.com"]


# --- message body -----------------------------------------------------------------------------


def test_subject_states_the_headline_finding():
    analysis = build_analysis()
    subject = build_subject(analysis)
    assert subject.startswith("Lead Investor Map: Testco")
    assert "Series A" in subject
    assert "qualified lead" in subject


def test_subject_says_so_when_nothing_qualifies():
    analysis = build_analysis()
    for prospect in analysis.prospects:
        prospect.tier = None
    assert "no qualified lead" in build_subject(analysis)


def test_html_body_carries_the_decision_content():
    analysis = build_analysis()
    html = build_html(analysis, "disclaimer text")

    for heading in (
        "Round snapshot",
        "Lead candidates",
        "Momentum",
        "Outreach sequence",
        "Gaps and risks",
        "Disqualified as leads",
        "Run detail",
    ):
        assert heading in html
    assert "disclaimer text" in html
    assert analysis.lead_shortlist[0].investor_name in html


def test_text_body_mirrors_the_html():
    analysis = build_analysis()
    text = build_text(analysis, "disclaimer text")
    assert "ROUND SNAPSHOT" in text
    assert "LEAD CANDIDATES" in text
    assert analysis.lead_shortlist[0].investor_name in text
    assert "disclaimer text" in text


def test_bodies_report_an_empty_shortlist_honestly():
    analysis = build_analysis()
    analysis.lead_shortlist = []
    html = build_html(analysis, "d")
    text = build_text(analysis, "d")
    assert "No prospect met the lead standard" in html
    assert "None. No prospect met the lead standard" in text


def test_investor_names_cannot_inject_markup():
    analysis = build_analysis()
    analysis.lead_shortlist[0].investor_name = "<script>alert(1)</script> Capital"
    html = build_html(analysis, "d")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_missing_values_reach_the_email_as_not_provided():
    analysis = build_analysis()
    analysis.round.target_close = analysis.round.target_close.__class__.missing("Target close")
    assert "NOT PROVIDED" in build_text(analysis, "d")


# --- sending ----------------------------------------------------------------------------------


def test_a_successful_send_reports_the_message_id(transport, settings, files):
    transport(_Response(200, {"id": "msg_123"}))
    pdf, csv = files

    outcome = send_analysis_email(build_analysis(), pdf, config=settings, extra_attachments=[csv])

    assert outcome.sent is True
    assert outcome.message_id == "msg_123"
    assert outcome.to == ["Info@tencapital.group"]
    assert "Emailed to Info@tencapital.group" in outcome.summary()


def test_the_request_is_shaped_the_way_resend_expects(transport, settings, files):
    stub = transport(_Response(200, {"id": "msg_1"}))
    pdf, csv = files

    send_analysis_email(build_analysis(), pdf, config=settings, extra_attachments=[csv])
    request = stub.calls[0]

    assert request["url"] == "https://api.resend.com/emails"
    assert request["headers"]["Authorization"] == "Bearer re_test_key"
    payload = request["json"]
    assert payload["from"] == "TEN Capital <reports@tencapital.group>"
    assert payload["to"] == ["Info@tencapital.group"]
    assert payload["subject"] and payload["html"] and payload["text"]

    names = [a["filename"] for a in payload["attachments"]]
    assert names == ["map.pdf", "map.csv"]
    assert base64.b64decode(payload["attachments"][0]["content"]) == pdf.read_bytes()


def test_an_explicit_recipient_overrides_the_default(transport, settings, files):
    stub = transport(_Response(200, {"id": "m"}))
    outcome = send_analysis_email(build_analysis(), files[0], to="someone@example.com", config=settings)
    assert outcome.to == ["someone@example.com"]
    assert stub.calls[0]["json"]["to"] == ["someone@example.com"]


def test_reply_to_is_included_when_configured(transport, files):
    stub = transport(_Response(200, {"id": "m"}))
    settings = EmailSettings(api_key="k", reply_to="deals@tencapital.group")
    send_analysis_email(build_analysis(), files[0], config=settings)
    assert stub.calls[0]["json"]["reply_to"] == "deals@tencapital.group"


# --- the failure modes, none of which may raise --------------------------------------------------


def test_no_api_key_skips_rather_than_fails(files):
    outcome = send_analysis_email(build_analysis(), files[0], config=EmailSettings(api_key=None))
    assert outcome.sent is False
    assert outcome.skipped == "no RESEND_API_KEY configured"


def test_disabled_email_skips(files):
    settings = EmailSettings(api_key="k", enabled=False)
    outcome = send_analysis_email(build_analysis(), files[0], config=settings)
    assert outcome.skipped == "email disabled"


def test_an_invalid_recipient_is_reported_not_sent(transport, files):
    transport(_Response(200, {"id": "m"}))
    settings = EmailSettings(api_key="k", default_to="not-an-address")
    outcome = send_analysis_email(build_analysis(), files[0], config=settings)
    assert outcome.sent is False
    assert "not a valid email address" in outcome.skipped


def test_a_network_failure_is_caught(transport, settings, files):
    transport(ConnectionError("dns exploded"))
    outcome = send_analysis_email(build_analysis(), files[0], config=settings)
    assert outcome.sent is False
    assert "could not reach Resend" in outcome.error


def test_an_unverified_domain_gets_an_actionable_message(transport, settings, files):
    transport(_Response(403, {"message": "You can only send testing emails to your own email address"}))
    outcome = send_analysis_email(build_analysis(), files[0], config=settings)
    assert outcome.sent is False
    assert "verify" in outcome.error.lower()
    assert "resend.com/domains" in outcome.error
    assert "reports@tencapital.group" in outcome.error


@pytest.mark.parametrize(
    "status,fragment",
    [
        (401, "rejected the API key"),
        (422, "could not accept the message"),
        (429, "rate limit"),
        (500, "Resend returned 500"),
    ],
)
def test_api_errors_are_explained(transport, settings, files, status, fragment):
    transport(_Response(status, {"message": "detail from resend"}))
    outcome = send_analysis_email(build_analysis(), files[0], config=settings)
    assert outcome.sent is False
    assert fragment in outcome.error


def test_a_non_json_error_body_is_still_reported(transport, settings, files):
    transport(_Response(500, None, text="<html>gateway error</html>"))
    outcome = send_analysis_email(build_analysis(), files[0], config=settings)
    assert outcome.sent is False
    assert "500" in outcome.error


def test_a_missing_attachment_does_not_stop_the_send(transport, settings, tmp_path):
    stub = transport(_Response(200, {"id": "m"}))
    outcome = send_analysis_email(build_analysis(), tmp_path / "never_rendered.pdf", config=settings)
    assert outcome.sent is True
    assert "attachments" not in stub.calls[0]["json"]


def test_an_oversized_attachment_is_dropped_not_sent(transport, settings, tmp_path, monkeypatch):
    stub = transport(_Response(200, {"id": "m"}))
    big = tmp_path / "big.pdf"
    big.write_bytes(b"x" * 2048)
    monkeypatch.setattr("src.notifications.emailer.MAX_ATTACHMENT_BYTES", 1024)

    outcome = send_analysis_email(build_analysis(), big, config=settings)
    assert outcome.sent is True
    assert "attachments" not in stub.calls[0]["json"]
    assert MAX_ATTACHMENT_BYTES > 1024  # the real cap is generous


# --- pipeline integration -------------------------------------------------------------------------


def test_the_pipeline_emails_and_records_the_outcome(monkeypatch, deck_path, investors_csv, tmp_path):
    sent: dict = {}

    def fake_send(analysis, pdf_path, **kwargs):
        sent["company"] = analysis.company.display_name
        sent["pdf"] = pdf_path
        sent["extras"] = list(kwargs.get("extra_attachments") or [])
        return EmailOutcome(sent=True, to=["Info@tencapital.group"], message_id="msg_1")

    monkeypatch.setattr("src.pipeline.send_analysis_email", fake_send)

    result = run(
        PipelineOptions(
            deck_path=deck_path,
            supporting_paths=[investors_csv],
            use_llm=False,
            output_directory=tmp_path / "out",
        )
    )

    assert result.email.sent is True
    assert sent["company"] == "Testco"
    assert sent["pdf"] == result.pdf_path
    assert result.csv_path in sent["extras"]

    # The saved JSON records the notification, because email happens before it is written.
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert any("Emailed to Info@tencapital.group" in w["message"] for w in payload["warnings"])


def test_no_email_flag_suppresses_the_send(monkeypatch, deck_path, tmp_path):
    def explode(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("email must not be attempted when send_email is False")

    monkeypatch.setattr("src.pipeline.send_analysis_email", explode)

    result = run(
        PipelineOptions(
            deck_path=deck_path,
            use_llm=False,
            send_email=False,
            output_directory=tmp_path / "out",
        )
    )
    assert result.email.sent is False
    assert result.email.skipped == "email disabled for this run"


def test_an_email_failure_leaves_the_analysis_intact(monkeypatch, deck_path, tmp_path):
    monkeypatch.setattr(
        "src.pipeline.send_analysis_email",
        lambda *a, **k: EmailOutcome(to=["Info@tencapital.group"], error="Resend returned 500"),
    )

    result = run(PipelineOptions(deck_path=deck_path, use_llm=False, output_directory=tmp_path / "out"))

    assert result.pdf_path.exists()
    assert result.json_path.exists()
    assert result.email.sent is False
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    warning = next(w for w in payload["warnings"] if w["stage"] == "email")
    assert warning["severity"] == "warning"
    assert "files were produced normally" in warning["message"]


def test_the_test_suite_cannot_send_real_email():
    """The autouse fixture must neutralise both the key and the feature flag."""
    settings = EmailSettings.from_env()
    assert settings.api_key is None
    assert settings.enabled is False
    assert settings.available is False


def test_a_real_send_needs_no_network_in_tests(files):
    """With the fixture defaults, a send is skipped before any transport is touched."""
    outcome = send_analysis_email(build_analysis(), files[0])
    assert outcome.sent is False
    assert outcome.skipped
