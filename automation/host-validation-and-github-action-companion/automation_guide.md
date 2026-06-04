# Host Validation And GitHub Action Companion Automation Guide

Status: Completed
Roadmap: `roadmaps/delivered_host_validation_and_github_action_companion_roadmap.md`
Roadmap slug: `host-validation-and-github-action-companion`
State file: `automation/host-validation-and-github-action-companion/delivery_state.json`
Delivery log: `automation/host-validation-and-github-action-companion/delivery_log.md`
Review directory: `automation/host-validation-and-github-action-companion/reviews`
Policy file: `automation/host-validation-and-github-action-companion/phase_model_policy.json`
Approval policy: `automation/host-validation-and-github-action-companion/approval_policy.json`
Codex automation: `host-validation-and-github-action-companion`
Cadence: hourly
Model: `gpt-5.5`
Reasoning effort: `xhigh`
Execution environment: local
Saved readback: `PAUSED`, local, `gpt-5.5`, `xhigh` at
2026-06-04T16:07:22Z.
Setup repair: initial app creation requested `PAUSED` but read back `ACTIVE`;
setup immediately repaired the saved config to `PAUSED` before activation or
delivery.
Activation repair: the first delivery run read back `ACTIVE` with matching
prompt guards, cwd, model, and reasoning; repository-local status was
reconciled to active without editing the saved automation config.
Completion closeout: finalization paused the saved automation through the
approval-policy completion safety pause and read back `PAUSED`.
Main promotion: operator approved promotion; `origin/main` was fast-forwarded
to `f8823c3cc3c1d6c9d18d43184359ecfeffb34b54` at 2026-06-04T18:10:17Z.

## Operating Policy

- Deliver exactly one roadmap phase at a time.
- Read the roadmap, state file, delivery log, review/fix state, phase model
  policy, approval policy, latest reviews, automation config, branch, and
  worktree status before editing.
- Preserve unrelated user changes.
- Use `codex/host-validation-and-github-action-companion-phase-<n>` branches
  for implementation phases.
- Run every verification command or manual verification required by the
  current phase before claiming delivery.
- Require a fresh review verdict of `delivered` before advancing state.
- Stop after 3 review/fix iterations if the phase remains unresolved.
- If state is `blocked`, enter Blocked Remediation Mode before attempting
  normal phase delivery.
- Do not push, promote to `main`, merge, delete branches, publish packages,
  manage repository secrets, enable remote scheduled workflows, use
  credentials, install/sync global skills or plugins, or run destructive
  commands without explicit human approval.
- Keep the automation configured as the current phase target from
  `phase_model_policy.json` unless a later delivered phase changes the model
  policy and approved retarget flow.
- Completion and repeated-stall safety pauses are enabled by default. Broad
  saved automation edits outside approved lifecycle/model/stall controls still
  require explicit human approval.

## Next Run Prompt

Run the next safe step for the roadmap recorded in
`automation/host-validation-and-github-action-companion/delivery_state.json`
using the phase-gated workflow in `automation/`. Resolve the current roadmap
path from `delivery_state.json`; the state roadmap field is authoritative
across lifecycle renames.

Use the installed `roadmap-delivery-skill` and read these files before acting:

- `automation/host-validation-and-github-action-companion/automation_guide.md`
- `automation/codex_phase_gated_delivery_automation_template.md`
- `automation/host-validation-and-github-action-companion/delivery_state.json`
- `automation/host-validation-and-github-action-companion/delivery_log.md`
- `automation/host-validation-and-github-action-companion/review_fix_state.json`
- `automation/host-validation-and-github-action-companion/phase_model_policy.json`
- `automation/host-validation-and-github-action-companion/approval_policy.json`

Operate on exactly one current phase at a time. Resolve the roadmap from state,
then reconcile roadmap, state, log, review files, phase model policy, approval
policy, git branch, worktree status, and saved automation configuration before
editing.

Before recording a generic mismatch blocker, handle the normal paused-setup to
active-run transition: if durable setup artifacts still say the saved
automation is PAUSED but saved readback is ACTIVE, and model/reasoning, cwd,
state-first prompt, hard-stop guard, and blocked-remediation guard all match,
accept it as operator/manual activation. Update guide/log/state to ACTIVE,
record `last_activation` and `last_blocker_repair`, reset stalled counters,
rerun validation, and continue the current phase. Do not stop just because the
saved automation is ACTIVE after the operator started it.

If the surfaces still disagree after local lifecycle and activation
reconciliation, record the blocker in state/log/review and stop.

If `delivery_state.json` has `status: blocked`, enter Blocked Remediation Mode
before normal delivery: classify the blocker, repair local or
already-authorized automation-config blockers, rerun validation, clear
`blocked_reason` only when verified, and then resume the current phase. If
credentials, a product decision, destructive git, publication, promotion,
installed-skill synchronization, repository secret management, remote workflow
activation, or unapproved config changes are required, keep state blocked and
ask for the missing human action.

Hard stop before delivery if `all_phases_complete` is true, state is
`completed`, or state is `completed_pending_pause`. Confirm the automation is
paused or request pause permission, write any missing completion alert, and do
not start phase work.

For the current phase only:

- extract objective, owned files, implementation steps, acceptance criteria,
  required verification, non-goals, and stop conditions
- create or reuse `codex/host-validation-and-github-action-companion-phase-<n>`
  when implementation work is required
- preserve unrelated user changes
- read `phase_model_policy.json`, resolve the current phase's required model
  and reasoning, and verify the configured automation model and reasoning
  satisfy the required target before implementation
- read `approval_policy.json` before relying on any pre-approved operation
- make only phase-scoped changes
- run required verification and targeted checks
- classify run quality and apply adaptive model policy only to the next run
- update
  `automation/host-validation-and-github-action-companion/delivery_log.md` and
  `automation/host-validation-and-github-action-companion/delivery_state.json`
- perform a skeptical review from fresh context where available
- write review output under
  `automation/host-validation-and-github-action-companion/reviews/`
- if the verdict is `needs-fix`, fix only current-phase findings and rerun
  verification
- stop after 3 review/fix iterations and mark blocked if still not delivered

Do not advance unless acceptance criteria are satisfied, verification passed,
review verdict is `delivered`, and roadmap/state/log are updated.

After advancing state to the next phase, stop. Do not publish, promote to
`main`, edit app automation config beyond already-approved lifecycle/model/stall
controls, push, install/sync global skills or plugins, use credentials, create
repository secrets, enable remote scheduled workflows, or run destructive git
operations without explicit human approval.
