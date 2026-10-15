# State, Log, And Branches Reference

Use this reference for status inspection and for reconciling roadmap delivery
surfaces before work.

## Core Contract

The roadmap, delivery state, delivery log, review/fix state, review artifacts,
phase model policy, branch, and worktree status are the durable control plane.
Do not advance a phase when these surfaces disagree unless the mismatch is
current-phase scoped and locally repairable.

## Delivery State

State must record:

- roadmap path and slug
- current phase and branch
- status
- review iteration counters
- latest verification and review evidence
- last delivered phase
- blocker and blocker repair evidence
- manual activation evidence when setup PAUSED is reconciled to ACTIVE
- required and configured model/reasoning values
- run/stall counters, active run and semantic progress evidence
- operator alert evidence
- updated timestamp

Status values are `not_started`, `delivering`, `verifying`, `reviewing`,
`fixing`, `delivered`, and `blocked`. Blocked is a remediation state, not a
retry loop.

When a blocked run becomes repairable, record the repair in
`last_blocker_repair`, clear `blocked_reason` only after validation/readback
passes, and return the current phase to `not_started`, `delivering`, or
`fixing` as appropriate. A previous blocked review is historical evidence; it
does not prevent delivery when a later repair is recorded and reconciliation
passes.

When a manually activated runner resolves a setup PAUSED/ACTIVE mismatch, also
record `last_activation` with the accepted readback, source of acceptance, and
timestamp. The delivery log and automation guide must then agree that the
runner is ACTIVE before phase work resumes.

## Delivery Log

The log is append-only after delivery starts. Each phase entry records status,
branch, scope, changed files, verification commands and results, review file
and verdict, residual risks, and next action.

## Review Directory

Review artifacts live under:

```text
automation/<roadmap-slug>/reviews/
```

Names follow:

```text
<roadmap-slug>-phase-<n>-review-iteration-<m>.md
```

The latest review verdict must agree with state before phase advancement.

## Branches And Worktree

Implementation phases use a dedicated phase branch. The branch prefix is a
workflow setting supplied by the host adapter or project convention.

Preserve prior delivered and intentional planning changes, including uncommitted
phase-owned work. Investigate unexplained edits that affect verification. Never clean, stash,
restore, or rewrite unrelated work without operator approval.

## Progress And Stall Tracking

Use the shared semantic journal described in `model-policy-and-stall-control.md`.
Allocate one stable run ID before work; recover unfinished attempts and record
exactly one outcome per unique run. Only newly verified accepted work, satisfied
criteria or original-cause repair can reset `stalled_run_count`. Timestamps,
review filenames, log edits, repeated tests, commits and raw signatures cannot.
The first no-progress attempt counts one; the second reaches the default two-run
threshold. Preserve the actionable blocker and reconcile the terminal pause.

## Host Adapter Boundary

The core defines durable fields and reconciliation rules. Host adapters provide
concrete branch naming defaults, runner config readback, and status inspection
commands for their environment.
