from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from rosettalog.cli import app
from rosettalog.parsing import ParserRegistry

ROOT = Path(__file__).resolve().parents[1]
runner = CliRunner()


def test_cli_run_trace_verify_and_query(tmp_path: Path) -> None:
    raw_store = tmp_path / "raw"
    parquet = tmp_path / "parquet"
    event_file = tmp_path / "event.json"
    run_result = runner.invoke(
        app,
        [
            "run",
            str(ROOT / "samples" / "known" / "json.log"),
            "--raw-store",
            str(raw_store),
            "--parquet",
            str(parquet),
            "--parsers",
            str(ROOT / "parsers"),
            "--parser-schema",
            str(ROOT / "schemas" / "parser.schema.json"),
            "--envelope-schema",
            str(ROOT / "schemas" / "envelope.schema.json"),
        ],
    )
    assert run_result.exit_code == 0, run_result.output
    run_summary = json.loads(run_result.stdout)
    assert run_summary["events_written"] == 2

    event = json.loads((raw_store / "events.jsonl").read_text(encoding="utf-8").splitlines()[0])
    event_file.write_text(json.dumps(event), encoding="utf-8")
    trace_result = runner.invoke(app, ["trace", event["event_id"], "--raw-store", str(raw_store)])
    verify_event_result = runner.invoke(
        app,
        [
            "verify-event",
            str(event_file),
            "--envelope-schema",
            str(ROOT / "schemas" / "envelope.schema.json"),
            "--raw-store",
            str(raw_store),
        ],
    )
    verify_store_result = runner.invoke(
        app,
        [
            "verify-store",
            str(raw_store),
            "--envelope-schema",
            str(ROOT / "schemas" / "envelope.schema.json"),
        ],
    )
    query_result = runner.invoke(
        app,
        ["query", "SELECT event_id, action FROM events", "--parquet", str(parquet)],
    )

    assert trace_result.exit_code == 0, trace_result.output
    assert json.loads(trace_result.stdout)["raw_record"]["verified"] is True
    assert verify_event_result.exit_code == 0, verify_event_result.output
    assert json.loads(verify_event_result.stdout)["valid"] is True
    assert verify_store_result.exit_code == 0, verify_store_result.output
    assert json.loads(verify_store_result.stdout)["valid"] is True
    assert query_result.exit_code == 0, query_result.output
    assert len(json.loads(query_result.stdout)) == 2


def test_verify_event_rejects_a_tampered_raw_hash(tmp_path: Path) -> None:
    source = ROOT / "samples" / "known" / "json.log"
    raw_store = tmp_path / "raw"
    run_result = runner.invoke(
        app,
        [
            "run",
            str(source),
            "--raw-store",
            str(raw_store),
            "--parquet",
            str(tmp_path / "parquet"),
            "--parsers",
            str(ROOT / "parsers"),
            "--parser-schema",
            str(ROOT / "schemas" / "parser.schema.json"),
            "--envelope-schema",
            str(ROOT / "schemas" / "envelope.schema.json"),
        ],
    )
    assert run_result.exit_code == 0, run_result.output
    event = json.loads((raw_store / "events.jsonl").read_text(encoding="utf-8").splitlines()[0])
    event["raw_sha256"] = "0" * 64
    event_file = tmp_path / "bad.json"
    event_file.write_text(json.dumps(event), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "verify-event",
            str(event_file),
            "--envelope-schema",
            str(ROOT / "schemas" / "envelope.schema.json"),
        ],
    )

    assert result.exit_code == 1
    assert "raw SHA-256 mismatch" in result.stdout


def test_cli_learn_emits_reviewable_draft_only(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "learn",
            str(ROOT / "samples" / "known" / "fortigate.log"),
            "fortigate_candidate",
            "--output",
            str(tmp_path / "drafts"),
            "--review-list",
            str(tmp_path / "review.jsonl"),
            "--parser-schema",
            str(ROOT / "schemas" / "parser.schema.json"),
            "--synonyms",
            str(ROOT / "schemas" / "synonyms.yaml"),
        ],
    )

    assert result.exit_code == 0, result.output
    summary = json.loads(result.stdout)
    assert summary["state"] == "draft"
    assert Path(summary["parser_file"]).exists()
    assert (tmp_path / "review.jsonl").exists()
    registry = ParserRegistry(tmp_path / "drafts", ROOT / "schemas" / "parser.schema.json")
    assert registry.parse(
        (ROOT / "samples" / "known" / "fortigate.log").read_text(encoding="utf-8").splitlines()[0]
    ) is None