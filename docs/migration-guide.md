# Migration Guide

## Upgrade To The 0.3.0 Candidate

Back up the complete installed package and repository state/journals. Select
Python 3.12 first. Stage the complete Codex/Claude archive from the same release,
run the installed helpers with `-I -S` from an unrelated project, and approve
replacement of the live install only after verification. Do not overlay runtime
or schema files or delete progress, migration or terminal journals. The CLI
build needs local setuptools>=68 and wheel; the skill runtime needs no pip.

Installing this candidate leaves saved automations unchanged. Capture fresh
host readback and expected runner identity into the sanitized local files used
below. A snapshot has `source`, `scheduler_authoritative`, `revision` and `config`; the config contains the actual id/cwds/target/execution environment
and all observed settings. Expected identity comes from trusted project setup.
Do not mark an ordinary file read authoritative for a live scheduler. Inspect
one upgrade using the **installed** portable entrypoint:

```bash
python3.12 -I -S "$INSTALLED_SKILL/scripts/roadmap_delivery.py" plan-migration \
  --roadmap-slug example --runner-snapshot runner-readback.json \
  --expected-file expected-runner.json \
  --policy-file automation/example/approval_policy.json \
  --roadmap-path roadmaps/not_started_example.md --json
```

For the exact known legacy fixture this returns a planned prompt/policy upgrade;
unknown text returns `needs-decision`. Save and inspect its digest, exact effects,
policy path and diffs. Grant only that runner/plan/direction/effect scope from
trusted operator evidence. A supported `MigrationAdapter` may then call
`resume_migration` with the same plan and repository-local journal; there is no
live apply CLI. Readback must verify the result before `record_verified_migration`
updates version provenance/history. Retry the same journal after interruption;
an applied update is checked before being repeated. After rollback, obtain a
fresh forward plan and scope grant. Separate rollback authority is required.

An unrelated legacy/custom prompt question cannot delay an otherwise authorized
completion/stall pause. Preserve opt-outs, custom policies, model/schedule/
notification settings and pending decisions. Prompt preparation, migration
planning, an acknowledgement and a verified host effect are distinct outcomes.

## Versioned Saved-Prompt Upgrades

Runtime contract versions record framework, prompt template (3), policy (2),
and semantic progress evidence (1), with local-generation or verified-migration
provenance. Installing an updated skill does not change saved prompts. New
scaffolds keep configured model/reasoning null until real runner readback.

Inspect one automation with authoritative adapter readback and a trusted expected
identity (id, cwds, target, execution_environment). Use sanitized local snapshots:

```bash
python3 -m roadmap_delivery.cli plan-migration --roadmap-slug example \
  --runner-snapshot runner-readback.json --expected-file expected-runner.json \
  --policy-file automation/example/approval_policy.json \
  --roadmap-path roadmaps/not_started_example.md --json
```

This command is read-only. It reports detected/planned/needs-decision separately,
exact prompt/policy diffs, effects, before/after values, and the plan digest.
The plan binds the observed host revision/source and the exact policy path,
including prompt-only plans that merely read that policy. Unbound plans cannot
execute, and even a no-effect plan requires fresh runner and policy readback.
After rollback, inspect and authorize a fresh plan before upgrading
again; a prior forward authorization cannot silently reverse a rollback. When
readback is otherwise unchanged (for example a policy-only rollback), pass
`--supersedes-rollback DIGEST` with the verified rollback receipt's digest to
create a distinct plan. The API equivalent is `supersedes_rollback`; execution
requires that receipt in the same journal and a new grant bound to the new plan.
Only exact generated prompt bodies frozen from repository history are recognized.
The literal-path legacy template needs its concrete old roadmap path. Arbitrary
text, appended human restrictions, missing policies and malformed policies need
an operator decision. Custom policies and explicit false pause flags are kept.
Only the exact known generated policy may make its existing implicit terminal
pause defaults explicit. History, model, status, schedule, notifications and
unknown runner fields are preserved.

The Python migration API accepts a supported `MigrationAdapter`; there is no
automatic live file-edit backend or bulk-upgrade CLI. `resume_migration` requires
scoped trusted setup/session authorization: authorized=true, runner_id, plan_id,
direction, exact effects, and evidence source. An already granted authorization
can be reused for its exact scope. Terminal status-only pause authority alone
does not authorize a prompt upgrade. Adapters must compare expected_revision,
preserve non-prompt settings, deduplicate request_id, and return authoritative
readback. A transport acknowledgement never proves verified migration.

Keep a repository-local journal and policy path in the same directory. Intent
is recorded before the host effect; applied and verified are distinct. Retry
the same plan/journal after an interruption: observed target values are verified
first, so an applied host update need not be repeated. Each direction has a
maximum of three effect attempts, including failed local policy writes. Completed
effects are verified before retrying only the remaining effects. Concurrent identity, prompt, policy or forward-runner
setting changes stop that individual migration for reconciliation.

`remember_decision` persists pending/approved/declined operator questions by
content digest, excluding transport-only revisions/timestamps. Authorization
continues to require the exact current plan digest. A repeated pending request returns ask_again=false without
rewriting the record. Unresolved decisions remain inspectable; they do not gate
an otherwise authorized completion/stall pause. `record_verified_migration`
merges matching verified receipts and version provenance into existing history;
it never populates configured fields from a proposal.

