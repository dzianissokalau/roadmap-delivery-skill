# Onboarding Wizard And Proof Demos Roadmap

Status: Delivered
Current phase: Complete
Last completed phase: Phase 5 - Quickstart Documentation And Closeout
Last updated: 2026-06-02
Next action: Pause the saved automation or explicitly keep the completed-state
hard-stop guard active.
Blocked by: None.

## Purpose

This roadmap turns the review recommendations about first-use friction,
guided setup, fit signalling, golden-path demos, and measurable proof into a
delivery plan.

Commercialisation, pricing, paid support, and sales positioning are out of
scope. The target is practical onboarding and evidence that the workflow adds
value, not a buyer pitch.

## Review Recommendations Addressed

- Add a policy/setup wizard to generate `approval_policy.json`, model policy,
  and starter artifacts.
- Create a "who this is for / who this is not for" quickstart with two
  golden-path demos.
- Produce a measurable benchmark or case study showing fewer invalid
  promotions or better delivery evidence.
- Reduce first-use friction created by roadmap slugs, policies, validation
  artifacts, branch discipline, and package choice.

## Automation Readiness

Recommended automation setup:

```text
ROADMAP_PATH=roadmaps/delivered_onboarding_wizard_and_proof_demos_roadmap.md
ROADMAP_SLUG=onboarding-wizard-and-proof-demos
AUTOMATION_DIR=automation/onboarding-wizard-and-proof-demos
AUTOMATION_ID=onboarding-wizard-and-proof-demos
INITIAL_MODEL=gpt-5.5
INITIAL_REASONING=xhigh
CADENCE=hourly
EXECUTION_ENVIRONMENT=local
```

The roadmap changes user-facing CLI behavior and examples. The automation may
create local fixtures and docs, but it must not modify a user's live Codex or
Claude home, publish recordings, or claim benchmark outcomes that were not
measured in the repository.

## Strategic Outcome

A new user should be able to answer "is this for me?", generate a starter
roadmap automation contract, run a safe demo, inspect the resulting evidence,
and understand why the extra ceremony exists.

The end state is a guided local path from empty checkout to validated demo
evidence, plus an honest proof artifact that measures evidence quality rather
than vague productivity claims.

## Design Principles

- Teach by running a safe fixture before touching a user's real project.
- Prefer generated files that match current schemas over copy-paste snippets.
- Keep onboarding paths short, but preserve the approval and review gates that
  define the framework.
- Measure evidence quality, invalid-advancement prevention, and recovery from
  blocked runs before claiming value.
- Use neutral proof language: report what was measured and where the benchmark
  is limited.
- Keep host-specific steps optional when live Codex or Claude binaries are not
  present.

## Target Repository Shape

Likely additions or updates:

```text
src/roadmap_delivery/
  cli.py
  scaffold.py
  wizard.py
  reports.py
schemas/
  approval_policy.schema.json
  phase_model_policy.schema.json
core/templates/
  approval_policy.md
  delivery_state.md
  delivery_log.md
docs/
  quickstart.md
  who-this-is-for.md
  onboarding-wizard.md
  evidence-benchmark.md
examples/
  demo-roadmap/
  onboarding-wizard/
  evidence-benchmark/
tests/
  test_cli.py
  test_schema_validation.py
  test_smoke_demo.py
  test_onboarding_wizard.py
  test_evidence_benchmark.py
roadmaps/
  delivered_onboarding_wizard_and_proof_demos_roadmap.md
```

Do not add commercial pricing, paid support paths, hosted onboarding services,
or unverifiable ROI claims.

## Phase Model Guidance

```text
Phase 0: gpt-5.5 / xhigh
Phase 1: gpt-5.5 / xhigh
Phase 2: gpt-5.5 / xhigh
Phase 3: gpt-5.5 / xhigh
Phase 4: gpt-5.5 / xhigh
Phase 5: gpt-5.5 / xhigh
```

## Phase Overview

