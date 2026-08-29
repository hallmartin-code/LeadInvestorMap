"""Lead Investor Map - command line and Streamlit entry point.

    python app.py --deck deck.pdf --support targets.csv --support notes.md
    streamlit run app.py

The same file serves both: when Streamlit is running the process, the browser UI is
rendered; otherwise the arguments are parsed and the run happens on the terminal.
"""

from __future__ import annotations

import argparse
import hmac
import sys
from pathlib import Path

from src.ingestion.loader import SUPPORTED_EXTENSIONS
from src.models.evidence import SourceType
from src.pipeline import PipelineOptions, run, write_outputs
from src.reporting.json_exporter import load_json
from src.reporting.pdf_generator import render
from src.reporting.template import blank_map
from src.utils.config import (
    EmailSettings,
    ExitCode,
    anthropic_key,
    app_password,
    is_public_deployment,
    llm_provider,
)
from src.utils.logging import configure, get_logger
from src.web import theme

ROLE_CHOICES = {
    "deck": SourceType.PITCH_DECK,
    "list": SourceType.INVESTOR_LIST,
    "crm": SourceType.CRM_EXPORT,
    "notes": SourceType.MEETING_NOTES,
    "research": SourceType.INVESTOR_RESEARCH,
    "diligence": SourceType.DILIGENCE_DOC,
}


