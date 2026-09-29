# RosettaLog

RosettaLog is an air-gapped, containerized framework that converts perimeter-network logs into a lossless, traceable, OCSF-aligned event stream. The project is intentionally scoped to perimeter devices and to offline, auditable processing. It does not claim to ingest arbitrary logs or require a networked model.

## Gate 0 status

This repository is the Gate 0 baseline. It contains the frozen schema contracts, CI pipeline, offline Docker build, and documentation skeleton required before runtime parsing features are added.

The current code is intentionally minimal and includes explicit STUB markers where later gates will add behavior.

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

This repository is structured for the Gate 0 baseline and is not yet the fully implemented runtime system described in later gates. Each later gate will add working logic behind the frozen contracts.
