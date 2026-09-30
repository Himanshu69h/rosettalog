# RosettaLog

RosettaLog is an air-gapped, containerized framework that converts perimeter-network logs into a lossless, traceable, OCSF-aligned event stream. The project is intentionally scoped to perimeter devices and to offline, auditable processing. It does not claim to ingest arbitrary logs or require a networked model.

## Implementation status

Gate 0 is frozen. Gate 1 provides YAML-driven parsing for the four checked-in formats, append-only compressed raw retention, schema-validated envelopes, quarantine, Parquet output, DuckDB queries, and CLI lineage verification. Gate 2 adds offline parser learning, field inference, OCSF alias mapping, draft YAML emission, and a review queue. Gate 3 adds labeled-fixture verification, report-bound parser activation, JSON/HTML reports, and measured parser benchmarks. Gate 4 adds drift monitoring with draft re-learn proposals, lossless-envelope NDJSON/CEF/syslog export, a FastAPI service, and a Streamlit UI.

The Gate 4 Docker/Compose and network-disabled test path are implemented but
**UNTESTED** because Docker is unavailable in the current environment.


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

The parser lifecycle commands are `rosetta learn`, `rosetta verify`, and
`rosetta activate`. Verification fixture format and state transitions are
described in [docs/parser-verification.md](./docs/parser-verification.md).
Drift monitoring and export commands, plus the API/UI service, are described in
[docs/monitoring-export-api.md](./docs/monitoring-export-api.md).
Capture a local parser-throughput measurement with:

```powershell
python -m rosettalog bench samples\known\asa.log --report docs\benchmarks.md
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

Frozen schemas remain the contracts for all later gates. Benchmark measurements
are local runs on the named fixture and must not be interpreted as billion-event
scale results.
