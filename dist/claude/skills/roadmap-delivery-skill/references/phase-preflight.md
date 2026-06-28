# Phase Preflight Reference

Use this reference to scan later roadmap phases for prerequisites before a
Claude-run delivery reaches them.

## Core Contract

Before activating or resuming scheduled delivery, perform a read-only scan over
every remaining phase and finalization. The scan does not deliver future work.
It records likely blockers, mitigations, approvals, and operator actions so
later runs do not discover avoidable human-gated issues one phase at a time.

Create or refresh these repository-local evidence files when the scan finds
anything material:

```text
automation/<roadmap-slug>/phase_prerequisites.json
automation/<roadmap-slug>/phase_preflight.md
```

For each remaining phase, inspect the roadmap body, delivery state, phase model
policy, approval policy, known runner configuration, and current shell
environment. Record:

- required model and reasoning floors
- missing environment variables, without printing secret values
- network, external API, download, upload, or package-install requirements
- local tools, services, fixtures, datasets, or filesystem prerequisites
- branch, commit, push, publication, promotion, runner-retarget, pause, or
  destructive operations that need explicit approval
- external product, policy, account, billing, or scope decisions
- finalization prerequisites, including terminal runner pause evidence

Classify each finding as ready, needs mitigation, needs approval, forbidden, or
unknown. Say when the result is static analysis and cannot prove the eventual
runner environment. Tool availability checked in the current shell may differ
from the later runner.

## Claude Manual Procedure

This Claude package does not ship a host-specific preflight helper. Use
read-only file inspection and shell checks, then write the evidence files only
after the findings are clear.

Suggested scan steps:

1. Read `delivery_state.json`, `delivery_log.md`, `approval_policy.json`,
   `phase_model_policy.json`, and the roadmap recorded in state.
2. Extract every remaining `Phase N` section plus finalization.
3. For each phase, list required env vars, commands, network/API needs,
   runner model/reasoning requirements, and risky operations.
4. Resolve approval-policy decisions for local commits, branch pushes, runner
   retargets, runner pauses, publication, promotion, credential use, and
   destructive operations.
5. Write `phase_prerequisites.json` with structured findings and
   `phase_preflight.md` with a concise operator-action checklist.

Credential handling must report only variable names and presence. A missing
credential is a blocker. A present credential still requires explicit operator
approval before use.

If static preflight reports a network blocker for a current phase, consult
`network-blocker-remediation.md` before preserving that blocker. Another
approved host network surface may still provide a verified public-source
recovery path.

## Host Adapter Boundary

Claude relies on repository-local files, the current shell environment, and any
runner configuration supplied by the operator. If a recurring-runner surface
cannot prove model, reasoning, status, network, or pause support, record that
as unknown with a mitigation rather than assuming parity.
