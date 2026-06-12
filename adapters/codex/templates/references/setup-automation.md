# Setup Automation Reference

Use this reference when creating a new file-backed roadmap delivery automation.
The goal is a conservative, inspectable workflow that starts paused unless the
human operator explicitly asks for activation.

## Suitability Checklist

Use autonomous phase-gated delivery only when all of these are true:

- The roadmap is already decomposed into clear phases.
- Each phase has owned files, non-goals, acceptance criteria, verification, and
  stop conditions.
- The repository can tolerate local branch work without hidden publication.
- Durable artifacts can live in the repository under `automation/<slug>/`.
- Human approval remains required for publication, promotion, destructive
  operations, credentials, and ambiguous product decisions.

Do not set it up for broad project management, open-ended refactors, release
automation, or workflows where the model must infer phase scope.

## Roadmap Slug And Path

Pick a short lowercase slug from the roadmap title:

```text
ROADMAP_PATH=roadmaps/<roadmap-file>.md
ROADMAP_SLUG=<short-lowercase-slug>
AUTOMATION_DIR=automation/<roadmap-slug>
```

Record the exact path in the roadmap header, state JSON, delivery log, and
automation guide. The saved automation prompt should be state-first: point it
at stable automation artifacts, require it to read `delivery_state.json`, and
say that the roadmap path recorded in `delivery_state.json` is authoritative.
Do not make the saved automation prompt depend on the lifecycle-prefixed
roadmap filename.

If the roadmap becomes active or advances to Phase 1+, it must not keep a
`not_started_` filename. If the roadmap filename changes during a lifecycle
rename, repair repository-local references in the roadmap, state, guide, log,
reviews, and run bookkeeping before doing delivery work. A saved automation
prompt update is not required when the prompt is state-first and still
references the stable state/guide files.

## Artifact Layout

Create this repository-local layout:

```text
automation/<roadmap-slug>/
  automation_guide.md
  approval_policy.json
  delivery_state.json
  delivery_log.md
  review_fix_state.json
  review_fix_log.md
  phase_model_policy.json
  automation_run_log.jsonl
  alerts/
  reviews/
```

Keep app automation config outside the repository unless the user explicitly
asks to edit it. Keep the automation `cwd` rooted at the repository root.

Create `approval_policy.json` during setup and record its path, active mode,
and last readback in `delivery_state.json`. Start conservative unless the
operator explicitly selects a delegated or custom mode. Do not leave model
retargeting dependent on a missing policy file; a later phase may need
`retarget_saved_automation` before it can safely start.

If the operator manually activates an automation that setup originally recorded
as paused, the next run should reconcile that accepted ACTIVE state when it is
the only drift. Read back model/reasoning, prompt path, cwd, hard-stop guard,
and blocked-remediation guard first; if they are clean, update guide/log/state
to ACTIVE and record `last_activation` instead of leaving the roadmap blocked.

## Initial State JSON

Start with this shape and fill in concrete values. Resolve the first phase's
required model and reasoning from `phase_model_policy.json` before saving the
state. Leave configured automation fields null until a saved automation
readback proves them.

```json
{
  "roadmap": "roadmaps/<roadmap-file>.md",
  "roadmap_slug": "<roadmap-slug>",
  "current_phase": "Phase 0 - Scope Confirmation",
  "branch": null,
  "status": "not_started",
  "review_iterations": 0,
  "max_review_iterations": 3,
  "last_verification": null,
  "last_review": null,
  "last_delivered_phase": null,
  "blocked_reason": null,
  "required_model": "<first-phase-required-model>",
  "required_reasoning_effort": "<first-phase-required-reasoning-effort>",
  "configured_automation_model": null,
  "configured_automation_reasoning_effort": null,
  "run_count": 0,
  "stalled_run_count": 0,
  "max_stalled_runs": 2,
  "last_progress_signature": null,
  "last_progress_at": null,
  "last_operator_alert": null,
  "last_run_quality": null,
  "last_adaptive_action": null,
  "model_history": [],
  "adaptive_escalation_count": 0,
  "adaptive_deescalation_count": 0,
  "adaptive_flawless_streak": 0,
  "auto_advance_after_delivered_review": true,
  "push_to_github": false,
  "updated_at": null
}
```