`rollback_plan` provides a bounded reverse plan. It restores only the migrated
prompt and an owned policy still equal to the migration output. Later human
prompt/policy edits require a decision. Later model, schedule, notification and
other settings are copied from fresh readback and preserved. Rollback needs
separate direction-scoped authorization and verified readback, and records its
own receipt rather than deleting history.

Compatibility: Python 3.12, stdlib-only portable runtime, cooperative POSIX
directory locks, host compare-and-set/idempotency support. Digests detect local
integrity changes; they do not authenticate an operator or prove external host
behavior. Required tests use isolated fake hosts. Optional live migration and
scheduler checks are skipped unless separately authorized and available.

This guide is for moving an existing Codex-only roadmap delivery setup onto the
framework core layout.

## What Changed

The old shape treated `skill/roadmap-delivery-skill/` as both source of truth
and installable package. The framework layout keeps that path installable, but
moves canonical behavior into:

- `core/references/` for workflow rules
- `core/templates/` and `core/prompts/` for reusable artifact text
- `schemas/` for versioned state, policy, review, and run-log contracts
- `src/roadmap_delivery/` for shared Python behavior
- `adapters/codex/` for Codex package rendering inputs

## Migration Steps

1. Keep the existing Codex install path:
   `skill/roadmap-delivery-skill/`.
2. Add or verify repository-local automation artifacts under
   `automation/<roadmap-slug>/`.
3. Add `schema_version: 1` to active delivery state when the automation is
   ready for schema validation.
4. Add `phase_model_policy.json` with required model and reasoning values.
5. Update automation prompts to include blocked remediation, model-policy
   gates, review gates, and completion hard stops.
6. Run artifact validation and status inspection from the repository checkout.
7. Use `scripts/build_codex_package.py --check` to prove the committed Codex
   package matches canonical core sources and the Codex adapter overlay.

## Autonomy Policy Opt-In

Existing automations stay conservative until each automation opts in. Migrate
one roadmap automation at a time:

1. Create `automation/<roadmap-slug>/approval_policy.json` with
   `approval_mode: "conservative"` first.
2. Run `python3 -m roadmap_delivery.cli validate ... --json` and confirm the
   effective approval mode, approved operations, and pause decisions are
   visible in the report.
3. Change to `delegated_local`, `delegated_delivery`, or `custom` only after
   the operator accepts the exact operation set.
4. Keep ordinary `retarget_saved_automation`, `pause_saved_automation`, and
   `push_current_phase_branch` disabled unless approved. Completion/stall
   status-only self-pause is separately allowed by default unless its context
   flag is explicitly false, including conservative and custom modes.
5. Never opt in operations listed under `never_auto`; validation treats those
   as forbidden even when an automation is otherwise delegated.

If `approval_policy.json` is missing, validators and inspectors use the
conservative legacy fallback. That is a valid legacy state. A state file that
claims delegated approval while the policy file is missing or invalid is not a
valid migration state.

Use `examples/autonomy-controls/approval-policy-examples.json` to compare the
standard modes before changing a live roadmap. To try delegated local behavior
without touching a real automation, copy
`examples/demo-roadmap/scenarios/delegated-local/approval_policy.json` into a
temporary demo checkout and run `inspect`; it should show local commits,
retargets, and completion or stall pauses as allowed while branch push remains
ask-first.

## Adaptive And Pause Evidence

When adopting adaptive model policy, add `adaptive_model_policy` to
`phase_model_policy.json` and keep caps explicit. The validator should show the
required model, configured model, run quality, and adaptive decision before any
saved automation retarget is attempted.

Completion and stall self-pause require readback evidence:

- `last_automation_pause` records the attempted pause decision and result.
- Successful pauses must include `PAUSED` readback.
- Completed roadmaps must keep a completed operator alert and final review
  evidence, even when a human still needs to pause an active automation.
- Run-log entries may include `run_quality` and `adaptive_action` so repeated
  runs can be audited without reopening older state snapshots.

Reference shapes are available under `examples/autonomy-controls/`:

- `adaptive-escalation-trace.json` shows why the next run is retargeted after a
  non-flawless run.
- `completion-self-pause-state.json` shows completed state with completed alert,
  final deep-review prompt metadata, and `PAUSED` readback.
- `stall-self-pause-run-log.jsonl` shows the stall-threshold audit line.

## Validation Commands

```bash
python3 -m roadmap_delivery.cli inspect \
  --repo-root /path/to/repo \
  --roadmap-slug <roadmap-slug> \
  --automation-id <automation-id> \
  --json

python3 -m roadmap_delivery.cli validate \
  --repo-root /path/to/repo \
  --roadmap-slug <roadmap-slug> \
  --automation-id <automation-id> \
  --strict \
  --allow-warning worktree_dirty \
  --json

python3 scripts/build_codex_package.py --check
```

## Compatibility Rules

- Do not mutate installed copies under
  `${CODEX_HOME:-$HOME/.codex}/skills/roadmap-delivery-skill` during migration.
- Do not rewrite historical roadmap evidence to satisfy new schemas unless a
  roadmap phase explicitly owns that migration.
- Keep generated package updates committed and reviewable.
- Treat publication, promotion, live automation config edits beyond terminal
  status-only self-pause, and installed skill synchronization as
  human-approved follow-ups.
