# Host Validation And GitHub Action Companion Roadmap

Status: Delivered
Current phase: Complete
Last updated: 2026-06-04
Next action: Main promotion is complete; publication, remote schedule
activation, repository secrets, and installed package synchronization remain
separate human-approved actions.
Blocked by: None.

## Purpose

This roadmap turns the review recommendations about optional live host smoke
checks and a lightweight GitHub Action companion into a delivery plan.

Commercialisation, pricing, paid support, hosted control planes, and
marketplace monetisation are out of scope. The target is stronger validation
and CI evidence for teams that already use repository workflows.

## Review Recommendations Addressed

- Add optional live host smoke checks in CI or nightly workflows for supported
  Codex and Claude paths.
- Add a lightweight GitHub Action companion for validation and review-evidence
  checks.
- Keep host-parity limits explicit and avoid over-claiming unsupported live
  behavior.
- Reduce false-safety risk by documenting what CI and host smoke checks can and
  cannot prove.

## Automation Readiness

Recommended automation setup:

```text
ROADMAP_PATH=roadmaps/delivered_host_validation_and_github_action_companion_roadmap.md
ROADMAP_SLUG=host-validation-and-github-action-companion
AUTOMATION_DIR=automation/host-validation-and-github-action-companion
AUTOMATION_ID=host-validation-and-github-action-companion
INITIAL_MODEL=gpt-5.5
INITIAL_REASONING=xhigh
CADENCE=hourly
EXECUTION_ENVIRONMENT=local
```

This roadmap touches CI and optional host checks. The automation may add local
workflow files, action metadata, tests, and docs. It must not configure
repository secrets, enable scheduled workflows in a remote repository, publish
a GitHub Marketplace action, or run live host commands that require unavailable
credentials without explicit human approval.

## Strategic Outcome

Teams should be able to run roadmap delivery validation and review-evidence
checks in GitHub Actions, while maintainers can optionally run host smoke
checks that verify package assumptions against Codex and Claude when the
required binaries and secrets are present.

The end state is a conservative CI companion: useful for detecting drift,
missing evidence, privacy risk, and unsupported host assumptions, but honest
about what it cannot guarantee.

## Design Principles

- Offline validation must remain the default and must not require secrets.
- Live host smoke checks must be opt-in, skip cleanly when prerequisites are
  missing, and never hide skipped coverage.
- GitHub Action output should be structured enough for PR review and simple
  enough for humans to read.
- The action should use the existing CLI and schemas instead of duplicating
  validation logic in shell scripts.
- Host parity claims must be backed by capability metadata, tests, and docs.
- CI cannot prove compliance or safety; it can only check declared evidence and
  known guardrails.

## Target Repository Shape

Likely additions or updates:

```text
.github/
  actions/
    roadmap-delivery-validate/
      action.yml
      README.md
  workflows/
    ci.yml
    release-check.yml
    host-smoke-nightly.yml
docs/
  github-action.md
  host-smoke-checks.md
  compatibility.md
host-capabilities/
  codex.yaml
  claude.yaml
  generic.yaml
scripts/
  host_smoke.py
  build_release.py
src/roadmap_delivery/
  cli.py
  reports.py
  validation.py
tests/
  test_github_action.py
  test_host_smoke.py
  test_adapter_parity.py
roadmaps/
  delivered_host_validation_and_github_action_companion_roadmap.md
```

Do not add hosted service dependencies, billing flows, marketplace publication,
or mandatory live-host requirements.

## Phase Model Guidance

```text
Phase 0: gpt-5.5 / xhigh
Phase 1: gpt-5.5 / xhigh
Phase 2: gpt-5.5 / high
Phase 3: gpt-5.5 / xhigh
Phase 4: gpt-5.5 / xhigh
Phase 5: gpt-5.5 / high
Phase 6: gpt-5.5 / xhigh
```

## Phase Overview

```text
Phase 0 - Host Validation Safety Contract
Phase 1 - GitHub Action Contract And Offline Validation
Phase 2 - GitHub Action Implementation
Phase 3 - Optional Codex Live Smoke Harness
Phase 4 - Optional Claude Live Smoke Harness
Phase 5 - Nightly Workflow And Capability Metadata
Phase 6 - Trust Evidence Closeout
```

## Phase 0 - Host Validation Safety Contract

### Objective

Define what CI validation and live host smoke checks are allowed to prove, what
they must skip, and what requires operator approval.

### Owned Files

```text
roadmaps/delivered_host_validation_and_github_action_companion_roadmap.md
docs/host-smoke-checks.md
docs/github-action.md
docs/compatibility.md
README.md
```

