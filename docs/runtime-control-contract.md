# Runtime Control Contract

Contract version: 2
Roadmap: Runtime Reliability And Portable Installation, Phases 0-1
Baseline: `517bbdd899f7fb9aea9124e471ae36fb1aa620cd`

This is the behavioral specification for Phases 1-8. Phase 0 records defects
and expected results; it does not implement the controller or change a live
runner. `tests/fixtures/runtime-reliability/cases.json` holds R1-R6 inputs and
expected results. `baseline-report.json` records fresh observations separately.
An observation is never the expected oracle merely because the old suite passes.

## Phase 1 Executable Plan

`roadmap_delivery.control.decide_control(state, policy, evidence, runner,
event="start_run")` is the canonical pure decision function. It returns a
versioned object with stage, action, reason_code, effective authority/source,
proposed_state_changes, required_effects and evidence_references. It does not
read files, query a clock or host, mutate its inputs, or execute the effects.
`extract_phase` and `completion_claim` explicitly describe the gate; a requested
pause never establishes completion. Validation, inspection and both Codex
planners expose this same plan alongside their existing diagnostic reports.

The policy input is a raw policy object or an execution report from
`read_approval_policy`. `None` means missing policy. A malformed file, JSON null,
invalid schema/map/flag, or unreadable policy is invalid for execution. Its
conservative reporting fallback supplies no approved operations. Default pause
provenance remains distinct from an explicit true flag after normalization.
Context decisions use allowed, disabled or forbidden; disabled is not a request
for broader permission. A separately scoped manual pause request can authorize
that effect without rewriting stored opt-outs.

Runner input separates `expected` identity (id, project_id, cwd and execution
environment) from `observed` host readback (including status, model, reasoning
and prompt_guards). `capabilities.readback` and `capabilities.status_update`
must be explicitly true before their corresponding effects can be relied on.
An already-PAUSED runner needs readback support only. File-based CLI inspection
does not infer host capability or successful scheduler pause from file text.
The legacy TOML fallback can leave inline project identity unavailable; until
Phase 3 fixes parsing, use an explicit observed runner snapshot to resolve that
inspection limitation. Missing identity never becomes matching identity.
Activation requires the full matching identity, model/reasoning and all three
state_first/terminal/blocked_remediation guards. Terminal reconciliation wins
over activation and phase model/review gates.

Evidence passed to the pure function must already be validated by its caller.
Blocker repair requires repair_verified, repaired_blocker matching the original
cause and repair_verification provenance. Advancement requires a delivered,
fresh current-phase review_file/review_phase, passing acceptance and verification,
and satisfied prerequisites. The final numbered phase proposes finalization,
never all_phases_complete. Completion claim additionally needs final verification,
delivered review, and a distinct deep-review prompt or recorded human waiver.

Inspect without effects:

```bash
python3 -m roadmap_delivery.cli plan-control --repo-root . \
  --roadmap-slug <slug> --automation-id <id> --json
```

Optional `--runner-snapshot` and `--evidence-file` accept validated JSON objects;
`--event` selects the boundary. Result/exit categories are stable:

| Result | Exit | Meaning |
| --- | --- | --- |
| ready, reconcile | 0 | Inspectable work/effect or reconciliation proposal |
| disabled, not_applicable | 0 | Explicit context opt-out or manual-run outcome |
| blocked, permission_required | 1 | Specific missing gate or authority |
| invalid_input | 2 | Malformed execution policy/input/evidence |
| unsupported | 3 | Required capability is unavailable |
| pending | 4 | Pause acceptance/readback has not confirmed PAUSED |

Run outcome/recovery accounting validates semantic evidence and journals each
unique attempt once. Completed scope always routes to terminal closeout, never
new accounting. Verified repairs are bound to the current blocker occurrence;
recurring causes require fresh occurrence-bound evidence. Effect receipts,
concurrency controls and bounded host retries are implemented by the runtime.

Host helpers import the bundled canonical runtime. The transitional copied-AST
bridge was removed in Phase 7. Rebuild packages and check generation with:

```bash
python3.12 scripts/build_adapters.py --write --json
python3.12 scripts/build_adapters.py --check --json
```

Tests verify packaged runtime integrity and compare normalized decisions across
host entrypoints, approval modes and terminal states without checkout imports.

## Ordered Transitions

Evaluate the first applicable row. Return an inspectable decision with action,
reason, effective authority and its provenance, proposed state changes, required
effects, and evidence references. Planning is pure; an adapter executes effects.
Use `transition-matrix.json` as data for later controller tests.

