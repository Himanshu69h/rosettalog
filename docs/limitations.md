# Limitations

## Current known limitations

- Drain may over-merge or over-split templates. Labeled verification fixtures can expose false matches and missed positives, but the learning system cannot guarantee perfect resolution outside the tested cases.
- Multi-line events require an explicit continuation rule; not solved in Gate 0.
- Raw retention and privacy masking are in tension. Raw-first retention is
  implemented; normalized-field masking is **STUB** and is not currently
  performed (the envelope marks `flags.masked` false).
- Scale is extrapolated rather than measured at billion-event volume.
- The OCSF alignment is intentionally a subset and should be confirmed with the relevant problem owner.

## Gate 0 note

These are documented limits, not hidden assumptions. The project intentionally surfaces them rather than claiming they are resolved.

## Gate 3 note

Verification reports are local files and are not signed attestations. Activation
checks that a referenced report is successful and matches the parser name and
version; protect parser files and reports from unauthorized modification.
Throughput figures in `docs/benchmarks.md` measure the checked-in sample under
the documented command only.

## Gate 4 and freeze status

- **UNTESTED:** Docker image build, Compose startup, and network-disabled runtime
  check. Docker is not installed in the implementation environment.
- **STUB:** CSV parsing, multiline event assembly, normalized-field masking,
  duplicate suppression/linking, Grok export, and ML-specific export.
- The API has no authentication or authorization. Compose binds to loopback and
  uses an internal network, but deployments must add an authenticated boundary
  before exposing the API to other hosts.
- Drift is evaluated per supplied batch; there is no scheduler, long-term
  baseline store, or statistically calibrated threshold.
- Parser inference and verification use bounded labeled fixtures, not a
  representative production corpus. No billion-event or separate-machine test
  has been run.
- The measured throughput result excludes registry loading and file I/O and
  repeats a three-record fixture; it is not an end-to-end pipeline benchmark.
