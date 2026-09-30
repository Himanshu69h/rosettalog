# RosettaLog Benchmarks

## End-to-end pipeline

Each format used 100,000 deterministic synthetic records generated with seed `2026`. The timer includes raw-store append, parsing, normalized-envelope validation, event-ledger writes, final durability syncs, and Parquet serialization. Input bounds and the parser registry are checked before timing; ingestion rereads the source inside the timer. All records parsed, all rows were written to Parquet, and no records were quarantined.

Benchmark mode batches raw-store syncs every 1,000 records and syncs event-ledger files once after ingestion. Final syncs are included in the timer. Normal `rosetta run` retains per-record syncs. The four format runs were launched concurrently on the same host; per-core throughput is aggregate events/sec divided by the host's 8 logical CPUs, not a parallel-scaling claim.

Environment: Windows 10 build 26200, Python 3.11.9, 8 logical CPUs.

| Format | Records | Parquet rows | Elapsed (s) | Events/s | Events/s/logical core |
|---|---:|---:|---:|---:|---:|
| ASA syslog | 100,000 | 100,000 | 153.49 | 651.50 | 81.44 |
| FortiGate key/value | 100,000 | 100,000 | 158.69 | 630.15 | 78.77 |
| CEF | 100,000 | 100,000 | 137.94 | 724.97 | 90.62 |
| JSON | 100,000 | 100,000 | 137.55 | 726.98 | 90.87 |

The measurements use synthetic data and local temporary storage. They are not production estimates or billion-event-scale claims.

Reproduce the generated inputs and the end-to-end runs from the repository root:

```powershell
.\.venv\Scripts\python.exe samples\generate.py --records-per-format 100000 --seed 2026
.\.venv\Scripts\python.exe -m rosettalog bench samples\benchmark\asa.log --report $env:TEMP\rosettalog-bench-asa.md
.\.venv\Scripts\python.exe -m rosettalog bench samples\benchmark\fortigate.log --report $env:TEMP\rosettalog-bench-fortigate.md
.\.venv\Scripts\python.exe -m rosettalog bench samples\benchmark\cef.log --report $env:TEMP\rosettalog-bench-cef.md
.\.venv\Scripts\python.exe -m rosettalog bench samples\benchmark\json.log --report $env:TEMP\rosettalog-bench-json.md
```

## Unseen-format onboarding

The Northstar key/value format was not in the runtime parser registry. CLI learning of 3 records and verification of 3 positive plus 1 negative case produced a valid report in 1.9228 seconds.

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_onboarding.py
```

## Parser-only microbenchmark

This result is intentionally labeled as a microbenchmark. It repeats the three-record checked-in ASA fixture 1,000 times (3,000 parser calls), with 100% sample coverage. It excludes raw storage, envelope validation, event-ledger writes, and Parquet; it is not comparable to the end-to-end figures above.

```powershell
.\.venv\Scripts\python.exe -m rosettalog bench samples\known\asa.log --micro --iterations 1000 --report $env:TEMP\rosettalog-microbenchmark.md
```

Measured: 3,000 records, 0.4564 seconds, 6,573.84 parser calls/sec, 100% coverage on the fixture.
