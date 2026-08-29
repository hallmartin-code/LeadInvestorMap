"""The command-line entry point."""

from __future__ import annotations

import json

import pytest

from app import build_parser, cli, parse_roles
from src.models.evidence import SourceType
from src.utils.config import ExitCode


def test_roles_are_parsed(tmp_path):
    roles = parse_roles(["targets.csv=list", "notes.md=notes"])
    assert roles["targets.csv"] == SourceType.INVESTOR_LIST
    assert roles["notes.md"] == SourceType.MEETING_NOTES


def test_an_unknown_role_is_rejected():
    with pytest.raises(SystemExit):
        parse_roles(["targets.csv=nonsense"])


def test_round_overrides_are_exposed_as_flags():
    args = build_parser().parse_args(
        ["--deck", "d.pdf", "--raise-amount", "$6M", "--close", "October 2026", "--cap", "$12M"]
    )
    assert args.raise_amount == "$6M"
    assert args.target_close == "October 2026"
    assert args.safe_cap == "$12M"


def test_no_arguments_exits_with_guidance(capsys):
    code = cli([])
    assert code == int(ExitCode.UNSUPPORTED_FILE)
    assert "pitch deck" in capsys.readouterr().out


def test_a_full_run_writes_every_output(deck_path, investors_csv, notes_path, tmp_path, capsys):
    out = tmp_path / "cli-out"
    code = cli(
        [
            "--deck",
            str(deck_path),
            "--support",
            str(investors_csv),
            "--support",
            str(notes_path),
            "--no-llm",
            "--out",
            str(out),
        ]
    )
    assert code == int(ExitCode.OK)

    printed = capsys.readouterr().out
    assert "Lead Investor Map" in printed
    assert "Lead candidates" in printed

    files = {p.suffix for p in out.iterdir()}
    assert {".pdf", ".json", ".csv"} <= files


def test_csv_can_be_skipped(deck_path, tmp_path):
    out = tmp_path / "nocsv"
    cli(["--deck", str(deck_path), "--no-llm", "--no-csv", "--out", str(out)])
    assert not any(p.suffix == ".csv" for p in out.iterdir())


def test_outputs_can_be_regenerated_from_saved_json(deck_path, investors_csv, tmp_path):
    first = tmp_path / "first"
    cli(["--deck", str(deck_path), "--support", str(investors_csv), "--no-llm", "--out", str(first)])
    saved = next(p for p in first.iterdir() if p.name.endswith("_map.json"))

    second = tmp_path / "second"
    code = cli(["--from-json", str(saved), "--out", str(second), "--no-llm"])
    assert code == int(ExitCode.OK)

    original = json.loads(saved.read_text(encoding="utf-8"))
    regenerated = next(p for p in second.iterdir() if p.name.endswith("_map.json"))
    reloaded = json.loads(regenerated.read_text(encoding="utf-8"))
    assert [p["investor_name"] for p in reloaded["prospects"]] == [
        p["investor_name"] for p in original["prospects"]
    ]


def test_a_missing_deck_file_does_not_crash_the_run(tmp_path, investors_csv, capsys):
    out = tmp_path / "missing"
    code = cli(
        [
            "--deck",
            str(tmp_path / "nope.pdf"),
            "--support",
            str(investors_csv),
            "--no-llm",
            "--out",
            str(out),
        ]
    )
    assert code == int(ExitCode.OK)
    assert "error" in capsys.readouterr().out.lower()
    assert (out / "COMPANY_NOT_IDENTIFIED_lead_investor_map.pdf").exists()
