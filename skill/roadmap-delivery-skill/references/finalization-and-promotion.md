# Finalization And Promotion Reference

Use this reference only after all roadmap phases are delivered or when the user
explicitly asks for finalization or promotion.

## All Phases Complete Checklist

Before finalization:

- roadmap shows every phase delivered or explicitly deferred by human decision
- delivery state has no current in-progress phase
- latest review verdict is `delivered`
- required final verification passed
- delivery log contains the final verification evidence
- completed alert file has been written or is the next required action
- no unresolved blocker remains
- automation status has been reviewed
- dirty worktree is explained

The phase review artifact and final deep-review prompt are separate
deliverables. A phase review checks the just-delivered phase diff. The final
deep-review prompt hands the complete roadmap to another LLM or fresh reviewer
for whole-roadmap acceptance and promotion readiness.

## Final Verification

Run the roadmap's final checks plus targeted smoke checks for changed helper
scripts and references. Do not rely on phase-level evidence alone if later
bookkeeping or repair changed shared workflow behavior.

## Finalization Model Policy

Before entering finalization, resolve the `finalization` entry in
`phase_model_policy.json` when the roadmap has a model policy. If the entry is
missing, use policy defaults and record that fallback in the delivery log.

If the saved automation config already matches the finalization model and
reasoning effort, record the readback and continue the finalization checklist.
If it does not match, retarget only when `retarget_saved_automation` resolves
to `allowed` or explicit human approval is already present, read back the saved
config, and stop so finalization starts in a fresh run with the right model.

If retargeting or readback fails, do not mark the roadmap complete. Keep or set
state to `blocked`, write or request a `retarget-failed` alert, and preserve
the last delivered phase evidence for the next operator action.

## Final Deep Review Prompt

A final deep-review prompt is required before completion unless the human
operator explicitly waives it. It should ask for:

- roadmap acceptance against all phases
- state/log/review consistency
- verification sufficiency
- branch and worktree risk
- promotion readiness
- explicit list of unresolved risks
- verdict on whether human merge review can begin

Store the prompt or review artifact under the roadmap automation directory.
Record these fields in `delivery_state.json` before setting completion:

- `final_deep_review_prompt_prepared`: `true` when a prompt/artifact exists
- `final_deep_review_prompt_file`: path to the prompt or final review artifact
- `final_deep_review_status`: `prompt-prepared`, `review-complete`, or
  `waived-by-human`
- `final_deep_review_waiver_reason`: required when status is
  `waived-by-human`

Do not treat a same-context phase review as this artifact. If the prompt or
review artifact is not prepared and no human waiver is recorded in both state
and log, finalization is blocked.

## Completion Hard Stop

When all roadmap phases are complete, treat completion as a stop state before
any further delivery extraction:

1. Confirm final verification passed.
2. Confirm the latest review verdict is `delivered`.
3. Confirm a final deep-review prompt/review artifact exists, or record an
   explicit human waiver.
4. Record the final deep-review state fields.
5. Confirm publication or final branch push is `allowed` by approval policy or
   explicitly approved before attempting it.
6. Set `all_phases_complete` or an equivalent completed status in state.
7. Write a `completed` operator alert before any optional notification sink.
8. Pause the automation when `pause_saved_automation` is `allowed`,
   `pause_automation_on_completion` allows the completion safety context, the
   flag is absent and default terminal safety pause applies, or the pause is
   explicitly approved, then read back status.
9. If pause is explicitly disabled or tooling/readback is unavailable, record
   `completed_pending_pause`, keep the hard-stop guard active, and ask the
   operator to pause the automation.

Do not set `all_phases_complete: true`, `status: completed`, or
`status: completed_pending_pause` before the final deep-review prompt/review
artifact or waiver is recorded. Validation treats that as a closeout blocker.

Completed state must not start another phase. A later run that sees completed
state should only verify the pause/alert evidence or ask for the missing pause
action.

Set `status: completed` only after completed alert evidence exists and pause
readback reports `PAUSED` when policy allowed an automatic completion pause. If
pause is explicitly disabled or readback is missing, use
`status: completed_pending_pause`, keep the hard-stop guard active, and make
the pause action explicit.

## Final Branch

Use a clearly named local branch, for example:

```text
codex/<roadmap-slug>-finalization
```

Do not combine finalization with an unrelated feature branch.

## Final Bookkeeping Commit

If the operator wants a local commit, include only:

- roadmap final status updates
- delivery state/log updates
- review artifacts
- phase-owned files already delivered

Stage files by explicit path. Do not stage the whole worktree.

## Publication Rules

Publishing a branch requires `push_current_phase_branch` or the publication
operation to resolve to `allowed`, or explicit human approval in the current
conversation. Publication, promotion, credential use, installed-skill sync, and
destructive git remain `forbidden` when they match never-auto operations.
Before publication, confirm:

- branch name
- remote
- files included
- verification result
- whether the branch should be draft/review-only

Do not publish directly to `main`.

## Automation Pause Procedure

When the roadmap is complete or blocked on a human decision:

1. Read back the saved automation config.
2. Write the required local operator alert for the terminal state.
3. Pause through the available app/tooling when terminal self-pause is allowed
   by `pause_saved_automation`, the context flag, default terminal safety
   policy, or explicit approval.
4. If pause is explicitly disabled, record the operator's chosen non-paused
   terminal state instead of editing the automation.
5. Read back status.
6. Record the alert file, pause result, and any notification failure in
   delivery state and log.

If status-only update is rejected by the app, record the rejection and give the
operator the exact safe next step.

## Separate Promotion Flow

Promotion to `main` is separate from delivery finalization. It requires:

- explicit human approval in the current conversation
- clean final verification
- human review readiness
- no unexplained dirty files
- a fast-forward-only path from the final branch to `main`

If fast-forward-only promotion is not possible, stop and ask. Do not rewrite
history or merge around the guard without explicit approval.

## Pause Rules Before Final Response

When all roadmap phases are complete, or when delivery is blocked on a human
decision, pause handling must be addressed before the final response.

- Read back the saved automation status.
- If complete, write or confirm the `completed` alert file before optional
  external notification.
- If complete and active, ask for approval to pause or use the `allowed` pause
  flow. Do not continue delivery work while waiting.
- If blocked by product decision, credentials, verification environment, or max
  review iterations, recommend pause and record the reason.
- If the operator declines or approval is unavailable, record that the
  automation remains active, set or preserve a completed-pending-pause marker,
  and make the next human pause action explicit.

Do not claim operational closeout is complete until the pause decision and
readback result are recorded. If the automation is still active, the hard-stop
guard is the safety backstop, not a substitute for pause completion.

## Activation Is Not Promotion

Activation resumes scheduled delivery. Promotion publishes or merges delivered
work. Treat them as separate approvals:

- activation requires no artifact validation errors and a non-complete state.
- promotion requires final verification, human review readiness, and a
  fast-forward-only path to `main`.
- neither activation nor promotion may be inferred from a request to
  "finalize" or "clean up" unless the operator explicitly says so.

If validation reports blocking errors, refuse activation and promotion until
the errors are repaired and recorded through the phase-gated workflow.
