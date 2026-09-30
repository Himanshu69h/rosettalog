# Requirement traceability

This table maps the SIH26156 requirements (a-k) to the implemented code, an
automated evidence point, and the seven-step demo. “Partial” or “UNTESTED” is
used where the repository does not yet demonstrate the full requirement.

| Req | Requirement | Implementation | Automated evidence | Demo |
|---|---|---|---|---|
| a | Lossless raw retention | `src/rosettalog/ingest.py`, `src/rosettalog/rawstore.py`; raw bytes precede decoding and parsing | `tests/test_ingest.py`, `tests/test_rawstore.py` | 4, 5 |
| b | Source-specific fields preserved | `src/rosettalog/parsing.py`; captured but unmapped fields remain in the envelope's `unmapped` object | `tests/test_parser_runtime.py`, `tests/test_ingest.py` | 4 |
| c | Common event taxonomy | `schemas/ocsf_subset.json`, envelope validation, parser mapping | `tests/test_gate0_schemas.py`, `tests/test_envelope_schema.py` | 3, 4 |
| d | Full traceability | deterministic event IDs, raw SHA-256, source offsets, trace and verification CLI | `tests/test_cli.py`, `tests/test_rawstore.py`, `tests/test_ingest.py` | 5 |
| e | Plug-and-play parser onboarding | `src/rosettalog/learning.py`, review queue, verifier and state machine; current parser templates cover ASA-style syslog, FortiGate key/value, CEF, and JSON (CSV is not implemented) | `tests/test_learning.py`, `tests/test_verification.py`, `tests/test_parser_runtime.py` | 1-3, 7 |
| f | Unified visibility | Parquet sink, restricted DuckDB SELECT, API event list, Streamlit event view | `tests/test_analytics.py`, `tests/test_api.py` | 4, 6 |
| g | SIEM/data-lake export | validated NDJSON, CEF, and RFC 5424 syslog exporters preserve the complete envelope | `tests/test_exports.py` | 6 |
| h | AI/ML-ready normalized data | typed Parquet columns plus complete event/unmapped JSON; no model or ML-specific export is included | `tests/test_analytics.py`, `tests/test_exports.py` | 4, 6 |
| i | Reduced parser effort | learn/review workflow and real local throughput measurement; no comparison against manual onboarding or a Grok baseline has been measured | `tests/test_learning.py`, `docs/benchmarks.md` | 2, 3, 6 |
| j | Air-gapped operation | offline runtime dependencies from a wheelhouse, no-network Docker build, internal Compose network | Compose YAML and PowerShell syntax validated; actual Docker/network test is **UNTESTED** because Docker is unavailable | Clean-machine checklist |
| k | Container deployment | non-root Docker image, FastAPI/Streamlit Compose services, loopback ports | Docker/Compose files and airgap script exist; container build/runtime is **UNTESTED** because Docker is unavailable | Clean-machine checklist |

The seven-step demo runs from `scripts/demo.py`; its narration and expected
artifacts are in `docs/demo-script.md`. CSV ingestion, duplicate suppression,
normalized-field masking, Grok export, and full OCSF compliance are outside the
current implementation.
