# Who This Is For

Roadmap delivery is for work where a local file-backed control plane is useful:
roadmap phases, state, logs, reviews, approval policy, model policy, and
verification evidence all stay in the repository so a later operator can audit
what happened.

## Good Fit

Use this workflow when:

- the project has multi-step roadmap work that should be delivered one phase at
  a time
- acceptance criteria and verification commands can be written before
  implementation starts
- a fresh review verdict should gate phase advancement
- local evidence matters more than speed through a single task
- publication, promotion, credentials, destructive git, and installed-tool sync
  need explicit human approval boundaries
- blocked or stalled runs should leave enough state for the next run to repair
  or ask for a specific decision
- model and reasoning requirements should be read back from durable runner
  configuration before implementation

The workflow is especially useful for repository tooling, release-readiness
work, adapter/package generation, migration plans, and other changes where a
phase can own a clear set of files.

## Poor Fit

This workflow is usually not the right first tool when:

- the task is a small one-off edit with obvious tests
- the project cannot express phase-owned files or acceptance criteria
- the work depends on private credentials or external services from the start
- stakeholders expect the automation to publish, merge, or promote changes
  without explicit approval
- the desired output is exploratory brainstorming rather than a review-gated
  artifact
- the repository cannot tolerate local state, logs, review files, or generated
  automation artifacts
- the operator wants guaranteed productivity, compliance, safety, or release
  outcomes from the tool itself

Roadmap delivery can improve evidence discipline. It does not prove a release
is safe, replace human product decisions, or guarantee that an agent will make
the correct engineering tradeoff.

## Minimum Inputs

A practical first roadmap needs:

- a roadmap file with one current phase
- phase-owned file paths
- acceptance criteria
- required verification commands
- non-goals and stop conditions
- an approval policy
- a phase model policy
- a delivery state file and delivery log

The scaffold command can create starter artifacts, but an operator still needs
to review the generated contract before using it for real project work.

## Decision Check

Before using the workflow on a real project, answer these questions:

- Can the safe demo path run locally without credentials or live host edits?
- Can the normal evidence demo show delivered review evidence and model-policy
  readback from local fixture files?
- Can the policy-mismatch demo block advancement and then recover by changing
  only temporary fixture config?
- Can each phase name the files it owns?
- Can verification run from the repository checkout?
- Can a reviewer decide `delivered`, `needs-fix`, or `blocked` from local
  evidence?
- Are approval-gated operations acceptable as manual follow-ups?

If any answer is no, keep the workflow in demo or dry-run mode until the
missing contract is explicit.