# --- CLI ---------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lead-investor-map",
        description=("Build a one-page Lead Investor Map from a pitch deck and investor materials."),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Supported inputs: " + ", ".join(sorted(SUPPORTED_EXTENSIONS)) + "\n"
            "Round values you supply are labelled USER PROVIDED and override the deck.\n"
            "Each run is emailed to REPORT_EMAIL_TO (default Info@tencapital.group) when\n"
            "RESEND_API_KEY is set. Use --no-email to suppress it."
        ),
    )
    parser.add_argument("--deck", help="Pitch deck: .pdf, .pptx or .ppt")
    parser.add_argument(
        "--support",
        action="append",
        default=[],
        metavar="PATH",
        help="Supporting file (repeatable): investor list, CRM export, notes, research",
    )
    parser.add_argument(
        "--role",
        action="append",
        default=[],
        metavar="PATH=ROLE",
        help=f"Declare a file's role explicitly. ROLE is one of: {', '.join(ROLE_CHOICES)}",
    )
    parser.add_argument("--out", help="Output directory (default: OUTPUT_DIR or ./output)")
    parser.add_argument("--stem", help="Output filename stem (default: the company name)")

    model = parser.add_argument_group("model")
    model.add_argument(
        "--provider",
        choices=["anthropic", "openai", "local"],
        help="LLM provider. 'local' means rule-based extraction with no model calls.",
    )
    model.add_argument(
        "--no-llm",
        action="store_true",
        help="Rule-based extraction only (same as --provider local)",
    )
    model.add_argument(
        "--research",
        dest="research",
        action="store_true",
        default=None,
        help="Enable public investor research (needs a search backend key)",
    )
    model.add_argument("--no-research", dest="research", action="store_false", help="Disable public research")

    round_group = parser.add_argument_group(
        "round overrides (labelled USER PROVIDED and preferred over the deck)"
    )
    round_group.add_argument("--stage", help='e.g. "Series A"')
    round_group.add_argument("--raise-amount", dest="raise_amount", help='e.g. "$6M"')
    round_group.add_argument("--instrument", help="Priced Equity | SAFE | Convertible Note")
    round_group.add_argument("--pre-money", dest="pre_money", help='e.g. "$18M"')
    round_group.add_argument("--post-money", dest="post_money", help='e.g. "$24M"')
    round_group.add_argument("--cap", dest="safe_cap", help="SAFE valuation cap")
    round_group.add_argument("--committed", help='e.g. "$1.5M"')
    round_group.add_argument("--circled", help="Soft-circled amount")
    round_group.add_argument("--close", dest="target_close", help='e.g. "October 2026"')

    parser.add_argument("--no-csv", action="store_true", help="Skip the CSV export")

    email = parser.add_argument_group("email")
    email.add_argument(
        "--no-email",
        action="store_true",
        help="Do not email the result (default: email when RESEND_API_KEY is set)",
    )
    email.add_argument(
        "--email-to",
        metavar="ADDRESS",
        help="Override the recipient (default: REPORT_EMAIL_TO, else Info@tencapital.group)",
    )
    parser.add_argument(
        "--from-json",
        metavar="PATH",
        help="Re-render outputs from a saved analysis JSON instead of re-analysing",
    )
    parser.add_argument(
        "--template",
        nargs="?",
        const="lead_investor_map_TEMPLATE.pdf",
        metavar="PATH",
        help=(
            "Write the blank document template - structure, field slots and vocabularies "
            "only, with no company data - and exit"
        ),
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Debug logging")
    return parser


def write_template(target: str, directory: Path | None = None) -> int:
    """Render the blank document template through the ordinary renderer.

    Using the same renderer is the point: the template cannot describe a layout the
    application does not actually produce.
    """
    path = Path(target)
    if not path.is_absolute() and directory is not None:
        path = directory / path.name

    result = render(blank_map(), path)
    print()
    print("  Lead Investor Map - blank document template")
    print(f"  {'-' * 68}")
    print("  Structure, field slots and fixed vocabularies only. No company data.")
    print(f"  Pages: {result.pages}")
    print()
    print(f"  PDF    {result.path}")
    print()
    return int(ExitCode.OK if result.fits else ExitCode.RENDER_FAILURE)


def parse_roles(pairs: list[str]) -> dict[str, SourceType]:
    roles: dict[str, SourceType] = {}
    for pair in pairs:
        if "=" not in pair:
            raise SystemExit(f"--role expects PATH=ROLE, got: {pair}")
        path, role = pair.rsplit("=", 1)
        role = role.strip().lower()
        if role not in ROLE_CHOICES:
            raise SystemExit(f"Unknown role {role!r}. Choose from: {', '.join(ROLE_CHOICES)}")
        roles[path.strip()] = ROLE_CHOICES[role]
    return roles


def cli(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure(verbose=args.verbose)
    log = get_logger()

    if args.template:
        return write_template(args.template, Path(args.out) if args.out else None)

    overrides = {
        key: getattr(args, key)
        for key in (
            "stage",
            "raise_amount",
            "instrument",
            "pre_money",
            "post_money",
            "safe_cap",
            "committed",
            "circled",
            "target_close",
        )
        if getattr(args, key)
    }

    options = PipelineOptions(
        deck_path=args.deck,
        supporting_paths=list(args.support),
        roles=parse_roles(args.role),
        round_overrides=overrides,
        use_llm=not args.no_llm and args.provider != "local",
        provider_name=args.provider,
        public_research=args.research,
        output_directory=Path(args.out) if args.out else None,
        output_stem=args.stem,
        write_csv=not args.no_csv,
        send_email=not args.no_email,
        email_to=args.email_to,
    )

    if args.from_json:
        analysis = load_json(args.from_json)
        result = write_outputs(analysis, options)
    else:
        if not args.deck and not args.support:
            build_parser().print_help()
            print("\nA pitch deck (--deck) is required, or at least one --support file.")
            return int(ExitCode.UNSUPPORTED_FILE)
        result = run(options)

    analysis = result.analysis
    print()
    print(f"  {analysis.company.display_name} - Lead Investor Map")
    print(f"  {'-' * 68}")
    print(
        f"  Round        {analysis.round.stage.display()} / {analysis.round.raise_amount.display()} / "
        f"{analysis.round.instrument.display()}"
    )
    print(
        f"  Committed    {analysis.round.committed.display()}   Remaining "
        f"{analysis.round.remaining.display()}   Close {analysis.round.target_close.display()}"
    )
    print(f"  Lead check   {analysis.lead_requirement.display()} (estimated)")
    print(f"  Prospects    {len(analysis.prospects)}")
    print()
    if analysis.lead_shortlist:
        print("  Lead candidates")
        for entry in analysis.lead_shortlist:
            print(
                f"    {entry.rank}. {entry.investor_name:38} {entry.lead_confidence.value:7} "
                f"{entry.check_display:16} {entry.lead_evidence[:42]}"
            )
    else:
        print("  Lead candidates: none met the standard on the evidence supplied.")
    print()
    if analysis.highest_pull_commitment.investor_name:
        print(
            f"  Highest pull: {analysis.highest_pull_commitment.investor_name} "
            f"({analysis.highest_pull_commitment.confidence} confidence)"
        )
    errors = [w for w in analysis.warnings if w.severity == "error"]
    warns = [w for w in analysis.warnings if w.severity == "warning"]
    if errors or warns:
        print(f"  Warnings: {len(errors)} error(s), {len(warns)} warning(s)")
        for warning in (errors + warns)[:5]:
            print(f"    - {warning.message}")
    print()
    for label, path in (
        ("PDF   ", result.pdf_path),
        ("JSON  ", result.json_path),
        ("Sources", result.sources_path),
        ("CSV   ", result.csv_path),
    ):
        if path:
            print(f"  {label} {path}")
    print()
    print(f"  Email  {result.email.summary()}")
    print()

    if result.pdf_path is None:
        log.error("no PDF was produced")
        return int(ExitCode.RENDER_FAILURE)
    return int(ExitCode.OK)


# --- Streamlit ----------------------------------------------------------------------------


def _check_password(st) -> bool:  # pragma: no cover - exercised by hand
    """Gate the app behind APP_PASSWORD.

    Every analysis spends API credit, so an ungated public URL is a standing bill. When no
    password is set the app runs open on localhost, and refuses to run on a hosting
    platform rather than quietly serving the world.
    """
    secret = app_password()

    if not secret:
        if is_public_deployment():
            st.error(
                "APP_PASSWORD is not set. This app is deployed publicly and every visitor "
                "would spend your Anthropic credit, so it will not run until you set a "
                "password in the Railway variables."
            )
            st.stop()
        return True

    if st.session_state.get("authenticated"):
        return True

    theme.brand(st)
    with theme.card(
        st,
        eyebrow="Restricted",
        title="Lead Investor Map",
        lede="Enter the access password to continue.",
    ):
        entered = st.text_input("Password", type="password", label_visibility="collapsed")
    theme.footer(st)

    if not entered:
        st.stop()
    if not hmac.compare_digest(entered, secret):
        st.error("Incorrect password.")
        st.stop()

    st.session_state["authenticated"] = True
    return True


def streamlit_app() -> None:  # pragma: no cover - exercised by hand
    import tempfile

    import streamlit as st

    st.set_page_config(
        page_title="Lead Investor Map | TEN Capital Network",
        page_icon=theme.page_icon(),
        layout="wide",
    )
    theme.inject(st)
    _check_password(st)

    theme.brand(st)

    with st.sidebar:
        st.header("Run settings")
        # The configured provider leads the list, so a deployment set to LLM_PROVIDER=local
        # does not present a model engine as its default.
        engines = ["anthropic", "openai", "local (rule-based)"]
        configured = llm_provider()
        default = "local (rule-based)" if configured == "local" else configured
        if default in engines:
            engines.insert(0, engines.pop(engines.index(default)))
        provider = st.selectbox(
            "Analysis engine",
            engines,
            help="'local' makes no model calls. Extraction is rule-based and narrative is shorter.",
        )
        research = st.checkbox(
            "Enable public investor research",
            value=False,
            help="Requires a search backend API key. Without one, nothing is fetched.",
        )
        write_csv = st.checkbox("Also export CSV", value=True)

        email_settings = EmailSettings.from_env()
        send_email = st.checkbox(
            f"Email the result to {email_settings.default_to}",
            value=email_settings.available and email_settings.enabled,
            disabled=not email_settings.available,
            help=(
                "Sends the one-pager and CSV via Resend."
                if email_settings.available
                else "Set RESEND_API_KEY to enable email."
            ),
        )
        email_to = st.text_input(
            "Send to",
            value=email_settings.default_to,
            disabled=not send_email,
            help="Comma-separated for more than one recipient.",
        )
        st.divider()
        st.subheader("Round parameters")
        st.caption("Anything entered here overrides the deck and is labelled USER PROVIDED.")
        stage = st.text_input("Stage", placeholder="Series A")
        raise_amount = st.text_input("Amount being raised", placeholder="$6M")
        instrument = st.selectbox("Instrument", ["", "Priced Equity", "SAFE", "Convertible Note", "Other"])
        pre_money = st.text_input("Target pre-money valuation", placeholder="$18M")
        safe_cap = st.text_input("SAFE cap", placeholder="$12M")
        committed = st.text_input("Amount committed", placeholder="$1.5M")
        circled = st.text_input("Amount circled", placeholder="$500k")
        target_close = st.text_input("Target close date", placeholder="October 2026")

    # One card, as the mockup draws it: headline, both dropzones, the button and the
    # disclosure inside a single raised surface rather than floating on the ground.
    with theme.card(
        st,
        eyebrow="Lead Investor Map",
        title=theme.two_tone("Pitch Deck", "Who Can Lead This Round"),
        lede=(
            "Upload a deck and whatever investor material exists. You get a one-page PDF "
            "naming who can realistically lead, who can only follow, and in what order to "
            "approach them. Nothing is invented: what the sources do not establish is "
            "shown as NOT PROVIDED."
        ),
    ):
        deck_column, support_column = st.columns(2, gap="large")
        with deck_column:
            deck_file = st.file_uploader(
                "Pitch deck - required",
                type=list(theme.DECK_TYPES),
                accept_multiple_files=False,
            )
        with support_column:
            support_files = st.file_uploader(
                "Investor material - optional",
                type=list(theme.SUPPORT_TYPES),
                accept_multiple_files=True,
                help=(
                    "Target lists, CRM exports, meeting notes, investor research. Without "
                    "these there is no pipeline to map, only the round parameters."
                ),
            )
        theme.hint(st, st.get_option("server.maxUploadSize"))

        build = st.button(
            "Generate the Lead Investor Map",
            type="primary",
            width="stretch",
            disabled=deck_file is None,
        )
        theme.disclosure(st)

    if not anthropic_key() and llm_provider() == "anthropic":
        st.warning(
            "No ANTHROPIC_API_KEY is configured, so the analysis will fall back to "
            "rule-based extraction. Set the key in your environment or Railway variables."
        )
    if not build:
        theme.footer(st)
        st.stop()

    workdir = Path(tempfile.mkdtemp(prefix="lim_"))
    deck_path = workdir / deck_file.name
    deck_path.write_bytes(deck_file.getbuffer())

    support_paths: list[str] = []
    for uploaded in support_files or []:
        path = workdir / uploaded.name
        path.write_bytes(uploaded.getbuffer())
        support_paths.append(str(path))

    overrides = {
        "stage": stage,
        "raise_amount": raise_amount,
        "instrument": instrument,
        "pre_money": pre_money,
        "safe_cap": safe_cap,
        "committed": committed,
        "circled": circled,
        "target_close": target_close,
    }
    overrides = {k: v for k, v in overrides.items() if v}

    options = PipelineOptions(
        deck_path=str(deck_path),
        supporting_paths=support_paths,
        round_overrides=overrides,
        use_llm=not provider.startswith("local"),
        provider_name=None if provider.startswith("local") else provider,
        public_research=research,
        output_directory=workdir / "out",
        write_csv=write_csv,
        send_email=send_email,
        email_to=email_to if send_email else None,
    )

    with st.spinner("Reading documents, classifying investors, building the map..."):
        try:
            result = run(options)
        except Exception as exc:
            st.error(f"The run failed: {exc}")
            st.stop()

    analysis = result.analysis
    with theme.card(
        st,
        eyebrow="Analysis complete",
        title=analysis.company.display_name,
        lede=analysis.company.one_liner.display(),
    ):
        snapshot = st.columns(5)
        snapshot[0].metric("Stage", theme.md_safe(analysis.round.stage.display()))
        snapshot[1].metric("Raise", theme.md_safe(analysis.round.raise_amount.display()))
        snapshot[2].metric("Committed", theme.md_safe(analysis.round.committed.display()))
        snapshot[3].metric("Remaining", theme.md_safe(analysis.round.remaining.display()))
        snapshot[4].metric("Lead cheque", theme.md_safe(analysis.lead_requirement.display()))

    errors = [w for w in analysis.warnings if w.severity == "error"]
    warnings = [w for w in analysis.warnings if w.severity == "warning"]
    for warning in errors:
        st.error(warning.message)
    for warning in warnings:
        st.warning(warning.message)

    if result.email.sent:
        st.success(result.email.summary())
    elif result.email.error:
        st.warning(f"{result.email.summary()} Your files below are unaffected.")
    elif send_email:
        st.info(result.email.summary())

    with theme.card(st, eyebrow="Lead candidates"):
        if analysis.lead_shortlist:
            st.dataframe(
                [
                    {
                        "#": entry.rank,
                        "Investor": entry.investor_name,
                        "Confidence": entry.lead_confidence.value,
                        "Cheque": entry.check_display,
                        "Evidence": entry.lead_evidence,
                        "Relationship": entry.relationship,
                        "Next step": f"{entry.required_next_step} ({entry.next_step_owner})",
                    }
                    for entry in analysis.lead_shortlist
                ],
                width="stretch",
                hide_index=True,
            )
        else:
            st.info(
                "No prospect met the lead standard on the evidence supplied. See the "
                "fallback structures in the JSON."
            )

    left, right = st.columns(2, gap="large")
    with left, theme.card(st, eyebrow="Momentum"):
        pull = analysis.highest_pull_commitment
        st.write(
            f"**Highest pull:** {pull.investor_name or 'NOT ESTABLISHED'} "
            f"({pull.confidence} confidence)"
        )
        st.caption(theme.md_safe(pull.rationale))
        for step in analysis.momentum_sequence:
            st.write(f"{step.step}. {step.investor_name} - {step.event}")
    with right, theme.card(st, eyebrow="Disqualified as leads"):
        for item in analysis.disqualified_as_leads[:10]:
            st.write(f"- {theme.md_safe(item.display())}")

    sequence = analysis.outreach_sequence
    if sequence:
        with theme.card(st, eyebrow="Outreach sequence"):
            for phase in (
                sequence.phase_1,
                sequence.phase_2,
                sequence.phase_3,
                sequence.phase_4,
                sequence.hold_back,
            ):
                names = ", ".join(phase.investors) or "none identified"
                st.write(f"**{phase.phase}** - {theme.md_safe(names)}")
                st.caption(phase.objective)

    with theme.card(st, eyebrow="Downloads"):
        download_columns = st.columns(4)
        if result.pdf_path and Path(result.pdf_path).exists():
            download_columns[0].download_button(
                "One-page PDF",
                Path(result.pdf_path).read_bytes(),
                file_name=Path(result.pdf_path).name,
                mime="application/pdf",
                width="stretch",
            )
        if result.json_path:
            download_columns[1].download_button(
                "Analysis JSON",
                Path(result.json_path).read_bytes(),
                file_name=Path(result.json_path).name,
                mime="application/json",
                width="stretch",
            )
        if result.sources_path:
            download_columns[2].download_button(
                "Sources JSON",
                Path(result.sources_path).read_bytes(),
                file_name=Path(result.sources_path).name,
                mime="application/json",
                width="stretch",
            )
        if result.csv_path:
            download_columns[3].download_button(
                "Prospects CSV",
                Path(result.csv_path).read_bytes(),
                file_name=Path(result.csv_path).name,
                mime="text/csv",
                width="stretch",
            )
        st.caption(
            "Download anything you need now: the server filesystem is ephemeral, so these "
            "files are not kept after the session."
        )
    theme.footer(st)


def _running_under_streamlit() -> bool:
    try:
        from streamlit.runtime import exists

        return bool(exists())
    except Exception:
        return False


if _running_under_streamlit():  # pragma: no cover - Streamlit entry
    streamlit_app()
elif __name__ == "__main__":
    sys.exit(cli())
