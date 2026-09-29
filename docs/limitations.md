# Limitations

## Current known limitations

- Drain may over-merge or over-split templates. Verify will flag such cases, but the learning system cannot guarantee perfect resolution in every format.
- Multi-line events require an explicit continuation rule; not solved in Gate 0.
- Raw retention and privacy masking are in tension; the design chooses raw-first preservation with a masked normalized copy.
- Scale is extrapolated rather than measured at billion-event volume.
- The OCSF alignment is intentionally a subset and should be confirmed with the relevant problem owner.

## Gate 0 note

These are documented limits, not hidden assumptions. The project intentionally surfaces them rather than claiming they are resolved.
