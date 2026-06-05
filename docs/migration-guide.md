# Migration Guide

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
4. Keep `retarget_saved_automation`, `pause_saved_automation`, and
   `push_current_phase_branch` disabled unless the automation owner has
   explicitly approved those surfaces.
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