```text
Phase 0 - Onboarding Contract And Success Metrics
Phase 1 - Setup Wizard UX And CLI Contract
Phase 2 - Wizard Implementation And Scaffold Integration
Phase 3 - Golden Path Demo Fixtures
Phase 4 - Evidence Benchmark Harness
Phase 5 - Quickstart Documentation And Closeout
```

## Phase 0 - Onboarding Contract And Success Metrics

### Objective

Define the first-use journey, generated artifacts, demo expectations, and
evidence metrics before implementing a wizard or benchmark.

### Owned Files

```text
roadmaps/delivered_onboarding_wizard_and_proof_demos_roadmap.md
docs/quickstart.md
docs/who-this-is-for.md
docs/onboarding-wizard.md
docs/evidence-benchmark.md
README.md
```

### Inputs

- Deep research review recommendations.
- Existing demo fixture and runtime checklist.
- Current `roadmap-delivery scaffold`, `inspect`, and `validate` behavior.
- Approval policy, phase model policy, and delivery state schemas.
- Existing README operating model.

### Implementation Steps

1. Define two target onboarding paths: safe demo first and real-project
   scaffold second.
2. Draft "who this is for / who this is not for" guidance that focuses on fit,
   workflow constraints, and unsupported use cases.
3. Define the wizard contract: required inputs, optional inputs, generated
   files, validation commands, and safety warnings.
4. Define success metrics for proof demos: invalid advancement caught, evidence
   completeness, recovery path clarity, and verification reproducibility.
5. Add README links to the onboarding and proof docs.

### Acceptance Criteria

- The wizard can be implemented from the documented contract without inventing
  behavior later.
- The quickstart explains fit and non-fit without marketing exaggeration.
- Proof metrics are measurable from repository artifacts.
- The safe demo path does not require network access, credentials, or live host
  automation.

### Required Verification

```bash
python3 -m unittest tests.test_quality_gates tests.test_smoke_demo -v
git diff --check
```

### Non-Goals

- Wizard implementation.
- Recording videos or publishing demos.
- Pricing or commercial ROI claims.
- Changing the core phase gate.

### Stop Conditions

- Stop if the intended proof metric cannot be measured from local artifacts.
- Stop if quickstart language implies guaranteed productivity, compliance, or
  release safety.
- Stop if onboarding requires editing a live host configuration before the safe
  demo path is available.

## Phase 1 - Setup Wizard UX And CLI Contract

### Objective

Add a schema-backed command contract for generating starter roadmap automation
artifacts with explicit approval and model policies.

### Owned Files

```text
src/roadmap_delivery/cli.py
src/roadmap_delivery/scaffold.py
src/roadmap_delivery/wizard.py
schemas/approval_policy.schema.json
schemas/phase_model_policy.schema.json
core/templates/approval_policy.md
core/templates/delivery_state.md
core/templates/delivery_log.md
docs/onboarding-wizard.md
tests/test_cli.py
tests/test_onboarding_wizard.py
```

### Inputs

- Existing `scaffold` CLI behavior.
- Existing schema validation helpers.
- Approval policy mode definitions.
- Phase model policy and provider role config examples.
- User-reported friction around automation setup.

### Implementation Steps

1. Add or extend a CLI command for guided setup in dry-run and write modes.
2. Define non-interactive flags for roadmap path, slug, automation id,
   approval mode, initial model, reasoning effort, cadence, and host target.
3. Ensure the wizard can emit `approval_policy.json`,
   `phase_model_policy.json`, `delivery_state.json`, `delivery_log.md`, and
   `automation_guide.md` from schema-valid defaults.
4. Add a preview mode that lists files and policy choices without writing.
5. Add validation output that tells the user what command to run next.
6. Keep live automation creation as a separate explicit step.

### Acceptance Criteria

- The CLI contract works in non-interactive automation and human-guided local
  use.
- Generated artifacts validate immediately.
- Conservative approval mode is the default.
- Delegated modes require explicit selection and are recorded in generated
  policy files.
- The command does not create, edit, or activate live Codex automations.

### Required Verification

```bash
python3 -m unittest tests.test_cli tests.test_onboarding_wizard tests.test_schema_validation -v
python3 -m roadmap_delivery.cli scaffold --help
git diff --check
```

