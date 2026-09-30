from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from rosettalog.cli import app
from rosettalog.monitoring import monitor_file

ROOT = Path(__file__).resolve().parents[1]
PARSER_SCHEMA = ROOT / "schemas" / "parser.schema.json"
runner = CliRunner()


def _active_asa_parser(parser_dir: Path) -> Path:
    parser_dir.mkdir(parents=True, exist_ok=True)
    definition = yaml.safe_load((ROOT / "parsers" / "asa_syslog.yaml").read_text())
    definition["state"] = "active"
    parser_path = parser_dir / "asa_syslog.yaml"
    parser_path.write_text(yaml.safe_dump(definition, sort_keys=False), encoding="utf-8")
    return parser_path


def test_monitor_detects_drift_and_emits_draft_relearn_proposal(tmp_path: Path) -> None:
    parser_dir = tmp_path / "parsers"
    parser_path = _active_asa_parser(parser_dir)
    input_file = tmp_path / "incoming.log"
    asa_line = (ROOT / "samples" / "known" / "asa.log").read_text().splitlines()[0]
    input_file.write_text(asa_line + "\nunknown_event=xyz code=55\n", encoding="utf-8")

    report = monitor_file(
        input_file,
        "asa_syslog",
        parser_dir,
        PARSER_SCHEMA,
        ROOT / "schemas" / "synonyms.yaml",
        output_dir=tmp_path / "reports",
        draft_dir=tmp_path / "drafts",
        review_list_path=tmp_path / "review.jsonl",
        min_coverage=0.75,
    )

    assert report.drift
    assert report.coverage == 0.5
    assert report.candidate_parser
    proposal = tmp_path / "drafts" / f"{report.candidate_parser}.yaml"
    assert yaml.safe_load(proposal.read_text(encoding="utf-8"))["state"] == "draft"
    assert yaml.safe_load(parser_path.read_text(encoding="utf-8"))["state"] == "drifting"
    assert json.loads(Path(report.report_file).read_text(encoding="utf-8"))["drift"] is True
    assert (tmp_path / "review.jsonl").is_file()


def test_monitor_keeps_parser_active_when_coverage_is_stable(tmp_path: Path) -> None:
    parser_dir = tmp_path / "parsers"
    parser_path = _active_asa_parser(parser_dir)
    input_file = ROOT / "samples" / "known" / "asa.log"

    report = monitor_file(
        input_file,
        "asa_syslog",
        parser_dir,
        PARSER_SCHEMA,
        ROOT / "schemas" / "synonyms.yaml",
        output_dir=tmp_path / "reports",
        draft_dir=tmp_path / "drafts",
        review_list_path=tmp_path / "review.jsonl",
        min_coverage=1.0,
    )

    assert not report.drift
    assert report.coverage == 1.0
    assert report.candidate_parser is None
    assert yaml.safe_load(parser_path.read_text(encoding="utf-8"))["state"] == "active"


def test_monitor_cli_reports_drift(tmp_path: Path) -> None:
    parser_dir = tmp_path / "parsers"
    _active_asa_parser(parser_dir)
    input_file = tmp_path / "incoming.log"
    input_file.write_text("new_vendor=1 data=unknown\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "monitor",
            str(input_file),
            "asa_syslog",
            "--parsers",
            str(parser_dir),
            "--parser-schema",
            str(PARSER_SCHEMA),
            "--synonyms",
            str(ROOT / "schemas" / "synonyms.yaml"),
            "--output",
            str(tmp_path / "reports"),
            "--drafts",
            str(tmp_path / "drafts"),
            "--review-list",
            str(tmp_path / "review.jsonl"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["drift"] is True
