# Troubleshooting Reference

Use this reference when roadmap, state, log, automation config, branch, or
verification evidence disagree.

## Blocked Run Remediation

A blocked run should not loop forever by trying the same phase advancement
again. On the next run, handle `status: blocked` as a remediation gate:

1. Read the latest `blocked_reason`, failed verification, review findings, and
   automation readback.
2. Classify the blocker as:
   - `local-repairable`
   - `automation-config`
   - `permission-gated`
   - `external-decision`
   - `destructive-risk`
3. Repair `local-repairable` blockers when they are current-phase bookkeeping,
   stale paths, missing generated artifacts, branch drift, or malformed
   state/log entries.
4. Repair `automation-config` blockers only when the approval-policy decision
   is `allowed` or explicit human approval is already present.
5. Rerun validation/readback after repair.
6. If repair passes, record `last_blocker_repair`, clear `blocked_reason`,
   reset stalled counters when progress is real, and resume the current phase.
7. If repair needs credentials, a product decision, destructive git, broad
   publication, an approval-policy decision of `ask`, or a `forbidden`
   operation, keep state blocked and ask for the missing action or record the
   blocker.

Do not write another blocked review for the same issue until this remediation
classification has been attempted.

For network-disabled blockers, read `network-blocker-remediation.md` before
stopping. A host environment flag may not prove that all network surfaces are
unusable; direct terminal probes can sometimes provide an approved,
artifact-backed repair path for public unauthenticated source recovery.

Lifecycle-only prompt drift is not an automation-config blocker when the saved
automation prompt is state-first: it references stable automation artifacts,
requires reading `delivery_state.json`, and says the roadmap path recorded in
state is authoritative. In that case, repair the lifecycle filename and
repository-local references without requiring a saved automation prompt edit.

## Approval Policy Problems

Missing `approval_policy.json` keeps conservative legacy behavior: phase-owned
edits, state/log/review writes, phase branch creation, and verification can
proceed, while local commits, automation retarget, automation pause, branch
push, installed-skill sync, publication, promotion, credential use, and
destructive git must pass the approval gate.

Invalid approval policy is a blocker before relying on pre-approval. Record the
policy error in state/log/review, use conservative fallback only for reporting,
and stop before any operation that required the invalid policy.

Forbidden operations produce clear blocker messages, not prompts to bypass the
policy. Never-auto operations stay `forbidden` in conservative,
delegated-local, delegated-delivery, and custom modes.

## Automation Worktree Missing Local Phase Artifacts

Symptoms:

- scheduled runs start in `.codex/worktrees/...` at a detached or old commit
- the saved repository checkout has the phase branch and artifacts
- the active run cannot check out the phase branch because it is already used
  by the saved checkout

Repair options:

- switch the automation to local execution when the phase branch is intentionally
  local and unpublished
- push/publish the required branch only when the operator explicitly approves
  publication
- create a separate worktree branch only when branch ownership is clear

After repair, read back automation config, rerun artifact validation, and record
the repair before phase delivery resumes.

## Model Policy Problems

Missing policy file:

- If the roadmap requires model policy, record a blocker and do not deliver.
- If the roadmap is legacy or policy-optional, continue legacy behavior and
  record that no policy was present.

Invalid policy file:

- Record the parse or schema error.
- Do not infer model requirements from malformed JSON.
- Repair only when the current phase owns policy setup or the operator approves
  the repair.

Current automation model mismatch:

- Do not start phase implementation.
- Record required and configured model/reasoning.
- Retarget the automation only when `retarget_saved_automation` resolves to
  `allowed` or explicit human approval is already present.
- Read back the saved config and stop so the next run starts on the correct
  model.

Retarget update failure:

- Record the delivered phase, next phase, required model/reasoning,
  configured model/reasoning, attempted update surface, and readback result.
- Keep or set state blocked with `blocked_reason` explaining the failed
  retarget.
- Write or request a `retarget-failed` alert before relying on any optional
  notification sink.
