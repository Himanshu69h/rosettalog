# RosettaLog benchmark

Measured parser throughput for this invocation; this is not a scale extrapolation.

The input file and parser registry are loaded before timing. The timer covers repeated `ParserRegistry.parse` calls only; it excludes ingestion, raw storage, envelope validation, Parquet, and file I/O. This is not an end-to-end pipeline benchmark.
This run parsed the fixture's 3 records for 1000 iterations (3000 parser calls).
Reproduce it from the repository root with:

```powershell
.\.venv\Scripts\python.exe -m rosettalog bench samples\known\asa.log --report docs\benchmarks.md --iterations 1000
```

```json
{
  "coverage": 1.0,
  "elapsed_seconds": 0.23225970000021334,
  "input_file": "samples\\known\\asa.log",
  "iterations": 1000,
  "parsed_records": 3000,
  "parser_count": 4,
  "platform": "Windows-10-10.0.26200-SP0",
  "python_version": "3.11.9",
  "records_per_iteration": 3,
  "records_per_second": 12916.57571243416,
  "records_processed": 3000
}
```
