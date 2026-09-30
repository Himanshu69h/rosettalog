# Gate 0 brief

This repository implements the mandatory baseline for RosettaLog before runtime engine work starts.

## Completed in Gate 0

- repository structure and packaging
- offline Docker + Compose scaffolding
- schema definitions for envelope/parser/OCSF
- documentation skeleton
- seed sample generator
- schema validation tests

## Explicitly stubbed at the Gate 0 baseline

- parser learning engine
- verification engine
- runtime parser and quarantine pipeline
- DuckDB and Parquet access
- FastAPI and Streamlit UIs

These items were the original Gate 0 stubs. Parser learning, verification,
runtime ingestion, Parquet/DuckDB access, and API/UI support were implemented in
later gates. See `docs/limitations.md` for the current STUB and UNTESTED list.
