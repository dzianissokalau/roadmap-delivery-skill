# Runtime Reliability And Portable Installation Roadmap

Status: Completed Pending Pause
Created: 2026-10-13
Current phase: finalization
Last completed phase: Phase 9 - Documentation And Release Evidence
Next action: Independent re-review is delivered with no open findings. Complete the authorized code-promotion checks; keep the automation paused and confirm authoritative scheduler readback separately.
Blocked by: No open code-review finding. Operational closeout still lacks an authoritative scheduler pause receipt; saved configuration reads PAUSED. Numbered-phase history and terminal hard stop are preserved. This limitation does not certify live scheduler behavior.
Final deep review: [Sanitized review and verification summary](../automation/runtime-reliability-and-portable-installation/publication_review.md)
Historical review and host receipts: preserved locally, excluded from publication because they contain machine-specific evidence.

## Purpose

Deliver the six findings from the skill review and prevent their recurrence
through shared executable control decisions, portable installation, explicit
upgrade handling, and behavioral verification across consecutive runs.

This is one sequential roadmap because approval, progress, completion, package
generation, and saved-prompt migration share runtime contracts. The operator
requested automation creation after planning; setup does not deliver Phase 0
or publish changes.

## Evidence And Traceability

Review baseline: local `main` at `517bbdd`. The installed skill matched the
generated repository package. The existing suite ran 215 tests, with one
skipped and no failures; adapter generation checks passed. These results did
not prove the behaviors below. Reproduce against the delivery-time baseline
before relying on old line numbers or test counts.

| ID | Finding and evidence | Primary sources | Delivery phases |
|---|---|---|---|
| R1 | Five simulated runs with the same phase/blocker and changing log fingerprints all reset stalled runs to zero. | `src/roadmap_delivery/progress.py`, `tests/test_helper_scripts.py` | 0, 2, 8 |
| R2 | Installed validation/progress helpers failed outside the checkout with the package not importable; installation tests inject repository `src` into `PYTHONPATH`. | `skill/roadmap-delivery-skill/scripts/`, `tests/test_install_smoke.py`, `scripts/host_smoke.py` | 0, 4, 8 |
| R3 | Pause defaults conflict with residual approval language; updating a skill does not migrate legacy saved prompts. This is an instruction/upgrade ambiguity, not a live scheduler reproduction. | `core/`, `adapters/codex/templates/references/`, generated model-policy and troubleshooting references | 0, 1, 3, 6, 7, 8 |
| R4 | A valid status line with an inline comment produces a duplicate status key during pause editing. | `src/roadmap_delivery/automation.py`, `src/roadmap_delivery/toml.py` | 0, 3, 8 |
| R5 | Explicit completion/stall opt-outs still resolve to allowed in delegated modes. | `src/roadmap_delivery/approval.py`, duplicated adapter planners | 0, 1, 8 |
| R6 | A policy with a high reasoning floor validates but can select low after a flawless run. | `src/roadmap_delivery/adaptive.py`, adapter retarget planner | 0, 5, 8 |

## Delivery Defaults

```text
ROADMAP_SLUG=runtime-reliability-and-portable-installation
AUTOMATION_DIR=automation/runtime-reliability-and-portable-installation
STATE_FILE=automation/runtime-reliability-and-portable-installation/delivery_state.json
AUTOMATION_ID=runtime-reliability-and-portable-installation
MAX_STALLED_RUNS=2
MAX_REVIEW_ITERATIONS=3
PAUSE_ON_COMPLETION=true
PAUSE_ON_STALL=true
EXECUTION_ENVIRONMENT=local
CADENCE=hourly
```

The handoff guide and state are stable entrypoints. The saved prompt must
resolve the current roadmap from `delivery_state.json`; lifecycle renames must
not require editing that prompt.

Saved runner model: `gpt-6.1-sol` with `xhigh` for every phase and finalization.
Setup confirmed the actual configuration and activated `phase_model_policy.json`.
This saved-runner readback is not a claim about the current chat's model.
Keep adaptive selection disabled for this delivery until the operator chooses
otherwise; the roadmap tests adaptive behavior using fixtures.

Conservative approval mode is recorded in the handoff. Phase edits,
bookkeeping, verification, and local branch work are allowed. Commits are
optional for this roadmap. Existing explicit authorization remains valid for
its scope; do not ask again solely because an operation is normally gated.
No phase requires publication, global installation, or modification of an
unrelated saved automation to pass its offline acceptance criteria.

