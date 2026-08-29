"""Outbound notifications. Email never breaks an analysis."""

from .emailer import EmailOutcome, build_subject, parse_recipients, send_analysis_email

__all__ = ["EmailOutcome", "build_subject", "parse_recipients", "send_analysis_email"]