### Inputs

- Deep research review recommendations.
- Existing compatibility docs and host capability metadata.
- Existing CI and release-check workflows.
- Existing adapter parity and install smoke tests.
- Approval policy never-auto operations.

### Implementation Steps

1. Add `docs/host-smoke-checks.md` explaining offline checks, optional live
   checks, prerequisites, skip behavior, and false-safety limits.
2. Add `docs/github-action.md` draft contract for action inputs, outputs,
   supported validation modes, and failure semantics.
3. Define safe defaults: offline validation only, no secrets required, no live
   host automation unless explicitly enabled.
4. Define live smoke prerequisites for Codex and Claude separately.
5. Update compatibility docs with a capability statement for CI validation and
   host smoke coverage.

### Acceptance Criteria

- CI and live-host validation boundaries are documented before implementation.
- Skipped live checks must be visible as skipped, not passed.
- The action contract uses existing CLI behavior as the source of truth.
- No remote repository settings, secrets, or published actions are required.

### Required Verification

```bash
python3 -m unittest tests.test_quality_gates tests.test_adapter_parity -v
git diff --check
```

### Non-Goals

- Running live Codex or Claude checks.
- Creating GitHub repository secrets.
- Publishing a GitHub Marketplace action.
- Claiming CI can guarantee safety or compliance.

### Stop Conditions

- Stop if the contract requires unavailable credentials.
- Stop if live check failures would be hidden as successful offline validation.
- Stop if docs imply stronger host parity than capability metadata supports.

## Phase 1 - GitHub Action Contract And Offline Validation

### Objective

Design the GitHub Action companion around the existing CLI, with offline
validation and review-evidence checks as the first supported mode.

### Owned Files

```text
.github/actions/roadmap-delivery-validate/action.yml
.github/actions/roadmap-delivery-validate/README.md
docs/github-action.md
src/roadmap_delivery/cli.py
src/roadmap_delivery/reports.py
tests/test_github_action.py
```

### Inputs

- Current `roadmap-delivery inspect`, `validate`, `package`, and `version`
  commands.
- Review artifact schema.
- Delivery state schema.
- Release privacy checker.
- GitHub Actions local action conventions.

### Implementation Steps

1. Define action inputs for roadmap path, automation directory, roadmap slug,
   strict mode, privacy scan, adapter check, release check, and report format.
2. Define action outputs for validation status, warnings count, errors count,
   review evidence status, and report file path.
3. Decide whether the action uses a composite shell action, Docker action, or
   local Python entrypoint; prefer the simplest path that can run the existing
   CLI.
4. Add docs showing PR validation and release-check examples.
5. Add tests or fixtures that validate action metadata and command assembly.

### Acceptance Criteria

- The action contract can run offline in a GitHub Actions checkout.
- The action delegates validation logic to the existing CLI and scripts.
- Inputs and outputs are documented and stable enough for implementation.
- Strict mode is opt-in or clearly documented if enabled by default.

### Required Verification

```bash
python3 -m unittest tests.test_github_action tests.test_cli tests.test_schema_validation -v
git diff --check
```

### Non-Goals

- Marketplace publication.
- Live host checks.
- Creating a hosted API.
- Duplicating validation logic inside action scripts.

### Stop Conditions

- Stop if the action design cannot run without secrets.
- Stop if action output cannot distinguish warnings from errors.
- Stop if review-evidence checks require private local automation logs.

## Phase 2 - GitHub Action Implementation

### Objective

Implement the local GitHub Action companion and wire it into repository CI for
offline validation.

### Owned Files

```text
.github/actions/roadmap-delivery-validate/action.yml
.github/actions/roadmap-delivery-validate/README.md
.github/workflows/ci.yml
.github/workflows/release-check.yml
src/roadmap_delivery/cli.py
src/roadmap_delivery/reports.py
tests/test_github_action.py
tests/test_cli.py
```

### Inputs

- Phase 1 action contract.
- Existing CI and release-check workflows.
- Existing validation, release, privacy, and adapter scripts.

### Implementation Steps

1. Implement the action with a clear entrypoint and dependency-light setup.
2. Add action report output in text and JSON forms.
3. Add CI usage that validates framework artifacts without requiring a
   configured roadmap automation.
4. Add optional inputs for release builder, adapter drift, and privacy scan
   checks.
5. Add tests for action metadata, default inputs, strict-mode command assembly,
   and failure handling.
6. Update docs with copyable workflow examples.

### Acceptance Criteria

