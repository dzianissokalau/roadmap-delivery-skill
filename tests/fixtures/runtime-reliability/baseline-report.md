# Phase 0 Baseline Observations

Base commit: `517bbdd899f7fb9aea9124e471ae36fb1aa620cd`
Python: 3.9.6
Evidence captured: 2026-10-13 (exact time in baseline-report.json)
Source checkout: Phase 0 branch, production sources unchanged from base

Fresh pre-implementation suite: 215 tests, zero failures, one optional Claude
binary check skipped. Full output lives in the automation directory as
`phase-0-baseline-suite.txt`. This pass does not establish the desired behavior.

All raw inputs, expected results, source paths, reproduction commands and
observed outputs are in `baseline-report.json`. Expected results originate in
`cases.json`; default tests validate their format/traceability rather than
asserting that production must keep producing broken results.

| Finding | Fresh observation | Explicit expected behavior | Evidence boundary |
| --- | --- | --- | --- |
| R1 | Five bookkeeping-log changes yield stalled counts `[0,0,0,0,0]`; no threshold is reached. | First no-progress run counts one, second counts two and requires pause; no further phase attempts. | Pure planner calls with isolated state, no host effects. |
| R2 | Both installed validation/progress wrappers exit 2 with package-not-importable errors under `-I -S`. | Each helper starts successfully without checkout imports or undeclared site packages. | Temporary skill-only copy, separate working directory, no developer PYTHONPATH. This proves a startup defect, not a complete workflow evaluation. |
| R3 | Current core default terminal-pause language conflicts with residual adapter approval language. Copying the current skill leaves the isolated legacy saved prompt byte-identical. | Default status-only terminal pause is distinct from broad runner edits; propose any saved-prompt migration separately within its authority and provenance. | Sanitized instruction scenario, no live legacy runner or scheduler behavior verified. |
| R4 | An ACTIVE status with inline comment becomes two root status keys. Python 3.9 fallback readback reports paused anyway. | Exactly one status key, preserved other settings and trustworthy readback; duplicate keys cannot establish successful pause. | Temporary file backend only; no scheduler pause claim. |
| R5 | Both delegated modes return allowed for completion and stall despite explicit false context flags. | Each automatic pause is disabled regardless of broad permission; a manual request remains separate. | Four pure policy calls, no updates. |
| R6 | Policy/schema validation reports no errors and a high phase requirement; a flawless run selects low with no adaptive errors. | Resolved reasoning remains at least high and within caps. | Pure validation/resolution with fixture model. Missing optional state-field warnings are retained in raw evidence. |

## Reproduce

From the repository checkout:

```bash
python3 tests/test_runtime_contract.py --capture-baseline --output /tmp/runtime-reliability-baseline.json
python3 -m unittest tests.test_runtime_contract tests.test_quality_gates -v
git diff --check
```

The capture command is opt-in, uses temporary roots and writes only its selected
report path. Run it with a new output path to preserve this historical baseline.
No live host check was requested: scheduler execution and self-pause coverage
are **skipped**, optional and outside Phase 0 acceptance. The current delivery
runner's read-only configuration evidence is recorded in the delivery log.

## Owning Fixes

R5 receives passing behavioral assertions in Phase 1, R1 in Phase 2, R4 in
Phase 3, R2 in Phase 4 and R6 in Phase 5. R3 feeds Phases 1/3 and versioned
migration/instruction work in Phases 6/7. Phase 8 replays the combined behavior.
These observations remain historical; they must not become permanent broken
oracles or expected-failure regressions.