## Required End State

- One shared implementation decides workflow transitions and effective policy;
  adapters supply capabilities and execute permitted effects.
- Two consecutive unique runs without meaningful progress trigger the default
  stall pause; routine bookkeeping cannot reset the counter.
- Completion produces durable alert evidence and confirmed scheduler pause,
  or a truthful pending/disabled/unavailable outcome with a specific cause.
- Explicit context opt-outs override broad mode defaults. Specific operator
  instructions are preserved and never invented by migration.
- A skill-only install works in another repository without the source checkout,
  developer `PYTHONPATH`, or undeclared globally installed Python packages.
- Every resolved adaptive target obeys applicable model allowlists, reasoning
  floors, and caps; persisted targets cannot bypass current policy.
- Known legacy prompt upgrades are inspectable, resumable, and idempotent.
- Generated references, runtime decisions, tests, and user-facing instructions
  agree about completion, stalls, activation, and approval.

## Common Phase Contract

Deliver exactly one numbered phase per run. A successful phase needs its
acceptance evidence, required checks, and a fresh review artifact with verdict
`delivered` before advancement. A same-context review must state its limitation.
Allow at most three review/fix iterations; repair resolvable blockers before
repeating delivery. Do not count planning, a review rewrite, or a new commit as
phase delivery by itself.

Every phase may update this roadmap and its own directory under
`automation/runtime-reliability-and-portable-installation/`. Preserve unrelated
work. Use branches named `codex/runtime-reliability-and-portable-installation-phase-N`;
carry forward delivered work instead of starting each branch from old main.
Record branch/base/readback evidence when delivery actually starts.

When an owned canonical source changes, regenerate its corresponding outputs
under `skill/roadmap-delivery-skill/` and `dist/claude/`, plus affected adapter
snapshots. These derived changes are phase-owned; hand-editing generated
outputs is not. Regenerate by the repository builders, then require a clean
generation check. Do not expand a phase into unrelated adapter features.

Use the existing repository test conventions. Test module names below that do
not yet exist are deliverables of their owning phase. Add regression assertions
when the behavior is fixed; Phase 0 captures known failures without leaving
the default suite red or permanently accepting broken behavior.

Rename `not_started_` to `in_progress_` at delivery activation, before Phase 1
at the latest. Update current repository references consistently and preserve
history with an append-only rename record. Rename to `delivered_` only after
the finalization gate; the last numbered phase is not that gate.

## Phase Overview

| Phase | Outcome | Dependencies | Evidence |
|---|---|---|---|
| 0 | Reproductions and shared control contract | None | Six cases and a transition matrix |
| 1 | Canonical control decisions and pause precedence | 0 | Policy cross-product and transition tests |
| 2 | Meaningful progress and consecutive-run accounting | 1 | Repeated-run and retry tests |
| 3 | Safe runner updates and resumable terminal closeout | 1, 2 | Adapter and failure-injection tests |
| 4 | Self-contained skill and release runtime | 1, 2, 3 | Clean-install checks without checkout access |
| 5 | Adaptive target floors, caps, and provenance | 1, 4 | Target-resolution matrix |
| 6 | Versioned legacy prompt and policy migration | 1, 3, 4, 5 | Upgrade, rollback, and authorization fixtures |
| 7 | Concise instructions and complete runtime integration | 1 through 6 | All entrypoints use shared decisions |
| 8 | End-to-end behavioral acceptance | 0 through 7 | Install-to-completion and blocked-run replays |
| 9 | Documentation, release evidence, and review handoff | 8 | Full verification and final review prompt |
| Finalization | Record delivery and operational stop accurately | 9 | Alert, pause readback, or documented exception |

## Phase 0 - Regression Evidence And Control Contract

### Objective

Capture the review failures and agree on observable behavior before replacing
control logic.

### Owned Files

```text
docs/runtime-control-contract.md
tests/fixtures/runtime-reliability/
tests/test_runtime_contract.py
```

### Inputs And Prerequisites

Review R1-R6, current shared library, adapter planners, approval/model schemas,
and existing tests. Requires Python and Git; fixtures must use isolated roots.

### Implementation Steps

1. Record the actual base commit and reproduce each executable finding with
   raw input, observed output, expected output, and reproduction command.