| Order | Stage | Trigger | Decision and gate |
| --- | --- | --- | --- |
| 1 | terminal_reconciliation | Complete marker or recorded stall threshold | Reconcile alerts, evidence and status-only pause; never extract another phase. |
| 2 | intentional_activation | PAUSED setup reads ACTIVE with matching identity/configuration/guards | Record operator activation; continue without treating it as unexplained drift. |
| 3 | blocked_remediation | Actionable blocked state below threshold | Classify cause, repair only local or authorized causes, verify before clearing it. |
| 4 | phase_prerequisites | Nonterminal, reconciled state | Validate phase scope, policy, runner model/reasoning and prerequisites. |
| 5 | delivery_review | Prerequisites satisfied | Implement one owned phase, verify and obtain a fresh delivered review within three iterations. |
| 6 | next_phase_or_finalization | Delivered verdict with acceptance and verification | Plan next phase/target, or separate finalization; stop this run. |

Terminal reconciliation precedes ordinary model and phase gates. A wrong phase
model cannot prevent an otherwise authorized terminal pause. Terminal authority,
runner identity, valid policy and available capability are still checked.
Activation cannot reopen completed scope. Below the stall threshold, blocked
remediation precedes retrying delivery. At the threshold terminal handling wins,
preserves the blocker and performs no further phase attempt. After recording a
run outcome, re-enter terminal reconciliation if its new count hits the limit.

The matrix specifies event boundaries as well as stages. `start_run` uses the
observed state before phase work. `record_outcome` consumes a finished attempt's
initial/final evidence once, proposes updated counters, and applies terminal
priority to those proposed values before returning. `recover_run` reconciles an
interrupted attempt or recorded outcome without allocating another attempt ID.
`operator_resume` checks terminal conditions and any explicit fresh-budget
authority before activation. `phase_review` and `advance_phase` require the
respective verification/review evidence; they cannot bypass earlier gates.
These are decision inputs, not separate schedulers or permission grants.

Missing policy means conservative legacy defaults with completion/stall context
pauses enabled. Invalid/unreadable policy is an execution blocker, distinct from
missing policy; reporting fallback grants no authority. In a terminal state with
invalid policy, write a local alert and stop phase work; pause only if separate,
explicit, scoped human authority resolves the ambiguity. Record policy errors.

## Unique Runs And Recovery

A durable start record contains a unique `run_id`, roadmap/runner identity,
phase, attempt epoch, initial semantic evidence and counters. Timestamps do not
identify a run. Allocate the ID once before phase work; keep it through retries,
review/fix iterations and crash recovery. A single completion record determines
its outcome. Concurrent agents must compare the recorded revision and serialize
start/outcome writes; a conflicting writer stops instead of overwriting history.

| Event | Required semantics |
| --- | --- |
| First no-progress attempt | `run_count=1`, `stalled_run_count=1`; missing signatures do not imply progress. |
| Second unique no-progress attempt | `run_count=2`, `stalled_run_count=2`; alert and default pause in this run, no grace run. |
| Duplicate invocation/outcome | Reuse ID/outcome with no extra counts or progress reset. Resume unfinished closeout with the same effect key; a confirmed receipt needs no redundant update. |
| Restart with unfinished start | Recover same ID/effects. If prior attempt is abandoned, close it once as interrupted with its evidence before opening a new ID. |
| Interrupted attempt without accepted progress | Count one no-progress outcome on reconciliation, even if tests/delivery did not finish. |
| Interrupted attempt with verified new progress | Record that evidence once and reset the consecutive count; do not claim phase delivery without its gate. |
| Verified blocker repair | Clear original cause only after a check proves repair; reset consecutive count once for this new evidence. |
| Operator resumes scheduler | ACTIVE is activation evidence, not progress and not a counter reset. Preserve counts, cause, receipts and lifetime run history. |
| Resume at an already reached threshold | Reconcile and pause again unless repair is verified or operator explicitly authorizes a fresh attempt budget. |
| Explicit fresh attempt budget | Archive old epoch/counts and record scoped authorization; new consecutive window begins at zero. Lifetime count persists and this is not progress. |

A terminal-only invocation reconciles the existing outcome/closeout and is not
a new delivery attempt. It neither increments run/stall counts nor invents
progress. Explicit fresh-budget authority is processed inside terminal
reconciliation before activation; ACTIVE readback alone cannot grant it.

