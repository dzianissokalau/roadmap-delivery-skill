# Release Install And Distribution Trust Automation Guide

Status: Completed
Roadmap: `roadmaps/delivered_release_install_and_distribution_trust_roadmap.md`
Roadmap slug: `release-install-and-distribution-trust`
State file: `automation/release-install-and-distribution-trust/delivery_state.json`
Delivery log: `automation/release-install-and-distribution-trust/delivery_log.md`
Review directory: `automation/release-install-and-distribution-trust/reviews`
Policy file: `automation/release-install-and-distribution-trust/phase_model_policy.json`
Approval policy: `automation/release-install-and-distribution-trust/approval_policy.json`
Codex automation: `release-install-and-distribution-trust`
Cadence: hourly
Model: `gpt-5.5`
Reasoning effort: `xhigh`
Execution environment: local
Activation: Active after operator/manual run.
Saved readback: `ACTIVE`, local, `gpt-5.5`, `xhigh` at
2026-06-02T15:23:42Z.
Setup drift repair: initial app creation saved `ACTIVE` despite the requested
`PAUSED` status; setup immediately updated the saved automation to `PAUSED`
and confirmed readback before activation or delivery.
Activation drift repair: the saved automation now reads `ACTIVE` while local
setup artifacts still said `PAUSED`. Because cwd, model, reasoning, execution
environment, state-resolved prompt references, completed-state hard-stop, and
blocked-remediation guard all still match, this is treated as operator/manual
activation and the local durable artifacts were reconciled without editing the
saved automation config.

Completion state: all roadmap phases are delivered, the final deep-review
prompt has been prepared, and the operator manually paused the saved
automation. Saved readback is `PAUSED`, local, `gpt-5.5`, `xhigh` at
2026-06-02T19:34:22Z. Future runs must hard-stop on completed state and should
not start delivery work.

GitHub review branch:
https://github.com/dzianissokalau/roadmap-delivery-skill/tree/codex/release-install-and-distribution-trust-phase-5

Direct final deep-review prompt:
https://github.com/dzianissokalau/roadmap-delivery-skill/blob/codex/release-install-and-distribution-trust-phase-5/automation/release-install-and-distribution-trust/final-deep-review-prompt.md

## Operating Policy

- Deliver exactly one roadmap phase at a time.
- Read the roadmap, state file, delivery log, review/fix state, phase model
  policy, approval policy, latest reviews, automation config, branch, and
  worktree status before editing.
- Preserve unrelated user changes.
- Use `codex/release-install-and-distribution-trust-phase-<n>` branches for
  implementation phases.
- Run every verification command or manual verification required by the
  current phase before claiming delivery.
- Require a fresh review verdict of `delivered` before advancing state.
- Stop after 3 review/fix iterations if the phase remains unresolved.
- If state is `blocked`, enter Blocked Remediation Mode before attempting
  normal phase delivery.
- Do not push, promote to `main`, merge, delete branches, publish packages, use
  credentials, install/sync global skills or plugins, change repository
  visibility/security/billing, or run destructive commands without explicit
  human approval.
- Keep the saved automation configured as `gpt-5.5` with at least the required
  phase reasoning floor from `phase_model_policy.json`. Higher reasoning is
  sufficient and must not trigger a downgrade blocker.

## Next Run Prompt

Run the next safe step for the roadmap recorded in
`automation/release-install-and-distribution-trust/delivery_state.json` using
the phase-gated workflow in `automation/`. Resolve the current roadmap path
from `delivery_state.json`; the state roadmap field is authoritative across
lifecycle renames.

Use the installed `roadmap-delivery-skill` and read these files before acting:

- `automation/release-install-and-distribution-trust/automation_guide.md`
- `automation/codex_phase_gated_delivery_automation_template.md`
- `automation/release-install-and-distribution-trust/delivery_state.json`
- `automation/release-install-and-distribution-trust/delivery_log.md`
- `automation/release-install-and-distribution-trust/review_fix_state.json`
- `automation/release-install-and-distribution-trust/phase_model_policy.json`
- `automation/release-install-and-distribution-trust/approval_policy.json`

Operate on exactly one current phase at a time. Resolve the roadmap from state,
then reconcile roadmap, state, log, review files, phase model policy, approval
policy, git branch, worktree status, and saved automation configuration before
editing. If they disagree, classify whether the mismatch is local-repairable,
automation-config repairable, permission-gated, external-decision, or
destructive-risk.

If `delivery_state.json` has `status: blocked`, do not try to advance the
phase first. Enter Blocked Remediation Mode: fix local-repairable blockers and
already-authorized automation-config blockers first, rerun reconciliation and
validation, clear `blocked_reason` only after the repair is verified, record
the repair in state/log, and only then start or resume the current phase. If
credentials, a product decision, destructive git, publication, promotion,
installed-skill synchronization, repository visibility/security/billing, or
unapproved config changes are required, keep state blocked and ask for the
missing human action.

Hard stop before delivery if `all_phases_complete` is true, state is
`completed`, or state is `completed_pending_pause`. In that case, confirm the
automation is paused or request pause permission, write any missing completion
alert, and do not start phase work.

For the current phase only:

- extract objective, owned files, implementation steps, acceptance criteria,
  required verification, non-goals, and stop conditions
- create or reuse `codex/release-install-and-distribution-trust-phase-<n>` when
  implementation work is required
- preserve unrelated user changes
- read `phase_model_policy.json`, resolve the current phase's required model
  and reasoning, and verify the configured automation model matches and
  configured reasoning is at least the required floor before implementation
- read `approval_policy.json` before relying on any pre-approved operation
- make only phase-scoped changes
- run required verification and targeted checks
- classify run quality and apply adaptive model policy only to the next run
- update `automation/release-install-and-distribution-trust/delivery_log.md`
  and `automation/release-install-and-distribution-trust/delivery_state.json`
- perform a skeptical review from fresh context where available
- write review output under
  `automation/release-install-and-distribution-trust/reviews/`
- if the verdict is `needs-fix`, fix only in current phase scope and rerun
  verification
- stop after 3 review/fix iterations and mark blocked if still not delivered

Do not advance unless acceptance criteria are satisfied, verification passed,
review verdict is `delivered`, and roadmap/state/log are updated.

After advancing state to the next phase, stop unless the framework explicitly
permits immediate next-run scheduling and the required approval/readback gates
are satisfied. Do not publish, promote to `main`, edit app automation config,
push, install/sync global skills or plugins, use credentials, change repository
settings, or run destructive git operations without explicit human approval.