2. Capture R3 as an instruction/provenance scenario; do not label a simulated
   response as evidence that the live scheduler changed.
3. Define ordered transitions: terminal reconciliation, intentional activation,
   blocked remediation, current-phase prerequisites, delivery/review, then
   next-phase or finalization planning. Normal delivery gates must not prevent
   an otherwise authorized terminal status-only pause.
4. Define contracts for run identity, progress evidence, policy precedence,
   runner identity/capabilities, effect receipts, and completion outcomes.
5. Add data-driven fixtures and tests for the contract/fixture format. Store
   current defects in the baseline report until their owning fixes add passing
   regression assertions. Do not make broken outcomes the permanent oracle.

### Acceptance Criteria

- R1-R6 each have an input and an explicit expected result, with evidence type.
- The contract distinguishes real progress from activity and authorization from
  host capability, as well as desired configuration from observed readback.
- First failed run, second failed run, duplicate invocation, restart, and
  operator resume semantics are specified without an extra uncounted grace run.
- A review identifies no unresolved contract ambiguity that blocks Phase 1.

### Required Verification

```bash
python3 -m unittest tests.test_runtime_contract tests.test_quality_gates -v
git diff --check
```

### Non-Goals And Stop Conditions

No production controller or live runner changes. Stop for a genuine unresolved
contract decision; record environmental limitations without claiming a live
reproduction. Existing historical evidence is an input, not a fresh test pass.

## Phase 1 - Canonical Control Decisions And Pause Precedence

### Objective

Introduce a small shared decision layer and make explicit pause opt-outs work
consistently in every approval mode.

### Owned Files

```text
src/roadmap_delivery/control.py
src/roadmap_delivery/approval.py
src/roadmap_delivery/validation.py
src/roadmap_delivery/reports.py
src/roadmap_delivery/cli.py
schemas/approval_policy.schema.json
schemas/delivery_state.schema.json
adapters/codex/templates/scripts/plan_phase_prerequisites.py
adapters/codex/templates/scripts/plan_automation_retarget.py
tests/test_runtime_control.py
tests/test_approval_policy.py
tests/test_completion_pause_policy.py
tests/test_phase_preflight.py
tests/test_cli.py
docs/runtime-control-contract.md
```

### Inputs And Prerequisites

Phase 0 transition matrix and R5 regression inputs. The library remains the
source of truth; adapter distribution must remain usable during migration.

### Implementation Steps

1. Implement a pure decision function taking validated state, policy, evidence,
   and runner capabilities. Return the next action, reason code, effective
   authority, proposed state changes, and required effects without mutating.
2. Centralize pause resolution. An explicit context `false` suppresses automatic
   pausing even when broad pause permission is true; missing flags default true.
   A later explicit operator pause request remains a separately authorized act.
3. Reject malformed policies for execution; distinguish missing-policy defaults
   from invalid-policy fallback used only for reporting.
4. Expose an inspectable plan through the CLI and integrate existing validation
   and prerequisite callers. Specify stable exit/result categories.
5. Replace duplicated decisions where possible now. If standalone adapters need
   generated shared code until Phase 4, prove equivalence and remove that bridge
   in Phase 7; do not maintain hand-copied independent policy functions.

### Acceptance Criteria

- Conservative, delegated-local, delegated-delivery, and custom modes pass
  missing/true/false context flags crossed with broad permission true/false.
- Completion and stall defaults work without a policy file, while invalid
  policy and unavailable tools remain distinct outcomes.
- Intentional activation with matching identity/configuration is reconciled;
  activation cannot reopen a completed roadmap without an explicit new scope.
- The decision function is deterministic and has no filesystem or host effects.

### Required Verification

```bash
python3 -m unittest tests.test_runtime_control tests.test_approval_policy tests.test_completion_pause_policy tests.test_phase_preflight tests.test_cli -v
python3 scripts/build_adapters.py --check --json
git diff --check
```

### Non-Goals And Stop Conditions

No scheduler service or generic workflow engine. Do not widen permissions during
normalization. Stop if a valid policy produces divergent shared/adapter results.

## Phase 2 - Meaningful Progress And Consecutive Run Accounting

### Objective

Make the default two-run stall limit measure actual delivery progress.

### Owned Files