Use ISO-8601 UTC timestamps for `updated_at` and verification/review times.

## Initial Phase Model Policy

Create `phase_model_policy.json` by default for new roadmap delivery
automations. Ask for, or infer only from explicit operator setup answers:

- default model for phases without an override
- default reasoning effort
- optional per-phase model/reasoning overrides
- finalization model and reasoning effort
- `max_stalled_runs`, normally `2`
- notification mode, normally `alert_file`
- adaptive model policy, disabled by default unless the operator selected
  escalation/de-escalation behavior
- adaptive caps for allowed models, maximum reasoning effort, and optional
  provider or cost-class boundaries

Use lower-cost models or lower reasoning only for phases whose acceptance
criteria are documentation-only, status-only, or otherwise low-risk. Use the
strongest approved coding model and higher reasoning for implementation,
multi-file migrations, validation scripts, and finalization review. Do not infer
that every phase needs the most expensive model by default; make overrides
explicit in policy.

Minimum generated policy:

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
    "caps": {
      "allowed_models": ["<default-model>"],
      "max_reasoning_effort": "<default-reasoning-effort>"
    }
  }
}
```

Add numbered phase overrides only when the operator or roadmap has a concrete
reason to depart from defaults. Validate the generated policy before saving or
activating any automation. If validation fails, keep state `blocked` or leave
setup incomplete, record the validation error, and do not activate.

## Initial Delivery Log

Start the log with:

```markdown
# <Roadmap Name> Delivery Log

Status: Active
Roadmap: `roadmaps/<roadmap-file>.md`
State file: `automation/<roadmap-slug>/delivery_state.json`
Review directory: `automation/<roadmap-slug>/reviews`

## Operating Policy

- Deliver one phase at a time.
- Run required verification before claiming a phase is delivered.
- Require a fresh review verdict before phase advancement.
- Preserve unrelated worktree changes.
- Keep all publication and promotion human-approved.
```

Append entries only. Do not rewrite history except to fix malformed setup
before delivery starts.

## Automation Prompt Skeleton

Use concrete paths before saving:

```text
Run the next safe step for the roadmap recorded in
`automation/<roadmap-slug>/delivery_state.json` using the phase-gated workflow
in `automation/`. Resolve the current roadmap path from `delivery_state.json`;
the state roadmap field is authoritative across lifecycle renames.

Read these first:
- `automation/<roadmap-slug>/automation_guide.md`
- `automation/codex_phase_gated_delivery_automation_template.md`
- `automation/<roadmap-slug>/delivery_state.json`
- `automation/<roadmap-slug>/delivery_log.md`
- `automation/<roadmap-slug>/review_fix_state.json` when present
- `automation/<roadmap-slug>/phase_model_policy.json`

Operate on exactly one current phase at a time. Resolve the roadmap from state,
then reconcile roadmap, state, log, review files, phase model policy, git
branch, working tree, and saved automation configuration before editing.

Before recording a generic mismatch blocker, handle the normal paused-setup to
active-run transition: if durable setup artifacts still say the saved
automation is PAUSED but saved readback is ACTIVE, and model/reasoning, cwd,
state-first prompt, hard-stop guard, and blocked-remediation guard all match,
accept it as operator/manual activation. Update guide/log/state to ACTIVE,
record `last_activation` and `last_blocker_repair`, reset stalled counters,
rerun validation, and continue the current phase. Do not stop just because the
saved automation is ACTIVE after the operator started it.

If the surfaces still disagree after local lifecycle and activation
reconciliation, record the blocker in state/log/review and stop.

If state is `blocked`, enter Blocked Remediation Mode before normal delivery:
classify the blocker, repair local or already-authorized automation-config
blockers, rerun validation, clear `blocked_reason` only when the repair is
verified, and then resume the current phase. If the blocker needs credentials,
approval, a product decision, or destructive git, keep state blocked and ask for
the missing human action.

Hard stop before delivery if `all_phases_complete` is true, state is
`completed`, or state is `completed_pending_pause`. Confirm the automation is
paused or request pause permission, write any missing completion alert, and do
not start phase work.

