---
name: roadmap-delivery-skill
description: Use when Codex needs to set up roadmap delivery automation, inspect roadmap automation status, pause or activate roadmap automation, repair stale roadmap paths, deliver or review one current phase, use phase model policy/stall controls, or finalize/promote delivered roadmap branches in a phase-gated workflow. Do not use for ordinary feature implementation, generic PR review, general project management, unrelated Codex skill creation, or broad release automation without an explicit roadmap phase contract.
---

# Roadmap Delivery Skill

Use this skill for file-backed, phase-gated roadmap delivery workflows. Keep work anchored to the roadmap, `delivery_state.json`, `delivery_log.md`, review files, git branch and commit history, verification output, and `automation.toml`.

## First Move

1. Identify the exact roadmap path or automation id before acting.
2. Read the roadmap, delivery state, delivery log, review files, phase model policy when present, automation config, and `git status`.
3. Reconcile lifecycle rename drift, stale roadmap paths, branch names, and completed or blocked hard-stop states.
4. If state is `blocked`, route through blocked-run remediation before attempting normal phase delivery.
5. Stop and report the mismatch only when roadmap, state, log, review files, verification output, automation config, branch, or worktree evidence disagree and the blocker is not safely repairable in the current run.

## Route The Task

- Setup new automation: read `references/setup-automation.md`.
- Deliver one current phase: read `references/phase-loop.md`.
- Handle review findings: read `references/review-and-fix.md`.
- Inspect status, branches, state, or logs: read `references/state-log-and-branches.md`. Once Phase 4 exists, use `scripts/inspect_delivery_state.py` for status questions.
- Finalize, promote, or close out delivered work: read `references/finalization-and-promotion.md`.
- Repair bad state, stale paths, blocked runs, or lifecycle drift: read `references/troubleshooting.md`.
- Diagnose or repair network-disabled blockers before stopping on them: read `references/network-blocker-remediation.md`.
- Use phase model policy, stalled-run handling, or model-aware automation: read `references/model-policy-and-stall-control.md`.
- Preflight future phases, prerequisites, mitigations, or approvals: read `references/phase-preflight.md`.

## Package Readiness

This generated Codex package is a local skill package, not a marketplace
submission. Treat the package as ready for human distribution review only when
adapter checks prove the `SKILL.md`, router agent, canonical references, helper
scripts, host capability metadata, install documentation, compatibility limits,
privacy limits, and explicit submission blockers are present. Installed skill
synchronization, publication, package registry upload, marketplace submission,
credential use, branch pushes, and repository setting changes remain
human-approved operations. Host capability metadata is required readiness
evidence for supported adapters.

## Hard Rules

- Work exactly one roadmap phase at a time.
- When state is `blocked`, try blocked-run remediation before retrying normal phase advancement.
- Run required verification before claiming delivery.
- Require a fresh review verdict before phase advancement.
- Preserve unrelated worktree changes; never revert user work without explicit instruction.
- Do not broadly stage files or hide unrelated diffs inside phase work.
- Do not force-push.
- Do not promote to `main`, merge, push, or change Codex app automation config without explicit human approval, except for the narrow status-only completion/stall self-pause described below.

## Policy Gates

- Read `approval_policy.json` when present. Missing policy means conservative
  legacy behavior: phase-owned edits, state/log/review writes, branch creation,
  and verification can proceed, while commits, pushes, saved automation
  retargets, publication, promotion, credentials, destructive git, and
  installed skill sync still require approval or remain forbidden. Completion
  and repeated-stall status-only self-pause is allowed by default unless
  `pause_automation_on_completion` or `pause_automation_on_stall` is explicitly
  `false`.
- Treat `phase_model_policy.json` and `adaptive_model_policy` as next-run
  controls. A non-flawless run may update durable state and propose or perform
  an approved saved automation retarget, but it does not change the active
  model inside the current session.
- A paused setup that reads back as ACTIVE after the operator starts the
  automation is a normal activation transition, not a blocker, when cwd,
  model/reasoning, state-first prompt, hard-stop guard, and
  blocked-remediation guard all match. Reconcile guide/log/state to ACTIVE,
  record `last_activation`, and continue before applying the generic
  disagreement stop rule.
- Completion and repeated-stall self-pause are default safety behaviors for
  generated policies through `pause_automation_on_completion` and
  `pause_automation_on_stall`. This is a narrow terminal status-only pause
  exception; `pause_saved_automation` still gates broad saved-runner edits in
  conservative mode. If a roadmap explicitly disables a context pause, or
  pause tooling/readback is unavailable, write the local alert and keep the
  state in the appropriate blocked or `completed_pending_pause` form.

## Stop Conditions

Stop and report clearly when required files are missing, state surfaces disagree, verification cannot run, review/fix iterations reach their limit, credentials or approval are needed, the phase scope is ambiguous, destructive git operations would be required, or the requested work expands beyond the current roadmap phase.