```text
src/roadmap_delivery/progress.py
src/roadmap_delivery/control.py
src/roadmap_delivery/state.py
src/roadmap_delivery/validation.py
src/roadmap_delivery/reports.py
schemas/delivery_state.schema.json
schemas/automation_run_log.schema.json
tests/test_progress_semantics.py
tests/test_helper_scripts.py
tests/test_library_units.py
tests/test_completion_pause_policy.py
core/references/model-policy-and-stall-control.md
adapters/codex/templates/references/model-policy-and-stall-control.md
```

### Inputs And Prerequisites

Phase 1 decisions and Phase 0 progress contract. Tests use temporary state and
fake runner adapters; no real automation is required.

### Implementation Steps

1. Introduce versioned semantic progress evidence: new accepted phase work,
   newly satisfied verification/acceptance criteria, or a verified blocker
   resolution. Mere claims or different hashes must not prove progress.
2. Exclude timestamps, log size/content, repeated review paths/verdicts, wording
   changes, and bookkeeping-only commits from progress advancement.
3. Track unique run IDs and initial/ending evidence. Count the first completed
   no-progress attempt as one and the second as two; retries of the same run
   must not increment counters twice.
4. Migrate old signatures without treating the migration as delivery progress
   or silently erasing known consecutive failures. Record uncertain history.
5. Preserve the actionable blocker while storing stall metadata separately.
   Feed threshold decisions into terminal closeout, not repeated phase work.

### Acceptance Criteria

- Ten unchanged-blocker runs with fresh logs/reviews/commits cannot evade the
  two-run threshold; one confirmed repair resets the consecutive count once.
- Configurable thresholds one, two, and three have exact, tested boundaries.
- Duplicate and interrupted recordings preserve run counts and original causes.
- Changed failure wording and repeated passing checks are not new progress.

### Required Verification

```bash
python3 -m unittest tests.test_progress_semantics tests.test_runtime_control tests.test_helper_scripts tests.test_library_units tests.test_completion_pause_policy -v
python3 scripts/build_adapters.py --check --json
git diff --check
```

### Non-Goals And Stop Conditions

Do not measure productivity by tokens, narration, or raw diff size. Stop if
migration loses history or test outcomes depend on wall-clock timing.

## Phase 3 - Safe Runner Updates And Resumable Terminal Closeout

### Objective

Complete authorized terminal pauses reliably and record what the runner
actually acknowledged, including interrupted or failed attempts.

### Owned Files

```text
src/roadmap_delivery/automation.py
src/roadmap_delivery/toml.py
src/roadmap_delivery/control.py
src/roadmap_delivery/progress.py
src/roadmap_delivery/state.py
src/roadmap_delivery/alerts.py
src/roadmap_delivery/validation.py
src/roadmap_delivery/cli.py
schemas/delivery_state.schema.json
host-capabilities/codex.yaml
host-capabilities/claude.yaml
tests/test_runner_updates.py
tests/test_terminal_closeout.py
tests/test_completion_pause_policy.py
tests/test_library_units.py
```

### Inputs And Prerequisites

Phase 1 effect contract, Phase 2 run identity, and R4 TOML reproduction. Use a
fake host with observable status. Actual host mutation requires an available
supported operation and authorization for the selected automation.

### Implementation Steps

1. Define a narrow runner interface for readback and status-only pause. Prefer
   the host's supported operation; a CLI may emit an action request for the
   agent's host tool instead of pretending Python can call an unavailable tool.
2. Verify runner identity, scope, and observed revision before an update.
   Preserve prompt, schedule, model, cwd/project, notification settings, and
   unrelated fields even when a host requires a full update payload.
3. Replace regex TOML mutation. Permit a file backend only where the host
   contract supports it; parse with a real TOML parser, validate the candidate,
   use atomic replacement/concurrency checks, and preserve unrelated values.
4. Add resumable closeout: record intent and local alert, request pause, read
   back through the adapter, then record the receipt and final state. Replaying
   after any step must neither restart phase delivery nor duplicate effects.
5. Distinguish paused, intentionally disabled, permission required, unsupported,
   and transient failure. Do not claim scheduler pause from file text alone
   unless the adapter's documented source of truth warrants that claim.
6. Bound transient retries, preserve evidence, and expose the exact remaining
   action if the host cannot be controlled. Do not require a stronger execution
   model solely to perform already-authorized terminal cleanup.

### Acceptance Criteria

- Completion and repeated-stall fixtures end with acknowledged PAUSED by
  default; explicit opt-outs leave the runner untouched and are recorded.
