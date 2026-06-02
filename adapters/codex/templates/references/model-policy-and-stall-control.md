# Model Policy And Stall Control Reference

Use this reference when a roadmap automation has `phase_model_policy.json`,
phase-specific model requirements, stalled-run thresholds, or completion/stall
alerts.

## Model Control Boundary

The skill cannot switch the model or reasoning effort of an already-running
Codex session. Model and reasoning selection belong to the runner:

- Codex app automation config
- CLI model/reasoning flags or profile
- another explicit execution surface

The skill may read policy, compare required versus configured model, update
state, write a retarget plan, and request or perform an approved automation
update. It must not claim that prompt text alone changes the active model.

## Policy File

Recommended location:

```text
automation/<roadmap-slug>/phase_model_policy.json
```

Recommended shape:

```json
{
  "schema_version": 1,
  "max_stalled_runs": 2,
  "notification": {
    "mode": "alert_file",
    "fallback": "alert_file"
  },
  "defaults": {
    "model": "gpt-5.5",
    "reasoning_effort": "xhigh"
  },
  "phases": {
    "1": {
      "model": "gpt-5.5",
      "reasoning_effort": "xhigh"
    },
    "finalization": {
      "model": "gpt-5.5",
      "reasoning_effort": "xhigh"
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
      "model": "gpt-5.5",
      "reasoning_effort": "xhigh"
    },
    "caps": {
      "allowed_models": ["gpt-5.5"],
      "max_reasoning_effort": "xhigh",
      "allowed_providers": ["openai"],
      "allowed_cost_classes": ["standard"]
    }
  }
}
```

Allowed `reasoning_effort` values:

- `minimal`
- `low`
- `medium`
- `high`
- `xhigh`

Treat reasoning effort as an ordered minimum floor:

`minimal < low < medium < high < xhigh`

A saved automation configured with higher reasoning than the phase requires
satisfies the phase. For example, `xhigh` satisfies a phase that requires
`high`. Do not block delivery, write a retarget-failed alert, or request
`retarget_saved_automation` merely to downgrade reasoning. Downward retargets
are optional cost optimizations and must never be required before the next
phase can start. A saved automation configured with lower reasoning than
required still fails the model-policy gate.

## Adaptive Model Policy

Classify run quality after verification and the review verdict:

- `flawless`
- `delivered_with_fixes`
- `verification_failed`
- `review_needs_fix`
- `blocked_local_repairable`
- `blocked_human_required`
- `stalled`
- `retarget_failed`
- `completion_closeout_failed`

Adaptive policy applies only to the next run. It never changes the model inside
an already-running Codex session. Non-flawless local delivery outcomes may
escalate to the configured `escalation` target. Human-gated blockers skip model
escalation and keep asking for the missing human action. A flawless streak may
de-escalate only when explicitly configured.

When adaptive policy is enabled, caps are required. Use `allowed_models`,
`max_reasoning_effort`, and optional provider or cost-class caps to prevent
unbounded model, provider, or cost changes without inferring provider-specific
pricing.

## Provider Role Config

Provider-role config lets the package describe reusable model choices for
workflow roles without replacing `phase_model_policy.json`.

Repository examples live at:

```text
config/providers.example.yaml
schemas/provider_config.schema.json
```

The standard roles are:

- `executor`: implement one current phase and run verification
- `reviewer`: perform the skeptical phase-gate review
- `inspector`: inspect state, logs, branches, and generated artifacts
- `finalizer`: run final verification and completion checks
- `repairer`: repair local or already-authorized blockers

The config maps each role to the current phase model-policy fields:

```json
{
  "phase_model_policy": {
    "model_field": "model",
    "reasoning_effort_field": "reasoning_effort"
  }
}
```

For Codex, role mappings may name the Codex runner fields `model` and
`reasoning_effort`. Those values are only proposed or documented until the
Codex app automation config, CLI flags, profile, or another trusted runner
source reads back matching values. A provider-role config does not prove the
active runner is configured correctly.

For Claude or other hosts, role mappings may name a model field but must not
claim explicit reasoning-effort control unless that runner exposes and reads
back such a field. Record unsupported controls as host limitations and keep the
start-run gate strict.

## Migrating Existing Automations

Existing roadmap delivery automations can adopt model policy without rewriting
their whole history. Treat migration as a reconciliation step, not as phase
delivery:

1. Confirm the current roadmap path, automation slug, delivery state, delivery
   log, review directory, branch, and saved automation prompt already agree.
2. Add `phase_model_policy.json` under the existing
   `automation/<roadmap-slug>/` directory.
3. Set policy defaults for ordinary phases, add only justified numbered
   overrides, add a `finalization` policy entry, and set `max_stalled_runs`.