### Non-Goals

- Creating saved Codex automations.
- Editing global Codex or Claude configuration.
- Prompting for credentials.
- Changing existing automation state.

### Stop Conditions

- Stop if generated artifacts fail schema validation.
- Stop if the wizard would overwrite existing automation artifacts without an
  explicit force flag.
- Stop if delegated approval is silently selected by default.

## Phase 2 - Wizard Implementation And Scaffold Integration

### Objective

Implement the setup wizard and connect it to existing validation, inspection,
and scaffold behavior.

### Owned Files

```text
src/roadmap_delivery/wizard.py
src/roadmap_delivery/scaffold.py
src/roadmap_delivery/cli.py
src/roadmap_delivery/validation.py
src/roadmap_delivery/reports.py
docs/onboarding-wizard.md
tests/test_onboarding_wizard.py
tests/test_cli.py
tests/test_library_units.py
```

### Inputs

- Phase 1 CLI contract.
- Current scaffold implementation.
- Existing validation and inspection report behavior.
- Templates under `core/templates/`.

### Implementation Steps

1. Implement artifact generation using structured data and schema-aware helpers.
2. Add file-existence protection and a clear overwrite policy.
3. Add validation and inspect readback immediately after generation.
4. Add dry-run JSON output for automation and docs.
5. Add tests for default conservative mode, delegated mode selection,
   invalid roadmap path, existing file protection, and validation failures.
6. Update docs with exact commands and generated file examples.

### Acceptance Criteria

- A dry run reports the same files that write mode would create.
- Write mode creates schema-valid artifacts in the expected automation
  directory.
- The resulting state can be inspected and validated without manual edits.
- Tests cover both success paths and common setup mistakes.

### Required Verification

```bash
python3 -m unittest tests.test_onboarding_wizard tests.test_cli tests.test_library_units tests.test_schema_validation -v
python3 -m roadmap_delivery.cli scaffold --help
git diff --check
```

### Non-Goals

- Interactive terminal UI polish beyond clear prompts and flags.
- Live automation creation.
- External network calls.
- Modifying installed host packages.

### Stop Conditions

- Stop if generator output is not deterministic.
- Stop if schema validation requires hand-edited fixes after generation.
- Stop if preview and write behavior diverge.

## Phase 3 - Golden Path Demo Fixtures

### Objective

Create two safe demos that show the workflow succeeding and recovering from a
blocked or invalid-advancement scenario.

### Owned Files

```text
examples/demo-roadmap/
examples/onboarding-wizard/
examples/evidence-benchmark/
docs/quickstart.md
docs/who-this-is-for.md
docs/onboarding-wizard.md
tests/test_smoke_demo.py
tests/test_onboarding_wizard.py
```

### Inputs

- Existing demo-roadmap fixture.
- Runtime checklist.
- Wizard implementation.
- Validation and inspection CLI behavior.
- Review recommendation for two golden-path demos.

### Implementation Steps

1. Define Demo A: create or inspect a tiny roadmap, validate state, deliver a
   harmless phase, and show a review/evidence trail.
2. Define Demo B: intentionally trigger a safe policy or lifecycle mismatch,
   remediate it, and show how the framework prevents invalid advancement.
3. Add fixture files that can run locally without credentials, network access,
   or live automation.
4. Add smoke tests that verify demo commands and expected report fields.
5. Add quickstart documentation with short command sequences and expected
   outputs.
6. Ensure demos do not include local user paths or sensitive automation data.

### Acceptance Criteria

- Both demos run from a clean checkout using local fixtures.
- Demo A shows normal evidence generation and validation.
- Demo B shows a blocked/remediated flow without requiring real risky actions.
- The quickstart explains what the user should observe without copying long
  transcripts into docs.

### Required Verification

```bash
python3 -m unittest tests.test_smoke_demo tests.test_onboarding_wizard tests.test_privacy_sanitization -v
python3 scripts/check_release_privacy.py --repo-root .
git diff --check
```

### Non-Goals