- CI can run the action locally against the repository.
- The action fails on validation errors and reports warnings separately.
- Privacy and adapter checks can be enabled without rewriting workflows.
- Action docs explain how to use it in another repository.

### Required Verification

```bash
python3 -m unittest tests.test_github_action tests.test_cli tests.test_quality_gates -v
python3 scripts/build_adapters.py --check --json
python3 scripts/build_release.py --check --json
python3 scripts/check_release_privacy.py --repo-root .
git diff --check
```

### Non-Goals

- Publishing the action externally.
- Running scheduled workflows on GitHub from local automation.
- Adding secrets.
- Validating private user roadmaps by default.

### Stop Conditions

- Stop if CI would leak local automation evidence.
- Stop if action execution requires network access for normal offline checks.
- Stop if action failures are ambiguous or non-actionable.

## Phase 3 - Optional Codex Live Smoke Harness

### Objective

Add an opt-in Codex live smoke harness that checks install-package assumptions
when the Codex binary and a temporary `CODEX_HOME` are available.

### Owned Files

```text
scripts/host_smoke.py
docs/host-smoke-checks.md
docs/installing-codex.md
host-capabilities/codex.yaml
tests/test_host_smoke.py
tests/test_install_smoke.py
```

### Inputs

- Current Codex install smoke docs.
- Existing demo fixture.
- Host capability metadata.
- Current install helper scripts.
- Approval policy boundaries for live host configuration.

### Implementation Steps

1. Implement a Codex smoke mode that uses an isolated temporary `CODEX_HOME`.
2. Verify package layout, `codex --help` availability when present, helper
   script execution, and validation against the demo fixture.
3. Skip with explicit reason when the Codex binary is unavailable.
4. Ensure smoke mode never touches active Codex home or saved real automations.
5. Add docs for local use and CI opt-in prerequisites.
6. Add tests for skip behavior, temporary home isolation, and report output.

### Acceptance Criteria

- Codex live smoke runs only when explicitly requested.
- Missing Codex binary is reported as skipped, not passed or failed by default.
- The harness uses a temporary home and demo fixture.
- No live automation is created, activated, or modified.

### Required Verification

```bash
python3 -m unittest tests.test_host_smoke tests.test_install_smoke tests.test_adapter_codex -v
git diff --check
```

Optional, only when the Codex binary is available and operator approves live
host smoke:

```bash
python3 scripts/host_smoke.py --host codex --isolated-home --json
```

### Non-Goals

- Testing every Codex feature.
- Using the user's active `CODEX_HOME`.
- Creating real recurring automations.
- Requiring Codex for normal CI.

### Stop Conditions

- Stop if the harness would touch active Codex configuration.
- Stop if host smoke requires credentials that are not already available and
  approved.
- Stop if skip output can be mistaken for a successful live check.

## Phase 4 - Optional Claude Live Smoke Harness

### Objective

Add an opt-in Claude live smoke harness that checks local plugin package
assumptions when the Claude binary or plugin surface is available.

### Owned Files

```text
scripts/host_smoke.py
docs/host-smoke-checks.md
docs/installing-claude.md
dist/claude/README.md
host-capabilities/claude.yaml
tests/test_host_smoke.py
tests/test_claude_plugin_package.py
tests/test_claude_hooks.py
```

### Inputs

- Current Claude install docs.
- Generated Claude plugin package.
- Claude host capability metadata.
- Existing hook guard tests.
- Compatibility notes for Claude fallbacks.

### Implementation Steps

1. Implement a Claude smoke mode that validates local plugin package layout and
   optional host binary availability.
2. Use temporary configuration paths and offline plugin/package checks by
   default.
3. Add optional live checks only when the host surface is present and explicitly
   enabled.
4. Report unsupported Claude surfaces as capability notes, not failures, unless
   docs claim they are required.
5. Add tests for package layout, hook guard behavior, skip reasons, and report
   output.
6. Update install docs with live smoke prerequisites and fallback behavior.

### Acceptance Criteria

- Claude package smoke remains useful without a live Claude binary.
- Live checks are clearly opt-in and skip cleanly when unsupported.
- Capability metadata and docs agree about required, optional, and unsupported
  surfaces.
- Hook checks remain guardrails and are not described as complete DLP.

### Required Verification

```bash
python3 -m unittest tests.test_host_smoke tests.test_claude_plugin_package tests.test_claude_hooks -v
python3 scripts/build_adapters.py --adapter claude --check --json
git diff --check
```

Optional, only when the Claude host surface is available and operator approves
live host smoke:

```bash
python3 scripts/host_smoke.py --host claude --isolated-home --json
```

### Non-Goals

