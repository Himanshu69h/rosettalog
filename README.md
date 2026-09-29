# RosettaLog

RosettaLog is an air-gapped, containerized framework that converts perimeter-network logs into a lossless, traceable, OCSF-aligned event stream. The project is intentionally scoped to perimeter devices and to offline, auditable processing. It does not claim to ingest arbitrary logs or require a networked model.

## Implementation status

Gate 0 is frozen. Gate 1 now provides YAML-driven parsing for the four checked-in formats, append-only compressed raw retention, schema-validated envelopes, quarantine, Parquet output, DuckDB queries, and CLI lineage verification.

Remaining work is explicitly marked STUB until its gate is implemented:

- STUB: Gate 2 parser learning, field inference, OCSF mapping, YAML emission, and review workflow.
- STUB: Gate 3 verification reports, parser state machine, and benchmark command.
- STUB: Gate 4 drift monitoring, export formats, FastAPI service, Streamlit UI, and airgap test.

## Product scope

- In scope: firewalls, routers, IDS/IPS, VPN appliances, proxies
- Formats: syslog, key/value, CSV, JSON, CEF
- Air-gapped, offline operation
- Lossless raw retention and lineage
- OCSF-aligned normalized events
- Parser lifecycle: learn -> verify -> run -> monitor

## Repository layout

```text
rosettalog/
├── Makefile
├── README.md
├── LICENSE
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── .github/workflows/ci.yml
├── docs/
│   ├── architecture.md
│   ├── data-dictionary.md
│   ├── requirements-traceability.md
│   ├── benchmarks.md
│   ├── limitations.md
│   ├── decisions.md
│   └── gate0-brief.md
├── schemas/
│   ├── envelope.schema.json
│   ├── parser.schema.json
│   ├── ocsf_subset.json
│   └── synonyms.yaml
├── parsers/
│   ├── asa_syslog.yaml
│   ├── fortigate_kv.yaml
│   ├── cef_generic.yaml
│   └── json_generic.yaml
├── samples/
│   ├── generate.py
│   ├── known/
│   ├── unseen/
│   └── adversarial/
├── src/rosettalog/
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py
│   ├── models.py
│   └── ...
├── tests/
│   └── test_gate0_schemas.py
└── wheels/
```

## Quick start

```bash
make vendor
python -m pytest -q
python -m mypy src
python -m ruff check .
```

Or with Docker:

```bash
docker compose build
```

## Security and compliance choices

- Raw bytes are kept unchanged in an append-only store.
- Normalized copies may be masked according to configurable rules.
- Vendor-specific fields are retained in `unmapped` rather than silently discarded.
- No outbound network is required; the design is deterministic and offline.

## Gate 0 freeze

The following schemas are intentionally frozen at this stage:

- `schemas/envelope.schema.json`
- `schemas/parser.schema.json`
- `schemas/ocsf_subset.json`

These are baseline contracts for the rest of the system and should not be changed without explicit approval.

## Notes

Frozen schemas remain the contracts for all later gates. The STUB list above is the current implementation boundary; benchmark and accuracy results will be documented only after real runs.
