# Review And Fix Reference

Use this reference after a phase delivery attempt or when handling review
findings.

## Core Contract

The reviewer evaluates delivered behavior against the current phase objective,
owned files, non-goals, stop conditions, acceptance criteria, and required
verification. The review must inspect changed artifacts, relevant surrounding
workflow docs or code, verification evidence, delivery log, state, branch, and
worktree status.

Review findings should focus on missed acceptance criteria, insufficient
verification, scope creep, stale state/log/review contradictions, unsafe branch
or data handling, approval-boundary violations, and claims that overstate what
was delivered.

## Verdict Values

Use exact lowercase verdicts:

- `delivered`: acceptance criteria are met, verification passed, scope stayed
  within the current phase, and no blocking findings remain
- `needs-fix`: at least one valid current-phase finding can be fixed without
  a missing decision, permission, destructive operation, or scope expansion
- `blocked`: required input, permission, environment, or scope clarity is
  missing, or max review/fix iterations were reached

No other final verdict values are valid.

## Review Artifact

Each review must include the roadmap path, phase, reviewed timestamp, branch,
findings ordered by severity, missing tests or checks, finding dispositions,
residual risks, and verdict.

Use priority labels:

- `[P0]` destructive action, data loss, security exposure, or phase corruption
- `[P1]` missed acceptance criteria, broken required behavior, missing required
  verification, or unsafe advancement
- `[P2]` important reliability, operator clarity, path, or state drift gap
- `[P3]` minor cleanup that does not block delivery

## Fix Loop

For valid current-phase findings, patch only current-phase scope, rerun required
verification and targeted checks, update log/state evidence, and write a new
review iteration. Do not edit an earlier review verdict.

For valid future-phase findings, record residual risk or backlog and do not
implement the future phase. For invalid findings, explain the rejection with
concrete file, state, log, review, or command evidence.

If verification cannot run after a fix, the phase is blocked unless the roadmap
explicitly allows confirmation without execution.

## Host Adapter Boundary

The core defines review evidence and verdict gates. Host adapters may provide
fresh reviewer delegation, but same-context review is acceptable only when the
limitation is explicit and evidence directly satisfies the phase gate.

## Codex Execution

Use a fresh local-change reviewer when available and authorized. Otherwise
record same-context review explicitly and tie each acceptance criterion to
passed checks and changed artifacts. Review availability never replaces tests.
