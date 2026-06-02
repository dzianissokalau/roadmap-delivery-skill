# State, Log, And Branches Reference

Use this reference for status inspection and for reconciling roadmap delivery
surfaces before work.

## Delivery State Schema

Recommended fields:

```json
{
  "roadmap": "roadmaps/<roadmap-file>.md",
  "roadmap_slug": "<slug>",
  "current_phase": "Phase N - Name",
  "branch": "codex/<slug>-phase-N",
  "status": "not_started",
  "review_iterations": 0,
  "max_review_iterations": 3,
  "last_verification": null,
  "last_review": null,
  "last_delivered_phase": null,
  "blocked_reason": null,
  "last_blocker_repair": null,
  "last_activation": null,
  "required_model": null,
  "required_reasoning_effort": null,
  "configured_automation_model": null,
  "configured_automation_reasoning_effort": null,
  "run_count": 0,
  "stalled_run_count": 0,
  "max_stalled_runs": 2,
  "last_progress_signature": null,
  "last_progress_at": null,
  "last_operator_alert": null,
  "updated_at": null
}
```

## Status Values

- `not_started`: phase is selected but no delivery attempt has begun
- `delivering`: implementation is in progress
- `verifying`: verification is running or awaiting evidence
- `reviewing`: delivery is awaiting review
- `fixing`: review found in-scope fixes
- `delivered`: current phase passed the gate
- `blocked`: work cannot continue until a blocker is repaired or a human action
  is supplied

When a blocked run becomes repairable, record the repair in
`last_blocker_repair`, clear `blocked_reason` only after validation/readback
passes, and return the current phase to `not_started`, `delivering`, or
`fixing` as appropriate. A previous blocked review is historical evidence; it
does not prevent delivery when a later repair is recorded and reconciliation
passes.

When setup recorded PAUSED but the saved automation now reads ACTIVE because of
operator/manual activation, record `last_activation` with the accepted
readback, acceptance source, and timestamp. Update the guide, log, and state to
ACTIVE before phase work resumes.

## Setup State Fields

During new automation setup, resolve `required_model` and
`required_reasoning_effort` from `phase_model_policy.json` for the first current
phase before saving `delivery_state.json`. Set `max_stalled_runs` from policy,
defaulting to `2` only when policy omits it.

Set `configured_automation_model` and
`configured_automation_reasoning_effort` only from saved automation readback or
another explicit runner config. Do not copy desired proposal values into these
fields before readback; unknown configured values should stay null and block
activation when the roadmap is model-strict.

After setup readback:

- if configured values match required values, mirror them in state and keep
  `blocked_reason` null
- if configured values are missing or mismatched, keep the automation paused or
  mark state blocked, record the mismatch, and do not activate delivery
- if the saved prompt lacks the model-policy hard stop, repair the prompt before
  activation or record an automation-config blocker

## Delivery Log Schema

The log is append-only. Each phase entry should record:

- status
- branch
- scope
- changed files
- verification commands and results
- review file and verdict
- residual risks
- next action

## Review Directory

Review artifacts live under:

```text
automation/<slug>/reviews/
```

Names should follow:

```text
<slug>-phase-<n>-review-iteration-<m>.md
```

The latest review must agree with state before advancement.

## Branch Naming

Use:

```text
codex/<roadmap-slug>-phase-<phase-number>
```

Finalization or promotion branches are separate and require explicit operator
approval. A current-phase branch mismatch is a warning; an unexplained mismatch
that affects owned files is a blocker.

## Status Inspection Commands

Run from the repository root:

```bash
git rev-parse --is-inside-work-tree
git branch --show-current
git status --short --branch
git branch --list 'codex/<roadmap-slug>*'
rg -n "^Status:|^Current phase:|^Last completed phase:|^Next action:" ROADMAP_PATH
python3 -m json.tool automation/<slug>/delivery_state.json
```

If an automation id is known, inspect:

```bash
cat $CODEX_HOME/automations/<automation-id>/automation.toml
```

Do not edit app automation config during status inspection.

## Model Policy Status

When `phase_model_policy.json` exists, include these facts in status reports:

- current phase required model and reasoning effort
- configured automation or runner model and reasoning effort, when available
- whether required and configured values match
- `run_count`, `stalled_run_count`, `max_stalled_runs`, and
  `last_progress_signature`
- latest operator alert path, if one exists

If configured values cannot be read, say that explicitly. Do not infer that the
active Codex session is on the required model merely because the policy asks
for it.

## Progress Signature And Stall Status

Progress detection uses durable state, not narration. Compute the signature
from:

- `current_phase`
- `status`
- `last_delivered_phase`
- `review_iterations`
- `last_verification`
- `last_review`
- current git `HEAD`
- delivery log size and SHA-256
- `blocked_reason`

Use `scripts/compute_progress_signature.py` to compute the current signature.
By default it is read-only. With `--record-run`, it updates
`delivery_state.json` and appends one JSON object to
`automation_run_log.jsonl`.

The end-of-run update must:

