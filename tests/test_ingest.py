from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from jsonschema import ValidationError, validate

from rosettalog.ingest import Ingestor
from rosettalog.parsing import ParserRegistry
from rosettalog.rawstore import RawStore

ROOT = Path(__file__).resolve().parents[1]
FIXED_TIME = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def setup_ingestor(tmp_path: Path) -> tuple[Ingestor, RawStore]:
    store = RawStore(tmp_path / "raw")
    registry = ParserRegistry(ROOT / "parsers", ROOT / "schemas" / "parser.schema.json")
    ingestor = Ingestor(
        store,
        registry,
        envelope_schema_path=ROOT / "schemas" / "envelope.schema.json",
    )
    return ingestor, store


@pytest.mark.parametrize("filename", ["asa.log", "fortigate.log", "cef.log", "json.log"])
def test_ingest_known_format_produces_traceable_envelope(
    setup_ingestor: tuple[Ingestor, RawStore], tmp_path: Path, filename: str
) -> None:
    ingestor, store = setup_ingestor
    source = ROOT / "samples" / "known" / filename

    result = ingestor.ingest_file(source, ingest_time=FIXED_TIME)

    assert result.records_seen == len(source.read_bytes().splitlines())
    assert result.events
    envelope = result.events[0]
    raw = store.read(store.records()[0])
    assert envelope["raw"] == raw.decode("utf-8")
    assert envelope["raw_sha256"] == hashlib.sha256(raw).hexdigest()
    assert envelope["source"]["byte_offset"] == 0
    assert envelope["event"]["action"]
    assert envelope["flags"]["masked"] is False
    assert (store.root / "events.jsonl").exists()


def test_unknown_record_is_quarantined_without_losing_raw(
    setup_ingestor: tuple[Ingestor, RawStore], tmp_path: Path
) -> None:
    ingestor, store = setup_ingestor
    source = tmp_path / "unknown.log"
    raw = b"unsupported input\r\n"
    source.write_bytes(raw)

    result = ingestor.ingest_file(source, ingest_time=FIXED_TIME)

    assert not result.events
    assert result.quarantined[0].reason_code == "no_parser_match"
    assert store.read(result.quarantined[0].raw_refs[0]) == raw
    stored_quarantine = json.loads((store.root / "quarantine.jsonl").read_text(encoding="utf-8"))
    assert stored_quarantine["reason_code"] == "no_parser_match"


def test_oversized_line_is_chunked_into_rawstore_and_quarantined(
    setup_ingestor: tuple[Ingestor, RawStore], tmp_path: Path
) -> None:
    ingestor, store = setup_ingestor
    ingestor.max_line_bytes = 16
    source = tmp_path / "long.log"
    raw = b"x" * 50 + b"\n"
    source.write_bytes(raw)

    result = ingestor.ingest_file(source, ingest_time=FIXED_TIME)

    assert result.quarantined[0].reason_code == "line_too_large"
    refs = result.quarantined[0].raw_refs
    assert b"".join(store.read(ref) for ref in refs) == raw
    assert store.verify().valid


def test_ingest_event_ids_and_output_are_deterministic(
    setup_ingestor: tuple[Ingestor, RawStore], tmp_path: Path
) -> None:
    ingestor, _ = setup_ingestor
    source = tmp_path / "event.jsonl"
    source.write_bytes((ROOT / "samples" / "known" / "json.log").read_bytes())

    first = ingestor.ingest_file(source, ingest_time=FIXED_TIME).events[0]
    second = ingestor.ingest_file(source, ingest_time=FIXED_TIME).events[0]

    assert first["event_id"] == second["event_id"]
    assert first["raw_sha256"] == second["raw_sha256"]


def test_adversarial_records_are_quarantined_and_retained(
    setup_ingestor: tuple[Ingestor, RawStore], tmp_path: Path
) -> None:
    ingestor, store = setup_ingestor
    ingestor.max_line_bytes = 16
    source = tmp_path / "hostile.log"
    source.write_bytes(b"bad\xffutf8\n{\"time\":\nunknown-record\n" + b"x" * 40 + b"\n")

    result = ingestor.ingest_file(source, ingest_time=FIXED_TIME)

    reason_codes = [record.reason_code for record in result.quarantined]
    assert "invalid_utf8" in reason_codes
    assert "line_too_large" in reason_codes
    assert "no_parser_match" in reason_codes
    assert store.verify().valid
    assert len(store.records()) == result.records_seen + len(
        result.quarantined[-1].raw_refs
    ) - 1


def test_invalid_typed_value_is_quarantined_with_raw_retained(
    setup_ingestor: tuple[Ingestor, RawStore], tmp_path: Path
) -> None:
    ingestor, store = setup_ingestor
    source = tmp_path / "invalid-ip.jsonl"
    raw = b'{"time":"2026-09-29T08:15:00Z","src_ip":"999.999.1.1","action":"deny"}\n'
    source.write_bytes(raw)

    result = ingestor.ingest_file(source, ingest_time=FIXED_TIME)

    assert not result.events
    assert result.quarantined[0].reason_code == "parser_error"
    assert store.read(result.quarantined[0].raw_refs[0]) == raw


def test_frozen_envelope_schema_rejects_missing_raw_field() -> None:
    schema = json.loads((ROOT / "schemas" / "envelope.schema.json").read_text(encoding="utf-8"))
    event = json.loads((ROOT / "examples" / "sample-event.json").read_text(encoding="utf-8"))
    del event["raw"]

    with pytest.raises(ValidationError):
        validate(instance=event, schema=schema)