# Requirement traceability

## Mapping of SIH26156 items to Gate 0

| Requirement | Code / schema / doc | Evidence |
|---|---|---|
| a. Lossless raw | `schemas/envelope.schema.json` | raw and raw_sha256 are explicit requirements |
| b. Source-specific attributes | `schemas/envelope.schema.json` and `docs/data-dictionary.md` | `unmapped` is required |
| c. Common taxonomy | `schemas/ocsf_subset.json` | event class subset is documented |
| d. Traceability | `docs/architecture.md` | event_id and raw provenance are core design rules |
| e. Plug-and-play onboarding | `samples/generate.py` and parser schema | sample-driven parser workflow is prepared |
| f. Unified visibility | `docs/architecture.md` | query layer is planned as a shared layer |
| g. SIEM/data-lake export | `docs/architecture.md` | sink layer is part of the architecture |
| h. AI/ML-ready | `docs/data-dictionary.md` | typed flat columns are the baseline |
| i. Less parser effort | `docs/benchmarks.md` | benchmark approach documented |
| j. Air-gapped | `Dockerfile` and `Makefile` | offline pip/wheel flow is included |
| k. Container | `docker-compose.yml` and `Dockerfile` | runtime and compose scaffolding exist |

The full implementation is intentionally not claimed in Gate 0; the repository is a validated baseline, not a complete production runtime.