- increment `run_count`
- compare the new signature to `last_progress_signature`
- reset `stalled_run_count` to `0` when progress changed
- increment `stalled_run_count` when no durable progress changed
- read `max_stalled_runs` from `phase_model_policy.json`, defaulting to `3`
- update `last_progress_signature`
- update `last_progress_at` only when progress changed

When `stalled_run_count >= max_stalled_runs`, the run is stalled. Mark state
`blocked`, preserve the stalled reason in `blocked_reason`, and set the local
run-log entry's `phase_6_alert_required` field to `true`. Phase 6 owns the
alert-file and optional notification sink behavior; Phase 5 does not pause
automations or decide external notification sinks.

`automation_run_log.jsonl` is append-only. Each non-empty line must be a JSON
object with the recorded timestamp, phase, status, progress signature,
previous signature, run count, stalled count, threshold, and threshold result.
Validation treats corrupt JSONL as an error because the run history can no
longer be trusted.

Status inspection should report the stored count values and the next computed
run result:

```bash
python3 skill/roadmap-delivery-skill/scripts/inspect_delivery_state.py \
  --repo-root /path/to/repo \
  --roadmap-slug <slug> \
  --automation-id <automation-id>
```

To record an end-of-run update:

```bash
python3 skill/roadmap-delivery-skill/scripts/compute_progress_signature.py \
  --repo-root /path/to/repo \
  --roadmap-slug <slug> \
  --record-run
```

## Mismatch Warnings

Warn or block when:

- roadmap path in state does not exist
- automation prompt references an old roadmap path
- roadmap current phase differs from state current phase
- state branch differs from current branch
- latest review verdict differs from state
- policy required model/reasoning differ from saved automation readback
- saved automation prompt lacks the model-policy hard stop
- state is blocked but the next run is trying to advance before classifying and
  repairing the blocker
- state says complete but automation remains active
- multiple lifecycle roadmap files could match the same slug
- dirty worktree includes current phase owned files with unexplained edits

When in doubt, report the mismatch and stop instead of choosing a side.

## Artifact Validation

Phase 6 adds a read-only artifact validator for pre-delivery reconciliation:

```bash
python3 $CODEX_HOME/skills/roadmap-delivery-skill/scripts/validate_delivery_artifacts.py \
  --repo-root /path/to/repo \
  --roadmap-slug <roadmap-slug> \
  --automation-id <automation-id> \
  --json
```

Use it before acting on a roadmap when state, log, branch, review files, or
automation config might have drifted. The report contains `errors`, `warnings`,
and `info`:

- `errors`: blocking inconsistencies; stop and record the blocker before
  delivery work.
- `warnings`: non-blocking drift or operator attention items; continue only when
  they are understood and do not affect the current phase.
- `info`: paths and facts checked.

The validator is read-only. It does not repair stale paths, pause automations,
stage files, or update delivery state. Use `--strict` when warnings should fail
a CI or smoke check. Use `--allow-warning <code>` for expected environment
warnings, such as a GitHub-only reviewer without local automation config.
Without `--strict`, warnings return exit code 0 and errors return non-zero.

It checks the delivery state, delivery log, review directory, roadmap lifecycle
filename, state roadmap path, automation prompt roadmap references, model-policy
hard-stop guard, required versus configured model/reasoning, state/roadmap
current phase, completion/deep-review evidence, completed ACTIVE automation
drift, missing automation config, review verdict values, branch naming, and
dirty worktree status.

## Maintenance Checklist

Use this checklist before publishing or relying on an updated installed skill:

- Keep `SKILL.md` as a router. Put detailed procedures in references and
  deterministic checks in scripts or repository-local tests.
- Refresh setup and finalization prompt skeletons after Codex automation API or
  saved `automation.toml` behavior changes.
- Rerun validation after source template changes, roadmap lifecycle convention
  changes, or helper script edits.
- Add deterministic regressions for new failure modes whenever the behavior can
  be represented with local fixture files.
- Route new failure modes to the narrowest home:
  `state-log-and-branches.md` for reconciliation/status drift,
  `troubleshooting.md` for repair paths, `phase-loop.md` for delivery gates,
  `review-and-fix.md` for reviewer behavior, and
  `finalization-and-promotion.md` for closeout or promotion. Use
  `model-policy-and-stall-control.md` for model policy, progress signatures,
  stalled-run thresholds, and alert behavior.
- Keep platform work such as dashboards, telemetry, attestations, multi-repo
  APIs, and automatic promotion outside the installed skill until explicitly
  approved as separate platform work.

Before declaring a maintenance update ready, run:

```bash
python3 -m py_compile $CODEX_HOME/skills/roadmap-delivery-skill/scripts/inspect_delivery_state.py
python3 -m py_compile $CODEX_HOME/skills/roadmap-delivery-skill/scripts/validate_delivery_artifacts.py
python3 -m unittest discover -s tests -v
python3 $CODEX_HOME/skills/roadmap-delivery-skill/scripts/validate_delivery_artifacts.py --repo-root /path/to/repo --roadmap-slug <slug> --automation-id <automation-id> --json
```
