from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import typer
from jsonschema import FormatChecker, ValidationError, validate

from rosettalog.analytics import ParquetSink, query_events
from rosettalog.benchmarks import (
    run_benchmark,
    run_pipeline_benchmark,
    write_benchmark_report,
    write_pipeline_benchmark_report,
)
from rosettalog.exports import export_events
from rosettalog.ingest import Ingestor
from rosettalog.learning import ParserLearner, ReviewList, YamlEmitter
from rosettalog.monitoring import monitor_file
from rosettalog.parsing import ParserRegistry
from rosettalog.rawstore import RawStore, RawStoreError
from rosettalog.verification import ParserVerifier, transition_parser

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
def learn(
    input_file: Path,
    name: str,
    output_dir: Path = typer.Option(Path("draft_parsers"), "--output"),
    review_list: Path = typer.Option(Path("review_queue.jsonl"), "--review-list"),
    source_format: str = typer.Option("key_value", "--source-format"),
    parser_schema: Path = typer.Option(Path("schemas/parser.schema.json"), "--parser-schema"),
    synonyms: Path = typer.Option(Path("schemas/synonyms.yaml"), "--synonyms"),
) -> None:
    """Learn a parser candidate and leave it in the review queue as a draft."""
    max_file_bytes = 50 * 1024 * 1024
    try:
        if input_file.stat().st_size > max_file_bytes:
            raise ValueError(f"training file exceeds {max_file_bytes} bytes")
        records = [
            line
            for line in input_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        learner = ParserLearner(
            synonyms,
            parser_schema,
            review_list=ReviewList(review_list),
        )
        result = learner.learn(
            records,
            name=name,
            source_format=source_format,
            created_from=str(input_file),
        )
        output_path = YamlEmitter(parser_schema).emit(result.definition, output_dir)
    except (OSError, UnicodeDecodeError, ValueError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error
    typer.echo(
        json.dumps(
            {
                "parser_file": str(output_path),
                "review_list": str(review_list),
                "state": result.definition["state"],
                "records_used": result.records_used,
                "cluster_count": result.cluster_count,
                "inferred_fields": [
                    {
                        "name": field.name,
                        "type": field.field_type,
                        "ocsf_path": field.ocsf_path,
                        "confidence": field.confidence,
                    }
                    for field in result.inferred_fields
                ],
            },
            sort_keys=True,
        )
    )


@app.command()
def verify(
    parser_file: Path,
    cases_file: Path,
    parser_schema: Path = typer.Option(Path("schemas/parser.schema.json"), "--parser-schema"),
    report_dir: Path = typer.Option(Path("verification_reports"), "--report-dir"),
) -> None:
    """Verify a draft parser against labeled JSONL cases and create reports."""
    try:
        verifier = ParserVerifier(parser_schema)
        report = verifier.verify(parser_file, cases_file)
        json_report, html_report = verifier.write_reports(report, report_dir)
        if report.valid:
            transition_parser(
                parser_file,
                "verified",
                parser_schema,
                verify_report_ref=str(json_report.resolve()),
            )
    except (OSError, ValueError, ValidationError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error
    typer.echo(
        json.dumps(
            {
                **report.as_dict(),
                "json_report": str(json_report),
                "html_report": str(html_report),
            },
            sort_keys=True,
        )
    )
    if not report.valid:
        raise typer.Exit(code=1)


@app.command()
def activate(
    parser_file: Path,
    parser_schema: Path = typer.Option(Path("schemas/parser.schema.json"), "--parser-schema"),
) -> None:
    """Activate a parser that has passed verification."""
    try:
        transition_parser(parser_file, "active", parser_schema)
    except (OSError, ValueError, ValidationError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error
    typer.echo(json.dumps({"parser_file": str(parser_file), "state": "active"}))


@app.command()
def bench(
    input_file: Path,
    parser_dir: Path = typer.Option(Path("parsers"), "--parsers"),
    parser_schema: Path = typer.Option(Path("schemas/parser.schema.json"), "--parser-schema"),
    report: Path = typer.Option(Path("docs/benchmarks.md"), "--report"),
    iterations: int = typer.Option(1, min=1, max=1000),
    micro: bool = typer.Option(False, "--micro", help="Run parser-only microbenchmark."),
    envelope_schema: Path = typer.Option(
        Path("schemas/envelope.schema.json"), "--envelope-schema"
    ),
) -> None:
    """Measure end-to-end ingestion and Parquet throughput, or parser-only with --micro."""
    result_data: dict[str, str | int | float]
    try:
        if micro:
            micro_result = run_benchmark(
                input_file,
                parser_dir,
                parser_schema,
                iterations=iterations,
            )
            write_benchmark_report(micro_result, report)
            result_data = micro_result.as_dict()
        else:
            pipeline_result = run_pipeline_benchmark(
                input_file,
                parser_dir,
                parser_schema,
                envelope_schema,
            )
            write_pipeline_benchmark_report(pipeline_result, report)
            result_data = pipeline_result.as_dict()
    except (OSError, UnicodeDecodeError, ValueError, ValidationError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error
    typer.echo(json.dumps({**result_data, "report": str(report)}, sort_keys=True))


@app.command()
def monitor(
    input_file: Path,
    parser_name: str,
    parser_dir: Path = typer.Option(Path("parsers"), "--parsers"),
    parser_schema: Path = typer.Option(Path("schemas/parser.schema.json"), "--parser-schema"),
    synonyms: Path = typer.Option(Path("schemas/synonyms.yaml"), "--synonyms"),
    output_dir: Path = typer.Option(Path("monitor_reports"), "--output"),
    draft_dir: Path = typer.Option(Path("draft_parsers"), "--drafts"),
    review_list: Path = typer.Option(Path("review_queue.jsonl"), "--review-list"),
    min_coverage: float = typer.Option(0.9, min=0.0, max=1.0),
) -> None:
    """Monitor parser coverage and create a draft re-learn proposal on drift."""
    try:
        report = monitor_file(
            input_file,
            parser_name,
            parser_dir,
            parser_schema,
            synonyms,
            output_dir=output_dir,
            draft_dir=draft_dir,
            review_list_path=review_list,
            min_coverage=min_coverage,
        )
    except (OSError, UnicodeDecodeError, ValueError, ValidationError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error
    typer.echo(json.dumps(report.as_dict(), sort_keys=True))


@app.command()
def export(
    event_file: Path,
    output_file: Path,
    output_format: Literal["ndjson", "cef", "syslog"] = typer.Option(
        "ndjson", "--format"
    ),
    envelope_schema: Path = typer.Option(
        Path("schemas/envelope.schema.json"), "--envelope-schema"
    ),
) -> None:
    """Export verified event envelopes as NDJSON, CEF, or RFC 5424 syslog."""
    try:
        count = export_events(event_file, output_file, envelope_schema, output_format)
    except (OSError, UnicodeDecodeError, ValueError, ValidationError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error
    typer.echo(
        json.dumps(
            {"events_exported": count, "format": output_format, "output_file": str(output_file)},
            sort_keys=True,
        )
    )


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
    mask_ips: bool = typer.Option(False, "--mask-ips"),
    ipv4_prefix_length: int = typer.Option(24, "--ipv4-prefix-length", min=0, max=32),
    ipv6_prefix_length: int = typer.Option(64, "--ipv6-prefix-length", min=0, max=128),
    hash_usernames: bool = typer.Option(False, "--hash-usernames"),
    username_hash_salt: str = typer.Option(
        "", "--username-hash-salt", envvar="ROSETTALOG_USERNAME_HASH_SALT", hide_input=True
    ),
) -> None:
    """Ingest one file, preserving raw records and writing parsed events."""
    if hash_usernames and not username_hash_salt:
        raise typer.BadParameter(
            "provide --username-hash-salt or ROSETTALOG_USERNAME_HASH_SALT"
        )
    store = RawStore(raw_store, max_record_bytes=max_line_bytes)
    registry = ParserRegistry(parser_dir, parser_schema)
    ingestor = Ingestor(
        store,
        registry,
        envelope_schema_path=envelope_schema,
        max_line_bytes=max_line_bytes,
        mask_ips=mask_ips,
        ipv4_prefix_length=ipv4_prefix_length,
        ipv6_prefix_length=ipv6_prefix_length,
        hash_usernames=hash_usernames,
        username_hash_salt=username_hash_salt,
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
