from __future__ import annotations

import json
import os
import platform
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import pyarrow.parquet as parquet

from rosettalog.analytics import ParquetSink
from rosettalog.ingest import Ingestor
from rosettalog.parsing import ParserRegistry
from rosettalog.rawstore import RawStore


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    input_file: str
    parser_count: int
    records_per_iteration: int
    iterations: int
    records_processed: int
    parsed_records: int
    coverage: float
    elapsed_seconds: float
    records_per_second: float
    python_version: str
    platform: str

    def as_dict(self) -> dict[str, str | int | float]:
        return {
            "input_file": self.input_file,
            "parser_count": self.parser_count,
            "records_per_iteration": self.records_per_iteration,
            "iterations": self.iterations,
            "records_processed": self.records_processed,
            "parsed_records": self.parsed_records,
            "coverage": self.coverage,
            "elapsed_seconds": self.elapsed_seconds,
            "records_per_second": self.records_per_second,
            "python_version": self.python_version,
            "platform": self.platform,
        }


@dataclass(frozen=True, slots=True)
class PipelineBenchmarkResult:
    input_file: str
    parser_count: int
    records_processed: int
    parsed_records: int
    quarantined_records: int
    parquet_rows: int
    elapsed_seconds: float
    events_per_second: float
    logical_cpus: int
    events_per_second_per_core: float
    python_version: str
    platform: str

    def as_dict(self) -> dict[str, str | int | float]:
        return {
            "input_file": self.input_file,
            "parser_count": self.parser_count,
            "records_processed": self.records_processed,
            "parsed_records": self.parsed_records,
            "quarantined_records": self.quarantined_records,
            "parquet_rows": self.parquet_rows,
            "elapsed_seconds": self.elapsed_seconds,
            "events_per_second": self.events_per_second,
            "logical_cpus": self.logical_cpus,
            "events_per_second_per_core": self.events_per_second_per_core,
            "python_version": self.python_version,
            "platform": self.platform,
        }


def run_pipeline_benchmark(
    input_file: Path,
    parser_dir: Path,
    parser_schema_path: Path,
    envelope_schema_path: Path,
) -> PipelineBenchmarkResult:
    if input_file.stat().st_size > 100 * 1024 * 1024:
        raise ValueError("benchmark input exceeds 100 MiB")
    records_processed = 0
    with input_file.open("rb") as source:
        for line in source:
            records_processed += 1
            if len(line) > 65_536:
                raise ValueError("benchmark input contains a record exceeding 64 KiB")
    if records_processed == 0:
        raise ValueError("benchmark input contains no records")
    if records_processed > 1_000_000:
        raise ValueError("benchmark input exceeds 1000000 records")

    registry = ParserRegistry(parser_dir, parser_schema_path)
    logical_cpus = os.cpu_count() or 1
    with tempfile.TemporaryDirectory(prefix="rosettalog-bench-") as temporary_dir:
        root = Path(temporary_dir)
        store = RawStore(root / "raw", sync_every=1_000)
        ingestor = Ingestor(
            store,
            registry,
            envelope_schema_path=envelope_schema_path,
            sync_event_ledger=False,
        )
        parquet_root = root / "parquet"
        start = time.perf_counter()
        report = ingestor.ingest_file(input_file)
        store.close()
        parquet_path = ParquetSink(parquet_root).write_events(list(report.events))
        elapsed_seconds = time.perf_counter() - start
        parquet_rows = (
            parquet.ParquetFile(parquet_path).metadata.num_rows
            if parquet_path is not None
            else 0
        )

    return PipelineBenchmarkResult(
        input_file=str(input_file),
        parser_count=registry.parser_count,
        records_processed=records_processed,
        parsed_records=len(report.events),
        quarantined_records=len(report.quarantined),
        parquet_rows=parquet_rows,
        elapsed_seconds=elapsed_seconds,
        events_per_second=len(report.events) / elapsed_seconds if elapsed_seconds else 0.0,
        logical_cpus=logical_cpus,
        events_per_second_per_core=(
            len(report.events) / elapsed_seconds / logical_cpus if elapsed_seconds else 0.0
        ),
        python_version=platform.python_version(),
        platform=platform.platform(),
    )


def write_pipeline_benchmark_report(
    result: PipelineBenchmarkResult, output_path: Path
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(result.as_dict(), indent=2, sort_keys=True)
    output_path.write_text(
        "# RosettaLog end-to-end pipeline benchmark\n\n"
        "The timer covers raw-store append, parsing, envelope validation, event-ledger writes, "
        "Parquet serialization, and final syncs. Raw-store sync interval is 1,000 records; "
        "event-ledger files sync once after ingestion. Normal `rosetta run` syncs each record. "
        "Input bounds and the parser registry are checked before timing; "
        "ingestion rereads the source inside the timer. "
        "Events are never removed; quarantined records are reported separately.\n\n"
        "The per-core rate is aggregate throughput divided by the host's logical CPU count; "
        "it is not a claim of parallel scaling.\n\n"
        "```json\n"
        f"{payload}\n"
        "```\n",
        encoding="utf-8",
    )


def run_benchmark(
    input_file: Path,
    parser_dir: Path,
    parser_schema_path: Path,
    *,
    iterations: int = 1,
) -> BenchmarkResult:
    if iterations < 1 or iterations > 1000:
        raise ValueError("iterations must be between 1 and 1000")
    if input_file.stat().st_size > 100 * 1024 * 1024:
        raise ValueError("benchmark input exceeds 100 MiB")
    records = input_file.read_text(encoding="utf-8").splitlines()
    if not records:
        raise ValueError("benchmark input contains no records")
    if any(len(record.encode("utf-8")) > 65_536 for record in records):
        raise ValueError("benchmark input contains a record exceeding 64 KiB")
    if len(records) > 1_000_000:
        raise ValueError("benchmark input exceeds 1000000 records")
    registry = ParserRegistry(parser_dir, parser_schema_path)
    start = time.perf_counter()
    parsed_records = 0
    for _ in range(iterations):
        parsed_records += sum(registry.parse(record) is not None for record in records)
    elapsed_seconds = time.perf_counter() - start
    records_processed = len(records) * iterations
    return BenchmarkResult(
        input_file=str(input_file),
        parser_count=registry.parser_count,
        records_per_iteration=len(records),
        iterations=iterations,
        records_processed=records_processed,
        parsed_records=parsed_records,
        coverage=parsed_records / records_processed,
        elapsed_seconds=elapsed_seconds,
        records_per_second=records_processed / elapsed_seconds if elapsed_seconds else 0.0,
        python_version=platform.python_version(),
        platform=platform.platform(),
    )


def write_benchmark_report(result: BenchmarkResult, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(result.as_dict(), indent=2, sort_keys=True)
    output_path.write_text(
        "# RosettaLog benchmark\n\n"
        "Measured parser throughput for this invocation; this is not a scale extrapolation.\n\n"
        "The input file and parser registry are loaded before timing. The timer "
        "covers repeated `ParserRegistry.parse` calls only; it excludes ingestion, "
        "raw storage, envelope validation, Parquet, and file I/O. This is not an "
        "end-to-end pipeline benchmark.\n\n"
        "```json\n"
        f"{payload}\n"
        "```\n",
        encoding="utf-8",
    )
