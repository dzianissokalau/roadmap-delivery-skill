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
6. Resolve completion pause through the shared runtime and the precedence in
   `model-policy-and-stall-control.md`. Default terminal safety pause applies;
   an explicit false context flag overrides broad pause permission. Use supported
   host tooling, preserve other settings and read back PAUSED.
7. Record `disabled`, `not_applicable`, unavailable capability or a concrete
   pending action accurately. Do not request the same pause authority again.

Completed state is a hard stop for future scheduled runs.

For an external host tool, execute each non-null `action_request` once, using
its returned `external_attempt`. Persist the tool outcome in a JSON object
with `request_id`, `attempt`, `status` and nonempty `source`, then pass it to
`terminal-closeout --external-outcome outcome.json` with fresh
`--runner-snapshot` evidence. Status is `acknowledged`, `transient_failure`,
`permission_required`, `unsupported` or confirmed `not_executed`. An
acknowledgement is not PAUSED proof. Inspection does not reissue an outstanding
request; duplicate outcomes cannot allocate retries. After an interruption,
reconcile the original tool result instead of executing the stored request again.
The persisted attempt limit also covers abandoned reservations.

A damaged local alert must not prevent an authorized safety pause. Repair the
owned alert or record its specific failure, retaining completed-pending-pause
until alert evidence is available. Final reviews need one unambiguous actual
verdict; quoted historical verdicts and fenced examples cannot authorize completion.

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