- Do not advance to, or start delivery for, the next phase.
- If the update failed because approval was unavailable, classify it as
  `permission-gated` or `external-decision` rather than retrying automatically.
- If the update was approved but readback still mismatches, treat it as an
  automation-config blocker and require a fresh readback before resuming.

To diagnose without mutating files, run:

```bash
python3 skill/roadmap-delivery-skill/scripts/plan_automation_retarget.py \
  --repo-root <repo-root> \
  --roadmap-slug <roadmap-slug> \
  --automation-id <automation-id> \
  --delivered-phase "Phase N - Name" \
  --json
```

Repeated non-progress:

- Compute or inspect the durable progress signature.
- If the signature is unchanged, increment `stalled_run_count`.
- At `max_stalled_runs`, keep state blocked, resolve the stall pause approval
  decision, pause or request pause, and write a stalled alert with
  `write_operator_alert.py`.
- Before counting another stall, run Blocked Run Remediation for any explicit
  blocker.

## Operator Alert Problems

Alert files are the durable fallback for stalled, completed, blocked, and
retarget-failed automation states. Always write the local alert before relying
on optional notification sinks.

If `last_operator_alert.file` is missing:

- keep or set state blocked when the alert was required for a blocker
- rerun `write_operator_alert.py` with the same alert kind and reason
- rerun artifact validation
- record the repaired alert path in the delivery log

If an optional notification sink fails:

- do not delete or rewrite the local alert file
- record `notification_status: failed` and the failure reason in
  `last_operator_alert`
- append the notification failure to `delivery_log.md`
- classify missing credentials or unavailable approval as
  `permission-gated`

If alert content would expose secrets or sensitive private paths to an external
sink, do not send the external notification. Keep the local alert, record the
redaction concern, and ask for operator approval before sending anything
outside the repository.

## Automation Saved ACTIVE Despite Requested PAUSED

Read back the saved automation config. If it is active and the setup contract
required paused:

- if operator/manual activation is clear and ACTIVE is the only drift, accept
  the active state instead of blocking delivery
- require model/reasoning, prompt path, cwd, hard-stop guard, and
  blocked-remediation guard to read back cleanly before accepting ACTIVE
- update `automation_guide.md`, `delivery_log.md`, and `delivery_state.json`
  so durable artifacts agree with ACTIVE
- record `last_activation` and `last_blocker_repair`, clear
  `blocked_reason` only after validation/readback passes, reset stalled
  counters, and resume the current phase
- pause only if the user wants PAUSED or if ACTIVE was not an intentional
  operator action
- if any other automation field mismatches, keep state blocked and ask for the
  missing runner repair or operator decision

## Status-Only Automation Update Rejected

Record:

- attempted update
- app/tool error
- current saved status
- safest manual next step

Do not edit unrelated automation fields to sneak in a status change.

## Stale Roadmap Path After Lifecycle Rename

Symptoms:

- roadmap header is active, or current phase is Phase 1+, while the file still
  starts with `not_started_`
- roadmap moved from draft/in-progress to delivered filename
- state still points to old path
- automation prompt still references old path

Repair only after confirming the intended current roadmap file and lifecycle
state. Update the roadmap filename, state, guide, log, reviews, and run-log
bookkeeping together, then rerun validation or status inspection.

If the saved automation prompt is state-first and still references stable
automation artifacts, a saved prompt retarget is not required for lifecycle-only
path changes. Treat any old lifecycle path in the prompt as historical context
as long as the prompt tells the agent to resolve the current roadmap path from
`delivery_state.json`.

If the saved automation prompt hardcodes the lifecycle roadmap path and lacks
the state-resolved guard, update the automation prompt only when app automation
edits are approved. If approval is unavailable, keep state blocked and ask.

## Completed State But Automation Still ACTIVE

If state says the roadmap is complete and the automation is active:

- do not start a new phase
- verify the saved prompt has a completed-state hard-stop guard
- confirm a `completed` alert file exists and includes enough operator context
- record a pause-required warning in state/log or inspection output
- perform the terminal status-only self-pause when the completion context flag
  allows it or is absent and default terminal safety pause applies
- ask whether to pause the automation only when the pause flag is explicitly
  disabled or pause tooling/readback is unavailable
- preserve final verification evidence

An active automation with a completed-state hard-stop guard is safer than one
without the guard, but it is still not fully closed out. Pause remains the next
operator action.

If policy allowed a completion or stall pause but saved automation readback is
not `PAUSED`, classify the issue as an automation-config blocker. Keep or set
`completed_pending_pause` for completion closeout, keep the local alert, and
ask for the smallest runner repair or pause approval needed. Do not convert the
state to `completed` until readback proves the automation is paused.

## Completed State Missing Completed Alert

If a completed roadmap has no `last_operator_alert` or the last alert kind is
not `completed`:

- do not start phase work
- run `write_operator_alert.py --kind completed` with the completion reason and
  next human action
- rerun artifact validation
- record the repaired alert path in the delivery log

If the recorded completed alert file is missing, regenerate the local alert
before relying on optional notification sinks.

## Completed Notification Failure

If a completion notification sink fails:

- preserve the local completed alert file
- keep `notification_status: failed` and record `notification_failure`
- ask for credentials or approval only if the operator still wants the external
  notification sent
- continue to treat local alert plus pause handling as the durable completion
  record

## User Confusion Between Roadmaps

When a request names a roadmap vaguely:

- list candidate roadmap paths and automation ids
- identify current phase/status for each
- ask only if local evidence cannot disambiguate safely

Do not operate on the most recent roadmap merely because it appears first.

## Review Finds Medium Gaps After Delivery

If gaps are valid and in current phase scope, set status to `fixing`, patch
only that scope, rerun verification, and write a new review. If gaps belong to
a future phase, record residual risk and keep the current verdict grounded in
the current acceptance criteria.

## Dirty Worktree With Unrelated Files

Use path-specific diffs to separate owned files from unrelated work. Continue
only if unrelated changes do not affect phase verification. Never clean or
restore unrelated files without explicit instruction.

## Branch Exists With Unexpected Base

Stop when a phase branch exists but its base or contents are unexplained.
Record:

- expected branch name
- current branch
- relevant commit summary
- dirty files
- needed human decision

Do not recreate, delete, or rewrite the branch unless explicitly approved.

## Verification Cannot Run

Classify the failure:

- missing dependency
- sandbox permission
- network restriction
- command missing
- phase implementation failure
- ambiguous expected result

Retry with the narrowest approved escalation only when the workflow permits it.
If verification still cannot run, mark blocked with the exact command and
reason.

## Roadmap/State Current Phase Mismatch

If roadmap and state disagree:

- inspect delivery log for the last phase advancement
- inspect latest review verdict
- inspect branch and dirty files
- prefer the last fully recorded phase gate
- if still ambiguous, record blocker and stop

Never advance based only on one surface.

## Artifact Validator Reports Errors

Run the validator before delivering when the durable surfaces may disagree:

```bash
python3 $CODEX_HOME/skills/roadmap-delivery-skill/scripts/validate_delivery_artifacts.py \
  --repo-root /path/to/repo \
  --roadmap-slug <roadmap-slug> \
  --automation-id <automation-id> \
  --json
```

Treat `errors` as blockers. Record the exact code and message in state/log, then
stop unless the current phase explicitly owns the repair. Common blocking codes:

- `missing_state_file` or `invalid_state_json`: state cannot be trusted.
- `missing_delivery_log` or `missing_review_dir`: phase history is incomplete.
- `missing_roadmap_file`: state points at a roadmap that cannot be read.
- `current_phase_mismatch`: roadmap and state select different active phases.
- `completed_state_active_automation`: completed state would keep running
  without a hard-stop guard.
- `invalid_review_verdict`: review evidence cannot support phase advancement.

