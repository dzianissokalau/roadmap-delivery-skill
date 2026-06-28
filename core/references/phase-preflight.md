# Phase Preflight Reference

Use this reference to scan the whole roadmap for later prerequisites before a
runner reaches those phases.

## Core Contract

Before activating scheduled delivery, and whenever a permission-gated blocker
reveals a likely future class of blocker, perform a read-only phase preflight
over every remaining phase and finalization. The preflight does not deliver
future work. It only extracts prerequisites, approvals, mitigations, and
operator actions so later phases can run without avoidable human interruption.

Check each future phase for:

- required model and reasoning floors from phase model policy
- credential or secret names that must be present in the runner environment
- network or external API access
- required local tools, package managers, services, fixtures, or datasets
- filesystem locations outside normal phase-owned paths
- branch, commit, push, publication, promotion, runner-retarget, pause, or
  destructive operations that need approval-policy decisions
- external product, policy, account, billing, or scope decisions
- finalization prerequisites such as deep review, promotion evidence, and
  terminal runner pause

Classify each finding as ready, needs mitigation, needs approval, forbidden, or
unknown. Write a durable operator-action list that names the phase, missing
prerequisite, approval operation, current decision, and mitigation. If the
preflight is static and cannot prove availability, say that explicitly instead
of claiming certainty.

For credentials, report only variable names and presence. Missing credentials
are blockers. Present credentials still need explicit operator approval before
use; do not treat a secret value's presence as approval.

Preflight evidence should be stored near the roadmap automation artifacts, for
example as `phase_prerequisites.json` plus a human-readable
`phase_preflight.md`. Later runs must read those files when present and update
them when a newly discovered blocker changes the mitigation list.

If static preflight reports a network blocker for a current phase, consult
`network-blocker-remediation.md` before preserving that blocker. Another
approved host network surface may still provide a verified public-source
recovery path.

## Host Adapter Boundary

The core defines the preflight categories and durable evidence shape. Host
adapters provide concrete runner readback, environment inspection, network
availability checks, helper commands, and the exact way approvals are requested
or recorded.
