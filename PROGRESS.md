# RosettaLog Gate Progress

## Current state

- Current gate: Gate 1, blocked before implementation.
- Spec status: `PROJECT_BRIEF.md` is absent from the repository and workspace search. `docs/gate0-brief.md` contains only a short Gate 0 summary, not section 16 or the later-gate requirements. The user-provided request enumerates deliverables, but is not a substitute for the referenced complete spec.
- Baseline status: the worktree has all current project files staged as additions, but `git log` reports no commits and no `gate-0-frozen` tag exists. The claimed frozen baseline is therefore not verified in this checkout.
- In-progress item: obtain/restore the complete `PROJECT_BRIEF.md` and verify the Gate 0 baseline before implementing Gate 1.
- Known failures/blockers: missing authoritative spec; no Git commit or `gate-0-frozen` tag. Git author identity is not configured.
- STUB items recorded by `docs/gate0-brief.md`: parser learning engine; verification engine; runtime parser and quarantine pipeline; DuckDB and Parquet access; FastAPI and Streamlit UIs.

## Gate 0

- [x] Repository structure and packaging are present.
- [x] Offline Docker and Compose scaffolding are present.
- [x] Envelope, parser, and OCSF schemas are present.
- [x] Documentation skeleton is present.
- [x] Seed sample generator is present.
- [x] Schema validation tests are present.
- [ ] Verify the frozen baseline commit `gate-0-frozen` (not present in this checkout).
- [ ] Confirm clean Gate 0 validation output from this checkout before building on it.

## Gate 1

- [ ] Read and follow the complete Gate 1 specification in `PROJECT_BRIEF.md` section 16 (blocked: file missing).
- [ ] Append-only rawstore with zstd, SHA-256, and index.
- [ ] Ingest pipeline.
- [ ] Detector.
- [ ] Four hand-written YAML parsers: ASA-style syslog, FortiGate key=value, CEF, and JSON.
- [ ] Runtime engine.
- [ ] Quarantine with reason codes.
- [ ] Parquet sink.
- [ ] DuckDB query support.
- [ ] CLI commands: `run`, `trace`, `verify-event`, `verify-store`, and `query`.
- [ ] Seeded sample generator in `samples/generate.py`.
- [ ] Gate 1 tests, including the cases specified by the authoritative brief.
- [ ] Ordered validation: `pip check`, `pytest`, `ruff check`, `mypy`.
- [ ] Commit `Gate 1: <summary>` and tag `gate-1-done` after a green validation run.

## Gate 2

- [ ] Learner using drain3.
- [ ] Type inference.
- [ ] Key inference.
- [ ] OCSF mapper using `synonyms.yaml`.
- [ ] YAML emitter.
- [ ] Review list.
- [ ] Leave-one-format-out test with real `X of Y correct` mapping accuracy.
- [ ] Gate 2 tests and ordered validation from the authoritative brief.
- [ ] Commit `Gate 2: <summary>` and tag `gate-2-done` after a green validation run.

## Gate 3

- [ ] Verifier gate: coverage, required fields, over-merge, round-trip, and RE2 safety.
- [ ] HTML and JSON verification reports.
- [ ] Parser state machine.
- [ ] `rosetta bench` writes `docs/benchmarks.md` from real measurements.
- [ ] Gate 3 tests and ordered validation from the authoritative brief.
- [ ] Commit `Gate 3: <summary>` and tag `gate-3-done` after a green validation run.

## Gate 4

- [ ] Monitor and drift detection with re-learn proposal.
- [ ] NDJSON and CEF/syslog export.
- [ ] FastAPI service.
- [ ] Thin Streamlit UI.
- [ ] Docker Compose workflow.
- [ ] Airgap test with network disabled (mark UNTESTED if Docker is unavailable).
- [ ] Gate 4 tests and ordered validation from the authoritative brief.
- [ ] Commit `Gate 4: <summary>` and tag `gate-4-done` after a green validation run.

## Freeze

- [ ] README quick start.
- [ ] `docs/architecture.md`: two pages with a Mermaid diagram.
- [ ] `docs/requirements-traceability.md`: requirements a-k mapped to code, test, and demo step.
- [ ] `docs/limitations.md`.
- [ ] `docs/data-dictionary.md`.
- [ ] `scripts/demo.sh`: end-to-end seven-step demo.
- [ ] `docs/demo-script.md`: one narration line per step.
- [ ] `docs/slides-outline.md`: five slides (Problem, Solution, Architecture + a-k, Results including failures, Scale + roadmap).
- [ ] README clean-machine test checklist.
- [ ] Push-ready repository.
- [ ] Final validation, real benchmark results, and final report.
