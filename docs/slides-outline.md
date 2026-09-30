# Five-slide presentation outline

## 1. Problem

- Firewall, router, IDS/IPS, VPN, and proxy logs use incompatible formats.
- Preserve raw evidence and lineage while making common event fields queryable.
- Scope: four parser templates plus header-based CSV; full OCSF is not implemented.

## 2. Solution

- Offline Learn -> Verify -> Run -> Monitor lifecycle.
- Unverified parser definitions remain drafts and cannot be loaded for runtime.
- Raw-first ingestion, reason-coded quarantine, reviewable drift proposals, and
  exports that carry the complete envelope.

## 3. Architecture + requirements a-k

- Show `docs/architecture.md` Mermaid pipeline and the frozen envelope/parser/
  OCSF contracts.
- Walk through traceability table a-k in `docs/requirements-traceability.md`.
- Emphasize typed Parquet, bounded DuckDB SELECT, local API/UI, and the
  internal-only container design.

## 4. Results, including failures

- Hardening suite: 73 tests passed; `pip check`, Ruff, and mypy clean.
- End-to-end at 100,000 records/format: ASA 651.50, FortiGate 630.15, CEF
  724.97, and JSON 726.98 events/sec; see `docs/benchmarks.md` for per-core
  rates, environment, and benchmark sync scope.
- Unseen Northstar onboarding: 3 records learned and 4 cases verified in 1.9228s.
- Parser-only microbenchmark: 3,000 parses at 6,573.84/sec, 100% fixture
  coverage; not an end-to-end throughput claim.
- The end-to-end demo first exposed unsupported inferred `timestamp` values;
  the runtime conversion and UTC normalization were fixed and covered by test.
- Docker/Compose network-disabled run is **UNTESTED** because Docker is
  unavailable; do not present it as a pass.

## 5. Scale + roadmap

- Neither local synthetic benchmark is a billion-event throughput claim.
- **STUB:** Multiline assembly, Grok export, ML-specific export, API
  authentication, and scheduled drift baselines.
- Next: test on a clean machine with Docker, improve CSV schema configuration
  and duplicate scope, add API authentication, and validate against larger
  representative data.