- Inline comments, multiline prompts containing status-like text, tables,
  malformed TOML, read-only files, stale revisions, and rejected host updates
  do not corrupt configuration or produce a false success.
- Crash injection before/after each effect and duplicate invocation converge
  on one terminal outcome; state, log, alert, and receipt remain reconcilable.
- Already-paused and manual/no-scheduler workflows have explicit semantics.

### Required Verification

```bash
python3 -m unittest tests.test_runner_updates tests.test_terminal_closeout tests.test_completion_pause_policy tests.test_progress_semantics tests.test_library_units -v
python3 scripts/build_adapters.py --check --json
git diff --check
```

### Non-Goals And Stop Conditions

No live production automation mutations in tests. Stop an effect when identity
or readback cannot be proven; report unsupported live capability separately
from a failed offline implementation. No broad scheduler rewrite.

## Phase 4 - Self-Contained Skill And Release Runtime

### Objective

Make documented installation sufficient to run the skill in another project.

### Owned Files

```text
adapters/codex/
adapters/claude/
scripts/build_adapters.py
scripts/build_codex_package.py
scripts/build_release.py
scripts/host_smoke.py
src/roadmap_delivery/paths.py
src/roadmap_delivery/validation.py
src/roadmap_delivery/rendering.py
src/roadmap_delivery/scaffold.py
pyproject.toml
tests/test_portable_install.py
tests/test_install_smoke.py
tests/test_release_builder.py
tests/test_adapter_build_system.py
tests/test_adapter_codex.py
tests/test_claude_plugin_package.py
tests/test_host_smoke.py
docs/installing-codex.md
docs/installing-claude.md
```

### Inputs And Prerequisites

Phase 3 runtime, R2 reproduction, release manifest, and supported Python
versions. Build from local sources; fixtures must not download dependencies.

### Implementation Steps

1. Inventory runtime imports, schemas, templates, and data required by installed
   inspect, validate, progress, alerts, control, scaffold, and planner commands.
2. Bundle the shared runtime/resources in generated packages and load them
   relative to the installed package. Preserve documented helper entrypoints.
   Include any TOML compatibility dependency needed for supported Python.
3. Apply the same dependency closure to the Claude package and separately
   installed CLI. Detect/report mixed runtime and resource versions.
4. Remove checkout `PYTHONPATH` injection from install acceptance tests. Run
   subprocesses from an unrelated project with no source checkout on import
   paths and no undeclared site packages; check resolved module origins.
5. Test skill-directory installation, extracted release installation, and local
   CLI installation in isolated environments. Test that missing schemas fail
   clearly rather than silently weakening claimed full validation.
6. Update manifests, snapshots, checksums, size inventory, and installation
   instructions for the complete artifact. Do not copy user data into bundles.

### Acceptance Criteria

- R2 succeeds from a clean unrelated working directory with no framework
  checkout import access or developer environment variables.
- All documented installed commands load only bundled/declared dependencies
  and exercise actual validation, not only `--help`.
- Supported Python versions are tested, or the declared support range is
  explicitly revised with migration instructions and evidence.
- Builds remain reproducible and privacy checks exclude operational artifacts.

### Required Verification

```bash
python3 -m unittest tests.test_portable_install tests.test_install_smoke tests.test_release_builder tests.test_adapter_build_system tests.test_adapter_codex tests.test_claude_plugin_package tests.test_host_smoke -v
python3 scripts/build_adapters.py --check --json
python3 scripts/build_release.py --check --json
python3 scripts/check_release_privacy.py --repo-root .
git diff --check
```

### Non-Goals And Stop Conditions

No registry publication or global installation. Stop if a clean install needs
hidden checkout access, network downloads, or a package with unclear licensing.

## Phase 5 - Adaptive Targets Within Floors And Caps

### Objective

Ensure every selected next-run model/reasoning target is valid and justified.

### Owned Files

```text
src/roadmap_delivery/adaptive.py
src/roadmap_delivery/policy.py
src/roadmap_delivery/control.py
src/roadmap_delivery/validation.py
schemas/phase_model_policy.schema.json
adapters/codex/templates/scripts/plan_automation_retarget.py
tests/test_adaptive_model_policy.py
tests/test_model_target_constraints.py
tests/test_helper_scripts.py
core/references/model-policy-and-stall-control.md
adapters/codex/templates/references/model-policy-and-stall-control.md
```