- Live host automation.
- Video production.
- Hosted demos.
- Claims that demos represent all real-world delivery risks.

### Stop Conditions

- Stop if a demo requires credentials or external service availability.
- Stop if demo artifacts include local machine-specific paths.
- Stop if the blocked demo can accidentally edit real user project files.

## Phase 4 - Evidence Benchmark Harness

### Objective

Create a lightweight benchmark or case-study harness that measures delivery
evidence quality and invalid-advancement prevention.

### Owned Files

```text
examples/evidence-benchmark/
docs/evidence-benchmark.md
src/roadmap_delivery/reports.py
src/roadmap_delivery/progress.py
tests/test_evidence_benchmark.py
tests/test_smoke_demo.py
```

### Inputs

- Demo fixtures.
- Validation and inspection reports.
- Review artifact schema.
- Progress signature and stall logic.
- Current release and quality gate tests.

### Implementation Steps

1. Define benchmark scenarios: clean delivery, missing review artifact, stale
   lifecycle filename, mismatched automation status, and insufficient
   verification evidence.
2. Build fixtures or scripted checks that produce structured report output for
   each scenario.
3. Define metrics such as invalid advancement caught, evidence completeness,
   remediation clarity, and false-positive warnings.
4. Add a report command or docs workflow that summarizes benchmark results.
5. Write a case-study document that reports measured outcomes and limitations.
6. Keep benchmark claims tied to the exact fixture scenarios.

### Acceptance Criteria

- Benchmark results are reproducible from repository-local fixtures.
- At least one invalid-advancement scenario is caught by validation.
- Evidence quality is measured through concrete fields, not subjective claims.
- The case study includes limitations and avoids commercial ROI claims.

### Required Verification

```bash
python3 -m unittest tests.test_evidence_benchmark tests.test_smoke_demo tests.test_quality_gates -v
git diff --check
```

### Non-Goals

- Performance benchmarking of model speed or cost.
- Vendor comparison claims.
- Paid ROI claims.
- External telemetry collection.

### Stop Conditions

- Stop if benchmark outputs cannot be reproduced locally.
- Stop if the benchmark encourages disabling safety gates to get a better
  score.
- Stop if claims exceed the measured fixture scenarios.

## Phase 5 - Quickstart Documentation And Closeout

### Objective

Finalize the onboarding path, demo docs, benchmark proof, and final review
prompt so the roadmap can be delivered.

### Owned Files

```text
README.md
docs/quickstart.md
docs/who-this-is-for.md
docs/onboarding-wizard.md
docs/evidence-benchmark.md
examples/
automation/<roadmap-slug>/
roadmaps/delivered_onboarding_wizard_and_proof_demos_roadmap.md
```

### Inputs

- Wizard implementation and tests.
- Golden-path demo fixtures.
- Benchmark harness and case-study results.
- Phase review artifacts.

### Implementation Steps

1. Update README so the first-use journey starts with quickstart, safe demo,
   wizard, then real project setup.
2. Ensure docs distinguish target users, non-target users, safe demos, real
   automation, and host package installation.
3. Run full relevant test and privacy checks.
4. Prepare a final deep review prompt covering onboarding friction, generated
   artifact validity, demo safety, benchmark claim accuracy, and docs clarity.
5. Rename the roadmap to `delivered_...` only after finalization evidence is
   complete.

### Acceptance Criteria

- A new user can follow one short safe path before configuring real automation.
- Wizard docs and generated files match implementation.
- Benchmark docs contain measured results and limitations.
- Final deep review prompt exists or a human waiver is recorded.

### Required Verification

```bash
python3 -m unittest discover -s tests -v
python3 scripts/build_adapters.py --check --json
python3 scripts/build_release.py --check --json
python3 scripts/check_release_privacy.py --repo-root .
git diff --check
```

### Non-Goals

- Publishing demos externally.
- Changing repository commercial positioning.
- Live host install tests unless already available and explicitly approved.

### Stop Conditions

- Stop if quickstart commands do not match implementation.
- Stop if final benchmark claims are not supported by local results.
- Stop if final review prompt has not been prepared or waived.
