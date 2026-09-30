# Five-slide presentation outline

## 1. Problem

- Firewall, router, IDS/IPS, VPN, and proxy logs use incompatible formats.
- Preserve raw evidence and lineage while making common event fields queryable.
- Scope: four sample parser families; CSV and full OCSF are not implemented.

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

- Current local suite: 64 tests passed; Ruff and mypy clean (capture current
  final validation before presenting).
- Measured parser-only result: 3000 parses, 1.0 sample coverage, 12916.58
  records/sec on the three-line ASA fixture repeated 1000 times. See
  `docs/benchmarks.md` for environment and scope.
- The end-to-end demo first exposed unsupported inferred `timestamp` values;
  the runtime conversion and UTC normalization were fixed and covered by test.
- Docker/Compose network-disabled run is **UNTESTED** because Docker is
  unavailable; do not present it as a pass.

## 5. Scale + roadmap

- The local microbenchmark is not a billion-event throughput claim.
- Next: test on a clean machine with Docker, add CSV and multiline support,
  implement normalized-field masking and duplicate policies, add API
  authentication, and validate against larger representative data.
