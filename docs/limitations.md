# Limitations

## Current known limitations

- Drain may over-merge or over-split templates. Labeled verification fixtures can expose false matches and missed positives, but the learning system cannot guarantee perfect resolution outside the tested cases.
- Multi-line events require an explicit continuation rule; not solved in Gate 0.
- Raw retention and privacy masking are in tension; the design chooses raw-first preservation with a masked normalized copy.
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