Treat `warnings` as explicit reconciliation work, not automatic failure. Stale
automation roadmap paths, missing hard-stop guard text, missing deep-review
prompt paths in older completed automations, branch mismatch, and dirty worktree
warnings should be explained in the delivery log before continuing.

Do not use the validator to auto-repair artifacts. Repairs still follow the
phase-gated workflow and require current-phase scope or explicit operator
approval.

## Phase-Gated Repair Procedure

Use this procedure when repair is explicitly requested or when the current
phase owns the affected artifacts.

1. Read roadmap, delivery state, delivery log, review/fix state, latest review
   file, automation config, branch, and worktree status.
2. Run `validate_delivery_artifacts.py` when available.
3. Classify each issue as blocking `error`, non-blocking `warning`, or
   unrelated user work.
4. Repair only artifacts in current-phase scope unless the operator explicitly
   approves a broader repair.
5. Rerun validation and targeted readback.
6. Record the repair, verification, residual risks, and next action in
   state/log/review.

Do not use repair as a shortcut around the normal phase gate.

## Stale Prompt Path Repair

Repair stale roadmap prompt references only after confirming the current
roadmap path from durable state and the actual roadmap file.

- If the saved prompt resolves the current roadmap path from
  `delivery_state.json`, do not retarget it for lifecycle-only filename
  changes.
- If the saved prompt hardcodes the old lifecycle roadmap path and lacks the
  state-resolved guard, update the automation prompt reference to the current
  roadmap path only when app automation edits are approved.
- Keep the automation artifact directory unchanged unless the slug changed.
- Update state/log/guide references together when repository artifacts are
  stale.
- Read back the saved automation config after any app-level update.
- Rerun `validate_delivery_artifacts.py`.

If the app update is rejected or requires approval that is not available,
record the exact stale path, current path, and safest manual next step.

## Activation Refusal Rules

Refuse activation when any of these are true:

- artifact validation reports one or more `errors`.
- state says all phases are complete.
- state status is `blocked` and the blocker has not been fixed.
- roadmap and state disagree on the current phase.
- automation prompt still points at a stale roadmap path and does not resolve
  the authoritative current path from `delivery_state.json`.
- direct config edits would be required without explicit approval.

Report the exact validation code or file mismatch that caused the refusal.

## Pause Rules

Pause, or ask for approval to pause, in these cases:

- all phases are complete and final evidence has been recorded.
- the run is blocked by product decision, credentials, or verification
  environment.
- max review iterations have been reached.
- completed state is detected while automation remains active.

When pause approval is unavailable, record that the automation should be
paused and stop without starting new delivery work.

## Known Failure Mode Coverage

The troubleshooting surface must cover these known modes:

- automation saved `ACTIVE` despite a requested `PAUSED` setup.
- status-only automation update rejected.
- stale roadmap path after lifecycle rename.
- completed state but automation still `ACTIVE`.
- user confusion between similarly named roadmaps.
- review finds medium gaps after delivery.
- dirty worktree with unrelated files.
- branch exists with unexpected base.
- verification cannot run.
- roadmap/state current phase mismatch.
- repository layout mismatch between `roadmaps/automation/<slug>` and
  `automation/<slug>`.
- artifact validator reports blocking errors.
- activation requested while validation errors remain.
- blocked run repeats without remediation classification.
- automation worktree is missing local-only phase artifacts.

## Repository Layout Mismatch

Some roadmap repositories store automation artifacts under
`roadmaps/automation/<slug>/`, while newer roadmap-delivery workspaces may use
`automation/<slug>/` at the repository root.

When status inspection reports a missing state file:

- check both candidate layouts before treating the state as missing
- prefer the state file that exists and matches the requested `roadmap_slug`
- record a warning only when neither layout exists or the found state disagrees
  with the requested slug
- add a fixture test when a new repository layout is observed

Do not move existing automation artifacts just to normalize layout. Layout
repair is only safe when the roadmap explicitly owns that migration or the
operator approves it.
