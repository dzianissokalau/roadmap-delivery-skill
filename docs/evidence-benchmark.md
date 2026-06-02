# Evidence Benchmark

This document defines the proof metrics for onboarding demos and benchmark
artifacts. The repository-local harness reports measured outcomes from fixture
scenarios only; it does not claim productivity, ROI, compliance, model speed,
or vendor comparison results.

The benchmark should measure evidence quality and gate behavior, not generic
productivity.

## Metrics

| Metric | What It Measures | Artifact Sources |
|---|---|---|
| Invalid advancement caught | Whether validation or review prevents a phase from advancing when required evidence is missing or contradictory. | `delivery_state.json`, review artifacts, validator errors, roadmap phase status. |
| Evidence completeness | Whether a delivered phase records scope, branch, verification, review verdict, state update, log update, and residual risks. | Delivery log, state file, review file, roadmap header, git branch. |
| Recovery path clarity | Whether a blocked run names the blocker classification and the next human or local repair action. | `blocked_reason`, review verdict, delivery log, alert file when required. |
| Verification reproducibility | Whether required commands can be rerun from a clean or temporary checkout with documented environment setup. | Verification command output, runtime checklist, demo fixture, test logs. |

## Scoring Contract

Each metric should be scored from local evidence:

| Score | Meaning |
|---:|---|
| 0 | Required evidence is missing or contradictory. |
| 1 | Evidence exists but needs manual interpretation or has non-blocking gaps. |
| 2 | Evidence is complete, reproducible, and directly tied to the phase contract. |

A benchmark run may report totals, but it must also report each underlying
artifact path and command. Do not collapse the result into a single success
claim without showing the evidence.

## Invalid Advancement Cases

The benchmark should include local fixtures for at least these cases:

- missing required verification after a phase edit
- review verdict is `needs-fix`
- current branch does not match the expected phase branch
- model policy requires a different model or reasoning effort than saved
  automation readback
- completed state tries to start another phase
- blocked state lacks a remediation classification

The expected result is not "the agent fixes everything." The expected result is
that the framework stops before unsafe advancement and records the smallest
next action.

## Evidence Completeness Checklist

A delivered phase should have:

- roadmap header updated to the next phase or closeout state
- delivery state updated with current phase, branch, verification, review, run
  quality, and next required model fields
- delivery log entry with scope, changes, verification, review, residual risks,
  and next action
- review artifact with exact verdict `delivered`
- required verification commands rerun after the last change
- `git diff --check` clean
- unrelated worktree changes preserved and called out when present

The benchmark should count each item independently so partial evidence is
visible.

## Recovery Path Checklist

A blocked or needs-fix run should show:

- blocker classification: local-repairable, automation-config,
  permission-gated, external-decision, or destructive-risk
- current phase and owned files
- command or artifact that failed
- whether a local repair is allowed by approval policy
- next human action when permission, credentials, product decision,
  publication, promotion, installed-tool sync, or destructive git is required
- alert file path when the policy requires an alert

## Reproducibility Checklist

A benchmark or case study should record:

- repository commit or fixture path
- command list
- environment variables needed for local package imports or temporary homes
- expected warnings and why they are accepted
- actual exit status for each command
- generated report path

The safe demo benchmark must run without network access, credentials, or live
host automation. Optional live host checks may be reported separately and must
not be required for the local score.

## Local Benchmark Command

Run the benchmark from the repository root:

```bash
python3 -m roadmap_delivery.cli benchmark \
  --repo-root . \
  --json \
  --output /tmp/roadmap-delivery-evidence-benchmark.json
```

The command copies `examples/demo-roadmap/` into temporary repositories,
creates temporary saved automation configs, runs `validate` and `inspect`, and
emits a JSON report. It does not edit live Codex automations, use credentials,
publish telemetry, or mutate the source fixture.

## Measured Case Study

Current fixture results:

| Field | Result |
|---|---:|
| Scenarios | 5 |
| Invalid scenarios | 4 |
| Invalid advancement caught | 4 of 4 |
| Invalid advancement caught by validation errors | 1 |
| Evidence completeness score | 7 of 10 |
| Clean-fixture false-positive warnings | 0 |

Measured scenarios:

| Scenario | Detection |
|---|---|
| Clean delivery evidence | `validate` and `inspect` pass with no warnings. |
| Missing review artifact | Evidence check reports `review_artifact_missing`; validation also warns `empty_review_dir`. |
| Stale lifecycle filename | Validation errors with `roadmap_lifecycle_filename_mismatch`. |
| Mismatched automation status | Evidence check reports `automation_status_mismatch`. |
| Insufficient verification evidence | Evidence check reports `verification_evidence_missing`. |

The evidence completeness score is intentionally not perfect because several
invalid fixtures keep some control-plane fields intact while one required field
is missing or contradictory. The result should be read as a fixture coverage
report, not a claim about all possible roadmap failures.

## Reporting Language

Use neutral language:

- "caught 5 of 6 invalid advancement fixtures"
- "evidence completeness scored 10 of 12"
- "verification reproduced in a temporary checkout"
- "model-policy mismatch blocked before implementation"

Avoid claims such as guaranteed release safety, guaranteed compliance, ROI,
time saved, or productivity improvement unless a separate measured artifact
supports the claim.
