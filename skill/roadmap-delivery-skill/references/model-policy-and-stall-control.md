# Model Policy And Stall Control Reference

Use this reference when a roadmap automation has phase-specific model
requirements, reasoning requirements, stalled-run thresholds, or operator
alerts.

## Core Contract

Model and reasoning selection belong to the runner. The workflow may read
policy, compare required and configured values, update durable state, write
retarget plans, and request or perform approved runner updates. Prompt text
alone does not prove the active model or reasoning effort.

## Policy Shape

Policy lives with automation artifacts:

```text
automation/<roadmap-slug>/phase_model_policy.json
```

Minimum structure:

```json
{
  "schema_version": 1,
  "max_stalled_runs": 2,
  "notification": {
    "mode": "alert_file",
    "fallback": "alert_file"
  },
  "defaults": {
    "model": "<default-model>",
    "reasoning_effort": "<default-reasoning-effort>"
  },
  "phases": {
    "finalization": {
      "model": "<finalization-model>",
      "reasoning_effort": "<finalization-reasoning-effort>"
    }
  },
  "adaptive_model_policy": {
    "enabled": false,
    "escalate_on": [
      "delivered_with_fixes",
      "verification_failed",
      "review_needs_fix",
      "stalled",
      "retarget_failed"
    ],
    "human_gated_qualities": [
      "blocked_human_required",
      "completion_closeout_failed"
    ],
    "deescalate_after_flawless_runs": 0,
    "escalation": {
      "model": "<stronger-approved-model>",
      "reasoning_effort": "<stronger-approved-reasoning>"
    },
    "caps": {
      "allowed_models": ["<approved-model>"],
      "max_reasoning_effort": "<maximum-approved-reasoning>",
      "allowed_providers": ["<provider>"],
      "allowed_cost_classes": ["<cost-class>"]
    }
  }
}
```

Known reasoning effort values are `none`, `minimal`, `low`, `medium`, `high`,
`xhigh`, `max`, and `ultra`. Host support is a separate explicit capability.

Treat reasoning effort as an ordered minimum floor:

`none < minimal < low < medium < high < xhigh < max < ultra`

A runner configured with higher reasoning than the phase requires satisfies the
phase. For example, `xhigh` satisfies a phase that requires `high`. Do not
block delivery, write a retarget-failed alert, or request
`retarget_saved_automation` merely to downgrade reasoning. Downward retargets
are optional cost optimizations and must never be required before the next
phase can start. A runner configured with lower reasoning than required still
fails the model-policy gate.

## Adaptive Model Policy

Run quality is classified after verification and review:

- `flawless`
- `delivered_with_fixes`
- `verification_failed`
- `review_needs_fix`
- `blocked_local_repairable`
- `blocked_human_required`
- `stalled`
- `retarget_failed`
- `completion_closeout_failed`

Adaptive policy changes only the next run. It never claims to switch the active
model inside an already-running session. Non-flawless local delivery outcomes
may escalate to the configured `escalation` target. Human-gated blockers skip
model escalation and keep asking for the missing human action. A flawless streak
may de-escalate after `deescalate_after_flawless_runs`; the resolved phase
reasoning is always a minimum, combined with both explicit floor spelling fields.
A proposal below that floor is raised to it. A floor above the cap, unknown
value, or model outside the allowlist is an invalid policy with no usable target.

Caps are mandatory when adaptive policy is enabled. Supplied caps also apply
when adaptation is disabled. Defaults, overrides, no-change paths, escalation,
de-escalation and bound persisted targets use the same shared resolver. A higher
configured reasoning value already satisfying the target is preserved; the
planner does not require a cost-only downgrade.

Provider and cost-class limits require explicit trusted metadata from the
adapter/operator. Retarget, validation, inspection, preflight and control planning accept `--capabilities-file`
with `trusted: true`, a non-empty `source`, and `models` mapping model identifiers
to `reasoning_efforts`, `provider`, `cost_class` and optional integer `rank`.
This is an operator attestation, not authentication. Self-declared target
provider/cost fields and guessed model pricing are never evidence. Requested
limits without metadata return unresolved/invalid-policy, not enforced. A model
floor requires explicit ranks; names alone do not establish relative strength.
Absent host metadata reports `host_support: unknown` without changing the active
model. Explicit host support selects a supported reasoning value within the
floor/cap or reports unsupported.

