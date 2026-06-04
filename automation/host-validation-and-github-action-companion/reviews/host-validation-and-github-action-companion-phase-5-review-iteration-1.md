# Phase 5 Review - Iteration 1

Roadmap: `roadmaps/in_progress_host_validation_and_github_action_companion_roadmap.md`
Phase: Phase 5 - Nightly Workflow And Capability Metadata
Reviewed at: 2026-06-04T15:28:50Z
Branch: `codex/host-validation-and-github-action-companion-phase-5`
Verdict: delivered

## Findings

- None.

## Missing Tests Or Checks

- None. Required verification passed after the Phase 5 changes:
  `python3 -m unittest tests.test_host_smoke tests.test_adapter_parity tests.test_quality_gates -v`,
  `python3 scripts/build_adapters.py --check --json`, and `git diff --check`.
- Targeted checks also passed:
  `python3 -m unittest tests.test_github_action -v`,
  `PYTHONPYCACHEPREFIX=/private/tmp/roadmap-delivery-phase5-pycache python3 -m py_compile src/roadmap_delivery/reports.py tests/test_host_smoke.py tests/test_adapter_parity.py`,
  and a local `build_host_coverage_report` smoke with a skipped Codex live
  check.

## Finding Disposition

- No findings required disposition.

## Acceptance Criteria Review

- Nightly host smoke is available as an explicit maintainer opt-in:
  `.github/workflows/host-smoke-nightly.yml` uses `workflow_dispatch` only,
  has explicit `run_codex` and `run_claude` inputs, and does not define a
  remote `schedule`.
- Missing host binaries create visible skipped results: selected host smoke
  commands run `scripts/host_smoke.py --isolated-home --json`, preserve each
  host's raw JSON report, and the coverage report keeps skipped checks and
  reasons visible.
- Capability metadata is the source for compatibility claims:
  `host-capabilities/codex.yaml`, `host-capabilities/claude.yaml`, and
  `host-capabilities/generic.yaml` now record live smoke status, offline parity,
  skip visibility, workflow reference, and fallback surfaces; `reports.py`
  reads those fields into `host_coverage`.
- Default CI remains offline and secret-free: the new workflow is dispatch-only
  and existing `ci.yml` / `release-check.yml` were not changed in this phase.

## Residual Risks

- Review was performed in the same automation context because no separate
  reviewer context is available in this run.
- The optional real Codex and Claude live smoke commands were not run because
  this phase does not include explicit operator approval or installed host
  binaries; missing-binary and fake-binary behavior are covered by tests.
- The workflow template does not activate nightly scheduling by itself. A
  maintainer must separately approve any remote schedule or authenticated host
  setup.

## Verdict

delivered
