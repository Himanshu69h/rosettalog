# RosettaLog benchmark

Measured parser throughput for this invocation; this is not a scale extrapolation.
The three-line ASA fixture was parsed 1000 times (3000 record parses total).
Registry loading, regex compilation, and input-file I/O are outside the timed
region, so compare only runs made with the same benchmark method.

Reproduce with:

```powershell
python -m rosettalog bench samples\known\asa.log --report docs\benchmarks.md --iterations 1000
```

```json
{
  "coverage": 1.0,
  "elapsed_seconds": 0.2382356000002801,
  "input_file": "samples\\known\\asa.log",
  "iterations": 1000,
  "parsed_records": 3000,
  "parser_count": 4,
  "platform": "Windows-10-10.0.26200-SP0",
  "python_version": "3.11.9",
  "records_per_iteration": 3,
  "records_per_second": 12592.576424331513,
  "records_processed": 3000
}
```
