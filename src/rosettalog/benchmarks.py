from __future__ import annotations

import json
import platform
import time
from dataclasses import dataclass
from pathlib import Path

from rosettalog.parsing import ParserRegistry


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
        "```json\n"
        f"{payload}\n"
        "```\n",
        encoding="utf-8",
    )
