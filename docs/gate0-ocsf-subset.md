# Gate 0: OCSF subset and envelope schema

## Scope

The system uses an OCSF-aligned subset rather than a full OCSF implementation. This is a deliberate default for perimeter-device logs and is documented as such.

## Core event fields

### Required normalized event fields
- time
- class_name
- action
- src_endpoint.ip
- dst_endpoint.ip

### Optional normalized event fields
- class_uid
- activity_id
- severity
- src_endpoint.port
- dst_endpoint.port
- protocol_name
- message

## Supported event classes

- Network Activity
- Authentication
- Detection Finding

These cover the minimum event taxonomy required for firewall, VPN, IDS/IPS, and proxy telemetry.

## Vendor retention policy

Any field not recognized by the OCSF subset is stored in `unmapped`. This preserves raw vendor semantics and supports traceability without dropping useful evidence.

## Envelope schema summary

```json
{
  "event_id": "string",
  "ingest_time": "string",
  "source": {"id": "string", "file": "string", "byte_offset": 0, "line_no": 1},
  "raw": "string",
  "raw_sha256": "string",
  "parser": {"name": "string", "version": 1, "confidence": 0.97},
  "event": {"time": "2026-09-29T08:15:00Z", "class_name": "Network Activity", "action": "deny"},
  "unmapped": {"vendor_field": "value"},
  "flags": {"duplicate_of": null, "duplicate_count": 0, "tz_assumed": false, "masked": true}
}
```

## Compliance decision

The raw store is append-only and never modified. Masking only applies to the normalized copy so lossless evidence remains in the raw log store.

This is a compliance-by-design decision and is intentionally documented as such.