Optional `policy_version` is an operator label; a canonical fingerprint binds
all policy values even if that label is unchanged. Persisted decisions bind
source phase/run, target phase and a retained snapshot of verification/review/blocker evidence.
The decision also retains the explicitly supplied capability metadata; supplying
fresh metadata overrides that snapshot and detects changes. Destination-phase
verification or review does not invalidate its source decision. Missing or mixed
run identities cannot establish a flawless run or justify de-escalation. Old
unbound targets, changed policy/evidence and wrong run/phase are ignored; bound
targets still pass current constraints. Cached `last_run_quality` cannot replace current evidence. Flawless streaks
continue only from a preceding bound decision on the same policy; unbound
counters are reset for adaptive selection. Inspection, validation, prerequisite
planning and retargeting all resolve effective targets through the shared runtime.

## Provider Role Config

Provider-role config is an optional, host-neutral input that describes which
model policy should be used for workflow roles such as executor, reviewer,
inspector, finalizer, and repairer.

Repository examples live at:

```text
config/providers.example.yaml
schemas/provider_config.schema.json
```

The provider-role config maps each role to:

- the `phase_model_policy.json` field names it can populate (`model` and
  `reasoning_effort`)
- provider-specific model names
- whether the provider supports an explicit reasoning-effort control
- runner config field names when a host exposes them

`phase_model_policy.json` remains the durable start-run gate for a roadmap
phase. A provider-role config can be used to prepare or explain policy values,
but it does not prove the active runner is configured with those values. The
start-run gate still needs trusted runner readback before phase-owned edits.

## Start-Run Gate

Before implementation:

1. Resolve current phase from delivery state.
2. Resolve required model and reasoning from numbered policy override or
   defaults.
3. Read configured runner model and reasoning from a trusted config or readback
   source.
4. Stop before phase-owned edits if the configured model differs, configured
   reasoning is lower than required, or required values cannot be proven.

Retarget runner configuration only when `approval_policy.json` resolves
`retarget_saved_automation` to `allowed` or explicit human approval is already
present. If the decision is `ask`, record the required approval and stop. If the
decision is `forbidden`, record a blocker and do not attempt the retarget.
After retargeting, read back the saved config and stop so a later run starts
with the right settings.

## End-Run Retargeting

After a delivered review verdict, resolve the next phase's model and reasoning,
classify the run quality, apply `adaptive_model_policy` to the next target,
update durable state, compare against runner readback, and retarget only when
the runner is below the target floor or the model must change, and only when
the approval-policy decision is `allowed` or explicit human approval is already
present. If the saved runner already uses higher reasoning than the next phase
requires, leave it unchanged and continue; do not ask for approval just to
downgrade. The retarget plan should surface the run quality, adaptive action,
operation decision, and target source so conservative mode preserves ask-first
behavior and delegated modes avoid repeated prompts only for explicitly allowed
runner updates. If readback fails or remains below the required target, keep or
set blocked state, write an alert, and do not start the next phase.

## Progress And Stall Control

Use versioned semantic evidence and a stable unique `run_id`. Start the attempt
before phase work, capturing phase/runner identity, owned files, initial evidence
and counters. Reuse its ID for retries, review fixes and interrupted recovery.
Read-only inspection does not allocate an attempt or project a fictitious failure.

Count only verifier-backed accepted work, a newly satisfied named criterion, or
a check proving the original blocker resolved. Evidence version 1 includes phase,
kind, stable criterion/blocker and increment IDs, previous/current semantic states,
artifact SHA-256 and a verifier JSON path/hash. The verifier records the exact
transition and a passed check path/hash; accepted work also requires a delivered,
criterion-specific review path/hash and a phase-owned artifact. Local attestation
integrity is checked; its author identity is a trusted check/reviewer boundary.

The shared runtime derives event keys from semantic scope. Supplied evidence IDs,
new proof paths, timestamps, delivery log hashes, review verdicts/filenames, changed
failure wording, git commits and repeated passing checks cannot earn progress.
Deduplicate accepted increments and artifact revisions across runs. A previously
satisfied criterion cannot reset counters through another passing check.
For blocker repairs, copy the recorded `blocker_occurrence_id` from the active
attempt (or `progress_accounting.blocker_context.occurrence_id` after it closes)
into `previous.blocker_occurrence_id` in verifier-attested evidence. Retries of
that occurrence are deduplicated; a later recurrence has a new recorded identity
and requires new evidence. Old repair receipts cannot clear a new occurrence.

