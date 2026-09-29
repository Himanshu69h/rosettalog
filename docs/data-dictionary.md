# RosettaLog data dictionary

## Purpose

This document defines the data model in the Gate 0 baseline. The project is intentionally OCSF-aligned rather than full OCSF-compliant.

## Core envelope fields

| Field | Type | Meaning |
|---|---|---|
| event_id | ULID | Stable identity for the normalized event |
| ingest_time | ISO-8601 | UTC time the event was accepted |
| source.id | string | Source identifier such as `fw01` |
| source.file | string | Source file name or path |
| source.byte_offset | int | File offset where the raw line begins |
| source.line_no | int | Line number of the raw record |
| raw | string | Original line as stored on disk |
| raw_sha256 | hex | SHA-256 of the raw line |
| parser.name | string | Parser or template name |
| parser.version | int | Immutable parser version |
| parser.confidence | float | Confidence score from learning step |
| event.time | ISO-8601 | Normalized event timestamp |
| event.class_name | string | OCSF-aligned class name |
| event.action | string | Normalized action name |
| event.src_endpoint.ip | string | Source IP |
| event.dst_endpoint.ip | string | Destination IP |
| unmapped | object | Vendor or source-specific extras |
| flags | object | Duplicate, timezone, masking flags |

## OCSF-aligned subset

The subset is intentionally limited to the following event classes:

- Network Activity
- Authentication
- Detection Finding

This is documented as "OCSF-aligned" and is not a complete OCSF implementation.

## Data retention and masking

- Raw data is never modified.
- The normalized event may be masked.
- `unmapped` retains vendor-specific attributes not mapped to the core subset.
- The raw store is append-only and hash-verified.
