# Seven-step demo script

Run `.\.venv\Scripts\python.exe scripts\demo.py`. The script creates a unique
temporary output directory and prints every command and report.

| Step | Narration | What to show |
|---|---|---|
| 1. Generate | “We start with deterministic synthetic firewall and perimeter-device samples, so the demo can be repeated without external data.” | `generated\` contains ASA, FortiGate, CEF, and JSON samples. |
| 2. Learn | “The learner clusters the FortiGate records, infers their field types, and emits only a draft parser with a review-queue entry.” | Candidate YAML and `review_queue.jsonl`; state is `draft`. |
| 3. Verify and activate | “A labeled fixture checks coverage, required fields, raw round-trip, and RE2 safety; only a passing report allows activation.” | JSON/HTML report shows both records covered; candidate changes to `active`. |
| 4. Ingest | “The active learned parser ingests the sample while raw bytes, source offsets, the event ledger, and Parquet remain linked.” | `raw_store`, `events.jsonl`, and a Parquet part; both sample records are accepted. |
| 5. Trace | “We trace a normalized event back to its exact raw bytes, then verify the whole store and its hashes.” | `trace` output reports verified raw bytes; `verify-store` returns valid. |
| 6. Query and export | “We query normalized events and export NDJSON, CEF, and syslog while retaining the complete recoverable envelope.” | Query count and all three `events.*` exports. |
| 7. Monitor | “An unseen record lowers parser coverage, marks the active parser drifting, and proposes a separate draft for human review.” | Monitor report shows drift and names a new draft candidate. |

The generated files remain in the printed directory. The data is synthetic;
these results do not represent production or billion-event-scale performance.
