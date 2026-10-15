---
name: roadmap-delivery-skill
description: Use when Codex needs to set up roadmap delivery automation, inspect roadmap automation status, pause or activate roadmap automation, repair stale roadmap paths, deliver or review one current phase, use phase model policy/stall controls, or finalize/promote delivered roadmap branches in a phase-gated workflow. Do not use for ordinary feature implementation, generic PR review, general project management, unrelated Codex skill creation, or broad release automation without an explicit roadmap phase contract.
---

# Roadmap Delivery Skill

Use the roadmap, state, append-only log, reviews, verification and runner
readback as the evidence for a file-backed delivery workflow.

## Ordered Workflow

1. Read `delivery_state.json` first; its roadmap path is authoritative. Read the
   adjacent guide, policies, log and latest reviews, then runner and git status.
2. Handle the completion hard stop and two-run stall threshold before ordinary
   phase/model gates. Do not extract or start another phase during closeout.
3. Reconcile intentional manual activation before a generic disagreement stop.
   Matching identity, cwd/project, model/floor and prompt guards permit local
   guide/state reconciliation; record `last_activation`. Activation alone is
   neither progress nor a fresh stall budget. Authorized lifecycle filename
   repair needs no saved prompt retarget when the prompt resolves state.
4. When state is `blocked`, try blocked-run remediation before retrying normal
   delivery. Clear the original cause only after verified repair.
5. Validate approval and phase model policy using actual runner readback. Use
   the shared runtime decision, then implement the current phase on its branch.
6. Run required verification before claiming delivery.
   Require a fresh review verdict before phase advancement. Fix scoped findings within three iterations;
   record a same-context limitation when independent review is unavailable.
7. Record one semantic outcome per unique run, resolve the next-run target,
   advance only after `delivered`, then stop. The last numbered phase leads to
   separate finalization and a distinct final deep-review prompt or human waiver.

## Routes

- Setup: `references/setup-automation.md`.
- Deliver exactly one roadmap phase: `references/phase-loop.md`.
- Review or fix: `references/review-and-fix.md`.
- Inspect state/branches: `references/state-log-and-branches.md`.
- Blocked repair/lifecycle drift: `references/troubleshooting.md`.
- Network blocker: `references/network-blocker-remediation.md`.
- Policy, progress and terminal pause: `references/model-policy-and-stall-control.md`.
- Future phase preflight: `references/phase-preflight.md`.
- Finalization/promotion: `references/finalization-and-promotion.md`.

## Policy Gates

- Work exactly one roadmap phase at a time. Preserve uncommitted user work;
  stage explicit phase-owned paths only. Never force-push.
- Read `approval_policy.json`; shared decisions return `allowed`, `ask` or
  `forbidden`. Missing policy uses conservative defaults; invalid policy cannot
  grant authority. Honor existing scoped operator authorization.
- Default completion/stall status-only self-pause is allowed unless the matching
  `pause_automation_on_completion` or `pause_automation_on_stall` flag is explicitly
  false. These opt-outs override broad pause permission in every mode. Broad
  saved-runner restrictions do not revoke this narrow terminal exception.
- Write the local alert, preserve every other runner setting, use supported host
  tooling and require PAUSED readback before claiming pause. Unavailable capability
  or readback leaves a concrete blocked/`completed_pending_pause` outcome.
- Exact model and at least the reasoning floor are required before phase work.
  `adaptive_model_policy` changes only the next run; it cannot switch this session.
- Timestamps, logs, review paths, repeated tests and bookkeeping commits cannot
  reset stalls. Use verifier-backed accepted work, new criteria or repaired causes.
- Publication, promotion, credentials, global synchronization, destructive git
  and unrelated runner edits require their own explicit human approval or remain
  forbidden. Phase acceptance does not imply permission for them.

## Package Readiness

This is a local skill package, not a marketplace submission.
The package is ready for human distribution review when adapter checks prove
entrypoint, references, helpers, runtime closure, host capability metadata,
install documentation, compatibility limits, privacy limits and submission blockers.
Distribution, global sync and publication remain human-approved operations.

## Codex Host

Use `scripts/roadmap_delivery.py` for the packaged CLI and compatibility helpers
for existing invocations. Read-only files supply observed configuration, not host
capabilities. Saved updates require supported app tooling and readback receipts.
