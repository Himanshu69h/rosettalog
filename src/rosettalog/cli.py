from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import typer
from jsonschema import FormatChecker, ValidationError, validate

from rosettalog.analytics import ParquetSink, query_events
from rosettalog.ingest import Ingestor
from rosettalog.parsing import ParserRegistry
from rosettalog.rawstore import RawStore, RawStoreError

app = typer.Typer(add_completion=False, no_args_is_help=True, help="RosettaLog CLI")


@app.command()
def health() -> None:
    """Return health information for the service."""
    typer.echo("OK")


@app.command()
def version() -> None:
    """Display the package version."""
    typer.echo("0.1.0")


@app.command()
def run(
    input_file: Path,
    raw_store: Path = typer.Option(Path("raw_store"), "--raw-store"),
    parquet_root: Path = typer.Option(Path("parquet"), "--parquet"),
    parser_dir: Path = typer.Option(Path("parsers"), "--parsers"),
    parser_schema: Path = typer.Option(Path("schemas/parser.schema.json"), "--parser-schema"),
    envelope_schema: Path = typer.Option(
        Path("schemas/envelope.schema.json"), "--envelope-schema"
    ),
    max_line_bytes: int = typer.Option(65_536, min=1, max=65_536),
) -> None:
    """Ingest one file, preserving raw records and writing parsed events."""
    store = RawStore(raw_store, max_record_bytes=max_line_bytes)
    registry = ParserRegistry(parser_dir, parser_schema)
    ingestor = Ingestor(
        store,
        registry,
        envelope_schema_path=envelope_schema,
        max_line_bytes=max_line_bytes,
    )
    report = ingestor.ingest_file(input_file)
    parquet_path = ParquetSink(parquet_root).write_events(list(report.events))
    typer.echo(
        json.dumps(
            {
                "source_id": report.source_id,
                "records_seen": report.records_seen,
                "events_written": len(report.events),
                "quarantined": len(report.quarantined),
                "parquet_file": str(parquet_path) if parquet_path is not None else None,
            },
            sort_keys=True,
        )
    )


@app.command()
def trace(
    event_id: str,
    raw_store: Path = typer.Option(Path("raw_store"), "--raw-store"),
) -> None:
    """Show an event's envelope and verified source bytes."""
    store = RawStore(raw_store)
    event_path = raw_store / "events.jsonl"
    if not event_path.exists():
        typer.echo(f"No event ledger found in {raw_store}", err=True)
        raise typer.Exit(code=1)
    refs = {
        (ref.source_id, ref.byte_offset, ref.line_no): ref
        for ref in store.records()
    }
    for line in event_path.read_text(encoding="utf-8").splitlines():
        envelope = json.loads(line)
        if envelope.get("event_id") != event_id:
            continue
        source = envelope["source"]
        ref = refs.get((source["id"], source["byte_offset"], source["line_no"]))
        if ref is None:
            typer.echo("Event has no corresponding rawstore index entry", err=True)
            raise typer.Exit(code=1)
        raw = store.read(ref)
        if hashlib.sha256(raw).hexdigest() != envelope["raw_sha256"]:
            typer.echo("Event raw hash does not match rawstore", err=True)
            raise typer.Exit(code=1)
        typer.echo(
            json.dumps(
                {
                    "envelope": envelope,
                    "raw_record": {
                        "sequence": ref.sequence,
                        "frame_offset": ref.frame_offset,
                        "sha256": ref.sha256,
                        "verified": True,
                        "bytes_utf8": raw.decode("utf-8"),
                    },
                },
                sort_keys=True,
            )
        )
        return
    typer.echo(f"Event not found: {event_id}", err=True)
    raise typer.Exit(code=1)