4. Add missing state fields for required/configured model and reasoning,
   run/stall counters, progress signature, and last operator alert.
5. Resolve the current phase's required model/reasoning from policy.
6. Read back the Codex app automation, CLI profile, or runner config and record
   configured model/reasoning only from that readback.
7. Update the saved prompt so it reads the policy file, performs the start-run
   model gate before implementation, handles blocked remediation before retry,
   and hard-stops on completed states.
8. Run artifact validation and status inspection before allowing scheduled
   delivery to continue.

If any readback or prompt update requires an unapproved automation-config
change, stop with state blocked and ask for that approval. Do not infer that
the active session is on the right model because the policy requests it.

## Backward Compatibility

A missing `phase_model_policy.json` keeps legacy behavior unless the roadmap,
automation guide, or operator explicitly makes model policy strict. Legacy
roadmaps should still reconcile state, log, review, branch, and automation
prompt before delivery.

When introducing policy to an older automation, preserve existing review and
delivery history. Add new fields and log entries append-only where possible.
Configured automation model and reasoning fields should stay null until
readback proves them; desired proposal values are not evidence.

Release and operations notes:

- New setup flows should create policy by default.
- Existing automations can migrate one roadmap at a time.
- Local alert files are the durable fallback for stalled, blocked,
  retarget-failed, and completed states.
- External notification sinks are optional and must fail safe to the local
  alert file.
- Pausing, publication, promotion, branch deletion, and destructive git remain
  explicit operator-approved actions.

## Setup Integration

New roadmap delivery automations should create a phase model policy before the
automation is saved or activated. Setup must collect or confirm:

- default model
- default reasoning effort
- optional per-phase model and reasoning overrides
- finalization model and reasoning effort
- `max_stalled_runs`
- notification mode and fallback
- optional provider-role config path and selected role when the workflow uses
  `config/providers.example.yaml` or a project-specific equivalent

Use defaults for ordinary phases and add numbered overrides only when the
roadmap or operator has a concrete reason. Documentation-only or status-only
phases can use lower-cost models or lower reasoning. Implementation-heavy,
multi-file, migration, validator, and finalization phases should use the
strongest approved coding model and higher reasoning. Do not silently assign an
expensive model to every phase; make the tradeoff inspectable in
`phase_model_policy.json`.

Setup resolves the first phase's required model and reasoning from the policy,
then saves the Codex app automation or runner config with the exact model and
at least the required reasoning floor. Read back the saved config before
reporting success. If readback has the wrong model or reasoning below the
policy floor, correct it only when the automation-config surface is approved;
if it cannot be corrected, leave the automation paused or blocked and record
the mismatch.

When setup uses provider-role config, copy the selected role's model and
reasoning values into `phase_model_policy.json` first, then apply the same
readback gate. Do not treat the role file itself as runner readback.

Activation is not allowed until:

- `phase_model_policy.json` validates
- the saved automation model matches the first phase policy and reasoning
  satisfies the first phase floor
- the saved prompt includes the start-run model-policy hard stop
- repository artifacts, roadmap path, state, log, reviews, branch, and
  automation prompt reconcile without validator errors

## Start-Run Gate

Before implementation:

1. Read delivery state and current phase.
2. Read `phase_model_policy.json` when present.
3. Resolve required model and reasoning for the current phase. Use a numbered
   phase override first, then policy defaults.
4. Read saved automation config or explicit runner config when available.
5. Compare required versus configured values before phase extraction or any
   phase-owned file edit.

If the model matches and configured reasoning is at least the required floor,
continue normal phase extraction.

If the model mismatches or configured reasoning is below the required floor, do
not edit phase-owned files. Record:

- current phase
- required model and reasoning effort
- configured model and reasoning effort
- source of the configured values
- approval-policy decision for `retarget_saved_automation`

Retarget the automation only when `retarget_saved_automation` resolves to
`allowed` or explicit human approval is already present, then exit so the next
run starts on sufficient settings. If the decision is `ask`, record the missing
approval and stop. If the decision is `forbidden`, record a blocker. Do not ask
for approval merely to downgrade reasoning that is already above the required
floor.

If the active model cannot be proven and the roadmap is model-strict, stop and
ask for confirmation rather than guessing.

For manual CLI runs, use one of these relaunch patterns:

```bash
codex exec -m gpt-5.5 \
  -c 'model_reasoning_effort="xhigh"' \
  -C /path/to/repo \
  "Run the next safe phase-gated delivery step for roadmaps/example.md"
```

```bash
codex exec -p roadmap-delivery-xhigh \
  -C /path/to/repo \
  "Run the next safe phase-gated delivery step for roadmaps/example.md"
```

For Codex app automations, update the saved automation configuration only when
the model differs or reasoning is below the required floor. After an update,
read the config back. If readback still has the wrong model or insufficient
reasoning, keep or set state blocked and write a local alert.