The first unique completed or interrupted attempt without new evidence increments
both lifetime runs and consecutive failures; the second reaches default threshold
2, with no grace run. Thresholds 1 and 3 have the same exact boundary rule. Multiple
new evidence items in one outcome reset the consecutive counter once. A duplicate
outcome changes neither counter nor the outcome timestamp. Verified original-cause
repair clears that cause; failure wording and pause results never replace it.

Record starts/outcomes under a local writer lock, with revision conflict detection.
Append/fsync the version 2 journal before atomic state replacement. On interruption,
replay its recorded proposal and finish the same ID once; do not allocate a new ID
until the unfinished attempt closes. Corrupt/conflicting history stops recording.
Completion markers take precedence over recovery too: do not account another
outcome or replay an older accounting proposal over completed scope. Reconcile
any pending journal explicitly while retaining the terminal hard stop.
Legacy hashes remain diagnostic and migration preserves known run/stall counts,
seeds already consumed bootstrap events and explicitly records uncertain history.
Migration alone never resets counters or counts as progress.

Use the installed CLI or packaged `scripts/roadmap_delivery.py` helper:

```bash
roadmap-delivery progress \
  --repo-root /path/to/repo --roadmap-slug example --start-run \
  --run-id stable-attempt-id --owned-file src/example.py --json
roadmap-delivery progress \
  --repo-root /path/to/repo --roadmap-slug example --record-run \
  --run-id stable-attempt-id --evidence-file accepted-evidence.json --json
```

Omit `--evidence-file` for no progress. Use `--recover-run` with the same ID to
close an interrupted attempt, retaining any verified evidence. `--expected-revision`
rejects conflicting writers. A terminal-only invocation does not start another
attempt. At threshold, keep/set blocked state and retain the actionable
`blocked_reason`; store the trigger in `stall_metadata`. Accounting returns a
terminal plan and never edits a saved runner. The host closeout adapter writes the
local alert and resolves the context-authorized status-only pause, confirms PAUSED
through readback, or records a specific pending/disabled/unavailable outcome. No
phase may begin before terminal reconciliation. ACTIVE resume alone is neither
progress nor a fresh attempt budget. After an external repair at threshold,
`--resolve-blocker --evidence-file repair-evidence.json` consumes its verified
original-cause transition once, without allocating an attempt or incrementing
lifetime runs. A duplicate repair receipt cannot reset a later failed run.

## Self-Pause Policy

The shared approval resolver is the authority for completion/stall pause:
missing context flags default true; explicit `pause_automation_on_completion`
or `pause_automation_on_stall: false` disables automatic pausing even when broad
`pause_saved_automation` permission is true in a delegated mode. A later explicit
operator request to pause is separate scoped authority. Missing policy uses these
conservative defaults; malformed policy cannot grant execution authority.

Terminal closeout precedes ordinary phase/model/migration gates. A broad saved
runner restriction alone does not revoke the narrow status-only safety pause.
Write the local alert before effects, bind runner identity, preserve all other
settings, execute through supported host tooling and require authoritative
PAUSED readback. Attempted/applied updates alone are not verified receipts.

If the context pause is disabled, record `disabled` and preserve that choice.
If capability or readback is unavailable, record the precise pending action.
Completion remains `completed_pending_pause` when an applicable pause cannot be
verified; manual unscheduled runs record `not_applicable`. Final verification,
delivered review and a distinct final deep-review prompt/artifact or explicit
human waiver remain necessary before claiming completion.

## Alerts

Local alert files are the durable fallback for `stalled`, `completed`,
`blocked`, and `retarget-failed` states. External notifications are optional
and must fail safe to the local alert file.

## Host Adapter Boundary

The core defines policy fields, comparison rules, stall counters, pause
decisions, and alert requirements, including adaptive run quality and
model-target decisions. Host adapters own concrete model names, provider-role
guidance, runner readback, and runner update mechanisms. If a host cannot prove
or set a role's model, reasoning value, or paused status, the adapter must
record that limitation rather than claiming unsupported control.

## Codex Execution

Use `scripts/plan_automation_retarget.py` (CLI `plan-retarget`) for next-run
planning. `scripts/compute_progress_signature.py` (CLI `progress`) records unique
runs with verifier-backed evidence. Use `scripts/roadmap_delivery.py
terminal-closeout` to resume alert/readback receipts and emit supported host
requests; it never edits a live saved runner file. Reading automation.toml
supplies configuration evidence, not scheduler update capability.