### Inputs And Prerequisites

R6 reproduction, shared policy resolution, and the portable runtime. The
delivery runner itself stays on the selected fixed policy; tests vary targets.

### Implementation Steps

1. Resolve base phase requirements, adaptive proposal, applicable floors/caps,
   and supported host values into one final target. Define conflict outcomes.
2. Enforce floors on de-escalation and caps/allowlists on all resolved targets,
   including defaulted and persisted values. Fail clearly on floor above cap.
3. Preserve higher configured reasoning that already satisfies the requirement;
   optional cost reductions must not become delivery blockers.
4. Bind quality and target provenance to phase/run/policy version. Stale
   `last_run_quality` or `last_adaptive_action` must not override current evidence
   or a newer policy. Human-required blockers must not trigger pointless model
   escalation by default.
5. Enforce provider/cost-class limits only from explicit trusted metadata; an
   unresolved limit must not be presented as enforced through guessed pricing.

### Acceptance Criteria

- High floor plus low de-escalation never yields low; contradictory policies
  return a clear invalid-policy result.
- Defaults, overrides, escalation, de-escalation, persisted targets, invalid
  values, and changed policy versions pass the target-resolution matrix.
- Host capability uncertainty is explicit and does not change an active model.

### Required Verification

```bash
python3 -m unittest tests.test_model_target_constraints tests.test_adaptive_model_policy tests.test_helper_scripts tests.test_runtime_control -v
python3 scripts/build_adapters.py --check --json
git diff --check
```

### Non-Goals And Stop Conditions

No model leaderboard, vendor pricing integration, or live model retarget for
test coverage. Stop if constraints cannot be resolved without guessing.

## Phase 6 - Versioned Prompt And Policy Migration

### Objective

Upgrade existing automations so corrected behavior reaches saved prompts and
policies while preserving operator intent and history.

### Owned Files

```text
src/roadmap_delivery/migrations.py
src/roadmap_delivery/control.py
src/roadmap_delivery/scaffold.py
src/roadmap_delivery/wizard.py
src/roadmap_delivery/cli.py
src/roadmap_delivery/validation.py
schemas/delivery_state.schema.json
core/templates/automation_prompt.md
core/templates/delivery_state.md
core/templates/approval_policy.md
tests/test_runtime_migrations.py
tests/fixtures/runtime-reliability/
tests/test_cli.py
tests/test_onboarding_wizard.py
docs/migration-guide.md
```

### Inputs And Prerequisites

Versioned runtime contracts, safe runner adapter, bundled resources, and known
legacy generated prompts from the repository. Use sanitized fixtures only.

### Implementation Steps

1. Record framework, prompt-template, policy, and progress-evidence versions
   with provenance. Add a read-only migration plan with exact diffs and effects.
2. Recognize known generated approval language and state-first path upgrades.
   Distinguish template defaults from custom human restrictions and unknown
   prompt text; unknown text must not be silently rewritten.
3. Preserve scoped authorization already granted in setup/session evidence.
   A skill update alone is not evidence that a saved prompt was migrated, and
   migration must not claim authority to override explicit operator limits.
4. Apply approved changes through the runner adapter with readback; record
   before/after digests and migration receipts. Resume after interruption and
   provide a bounded rollback plan that preserves subsequent human changes.
5. Report detected, planned, applied, verified, and needs-decision separately.
   Prevent repeated identical approval questions by persisting the unresolved
   decision; keep terminal pause eligibility independent of unrelated upgrades.

### Acceptance Criteria

- Known old generated prompts can reach the new terminal behavior through an
  authorized migration with verified readback; reapplication is a no-op.
- Custom restrictions, disabled pauses, missing policies, malformed policies,
  partial migrations, and concurrent edits are tested.
- No migrated record falsely reports configured model/status or a host update.
- Unresolved real operator decisions remain visible without an unbounded retry
  loop or silently expanding permissions.

### Required Verification

```bash
python3 -m unittest tests.test_runtime_migrations tests.test_runner_updates tests.test_cli tests.test_onboarding_wizard tests.test_schema_validation -v
python3 scripts/build_adapters.py --check --json
git diff --check
```

### Non-Goals And Stop Conditions

No bulk edits to the user's saved automations during development. Stop an
individual migration for ambiguous provenance or changed runner identity;
complete unaffected local tests and report the decision needed.

