from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from jsonschema import ValidationError
from typer.testing import CliRunner

from rosettalog.cli import app
from rosettalog.exports import export_events

ROOT = Path(__file__).resolve().parents[1]
ENVELOPE_SCHEMA = ROOT / "schemas" / "envelope.schema.json"
runner = CliRunner()


def _ingest_known_file(tmp_path: Path) -> Path:
    raw_store = tmp_path / "raw_store"
    result = runner.invoke(
        app,
        [
            "run",
            str(ROOT / "samples" / "known" / "json.log"),
            "--raw-store",
            str(raw_store),
            "--parquet",
            str(tmp_path / "parquet"),
            "--parsers",
            str(ROOT / "parsers"),
            "--parser-schema",
            str(ROOT / "schemas" / "parser.schema.json"),
            "--envelope-schema",
            str(ENVELOPE_SCHEMA),
        ],
    )
    assert result.exit_code == 0, result.output
    return raw_store / "events.jsonl"


@pytest.mark.parametrize("output_format", ["ndjson", "cef", "syslog"])
def test_export_formats_preserve_full_envelope(tmp_path: Path, output_format: str) -> None:
    event_file = _ingest_known_file(tmp_path)
    output_file = tmp_path / f"export.{output_format}"
    original = json.loads(event_file.read_text(encoding="utf-8").splitlines()[0])

    count = export_events(event_file, output_file, ENVELOPE_SCHEMA, output_format)
    exported = output_file.read_text(encoding="utf-8").splitlines()[0]

    assert count == 2
    if output_format == "ndjson":
        restored = json.loads(exported)
    elif output_format == "syslog":
        assert exported.startswith("<134>1 ")
        message = json.loads(exported.split(" ", 6)[6])
        restored = json.loads(base64.b64decode(message["envelope_base64"]))
    else:
        assert exported.startswith("CEF:0|RosettaLog|")
        encoded = exported.rsplit("cs1=", 1)[1]
        restored = json.loads(base64.b64decode(encoded))
    assert restored == original
    assert restored["raw"] == original["raw"]


def test_export_command_rejects_invalid_ledger_without_replacing_output(
    tmp_path: Path,
) -> None:
    invalid_file = tmp_path / "invalid.jsonl"
    invalid_file.write_text('{"event_id":"bad"}\n', encoding="utf-8")
    output_file = tmp_path / "existing.ndjson"
    output_file.write_text("preserve me\n", encoding="utf-8")

    with pytest.raises(ValidationError):
        export_events(invalid_file, output_file, ENVELOPE_SCHEMA, "ndjson")

    assert output_file.read_text(encoding="utf-8") == "preserve me\n"


def test_export_cli_accepts_cef_and_writes_output(tmp_path: Path) -> None:
    event_file = _ingest_known_file(tmp_path)
    output_file = tmp_path / "events.cef"
    result = runner.invoke(
        app,
        [
            "export",
            str(event_file),
            str(output_file),
            "--format",
            "cef",
            "--envelope-schema",
            str(ENVELOPE_SCHEMA),
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["events_exported"] == 2