If a provider-role config exists, it may explain why the current phase uses an
executor, reviewer, inspector, finalizer, or repairer model. It does not loosen
the start-run gate: required values still come from `phase_model_policy.json`,
and configured values still come from runner readback.

The gate treats these as stop-before-delivery conditions:

- required model differs from configured model
- required reasoning effort is higher than configured reasoning effort
- required model exists but no configured model can be proven
- required reasoning effort exists but no configured reasoning effort can be
  proven

## End-Run Retargeting

After a phase is delivered and reviewed:

1. Resolve the next phase.
2. Resolve the next phase model and reasoning from policy.
3. Classify the delivered run quality and apply `adaptive_model_policy` to the
   next-run target.
4. Update state with next required model/reasoning, run quality, adaptive
   action, model history, and escalation/de-escalation counters.
5. Retarget automation only when `retarget_saved_automation` is `allowed` or
   explicit human approval is already present.
6. Read back automation config.
7. If readback fails or mismatches, mark blocked, write an alert, and do not
   start the next phase.

Do not deliver the next phase in the same run after retargeting.

## Progress And Stall Control

Use a durable progress signature, not narration, to detect repeated
non-progress. Include surfaces such as current phase, status, last delivered
phase, review iteration count, verification result, latest review verdict, git
HEAD, delivery log hash/size, and blocker reason.

When the signature changes, reset `stalled_run_count` to `0`.

When it does not change, increment `stalled_run_count`.

When `stalled_run_count >= max_stalled_runs`, keep or set state blocked, resolve
the `pause_saved_automation` approval decision for the stall context, pause the
automation when policy allows it, and write an operator alert. A pause attempt
is valid only after saved automation readback reports `PAUSED`.

## Blocked Runs

Blocked state is not permission to repeat the same failed phase advancement.
Before incrementing stall count or writing another blocked review, use Blocked
Run Remediation from `troubleshooting.md`.

If the blocker is repaired, record `last_blocker_repair`, clear
`blocked_reason`, reset the stall counter, and resume the current phase.

If the blocker cannot be repaired without human action, keep state blocked and
make the required action explicit.

## Alerts

Always write a local alert file before relying on optional external
notifications. Use:

```text
automation/<roadmap-slug>/alerts/<timestamp>-<kind>.md
```

Initial alert kinds:

- `stalled`
- `completed`
- `blocked`
- `retarget-failed`

Each alert must include enough operator context to act without reopening the
whole run transcript:

- roadmap path
- current phase
- current status
- alert reason
- required and configured model/reasoning when known
- last verification summary
- last review summary
- state, delivery log, and review paths
- next human action

Use `write_operator_alert.py` for deterministic local alerts:

```bash
python3 skill/roadmap-delivery-skill/scripts/write_operator_alert.py \
  --repo-root /path/to/repo \
  --roadmap-slug <roadmap-slug> \
  --kind stalled \
  --reason "Stalled after 2 consecutive runs without durable progress." \
  --json
```

Optional external sinks are conservative:

- `github_issue`: create one tracking issue per roadmap automation when
  credentials and approval are available; append or comment for repeated
  alerts; include state/log/review paths rather than large pasted logs.
- `none`: allowed only for tests and dry runs; the local alert still records
  the event.
- Slack, email, Codex thread, and webhook delivery are future extension
  points until a phase explicitly implements them.

If an external sink fails, preserve the local alert file, record
`notification_status: failed` and the failure reason in `last_operator_alert`,
append the failure to the delivery log, and continue to fail safe to the local
alert file.

## Completion Pause And Alert Flow

Completion uses the same local-alert fallback as blocked and stalled states,
but it is also a delivery hard stop.

When state has `all_phases_complete: true`, `status: completed`,
`status: completed_pending_pause`, or an equivalent completed current phase:

1. Do not extract or start another roadmap phase.
2. Confirm final verification and latest delivered review evidence.
3. Confirm a final deep-review prompt or review artifact is recorded when the
   roadmap requires one.
4. Write a local `completed` alert with `write_operator_alert.py`.
5. Attempt to pause the automation only when the pause surface is already
   approved by `pause_saved_automation`, the context-specific
   `pause_automation_on_completion` flag, or explicit human approval;
   otherwise record that pause is pending and ask the operator.
6. Read back the saved automation status after any pause attempt.
7. Record alert path, notification status, and pause status in state/log.

Inspection should make this state obvious:

- complete and `PAUSED`: no further automation work is expected
- complete and `ACTIVE`: pause is still required, even when the prompt contains
  a hard-stop guard
- complete with no completed alert: repair the local alert before treating
  completion as fully handled
- complete with notification failure: preserve the local alert and surface the
  failed optional sink
