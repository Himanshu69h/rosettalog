# Architecture decisions

## Default decisions for Gate 0

- OCSF alignment is intentionally a subset rather than full OCSF compliance.
- The normalized copy may be masked; the raw store is never modified.
- `unmapped` is the retention mechanism for vendor-specific fields.
- RE2 is the default matching engine for untrusted patterns.
- The project is intentionally offline and deterministic by design.

These choices are explicit defaults and should be revisited only in a later gate with a reviewed change.
