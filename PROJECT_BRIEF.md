Baseline is committed (9c7c4cb) and tagged gate-0-frozen. PROJECT_BRIEF.md is in the repo root and is the authoritative spec. PROGRESS.md may be out of date; the earlier blocker is resolved. Read PROJECT_BRIEF.md fully before doing anything.

AUTONOMOUS MODE: build Gate 1, Gate 2, Gate 3, Gate 4, and Freeze back-to-back WITHOUT stopping between gates. Stop early only for a hard blocker that needs a human (missing tool, missing credentials, contradiction in the spec).

PROGRESS TRACKING:
- Update PROGRESS.md after every meaningful step: current gate, done items, in-progress item, failures, STUB/UNTESTED items.
- If you lose context or restart, read PROGRESS.md and PROJECT_BRIEF.md, then resume from the first unchecked item. Never redo finished work.

PER-GATE LOOP:
1. Implement everything listed for that gate in PROJECT_BRIEF.md section 16, and nothing from later gates.
2. Write that gate's tests as you go (known_format, lossless, fuzz, leave_one_out, adversarial, schema negative tests).
3. Run in order: pip check, pytest, ruff check, mypy. Read the real output.
4. If anything fails, fix it and rerun all four. Max 3 fix cycles per failure; if still failing, mark it FAILING in PROGRESS.md and docs/limitations.md and move on.
5. When green: git add -A, git commit -m "Gate N: <summary>", git tag gate-N-done, and append the test output summary to PROGRESS.md.
6. Start the next gate immediately.

RULES:
- Follow the six design rules in the brief: raw is sacred, nothing disappears, everything traceable, nothing unverified runs, deterministic and offline, input is hostile.
- Do not edit the frozen schemas. If a change is truly needed, record it in docs/decisions.md and version it (envelope v1.1).
- Never invent numbers. Benchmarks, coverage, and accuracy in docs must come from real runs. Label anything unimplemented as STUB.
- Dev machine is Windows PowerShell. Use Python scripts, not bash-only or Linux-only tooling. Use the repo-local .venv.
- If Docker is unavailable, still write the Dockerfile, compose file, and airgap script, and mark them UNTESTED.
- If you run low on budget, cut in this order: UI polish, grok export, drift, ML export. NEVER cut trace, verify-event, verify-store, the Verify gate, or the container.
- You cannot record the video, test on a separate machine, or make slides. Instead produce scripts/demo.py (runs the 7-step demo flow), docs/demo-script.md, docs/slides-outline.md, and a README "Clean-machine test checklist".

FINISH: print a final report with per-gate status, lint and test summaries, the list of STUB/UNTESTED/FAILING items, real benchmark numbers, and the exact commands to demo it. Then stop.

Start Gate 1 now.