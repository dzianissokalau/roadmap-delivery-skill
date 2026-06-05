# Finalization And Promotion Reference

Use this reference only after all roadmap phases are delivered or when the
operator explicitly requests finalization or promotion.

## Core Contract

Before finalization, confirm every phase is delivered or explicitly deferred,
latest review verdict is `delivered`, required final verification passed, state
and log contain final evidence, no blocker remains, completion alert evidence
exists or is the next required action, runner status has been reviewed, and any
dirty worktree entries are explained.

Phase review artifacts and final deep-review handoff artifacts are distinct.
A phase review covers the current phase diff. A final deep-review prompt or
artifact asks a fresh reviewer to assess the whole roadmap, state/log/review
consistency, verification sufficiency, branch and worktree risk, promotion
readiness, unresolved risks, and whether human merge review can begin.

## Completion Hard Stop

When all phases are complete, do not extract or start another phase. Instead:

1. Confirm final verification and latest delivered review evidence.
2. Confirm a final deep-review prompt or final review artifact exists, or
   record an explicit human waiver.
3. Record `final_deep_review_prompt_prepared`,
   `final_deep_review_prompt_file`, and `final_deep_review_status` as
   `prompt-prepared`, `review-complete`, or `waived-by-human`.
4. Write a completed operator alert before relying on optional notification
   sinks.
5. Set completed state or completed-pending-pause state.
6. Pause the runner when the approval-policy decision for
   `pause_saved_automation` is `allowed`, `pause_automation_on_completion`
   allows the completion safety context, the flag is absent and default
   terminal safety pause applies, or explicit human approval is present, then
   read back the paused runner status.
7. If pause is explicitly disabled or pause tooling/readback is unavailable,
   record the required human pause action.

Completed state is a hard stop for future scheduled runs.

Set `status: completed` only after the completed alert exists and pause
readback reports `PAUSED` when policy allowed an automatic completion pause. If
pause is explicitly disabled or readback is missing, use
`status: completed_pending_pause`, keep the hard-stop guard active, and make
the pause action explicit.

Do not set `all_phases_complete: true` or a completed-pending-pause status
until the final deep-review prompt/artifact exists or the human waiver is
recorded in state and log.

## Final Verification

Run roadmap final checks plus targeted smoke checks for changed workflow,
scripts, schemas, templates, generated packages, and release artifacts. Do not
rely only on older phase verification if final bookkeeping changed shared
behavior.

## Promotion Boundary

Promotion, publication, merging, pushing, release upload, credential use,
installed skill sync, and destructive branch operations are separate protected
actions. A finalization run may prepare evidence, but it must not publish,
promote, or use credentials when the approval-policy decision is `ask`, and it
must record a blocker when the decision is `forbidden`.

## Host Adapter Boundary

The core defines completion gates, alert requirements, pause evidence, and
promotion separation. Host adapters own concrete pause, publication, and runner
status mechanisms.
