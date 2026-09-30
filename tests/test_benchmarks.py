from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from rosettalog.benchmarks import (
    run_benchmark,
    run_pipeline_benchmark,
    write_benchmark_report,
)
from rosettalog.cli import app

ROOT = Path(__file__).resolve().parents[1]
PARSER_SCHEMA = ROOT / "schemas" / "parser.schema.json"
runner = CliRunner()


def test_benchmark_measures_parser_and_writes_report(tmp_path: Path) -> None:
    input_file = ROOT / "samples" / "known" / "asa.log"
    result = run_benchmark(
        input_file,
        ROOT / "parsers",
        PARSER_SCHEMA,
        iterations=2,
    )
    report_path = tmp_path / "benchmarks.md"
    write_benchmark_report(result, report_path)

    assert result.records_processed == 6
    assert result.parsed_records == 6
    assert result.coverage == 1.0
    assert result.elapsed_seconds > 0
    assert result.records_per_second > 0
    report_contents = report_path.read_text(encoding="utf-8")
    assert "not an end-to-end pipeline benchmark" in report_contents
    assert json.loads(
        report_contents.split("```json\n", 1)[1].split("\n```", 1)[0]
    )["records_per_second"] > 0


def test_bench_cli_writes_requested_report(tmp_path: Path) -> None:
    report_path = tmp_path / "benchmarks.md"
    result = runner.invoke(
        app,
        [
            "bench",
            str(ROOT / "samples" / "known" / "asa.log"),
            "--parsers",
            str(ROOT / "parsers"),
            "--parser-schema",
            str(PARSER_SCHEMA),
            "--report",
            str(report_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert report_path.is_file()
    summary = json.loads(result.stdout)
    assert summary["parsed_records"] == 3
    assert summary["parquet_rows"] == 3
    assert summary["events_per_second"] > 0
    assert summary["events_per_second_per_core"] > 0
    assert "end-to-end pipeline benchmark" in report_path.read_text(encoding="utf-8")


def test_pipeline_benchmark_counts_written_events(tmp_path: Path) -> None:
    input_file = ROOT / "samples" / "known" / "asa.log"

    result = run_pipeline_benchmark(
        input_file,
        ROOT / "parsers",
        PARSER_SCHEMA,
        ROOT / "schemas" / "envelope.schema.json",
    )

    assert result.records_processed == 3
    assert result.parsed_records == 3
    assert result.quarantined_records == 0
    assert result.parquet_rows == 3
    assert result.events_per_second > 0
    assert result.events_per_second_per_core > 0