For the current phase only:
- extract objective, owned files, implementation steps, acceptance criteria,
  required verification, non-goals, and stop conditions
- create or reuse `codex/<roadmap-slug>-phase-<n>` when implementation work is
  required
- preserve unrelated user changes
- read `phase_model_policy.json`, resolve the current phase's required model and
  reasoning, and verify the configured automation model matches and reasoning
  is at least the required floor
  before implementation
- make only phase-scoped changes
- run required verification and targeted checks
- classify run quality and apply adaptive model policy only to the next run
- update `automation/<roadmap-slug>/delivery_log.md` and
  `automation/<roadmap-slug>/delivery_state.json`
- perform a skeptical review from fresh context where available
- write review output under `automation/<roadmap-slug>/reviews/`
- if the verdict is `needs-fix`, fix only in current phase scope and rerun
  verification
- stop after 3 review/fix iterations and mark blocked if still not delivered

Do not advance unless acceptance criteria are satisfied, verification passed,
review verdict is `delivered`, and roadmap/state/log are updated.

After advancing state to the next phase, stop. Do not publish, promote to
`main`, edit app automation config, or run destructive git operations without
explicit human approval.
```

## Cadence And Model

- Use cron for detached repository automation.
- Use a heartbeat/manual run while designing or repairing the workflow.
- Default detached cadence: hourly.
- Default model: the strongest approved coding model for implementation phases.
- Default reasoning: high or extra high for delivery phases, medium for
  status-only inspection when no edits are expected.
- Store defaults and any lower-cost or high-reasoning exceptions in
  `phase_model_policy.json`; do not rely on prompt wording alone to select a
  model.

## PAUSED By Default

Create new automations in `PAUSED` status unless the user explicitly requests
activation. If the app saves an automation as active despite a paused request,
record the drift, pause it if authorized, and do not start delivery until the
readback is correct.

## Readback Checklist

After creation or update, inspect the saved config:

- `id` matches the intended automation id.
- `status` is `PAUSED` unless explicit activation was requested.
- `cwd` is the repository root.
- prompt references the stable `delivery_state.json` path and says the roadmap
  path recorded in state is authoritative.
- prompt references the current automation guide and artifact directory.
- prompt includes the phase model policy hard stop before implementation.
- `model` and `reasoning_effort` match the first phase's required policy.
- cadence matches the requested schedule.
- no broad writable roots or global state edits were introduced.

## Operational Setup Checklist

Use this checklist when the operator asks to set up a new roadmap delivery
automation from a roadmap path. Keep the work repository-local until the
operator explicitly approves saving or activating an app automation.

### Inputs To Confirm

- `REPO_ROOT`: absolute path to the repository that owns the roadmap.
- `ROADMAP_PATH`: repository-relative path to the phased roadmap.
- `ROADMAP_SLUG`: short lowercase slug used under `automation/<slug>/`.
- `AUTOMATION_ID`: stable Codex automation id, usually derived from the slug.
- `BRANCH_PREFIX`: normally `codex/`.
- `MAX_REVIEW_ITERATIONS`: normally `3`.
- `DEFAULT_MODEL`: model for phases without an override.
- `DEFAULT_REASONING_EFFORT`: one of `minimal`, `low`, `medium`, `high`, or
  `xhigh`.
- `PHASE_MODEL_OVERRIDES`: optional numbered phase overrides.
- `FINALIZATION_MODEL` and `FINALIZATION_REASONING_EFFORT`.
- `MAX_STALLED_RUNS`: normally `3`.
- `NOTIFICATION_MODE`: normally `alert_file`.

Stop before creating anything if the roadmap does not define phases, owned
files, acceptance criteria, required verification, non-goals, and stop
conditions.

### Repository Artifacts To Create

Create or verify exactly these repository-local artifacts:

```text
automation/<roadmap-slug>/
  automation_guide.md
  delivery_state.json
  delivery_log.md
  review_fix_state.json
  review_fix_log.md
  phase_model_policy.json
  automation_run_log.jsonl
  alerts/
  reviews/