## Phase 7 - Instruction Consolidation And Runtime Integration

### Objective

Make every entrypoint use the shared control decisions and leave concise,
consistent instructions for the agent's remaining judgment.

### Owned Files

```text
core/references/
core/prompts/
core/templates/
adapters/codex/templates/
adapters/claude/templates/
adapters/generic/templates/
src/roadmap_delivery/cli.py
src/roadmap_delivery/scaffold.py
src/roadmap_delivery/wizard.py
src/roadmap_delivery/reports.py
automation/codex_phase_gated_delivery_automation_template.md
automation/roadmap_closeout_checklist.md
tests/test_core_sources.py
tests/test_adapter_parity.py
tests/test_phase_preflight.py
tests/test_onboarding_wizard.py
tests/test_runtime_entrypoints.py
docs/architecture.md
docs/autonomy-and-approval-policy.md
```

### Inputs And Prerequisites

Phases 1-6 and current skill-creator guidance. Read the existing entrypoint
routes before editing; preserve supported invocations and user intent.

### Implementation Steps

1. Route setup, start-run, blocked repair, progress recording, next-run model
   selection, completion, validation, and inspection through shared decisions.
2. Remove temporary duplicate implementations and stale phase-development
   language. Keep host-specific execution guidance separate from policy logic.
3. Reduce the skill entrypoint to routing, essential invariants, and a short
   ordered workflow. References should explain evidence and recovery, not
   independently redefine the permission model.
4. Make terminal exceptions, explicit opt-outs, intentional activation, and
   sufficient higher reasoning consistent across generated prompts/references.
5. Update the older automation template's three-stall default to two and audit
   setup examples against the effective runtime. Preserve historical logs.
6. Exercise equivalent inputs through CLI, installed helpers, scaffold/wizard,
   prerequisite planner, and applicable host adapters; compare semantic output.

### Acceptance Criteria

- Equivalent inputs have equivalent decisions across all supported entrypoints.
- No broad pause-approval statement contradicts terminal defaults or opt-outs.
- Manual activation and lifecycle filename repair remain local reconciliation
  where authorized; neither becomes an unnecessary saved-prompt retarget.
- Behavioral tests complement wording/snapshot tests rather than treating
  matching text as proof of runtime correctness.

### Required Verification

```bash
python3 -m unittest tests.test_runtime_entrypoints tests.test_core_sources tests.test_adapter_parity tests.test_phase_preflight tests.test_onboarding_wizard tests.test_portable_install -v
python3 scripts/build_adapters.py --check --json
python3 scripts/build_codex_package.py --check
git diff --check
```

### Non-Goals And Stop Conditions

No unrelated instruction rewrite or new host feature. Stop if simplification
removes an operational invariant or creates a new copy of shared policy logic.

## Phase 8 - End To End Behavioral Acceptance

### Objective

Prove complete multi-run workflows using released package contents and isolated
host doubles, and label the limits of that evidence accurately.

### Owned Files

```text
tests/test_runtime_scenarios.py
tests/test_portable_install.py
tests/test_terminal_closeout.py
tests/fixtures/runtime-reliability/
scripts/host_smoke.py
tests/test_host_smoke.py
.github/workflows/ci.yml
.github/workflows/release-check.yml
docs/host-smoke-checks.md
host-capabilities/codex.yaml
host-capabilities/claude.yaml
```

### Inputs And Prerequisites

Phases 0-7, packaged runtime, and fake scheduler with inspectable events. The
required suite is offline; live-host coverage is a separate opt-in activity.

### Implementation Steps

1. Run installation, setup, activation, phase delivery, review, finalization,
   alert, and scheduler pause as one scenario using isolated package contents.
2. Replay repeated unchanged blockers with new logs/reviews, genuine repair,
   duplicate run IDs, restart after partial writes, and concurrent stale plans.
3. Cross missing/conservative/delegated/custom policy with pause defaults and
   opt-outs. Replay higher reasoning, floor conflicts, and legacy prompt upgrade.
4. Inject failures before/after each closeout effect. Verify no duplicate phase
   work, lost blocker, fabricated readback, or endless closeout retry.
5. Add an independent fresh-context skill evaluation with raw fixtures and
   realistic requests, without supplying the intended answer. Evaluate intended
   tool actions and artifacts in a sandbox; report unavailable evaluation as
   skipped instead of claiming agent-level reliability.
