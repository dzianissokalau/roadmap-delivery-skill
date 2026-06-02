# Onboarding Wizard And Proof Demos Automation Guide

Status: Completed
Roadmap: `roadmaps/delivered_onboarding_wizard_and_proof_demos_roadmap.md`
Roadmap slug: `onboarding-wizard-and-proof-demos`
State file: `automation/onboarding-wizard-and-proof-demos/delivery_state.json`
Delivery log: `automation/onboarding-wizard-and-proof-demos/delivery_log.md`
Review directory: `automation/onboarding-wizard-and-proof-demos/reviews`
Policy file: `automation/onboarding-wizard-and-proof-demos/phase_model_policy.json`
Approval policy: `automation/onboarding-wizard-and-proof-demos/approval_policy.json`
Codex automation: `onboarding-wizard-and-proof-demos`
Cadence: hourly
Model: `gpt-5.5`
Reasoning effort: `xhigh`
Execution environment: local
Activation: Operator/manual activation accepted on 2026-06-02.
Saved readback: `PAUSED`, local, `gpt-5.5`, `xhigh` at
2026-06-02T12:23:56Z.
Lifecycle repair: Phase 0 delivered; roadmap moved to the in-progress
lifecycle path at 2026-06-02T09:21:39Z. Saved automation prompt retarget was
not required because the prompt references stable state/guide/log artifacts
and the framework treats `delivery_state.json` as the authoritative roadmap
path.
Completion: all phases delivered on 2026-06-02. The saved automation now reads
back `PAUSED`; this run did not edit saved automation config.

## Operating Policy

- Deliver exactly one roadmap phase at a time.
- Read the roadmap, state file, delivery log, review/fix state, phase model
  policy, approval policy, latest reviews, automation config, branch, and
  worktree status before editing.
- Preserve unrelated user changes.
- Use `codex/onboarding-wizard-and-proof-demos-phase-<n>` branches for
  implementation phases.
- Run every verification command or manual verification required by the
  current phase before claiming delivery.
- Require a fresh review verdict of `delivered` before advancing state.
- Stop after 3 review/fix iterations if the phase remains unresolved.
- If state is `blocked`, enter Blocked Remediation Mode before attempting
  normal phase delivery.
- Do not push, promote to `main`, merge, delete branches, publish packages, use
  credentials, install/sync global skills or plugins, or run destructive
  commands without explicit human approval.
- Keep the automation configured as the current phase target from
  `phase_model_policy.json` unless a later delivered phase changes the model
  policy and approved retarget flow.
- Initial app creation saved `ACTIVE` despite the requested `PAUSED` status;
  setup immediately repaired the saved config to `PAUSED` and confirmed
  readback before activation or delivery. The saved automation later read back
  as `ACTIVE`; because this run was operator-triggered and model, reasoning,
  cwd, prompt path, hard-stop guard, and blocked-remediation guard still
  matched, durable bookkeeping accepted that activation.

## Next Run Prompt

Run the next safe step for the roadmap recorded in
`automation/onboarding-wizard-and-proof-demos/delivery_state.json` using the
phase-gated workflow in `automation/`. Resolve the current roadmap path from
`delivery_state.json`; the state roadmap field is authoritative across
lifecycle renames.

Use the installed `roadmap-delivery-skill` and read these files before acting:

- `automation/onboarding-wizard-and-proof-demos/automation_guide.md`
- `automation/codex_phase_gated_delivery_automation_template.md`
- `automation/onboarding-wizard-and-proof-demos/delivery_state.json`
- `automation/onboarding-wizard-and-proof-demos/delivery_log.md`
- `automation/onboarding-wizard-and-proof-demos/review_fix_state.json`
- `automation/onboarding-wizard-and-proof-demos/phase_model_policy.json`
- `automation/onboarding-wizard-and-proof-demos/approval_policy.json`

Operate on exactly one current phase at a time. Resolve the roadmap from state,
then reconcile roadmap, state, log, review files, phase model policy, approval
policy, git branch, worktree status, and saved automation configuration before
editing. If they disagree, record the blocker in state, log, and review, then
stop.

If `delivery_state.json` has `status: blocked`, do not try to advance the
phase first. Enter Blocked Remediation Mode: classify the blocker as
local-repairable, automation-config repairable, permission-gated,
external-decision, or destructive-risk. If the blocker is local-repairable or
automation-config repairable and the operator has already authorized the needed
surface, fix the blocker first, rerun reconciliation and validation, clear
`blocked_reason`, record the repair in state/log, and only then start or resume
the current phase. If credentials, a product decision, destructive git,
publication, promotion, installed-skill synchronization, or unapproved config
changes are required, keep state blocked and ask for the missing human action.

Hard stop before delivery if `all_phases_complete` is true, state is
`completed`, or state is `completed_pending_pause`. In that case, confirm the
automation is paused or request pause permission, write any missing completion
alert, and do not start phase work.

For the current phase only:

- extract objective, owned files, implementation steps, acceptance criteria,
  required verification, non-goals, and stop conditions
- create or reuse `codex/onboarding-wizard-and-proof-demos-phase-<n>` when
  implementation work is required
- preserve unrelated user changes
- read `phase_model_policy.json`, resolve the current phase's required model
  and reasoning, and verify the configured automation model and reasoning match
  before implementation
- read `approval_policy.json` before relying on any pre-approved operation
- make only phase-scoped changes
- run required verification and targeted checks
- classify run quality and apply adaptive model policy only to the next run
- update `automation/onboarding-wizard-and-proof-demos/delivery_log.md` and
  `automation/onboarding-wizard-and-proof-demos/delivery_state.json`
- perform a skeptical review from fresh context where available
- write review output under
  `automation/onboarding-wizard-and-proof-demos/reviews/`
- if the verdict is `needs-fix`, fix only in current phase scope and rerun
  verification
- stop after 3 review/fix iterations and mark blocked if still not delivered

Do not advance unless acceptance criteria are satisfied, verification passed,
review verdict is `delivered`, and roadmap/state/log are updated.

After advancing state to the next phase, stop. Do not publish, promote to
`main`, edit app automation config, push, install/sync global skills or
plugins, or run destructive git operations without explicit human approval.