```

The initial state must point at the current roadmap path, start on the first
phase, set `status` to `not_started`, set `review_iterations` to `0`, set
`max_review_iterations`, set `max_stalled_runs` from policy, resolve
`required_model` and `required_reasoning_effort` for the first phase, and leave
`blocked_reason` null.

Create `phase_model_policy.json` with defaults, per-phase overrides if known,
`max_stalled_runs`, and a notification fallback. Mirror the current
required/configured model and reasoning fields in state. Before activation,
configured fields must come from automation readback, not from the desired
proposal.

The initial delivery log must record the roadmap path, state file, review
directory, operating policy, branch naming model, and publication guard. The
review directory should contain only a placeholder such as `.gitkeep` until the
first review is written.

### Paused Automation Proposal

Prepare a concrete automation proposal before saving anything in the Codex app:

```text
id=<automation-id>
kind=cron
status=PAUSED
rrule=FREQ=HOURLY;INTERVAL=1
execution_environment=worktree
cwd=<repo-root>
model=<approved model>
reasoning_effort=high or xhigh
```

Set `model` to the first phase's resolved policy value and set
`reasoning_effort` to that phase's required floor or a higher approved value.
If the first phase uses a lower-cost or high-reasoning override, the saved
automation must use the matching model and sufficient reasoning before
activation.

The prompt must include the stable `delivery_state.json` and automation guide
paths, require resolving the current roadmap path from state, list the required
files to read first, one-phase-at-a-time delivery rules, review/fix iteration
limits, Blocked Remediation Mode, phase-model-policy validation, the
model/reasoning hard stop before implementation, completion hard stop, the
no-push/no-main-promotion guard, and installed-skill permission handling when
relevant.

Do not activate the automation as part of setup unless the operator explicitly
asks for activation after validation.

### Setup Readback Checklist

After saving or updating an automation, read back the saved `automation.toml`
or connector response and confirm:

- `id` is the intended `AUTOMATION_ID`.
- `status = "PAUSED"` unless the operator explicitly requested activation.
- `cwd` is exactly `REPO_ROOT`.
- `model` equals the first phase's required policy model.
- `reasoning_effort` equals or exceeds the first phase's required policy
  reasoning effort.
- the prompt references `delivery_state.json` and states that the roadmap path
  recorded there is authoritative.
- the prompt references `automation/<roadmap-slug>/automation_guide.md`.
- the prompt references `delivery_state.json` and `delivery_log.md`.
- the prompt references `phase_model_policy.json`.
- the prompt includes the model-policy start-run hard stop.
- the prompt keeps work to one current phase and stops after phase advancement.
- no broad writable roots, global state patches, pushes, main promotion, or
  destructive git operations were introduced.

If readback shows the wrong model or reasoning, correct only with an approved
automation-config update and read back again. If correction is unavailable,
record the mismatch in state/log and do not activate. If readback shows `ACTIVE`
when `PAUSED` was requested, do not start delivery. Pause it only with explicit
approval or an already-approved setup flow; then read back again. If pausing
cannot be performed, record the drift in state/log and stop.

### Activation Gate

Activation is a separate operator decision. Before activating:

- the operator must explicitly request activation in the current conversation.
- `validate_delivery_artifacts.py` must report no `errors` for the roadmap.
- generated `phase_model_policy.json` must validate with allowed reasoning
  efforts, notification mode, defaults, and first-phase requirements.
- saved automation `model` must match the first phase's resolved policy and
  `reasoning_effort` must satisfy the first phase's required reasoning floor.
- saved prompt must include the phase-model-policy hard stop before
  implementation.
- state must not say all phases are complete.
- state must not be blocked unless the blocker has been fixed and recorded.
- roadmap, state, log, review directory, branch, and automation prompt paths
  must agree.

If any activation gate fails, refuse activation, report the blocking evidence,
and leave the automation paused or unchanged.

### Operator Summary

After setup or repair, report the exact paths created or changed:

- roadmap path
- automation artifact directory
- state file
- delivery log
- review directory
- automation id
- automation status after readback
- cwd after readback
- prompt roadmap references after readback