6. Run mandatory behavioral tests in CI. Keep offline simulation, host binary
   availability, real host update/readback, and independent agent evaluation as
   separate evidence categories. A `--help` call is not a scheduler test.

### Acceptance Criteria

- Every R1-R6 case has a passing behavioral regression through its deployed
  entrypoint, plus a scenario covering interactions with the other changes.
- Three independent temporary project roots show no shared state/config leaks.
- Tests detect deliberately reintroduced old behavior in the six regressions.
- All mandatory offline scenarios pass; optional/live skips are explicit and
  cannot support claims that real scheduler stopping was verified.

### Required Verification

```bash
python3 -m unittest tests.test_runtime_scenarios tests.test_portable_install tests.test_terminal_closeout tests.test_runtime_migrations tests.test_host_smoke -v
python3 -m unittest discover -s tests -v
python3 scripts/build_adapters.py --check --json
python3 scripts/build_release.py --check --json
python3 scripts/check_release_privacy.py --repo-root .
git diff --check
```

### Non-Goals And Stop Conditions

No mandatory credentials or real scheduled tasks in normal CI. Stop a live
test if isolation cannot be established. A missing optional host surface must
limit the evidence claim, not block already-proven offline delivery.

## Phase 9 - Documentation And Release Evidence

### Objective

Prepare a reviewable release candidate with honest installation, upgrade, and
operational guarantees.

### Owned Files

```text
README.md
CHANGELOG.md
docs/architecture.md
docs/compatibility.md
docs/quickstart.md
docs/installing-codex.md
docs/installing-claude.md
docs/migration-guide.md
docs/autonomy-and-approval-policy.md
docs/release-process.md
docs/host-smoke-checks.md
host-capabilities/
VERSION
pyproject.toml
scripts/build_release.py
tests/test_release_builder.py
```

### Inputs And Prerequisites

Phase 8 scenario results, all phase reviews, release manifest, migration report,
and actual host coverage. Choose the next version from the delivery-time
repository state; do not promise a version before compatibility is known.

### Implementation Steps

1. Document a clean user's install and first run, supported Python/host versions,
   default two-run pause behavior, opt-outs, and exact migration procedures.
2. Describe interrupted-closeout recovery and operational limitations. Clearly
   separate a prepared review prompt from an executed independent deep review.
3. Update changelog/version metadata consistently where a version change is
   warranted, build local release artifacts, and record reproducibility/privacy
   results with their tested source revision.
4. Prepare the final deep-review prompt under this roadmap's automation
   directory, covering all phases, evidence, migration, permissions, packaging,
   branch/worktree risks, and promotion readiness.
5. Record residual issues with severity, scope, and evidence. Any unresolved
   core regression returns to its owning phase/fix work before completion.

### Acceptance Criteria

- Install and migration instructions work against the tested release artifact.
- R1-R6 map to implementation, test, and review evidence; no core finding is
  closed by a prose change alone where executable behavior is involved.
- The release evidence distinguishes passed, failed, skipped, and untested.
- A standalone final review prompt exists and state records its actual status;
  Phase 9 delivery still leaves finalization outstanding.

### Required Verification

```bash
python3 -m unittest discover -s tests -v
python3 scripts/build_adapters.py --check --json
python3 scripts/build_codex_package.py --check
python3 scripts/build_release.py --check --json
python3 scripts/check_release_privacy.py --repo-root .
git diff --check
```

### Non-Goals And Stop Conditions

No automatic release publication, main promotion, or installed-skill sync.
Stop closeout if claims exceed the evidence or a core regression remains open.

## Finalization

Load the skill's finalization reference after Phase 9. Resolve the actual
finalization model policy and confirm final checks and delivered reviews. Keep
the prepared final review artifact distinct from each phase review; record
`prompt-prepared`, `review-complete`, or a genuine human waiver accurately.

For scheduled execution, run the terminal controller, write/confirm the local
completed alert, perform the default status-only self-pause, and verify the
selected runner's status through its adapter. Set completed only with the
required evidence; otherwise preserve the appropriate pending/disabled outcome
with a specific cause and bounded recovery action. For manual delivery, record
that no scheduler exists instead of fabricating PAUSED readback.

Reconcile lifecycle names and current references, record final verification and
branch/worktree state, and prepare promotion readiness. Delivery completion
does not itself publish changes or authorize global skill synchronization.
