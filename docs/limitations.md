# Limitations

## Current known limitations

- Drain may over-merge or over-split templates. Labeled verification fixtures can expose false matches and missed positives, but the learning system cannot guarantee perfect resolution outside the tested cases.
- Raw retention and privacy masking are in tension. Raw-first retention is
  implemented; normalized IP truncation and username hashing are opt-in and
  only affect the normalized copy. Raw bytes remain available in the rawstore.
- Scale has been measured on 100,000 synthetic records per format on this
  machine, but not at billion-event volume or on representative production data.
- The OCSF alignment is intentionally a subset and should be confirmed with the relevant problem owner.

## Gate 0 note

These are documented limits, not hidden assumptions. The project intentionally surfaces them rather than claiming they are resolved.

## Gate 3 note

Verification reports are local files and are not signed attestations. Activation
checks that a referenced report is successful and matches the parser name and
version; protect parser files and reports from unauthorized modification.
Throughput figures in `docs/benchmarks.md` include a full local pipeline run on
synthetic fixtures and a separately labeled parser-only microbenchmark.

## Gate 4 and freeze status

- **UNTESTED:** Docker image build, Compose startup, and network-disabled runtime
  check. Docker is not installed in the implementation environment.
- **STUB:** Multiline event assembly (requires explicit continuation rules),
  Grok export, and ML-specific export.
- Duplicate normalized events are linked but never deleted. Matching is limited
  to normalized events within one `ingest_file` call.
- CSV support requires a recognized first-line header and supports a fixed set
  of common columns; it is not a general-purpose schema inference engine.
- **STUB:** API authentication and authorization. Compose binds to loopback and
  uses an internal network, but deployments must add an authenticated boundary
  before exposing the API to other hosts.
- **STUB:** Scheduled drift evaluation and long-term baselines. Drift is
  evaluated per supplied batch; there is no scheduler, persistent baseline
  store, or statistically calibrated threshold.
- Parser inference and verification use bounded labeled fixtures, not a
  representative production corpus. No billion-event or separate-machine test
  has been run.
- The benchmark is synthetic and local; it does not establish production or
  billion-event throughput.
