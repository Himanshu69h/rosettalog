# Architecture decisions

## Default decisions for Gate 0

- OCSF alignment is intentionally a subset rather than full OCSF compliance.
- Normalized IP truncation and username hashing are opt-in policies. They run
  after raw retention; the raw store and envelope `raw`/`raw_sha256` are never
  modified. Username hashing may use a configured salt.
- Duplicate normalized events are retained; later occurrences point to the
  first event ID and carry an occurrence count. No event is suppressed.
- `unmapped` is the retention mechanism for vendor-specific fields.
- RE2 is the default matching engine for untrusted patterns.
- The project is intentionally offline and deterministic by design.

These decisions are current defaults; policy changes should be reviewed and
covered by tests before changing runtime behavior.
