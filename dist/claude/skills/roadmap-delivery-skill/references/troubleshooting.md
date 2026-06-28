# Troubleshooting Reference

Use this reference when roadmap, state, log, review, policy, branch, worktree,
runner config, or verification evidence disagree.

## Core Contract

Classify the issue before retrying delivery. Repair only local current-phase
bookkeeping, stale paths, missing generated artifacts, branch drift, malformed
state/log entries, or runner configuration changes whose approval-policy
decision is `allowed`. Keep state blocked and ask for human action when the
repair needs credentials, product input, destructive git, broad publication,
promotion, or an approval-policy decision of `ask`. Record a blocker when the
operation is `forbidden` or unknown.

## Approval Policy Problems

Missing `approval_policy.json` is conservative legacy behavior: local edits,
state/log/review writes, phase branch creation, and verification may proceed,
while local commits, automation retargets, automation pause, branch push,
installed skill sync, publication, promotion, credential use, and destructive
git require the approval gate.

Invalid approval policy is a blocker before delivery relies on pre-approval.
Record the invalid policy error in state/log/review, use conservative fallback
only for reporting, and stop before any operation that needed the invalid
policy.

Forbidden operations produce blockers, not prompts to bypass the policy.
Never-auto operations stay forbidden in conservative, delegated, and custom
modes.

## Common Blockers

- Missing or invalid state JSON.
- Missing delivery log or review directory.
- State roadmap path does not exist.
- Roadmap current phase and state current phase disagree.
- Latest review verdict is invalid or does not match state.
- Required model/reasoning and configured runner values mismatch.
- Automation prompt references a stale roadmap path and does not resolve the
  authoritative roadmap path from `delivery_state.json`.
- Saved runner is ACTIVE while setup artifacts still say PAUSED.
- Completed state would keep running without a hard-stop guard.
- Dirty worktree includes unexplained current-phase owned files.
- Branch exists with unexpected base or unexplained changes.
- Required verification cannot run.
- Static network preflight reports a blocker before an approved direct public
  probe path has been checked.

## Warning Handling

Warnings are reconciliation work, not automatic failure. Explain branch mismatch,
dirty worktree, lifecycle filename drift, missing optional prompt paths, or
legacy artifact compatibility in the log before continuing. Treat warnings as
blockers only when they affect current-phase correctness or verification.

Lifecycle-only prompt drift is not a blocker when the saved runner prompt is
state-first: it references stable automation artifacts, requires reading
`delivery_state.json`, and says the roadmap path recorded in state is
authoritative. In that case, perform the lifecycle rename and repository-local
reference repair without requiring a saved runner prompt edit. If the prompt
hardcodes the lifecycle roadmap path and lacks the state-resolved guard, treat
the saved prompt update as an automation-config repair that needs approval.

For network-disabled blockers, read `network-blocker-remediation.md` before
stopping. A host environment flag may not prove that all network surfaces are
unusable; direct public probes can sometimes provide an approved,
artifact-backed repair path for public unauthenticated source recovery.

## Blocked Run Remediation

On a blocked run:

1. Read the blocked reason, failed verification, latest review findings, and
   runner readback.
2. Classify the blocker.
3. Repair only local or approval-policy `allowed` runner configuration blockers.
4. Rerun validation/readback.
5. Record `last_blocker_repair`, clear `blocked_reason`, and reset stall
   counters only after repair evidence passes.
6. Resume the current phase only after reconciliation is clean.

Do not write another blocked review for the same issue until remediation
classification has been attempted.

## Manual Activation Reconciliation

If setup expected the runner to stay PAUSED but readback now says ACTIVE, first
check whether that ACTIVE state is an operator/manual activation rather than an
unexplained runner mutation.

Treat the mismatch as repairable activation acceptance when all are true:

- ACTIVE/PAUSED status drift is the only blocker.
- Required and configured model/reasoning values match or are not model-strict.
- Roadmap path, prompt, cwd, branch, and hard-stop/blocked-remediation guards
  are still valid.
- The roadmap is not already complete.
- Operator action or the current instruction clearly accepts active delivery.

In that case, do not pause the runner and do not keep blocking phase delivery.
Update durable guide/log/state surfaces to ACTIVE, record `last_activation` and
`last_blocker_repair`, clear `blocked_reason` only after validation/readback
passes, reset stalled counters, and resume the current phase.

If ACTIVE was not intended, or any other runner field mismatches, keep state
blocked and ask for the missing runner repair or operator decision.

## Completed-State Issues

If completed state is detected, do not start phase work. Confirm completed alert
evidence, confirm pause status or record pause-required action, and preserve the
final verification record.

If policy allowed a completion or stall pause but runner readback is not
`PAUSED`, classify the issue as an automation-config blocker. Keep or set
`completed_pending_pause` for completion closeout, keep the local alert, and ask
for the smallest runner repair or pause approval needed. Do not convert the
state to `completed` until readback proves the runner is paused.

## Host Adapter Boundary

The core defines classifications and repair rules. Host adapters own concrete
runner edits, credential surfaces, external notifications, and publication
mechanisms.
