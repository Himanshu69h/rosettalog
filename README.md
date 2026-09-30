# RosettaLog

RosettaLog is an air-gapped, containerized framework that converts perimeter-network logs into a lossless, traceable, OCSF-aligned event stream. The project is intentionally scoped to perimeter devices and to offline, auditable processing. It does not claim to ingest arbitrary logs or require a networked model.

## Implementation status

Gate 0 is frozen. Gate 1 provides YAML-driven parsing for four checked-in formats plus header-based CSV parsing, append-only compressed raw retention, schema-validated envelopes, quarantine, Parquet output, DuckDB queries, and CLI lineage verification. Gate 2 adds offline parser learning, field inference, OCSF alias mapping, draft YAML emission, and a review queue. Gate 3 adds labeled-fixture verification, report-bound parser activation, JSON/HTML reports, and benchmark commands. Gate 4 adds drift monitoring with draft re-learn proposals, lossless-envelope NDJSON/CEF/syslog export, a FastAPI service, and a Streamlit UI. Hardening adds opt-in normalized IP/username masking and duplicate linkage without deleting events.

The Gate 4 Docker/Compose and network-disabled test path are implemented but
**UNTESTED** because Docker is unavailable in the current environment.

## Product scope

- In scope: firewalls, routers, IDS/IPS, VPN appliances, proxies
- Formats: ASA-style syslog, key/value, header-based CSV, JSON, CEF
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
│   ├── claims-audit.md
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

## Quick start (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,api,ui]"
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe src
```

Run the seven-step local demo:

```powershell
.\.venv\Scripts\python.exe scripts\demo.py
```

The parser lifecycle commands are `rosetta learn`, `rosetta verify`, and
`rosetta activate`. Verification fixture format and state transitions are
described in [docs/parser-verification.md](./docs/parser-verification.md).
Drift monitoring and export commands, plus the API/UI service, are described in
[docs/monitoring-export-api.md](./docs/monitoring-export-api.md).
Start the local API or UI directly:

```powershell
.\.venv\Scripts\python.exe -m uvicorn rosettalog.api.app:app --host 127.0.0.1 --port 8000
.\.venv\Scripts\python.exe -m streamlit run src\rosettalog\ui\streamlit_app.py
```

Run an end-to-end raw-store, parse, and Parquet benchmark with:

```powershell
\.\.venv\Scripts\python.exe samples\generate.py --records-per-format 100000 --seed 2026
\.\.venv\Scripts\python.exe -m rosettalog bench samples\benchmark\asa.log --report $env:TEMP\rosettalog-bench-asa.md
```

The reproducible 100,000-record-per-format measurements and the separately
labeled parser-only microbenchmark are documented in
[docs/benchmarks.md](./docs/benchmarks.md).

## Clean-machine test checklist

1. Use a clean Windows x86_64 machine with Python 3.11 and Docker Desktop. Confirm
   that no `.env` credentials or prior `data` are needed.
2. Create the project environment and install the declared test/service extras
   using the Quick start commands. Run `pip check`, `pytest`, Ruff, and mypy.
3. On a connected preparation machine, cache the `python:3.11-slim` base image
   and prepare Linux x86_64 wheels with
   `.\scripts\test-airgap.ps1 -PrepareWheels`.
4. Transfer the repository and `wheels` directory to the clean machine, disable
   external networking, and run `.\scripts\test-airgap.ps1`. The image build
   uses `--network none`; Compose uses an internal-only network and loopback
   published ports. Docker execution has not been verified in this workspace.
5. Run `.\.venv\Scripts\python.exe scripts\demo.py`; verify the generated
   `events.ndjson`, `events.cef`, `events.syslog`, rawstore, verification
   report, and draft re-learn proposal in its printed output directory.
6. Open `http://127.0.0.1:8501` for the UI and `http://127.0.0.1:8000/docs`
   for the local API while Compose is up. Stop with
   `docker compose down`; the named application data volume is retained.

## Security and compliance choices

- Raw bytes are kept unchanged in an append-only store.
- Optional normalized IP truncation (`--mask-ips`, IPv4 `/24` and IPv6 `/64` by default) and username hashing (`--hash-usernames`) are applied after raw retention; hashing requires a salt via `ROSETTALOG_USERNAME_HASH_SALT` or `--username-hash-salt`.
- Duplicate normalized events are retained and linked through `flags.duplicate_of` and `flags.duplicate_count`.
- Vendor-specific fields are retained in `unmapped` rather than silently discarded.
- No outbound network is required by the application at runtime; offline image
  builds require a pre-populated Linux wheelhouse and cached base image.

## Gate 0 freeze

The following schemas are intentionally frozen at this stage:

- `schemas/envelope.schema.json`
- `schemas/parser.schema.json`
- `schemas/ocsf_subset.json`

These are baseline contracts for the rest of the system and should not be changed without explicit approval.

## Notes

Frozen schemas remain the contracts. **STUB:** multiline event assembly, Grok
export, ML-specific export, API authentication, and scheduled drift baselines.
Billion-event-scale testing has not been run.
Benchmark measurements are local synthetic-data runs and must not be
interpreted as billion-event scale results. Duplicate events are flagged, not
suppressed.
