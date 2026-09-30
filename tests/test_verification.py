from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from rosettalog.cli import app
from rosettalog.verification import ParserVerifier, transition_parser

ROOT = Path(__file__).resolve().parents[1]
PARSER_SCHEMA = ROOT / "schemas" / "parser.schema.json"
runner = CliRunner()


def _draft_parser(tmp_path: Path) -> Path:
    definition = yaml.safe_load((ROOT / "parsers" / "asa_syslog.yaml").read_text())
    definition["state"] = "draft"
    definition["verify_report_ref"] = None
    parser_path = tmp_path / "asa_candidate.yaml"
    parser_path.write_text(yaml.safe_dump(definition, sort_keys=False), encoding="utf-8")
    return parser_path


def _write_cases(path: Path, raw: str, expected: str | None = "asa_deny") -> None:
    item = {
        "raw": raw,
        "expected_template_id": expected,
        "required_fields": ["action", "src_ip"] if expected else [],
    }
    path.write_text(json.dumps(item) + "\n", encoding="utf-8")


def test_verifier_reports_coverage_required_fields_and_raw_roundtrip(
    tmp_path: Path,
) -> None:
    parser_path = _draft_parser(tmp_path)
    cases_path = tmp_path / "cases.jsonl"
    raw = (ROOT / "samples" / "known" / "asa.log").read_text().splitlines()[0] + "\r\n"
    _write_cases(cases_path, raw)

    verifier = ParserVerifier(PARSER_SCHEMA)
    report = verifier.verify(parser_path, cases_path)
    json_path, html_path = verifier.write_reports(report, tmp_path / "reports")
    result = json.loads(json_path.read_text(encoding="utf-8"))

    assert report.valid
    assert report.coverage == 1.0
    assert report.missing_required_fields == 0
    assert report.roundtrip_failures == 0
    assert result["case_results"][0]["roundtrip_ok"] is True
    assert html_path.is_file()


def test_verifier_detects_overmerge_against_negative_case(tmp_path: Path) -> None:
    parser_path = _draft_parser(tmp_path)
    cases_path = tmp_path / "cases.jsonl"
    raw = (ROOT / "samples" / "known" / "asa.log").read_text().splitlines()[0]
    _write_cases(cases_path, raw, expected=None)

    report = ParserVerifier(PARSER_SCHEMA).verify(parser_path, cases_path)

    assert report.overmerged_cases == 1
    assert not report.valid


def test_verifier_rejects_regex_outside_re2_syntax(tmp_path: Path) -> None:
    parser_path = _draft_parser(tmp_path)
    definition = yaml.safe_load(parser_path.read_text(encoding="utf-8"))
    definition["templates"][0]["regex"] = r"(?=unsafe).*"
    parser_path.write_text(yaml.safe_dump(definition, sort_keys=False), encoding="utf-8")
    cases_path = tmp_path / "cases.jsonl"
    _write_cases(cases_path, "unsafe")

    report = ParserVerifier(PARSER_SCHEMA).verify(parser_path, cases_path)

    assert not report.regex_safe
    assert not report.valid
    assert report.errors


def test_verifier_reports_invalid_typed_values_without_crashing(tmp_path: Path) -> None:
    parser_path = _draft_parser(tmp_path)
    cases_path = tmp_path / "cases.jsonl"
    _write_cases(
        cases_path,
        "Sep 29 08:15:00 fw01 %ASA-4-106023: Deny tcp src 10.0.0.5/443 "
        "dst 203.0.113.999/443 by access-group \"OUTSIDE_IN\"",
    )

    report = ParserVerifier(PARSER_SCHEMA).verify(parser_path, cases_path)

    assert not report.valid
    assert report.covered_cases == 0
    assert report.errors


def test_verify_cli_transitions_only_successful_candidate(tmp_path: Path) -> None:
    parser_path = _draft_parser(tmp_path)
    cases_path = tmp_path / "cases.jsonl"
    raw = (ROOT / "samples" / "known" / "asa.log").read_text().splitlines()[0]
    _write_cases(cases_path, raw)

    result = runner.invoke(
        app,
        [
            "verify",
            str(parser_path),
            str(cases_path),
            "--parser-schema",
            str(PARSER_SCHEMA),
            "--report-dir",
            str(tmp_path / "reports"),
        ],
    )
    definition = yaml.safe_load(parser_path.read_text(encoding="utf-8"))

    assert result.exit_code == 0, result.output
    assert definition["state"] == "verified"
    assert definition["verify_report_ref"]

    activate_result = runner.invoke(
        app,
        ["activate", str(parser_path), "--parser-schema", str(PARSER_SCHEMA)],
    )
    assert activate_result.exit_code == 0, activate_result.output
    assert yaml.safe_load(parser_path.read_text(encoding="utf-8"))["state"] == "active"


def test_parser_state_machine_rejects_unverified_activation(tmp_path: Path) -> None:
    parser_path = _draft_parser(tmp_path)

    with pytest.raises(ValueError, match="cannot transition"):
        transition_parser(parser_path, "active", PARSER_SCHEMA)

    with pytest.raises(ValueError, match="verification report reference"):
        transition_parser(parser_path, "verified", PARSER_SCHEMA)


def test_activation_requires_a_matching_successful_report(tmp_path: Path) -> None:
    parser_path = _draft_parser(tmp_path)
    definition = yaml.safe_load(parser_path.read_text(encoding="utf-8"))
    definition["state"] = "verified"
    report_path = tmp_path / "report.json"
    report_path.write_text(
        json.dumps(
            {
                "valid": True,
                "parser_name": "different",
                "parser_version": definition["version"],
            }
        ),
        encoding="utf-8",
    )
    definition["verify_report_ref"] = str(report_path)
    parser_path.write_text(yaml.safe_dump(definition, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="does not validate this parser version"):
        transition_parser(parser_path, "active", PARSER_SCHEMA)


def test_failed_verification_keeps_parser_draft(tmp_path: Path) -> None:
    parser_path = _draft_parser(tmp_path)
    cases_path = tmp_path / "cases.jsonl"
    _write_cases(cases_path, "not an ASA event")

    result = runner.invoke(
        app,
        [
            "verify",
            str(parser_path),
            str(cases_path),
            "--parser-schema",
            str(PARSER_SCHEMA),
            "--report-dir",
            str(tmp_path / "reports"),
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout)["missing_required_fields"] == 2
    assert yaml.safe_load(parser_path.read_text(encoding="utf-8"))["state"] == "draft"