@app.command("verify-event")
def verify_event(
    event_file: Path,
    envelope_schema: Path = typer.Option(
        Path("schemas/envelope.schema.json"), "--envelope-schema"
    ),
    raw_store: Path | None = typer.Option(None, "--raw-store"),
) -> None:
    """Validate an envelope and its raw SHA-256, optionally against rawstore."""
    errors: list[str] = []
    try:
        envelope = json.loads(event_file.read_text(encoding="utf-8"))
        schema = json.loads(envelope_schema.read_text(encoding="utf-8"))
        validate(instance=envelope, schema=schema, format_checker=FormatChecker())
        raw = envelope["raw"].encode("utf-8")
        if hashlib.sha256(raw).hexdigest() != envelope["raw_sha256"]:
            errors.append("raw SHA-256 mismatch")
        if raw_store is not None:
            _verify_envelope_rawstore(envelope, RawStore(raw_store), errors)
    except (OSError, json.JSONDecodeError, ValidationError, KeyError, TypeError) as error:
        errors.append(str(error))
    _report_verification(errors)


@app.command("verify-store")
def verify_store(
    raw_store: Path = typer.Argument(Path("raw_store")),
    envelope_schema: Path = typer.Option(
        Path("schemas/envelope.schema.json"), "--envelope-schema"
    ),
) -> None:
    """Verify rawstore frames, indexes, event schemas, and raw lineage."""
    errors: list[str] = []
    if not raw_store.exists():
        errors.append(f"rawstore does not exist: {raw_store}")
        _report_verification(errors)
        return
    store = RawStore(raw_store)
    verification = store.verify()
    errors.extend(verification.errors)
    event_path = raw_store / "events.jsonl"
    if event_path.exists():
        try:
            schema = json.loads(envelope_schema.read_text(encoding="utf-8"))
            refs = {
                (ref.source_id, ref.byte_offset, ref.line_no): ref for ref in store.records()
            }
            for line_no, line in enumerate(event_path.read_text(encoding="utf-8").splitlines(), 1):
                try:
                    envelope = json.loads(line)
                    validate(instance=envelope, schema=schema, format_checker=FormatChecker())
                    _verify_envelope_rawstore(envelope, store, errors, refs)
                except (json.JSONDecodeError, ValidationError, KeyError, TypeError) as error:
                    errors.append(f"event ledger line {line_no}: {error}")
        except (OSError, json.JSONDecodeError, RawStoreError) as error:
            errors.append(str(error))
    typer.echo(
        json.dumps(
            {
                "valid": not errors,
                "records_checked": verification.records_checked,
                "errors": errors,
            },
            sort_keys=True,
        )
    )
    if errors:
        raise typer.Exit(code=1)


@app.command()
def query(
    sql: str,
    parquet_root: Path = typer.Option(Path("parquet"), "--parquet"),
) -> None:
    """Run a read-only SQL SELECT against ingested Parquet events."""
    try:
        rows = query_events(parquet_root, sql)
    except (ValueError, OSError, Exception) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error
    typer.echo(json.dumps(rows, sort_keys=True, default=str))


def _verify_envelope_rawstore(
    envelope: dict[str, Any],
    store: RawStore,
    errors: list[str],
    refs: dict[tuple[str, int, int], Any] | None = None,
) -> None:
    source = envelope["source"]
    index = refs or {
        (ref.source_id, ref.byte_offset, ref.line_no): ref for ref in store.records()
    }
    ref = index.get((source["id"], source["byte_offset"], source["line_no"]))
    if ref is None:
        errors.append(f"event {envelope.get('event_id')} has no rawstore index entry")
        return
    try:
        raw = store.read(ref)
    except RawStoreError as error:
        errors.append(str(error))
        return
    raw_hash = hashlib.sha256(raw).hexdigest()
    if raw_hash != envelope.get("raw_sha256") or raw.decode("utf-8") != envelope.get("raw"):
        errors.append(f"event {envelope.get('event_id')} raw bytes do not match its envelope")


def _report_verification(errors: list[str]) -> None:
    typer.echo(json.dumps({"valid": not errors, "errors": errors}, sort_keys=True))
    if errors:
        raise typer.Exit(code=1)


def main() -> None:
    """CLI entrypoint."""
    app()


if __name__ == "__main__":
    main()