Thresholds 1, 2 and 3 apply to the first, second and third consecutive unique
no-progress outcomes respectively. Only a new accepted semantic event resets the
consecutive count. Recovery may rebuild counters from completed run records; it
must not invent a successful first run or erase known failures. Migrate old hash
signatures as historical diagnostics. Mark uncertain history explicitly and
preserve known counts; migration itself cannot reset them.

## Semantic Progress Evidence

Accept one or more previously unconsumed evidence IDs backed by artifacts:

- Accepted phase work: a changed owned artifact satisfies a named criterion or
  a reviewer accepts a concrete implementation increment, with artifact revision
  and the validating check/review recorded. A raw diff or author claim is insufficient.
- Newly satisfied acceptance/verification: a previously unmet named criterion now
  passes its relevant check against recorded inputs/artifact revision. Re-running
  an already satisfied check is activity, even with a new timestamp or filename.
- Verified blocker resolution: a check proves the original cause no longer
  prevents work. Changing failure wording or clearing a state field is insufficient.

Each item records kind, stable semantic ID, criterion/blocker ID, previous and
current evidence, artifact revision, verifier and result. Deduplicate by semantic
event, including across run IDs. Multiple qualifying items in one outcome cause
one reset, not extra runs. Record initial and final evidence so the distinction
is reviewable. Scope-specific accepted documentation/fixtures count when they
satisfy the current phase contract; routine log edits do not.

Exclude timestamps, status churn, log length/hash/content, review filename or
repeated verdict, branch/commit identifiers alone, bookkeeping-only commits,
repeated passing checks, and changed narration. Keep any original actionable
`blocked_reason` separate from stall metadata and pause failures. A repair cannot
be inferred from a different error message.

## Authority And Policy Precedence

Resolve automatic context pause separately from general runner edit permission:

1. Preserve explicit scoped human instructions and restrictions. A later manual
   pause request authorizes that manual action; it does not rewrite stored flags.
2. A valid explicit `pause_automation_on_completion=false` or
   `pause_automation_on_stall=false` suppresses that automatic effect in every
   mode, including delegated/custom modes with broad pause permission true.
3. For that automatic context, true or absent enables the narrow safety pause by
   default, even with conservative `pause_saved_automation=false`. Broad permission
   gates other saved-runner edits, not this default terminal exception.
4. Unknown operations, malformed policy and unavailable credentials never become
   allowed by normalization. Do not widen approval mode or unrelated permissions.

Automatic opt-out yields no pause effect and reason `context_pause_disabled`.
A separately authorized manual pause can still be planned. This distinction
avoids interpreting broad allowed/ask decisions as a context-specific mandate.
An explicit broader operator restriction must be preserved. Unknown legacy
prompt provenance requires an inspectable migration proposal/decision, never an
invented authorization. Known generated legacy wording can be proposed for a
versioned upgrade; saved prompt changes still need scoped migration authority.

Authorization and capability are independent. Allowed plus unsupported produces
an unsupported/pending effect, not success or a new approval request. Supported
plus missing authority produces permission-required, not an attempted mutation.
Invalid execution input is distinct from all three outcomes.

## Runner Identity, Readback And Effects

A runner snapshot records adapter, automation ID, project/cwd, execution
environment, prompt/guard revision, schedule, model/reasoning, notification
settings and observed configuration revision. Desired values are a proposal;
only actual readback is observed configuration. Require exact model plus at least
the phase reasoning floor at the normal phase gate. Never infer the active chat's
model from saved runner settings.

A status-only request binds context, runner identity, expected revision and
idempotency key. Preserve every non-status setting, even if the host API requires
a full payload. Reject ambiguous identity, stale revision, malformed config or
unexplained drift; reread and replan safely rather than overwriting. Capability
metadata names readback/update support and its source of truth. File text alone
is not scheduler readback unless the adapter contract makes it authoritative.

Write intent and local alert before requesting the effect. An effect receipt
records operation/key/context, authority source, previous snapshot/revision,
request result, observed status/revision, preserved-setting comparison, errors
and next action. Only trusted readback PAUSED confirms pause; accepted request,
edited TOML or attempted call alone cannot do so. Retry transient failures with
a finite budget; unsupported, stale, denied and malformed outcomes need a concrete
remaining action. Retrying the same effect uses the same key and reconciles an
already applied effect; no duplicate alert/effect or phase restart after a crash.