- Claiming full Claude marketplace certification.
- Replacing Claude's native permission model.
- Running live checks in default CI.
- Requiring Claude for normal release checks.

### Stop Conditions

- Stop if live smoke needs unapproved credentials or writes to active Claude
  configuration.
- Stop if docs overstate Claude support compared with capability metadata.
- Stop if skipped live checks are reported as passed.

## Phase 5 - Nightly Workflow And Capability Metadata

### Objective

Add optional nightly workflow support and capability metadata reporting for
maintainers who want recurring host smoke evidence.

### Owned Files

```text
.github/workflows/host-smoke-nightly.yml
docs/host-smoke-checks.md
docs/compatibility.md
host-capabilities/codex.yaml
host-capabilities/claude.yaml
host-capabilities/generic.yaml
src/roadmap_delivery/reports.py
tests/test_host_smoke.py
tests/test_adapter_parity.py
```

### Inputs

- Codex and Claude smoke harnesses.
- Host capability metadata.
- GitHub Actions companion.
- Existing compatibility docs.

### Implementation Steps

1. Add a disabled or opt-in nightly workflow template for host smoke checks.
2. Ensure workflow docs explain required secrets, host availability, and skip
   behavior without asking automation to create secrets.
3. Add capability metadata fields for live smoke status, offline parity, and
   known fallback surfaces.
4. Add a report view that summarizes host coverage and skipped live checks.
5. Add tests that compare docs, metadata, and report output for drift.

### Acceptance Criteria

- Nightly host smoke is available as an explicit maintainer opt-in.
- Missing secrets or host binaries create visible skipped results.
- Capability metadata is the source for compatibility claims.
- Default CI remains offline and secret-free.

### Required Verification

```bash
python3 -m unittest tests.test_host_smoke tests.test_adapter_parity tests.test_quality_gates -v
python3 scripts/build_adapters.py --check --json
git diff --check
```

### Non-Goals

- Enabling remote scheduled workflows from automation.
- Managing GitHub secrets.
- Commercial monitoring.
- Hosted dashboards.

### Stop Conditions

- Stop if the workflow requires secrets for default CI.
- Stop if capability metadata and docs disagree.
- Stop if host smoke reports encourage over-claiming unsupported host parity.

## Phase 6 - Trust Evidence Closeout

### Objective

Close the roadmap with clear evidence that GitHub Action validation, optional
host smoke checks, compatibility metadata, and false-safety warnings are
implemented and reviewed.

### Owned Files

```text
README.md
docs/github-action.md
docs/host-smoke-checks.md
docs/compatibility.md
.github/actions/roadmap-delivery-validate/
.github/workflows/
automation/<roadmap-slug>/
roadmaps/delivered_host_validation_and_github_action_companion_roadmap.md
```

### Inputs

- Completed GitHub Action implementation.
- Host smoke harness reports.
- Capability metadata.
- CI and release check output.
- Phase review artifacts.

### Implementation Steps

1. Run full validation, adapter, release, privacy, action, and host-smoke test
   suites.
2. Update README to point to the GitHub Action companion and host smoke docs.
3. Record which live host checks were run, skipped, or unavailable.
4. Prepare a final deep review prompt covering action behavior, CI safety,
   host smoke skip semantics, parity claims, secrets risk, and publication
   readiness.
5. Rename the roadmap to `delivered_...` only after review and finalization
   requirements are satisfied.
6. Leave marketplace publication or remote workflow activation as explicit
   human-approved next actions.

### Acceptance Criteria

- The action can validate roadmap delivery evidence in CI without secrets.
- Live host smoke checks are optional and transparent about skip coverage.
- Compatibility docs, capability metadata, and tests agree.
- Final review prompt exists or a human waiver is recorded.

### Required Verification

```bash
python3 -m unittest discover -s tests -v
python3 scripts/build_adapters.py --check --json
python3 scripts/build_release.py --check --json
python3 scripts/check_release_privacy.py --repo-root .
git diff --check
```

Optional, only with approved and available live host surfaces:

```bash
python3 scripts/host_smoke.py --host codex --isolated-home --json
python3 scripts/host_smoke.py --host claude --isolated-home --json
```

### Non-Goals

- Publishing a GitHub Marketplace Action.
- Enabling remote nightly workflows without human approval.
- Commercial monitoring or paid CI services.
- Claiming full host runtime enforcement.

### Stop Conditions

- Stop if final evidence cannot distinguish offline validation from live host
  checks.
- Stop if CI or host smoke requires unapproved secrets.
- Stop if final review prompt has not been prepared or waived.
