---
description: Use when Claude Code needs to set up, inspect, deliver, review, remediate blockers for, or finalize a file-backed phase-gated roadmap delivery workflow. Use only when a roadmap path or automation id is explicit.
---

# Roadmap Delivery Skill

Use this skill for file-backed, phase-gated roadmap delivery workflows. Keep
work anchored to the roadmap, delivery state, delivery log, review files, git
branch and commit history, verification output, and runner configuration.

## First Move

1. Identify the exact roadmap path or automation id before acting.
2. Read the roadmap, delivery state, delivery log, review files, phase model
   policy when present, saved runner configuration, branch, and worktree status.
3. Reconcile lifecycle rename drift, stale roadmap paths, branch names, and
   completed or blocked hard-stop states before editing.
4. If state is `blocked`, route through blocked-run remediation before
   attempting normal phase delivery.
5. Stop and report mismatches when roadmap, state, log, reviews, verification,
   runner config, branch, or worktree evidence disagree in a way that cannot be
   repaired locally.

## Route The Task

- Setup new automation: read `references/setup-automation.md`.
- Deliver one current phase: read `references/phase-loop.md`.
- Handle review findings: read `references/review-and-fix.md`.
- Inspect status, branches, state, or logs: read
  `references/state-log-and-branches.md`.
- Finalize, promote, or close out delivered work: read
  `references/finalization-and-promotion.md`.
- Repair bad state, stale paths, blocked runs, or lifecycle drift: read
  `references/troubleshooting.md`.
- Diagnose or repair network-disabled blockers before stopping on them: read
  `references/network-blocker-remediation.md`.
- Use phase model policy, stalled-run handling, or model-aware automation: read
  `references/model-policy-and-stall-control.md`.
- Preflight future phases, prerequisites, mitigations, or approvals: read
  `references/phase-preflight.md`.

## Package Readiness

This generated Claude plugin skill is a local package component, not a
marketplace submission. Treat the package as ready for human distribution
review only when adapter checks prove the plugin manifest, README, packaged
skill, reviewer agent, safety hooks, canonical references, host capability
metadata, install documentation, compatibility limits, privacy limits, and
explicit submission blockers are present. Installed plugin synchronization,
publication, package registry upload, marketplace submission, credential use,
branch pushes, and repository setting changes remain human-approved
operations. Host capability metadata is required readiness evidence for
supported adapters.

## Hard Rules

- Work exactly one roadmap phase at a time.
- When state is `blocked`, try blocked-run remediation before retrying normal
  phase advancement.
- Run required verification before claiming delivery.
- Require a fresh review verdict before phase advancement.
- Preserve unrelated worktree changes; never revert user work without explicit
  instruction.
- Do not broadly stage files or hide unrelated diffs inside phase work.
- Do not force-push.
- Do not promote, merge, push, publish, install global packages, use
  credentials, or change runner configuration without explicit human approval,
  except for the narrow status-only completion/stall self-pause described
  below.

## Policy Gates

- Read `approval_policy.json` when present. Missing policy means conservative
  legacy behavior: phase-owned edits, state/log/review writes, branch creation,
  and verification can proceed, while commits, pushes, runner retargets,
  publication, promotion, credentials, destructive git, and installed plugin
  sync still require approval or remain forbidden. Completion and repeated-stall
  status-only self-pause is allowed by default unless
  `pause_automation_on_completion` or `pause_automation_on_stall` is explicitly
  `false`.
- Treat `phase_model_policy.json` and `adaptive_model_policy` as next-run
  controls. A non-flawless run may update durable state and propose an
  approved runner retarget, but it does not change the active model inside the
  current session.
- Completion and stall self-pause use `pause_saved_automation`, the
  context-specific pause flags, or default terminal safety policy plus trusted
  runner readback. If a pause is explicitly disabled, or pause tooling/readback
  is unavailable, write the local alert and keep the state in the appropriate
  blocked or `completed_pending_pause` form.

## Claude Tool Permission Notes

- Use read-only tools first to inspect roadmap, state, log, review, policy,
  branch, and generated package evidence before editing.
- Run shell commands only for local repository inspection, required validation,
  and the current phase's required verification.
- Do not request credentials, publish, modify runner configuration, install
  global packages, or run destructive git commands unless the operator has
  explicitly approved that exact action.
- Use the `roadmap-delivery-reviewer` agent for the review gate when available.
  The reviewer is read-only and cannot replace implementation verification.
- If no independent reviewer agent is available, same-context review is allowed
  only when that limitation is recorded explicitly and the evidence satisfies
  the current phase gate.

## Claude Host Notes

- This plugin is a generated Claude Code package. It relies on repository-local
  roadmap artifacts and host runner readback supplied by the operator.
- Treat recurring automation as a host-runner concern; the repository state,
  logs, reviews, and alerts remain authoritative.
- Do not assume Claude Code exposes a status-only recurring automation pause
  API. Use local alerts and `completed_pending_pause` evidence unless a trusted
  runner pause surface reads back the paused status.
- Host capability differences must be recorded as compatibility notes or
  residual risks instead of hidden in prompts.
