# Setup Automation Reference

Use this reference when creating a file-backed roadmap delivery automation.
The goal is a conservative, inspectable workflow that starts inactive unless
the operator explicitly asks for scheduled delivery.

## Core Contract

An automation is suitable only when the roadmap is decomposed into phases with
owned files, non-goals, acceptance criteria, required verification, and stop
conditions. The repository must tolerate local branch work, and publication,
promotion, destructive operations, credentials, and product decisions must stay
operator-approved.

Create durable artifacts under the repository automation directory:

```text
automation/<roadmap-slug>/
  automation_guide.md
  approval_policy.json
  delivery_state.json
  delivery_log.md
  review_fix_state.json
  review_fix_log.md
  phase_model_policy.json
  automation_run_log.jsonl
  alerts/
  reviews/
```

Record the same roadmap path and slug in the roadmap header, state, delivery
log, review state, and automation guide. The saved runner prompt should be
state-first: point it at stable automation artifacts, require it to read
`delivery_state.json`, and say that the roadmap path recorded in
`delivery_state.json` is authoritative. Do not make the saved runner prompt
depend on the lifecycle-prefixed roadmap filename.

If a lifecycle rename changes the roadmap filename, repair repository-local
references in the roadmap, state, delivery log, review state, automation guide,
reviews, and run bookkeeping before delivery continues. A saved runner prompt
retarget is not required when the prompt is state-first and still references
the stable state/guide files.

If the operator manually activates a runner that setup originally recorded as
paused, the next run must reconcile the durable artifacts instead of treating
ACTIVE as a permanent setup failure. Accept ACTIVE only when readback proves the
model/reasoning, prompt, cwd, and safety guards still match, then update
guide/log/state to ACTIVE and record the activation. This reconciliation must
happen before the generic "surfaces disagree, stop" rule, so an intentional
activation does not waste a run by first creating a blocker.

## Required Initial Artifacts

The initial state must identify the roadmap, slug, current phase, phase branch
when known, status, review iteration counters, model policy fields, verification
evidence, latest review evidence, blocker fields, run/stall counters, and
updated timestamp. It must also record the approval policy path, active
approval mode, and last approval-policy readback.

The approval policy must start as `conservative` unless the operator explicitly
selects `delegated_local`, `delegated_delivery`, or `custom`. A missing approval
policy keeps legacy conservative behavior. An invalid approval policy must fail
validation before delivery relies on pre-approval. Custom policy must provide an
operation allow/deny map, with missing operations treated as denied.
Record the `retarget_saved_automation` decision because later phases may need a
runner model or reasoning retarget before delivery can safely resume.

The initial delivery log must describe the roadmap, state path, review path,
operating policy, configured runner, and next action. The log is append-only
after delivery starts.

The phase model policy must define default model and reasoning requirements,
optional phase overrides, finalization requirements, stall threshold, alert
mode, and disabled-by-default adaptive model policy fields with explicit caps.
Configured runner model and reasoning values may be written to state only after
readback proves them. Reasoning requirements are floors, not exact ceilings:
`xhigh` readback satisfies a policy requiring `high`, and setup must not block
or ask for approval merely to downgrade reasoning.

## Prompt Requirements

The saved runner prompt must require the agent to:

- read the automation guide, state, log, review state, policy, latest reviews,
  runner configuration, branch, and worktree status before editing
- resolve the current roadmap path from `delivery_state.json`, treating the
  state roadmap field as authoritative across lifecycle renames
- read and validate approval policy before relying on pre-approved operations
- use conservative legacy behavior when approval policy is missing
- stop before delivery when approval policy is invalid
- operate on exactly one current phase
- enter blocked remediation before retrying delivery when state is blocked
- hard-stop on completed or completed-pending-pause state
- verify model and reasoning against policy before phase-owned edits
- classify run quality and apply adaptive model policy only to the next run
- preserve unrelated worktree changes
- run required verification
- write a fresh review artifact before phase advancement
- avoid publication, promotion, destructive git, credentials, and unapproved
  runner configuration changes

The prompt may include the initial roadmap path as context, but lifecycle path
changes must not make saved runner prompt edits mandatory. If the prompt lacks
a state-resolved roadmap guard, lifecycle renames still require prompt retarget
approval before the next run can trust the saved prompt.

## Host Adapter Boundary

The core controls file-backed state, policy, logs, review artifacts, and safety
gates. Host adapters own how a scheduled runner is created, paused, activated,
or read back, and how model and reasoning settings are configured in that
runner.