External host actions are emitted once per reserved attempt. The caller records
`request_id`, `attempt`, `status` and `source` through `--external-outcome` before
another attempt can be reserved. Read-only inspection emits no second action;
duplicate or contradictory outcomes cannot reset or expand the retry budget.
Reservation transport and permanent effect rejections are durable facts, separate
from transient readback diagnostics. Switching to an in-process adapter does not
clear an outstanding external attempt; acknowledge its bound outcome first.
Acknowledgements still need authoritative PAUSED readback. Alert corruption or
write failure must not prevent an otherwise authorized pause; missing alert
evidence prevents a completed claim and records a specific recovery action.

A file backend, if supported, must use a real TOML parser, validate candidates,
preserve non-status values and check concurrency before atomic replacement.
Inline comments, duplicate keys, tables and multiline status-like prompt text
cannot be handled by a line regex. Python runtime/parser limitations must remain
visible; no silent permissive fallback may substantiate scheduler success.

## Completion And Stall Outcomes

Completion markers always hard-stop numbered phase work, including a partially
recorded finalization. Confirm final verification, a delivered phase review and
a distinct final deep-review prompt or recorded human waiver. A prepared prompt
is not an executed review. Missing completion evidence is reconciled/alerted as
a concrete incomplete gate; do not reopen numbered phase delivery. Safety pause
may proceed while recording incomplete evidence, and must not imply completion.

| Outcome | Evidence and state |
| --- | --- |
| paused | Alert exists, identity/settings agree, trusted readback PAUSED with receipt. Completion may become completed only when all final gates also pass. |
| already_paused | Confirm snapshot and preserve settings; record receipt without redundant update. |
| intentionally_disabled | Explicit context opt-out, alert and no host mutation. Completion remains completed_pending_pause with disabled outcome and optional manual action. |
| permission_required | Exact unresolved scope/authority and remaining action; no automatic mutation. |
| unsupported | Missing supported operation/readback, local alert and specific manual action. |
| transient_failure | Bounded attempts exhausted, errors and next action preserved; no false paused claim. |
| manual_no_scheduler | Explicit manual workflow identity; no fabricated runner or pause. Final gates plus alert allow completed with not_applicable pause outcome. |

For scheduled workflows, incomplete/unconfirmed pause keeps completion in
`completed_pending_pause`; intentional opt-out is recorded distinctly and must
not retry a disabled effect. For a stall, keep `status=blocked` and original
cause; store threshold, attempted pause and remaining action separately. The
runner being PAUSED does not repair the delivery blocker. Completion takes
precedence over a simultaneous stall flag; no duplicate closeout is required.

## Adaptive Targets And Portable Runtime

All targets, including base, escalation, de-escalation, human-gated no-change and
persisted selections, must be resolved against current constraints. Intersect
model allowlists and use the strongest applicable reasoning floor and weakest
cap. Unknown model/reasoning is invalid. An impossible intersection blocks
selection with an explicit reason. Revalidate persisted targets against current
policy and phase provenance. No path may return a target below the phase floor
merely because the adaptive candidate individually validates.

A skill-only package must include or declare its runtime. It must start helpers
and evaluate fixture workflows from another repository with the source checkout
unavailable, no developer PYTHONPATH and no undeclared global Python packages.
Use isolated offline installs and fake runners for mandatory coverage. Live
scheduler tests are optional, explicitly skipped when unavailable, and cannot
be inferred from file fixtures, instruction analysis or binary help output.

## Baseline Evidence And Phase Handoff

Run `python3 tests/test_runtime_contract.py --capture-baseline --output
<report-path>` from the checkout to reproduce all six cases in temporary roots.
The default unittest suite validates fixture/contract format, traceability and
coverage; it does not assert defective production behavior or call a scheduler.
R3 is an instruction/provenance scenario; its unchanged saved prompt after a
package copy is local evidence, not a live scheduler reproduction. R4 exposes
duplicate status keys; Python 3.9's permissive fallback may even report paused,
while a strict parser can reject them. Both are invalid evidence of success.

Phase 1 owns control decisions and R5 assertions; Phase 2 owns R1 counters;
Phase 3 owns R4 effects; Phase 4 owns R2 installs; Phase 5 owns R6 constraints;
Phases 6-7 own R3 migration/instruction integration; Phase 8 supplies behavioral
replays. Owners replace baseline-only defects with passing regression assertions
against expected results. Do not leave permanent expected-failure tests or make
observed broken results the future oracle. Existing generated packages are
unchanged in Phase 0 because no canonical production/template source changes.
