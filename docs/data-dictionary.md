# RosettaLog data dictionary

## Scope

The envelope is a RosettaLog contract aligned with a small OCSF subset. It is
not a full OCSF event implementation. Fields in the event object are validated
by `schemas/envelope.schema.json`; source/vendor additions not mapped to the
common event remain in `unmapped`.

## Event envelope

| Field | Type | Meaning |
|---|---|---|
| `event_id` | 64-character lowercase hex string | Deterministic SHA-256 of source ID, byte offset, and raw-record SHA-256 |
| `ingest_time` | RFC 3339 string | UTC time assigned by the ingestion run |
| `source.id` | string | First 16 hex characters of SHA-256 over the resolved input path |
| `source.file` | string | Input path recorded for traceability |
| `source.byte_offset` | non-negative integer | Zero-based byte offset of the raw record |
| `source.line_no` | positive integer | One-based record number |
| `raw` | string | UTF-8 view of the original record; line terminator is retained when present |
| `raw_sha256` | 64-character lowercase hex string | Digest of the exact stored raw bytes |
| `parser.name` | string | Parser definition used for this event |
| `parser.version` | positive integer | Parser definition version |
| `parser.confidence` | number from 0 to 1 | Lowest configured confidence among mapped fields; 1.0 when no field is mapped |
| `event` | object | Common OCSF-aligned fields plus permitted additions |
| `unmapped` | object | Parsed source fields that were not mapped to common event fields |
| `flags` | object | Duplicate, timezone-assumption, and masking status |

The rawstore is authoritative for exact bytes. It stores each line as its own
Zstandard frame in `records.zst`; `index.jsonl` provides frame and source
coordinates, byte sizes, and a SHA-256 digest.

## Common event fields

| Field | Type | Meaning |
|---|---|---|
| `event.time` | RFC 3339 string | Normalized timestamp in UTC |
| `event.class_uid` | integer or null | Numeric class identifier when configured |
| `event.class_name` | string | One of the supported OCSF-aligned classes |
| `event.activity_id` | integer or null | Activity identifier; currently initialized to `0` |
| `event.action` | string | Normalized action; parser-specific action is case-folded |
| `event.severity` | string or null | Source severity when mapped |
| `event.src_endpoint.ip` | string or null | Source IP when mapped |
| `event.src_endpoint.port` | integer or null | Source port when mapped |
| `event.dst_endpoint.ip` | string or null | Destination IP when mapped |
| `event.dst_endpoint.port` | integer or null | Destination port when mapped |
| `event.protocol_name` | string or null | Normalized protocol when mapped |
| `event.message` | string or null | Event message when mapped |
| `event.time_source` | string | Additional field indicating the timestamp source when fallback logic applies |

Nested event objects permit additional properties so a parser can preserve
future taxonomy fields without modifying the frozen envelope schema.

## Flags

| Field | Type | Current behavior |
|---|---|---|
| `flags.duplicate_of` | string or null | Always null; duplicate linking is not implemented |
| `flags.duplicate_count` | non-negative integer | Always zero; duplicate suppression is not implemented |
| `flags.tz_assumed` | boolean | True when ingestion applies its configured/default timezone to a timezone-less value |
| `flags.masked` | boolean | False; no normalized-field masking policy is currently implemented |

## Parquet query columns

The Parquet sink flattens commonly queried envelope properties into typed
columns: event and source identifiers, source byte offset and line number,
parser name/version/confidence, event time/class/action, source and destination
IP, protocol, and JSON strings for the full normalized event, unmapped fields,
and flags. `raw` and `raw_sha256` remain available for lineage checks.

## Known data-model limits

The supported class list is `Network Activity`, `Authentication`, and
`Detection Finding`. Vendor fields are retained only when the selected parser
captures them. CSV input parsing, normalized-field masking, and duplicate
linking are not implemented.
