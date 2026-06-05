# Automation Prompt Template

Use concrete paths before saving a runner prompt.

```text
Run the next safe phase-gated delivery step for the roadmap recorded in
`automation/<roadmap-slug>/delivery_state.json`. Resolve the current roadmap
path from `delivery_state.json`; the state roadmap field is authoritative
across lifecycle renames.

Read these files before acting:
- `automation/<roadmap-slug>/automation_guide.md`
- `automation/codex_phase_gated_delivery_automation_template.md`
- `automation/<roadmap-slug>/delivery_state.json`
- `automation/<roadmap-slug>/delivery_log.md`
- `automation/<roadmap-slug>/review_fix_state.json`
- `automation/<roadmap-slug>/phase_model_policy.json`
- `automation/<roadmap-slug>/approval_policy.json` when present

Operate on exactly one current phase at a time. Resolve the roadmap from state,
then reconcile roadmap, state, log, review files, phase model policy, approval
policy, branch, worktree status, and saved runner configuration before editing.

Before recording a generic mismatch blocker, handle the normal paused-setup to
active-run transition: if durable setup artifacts still say the saved runner is
PAUSED but saved readback is ACTIVE, and model/reasoning, cwd, state-first
prompt, hard-stop guard, and blocked-remediation guard all match, accept it as
operator/manual activation. Update guide/log/state to ACTIVE, record
`last_activation` and `last_blocker_repair`, reset stalled counters, rerun
validation, and continue the current phase. Do not stop just because the saved
runner is ACTIVE after the operator started it.

Validate approval policy before relying on pre-approved operations. If the
policy is missing, use conservative legacy behavior. If the policy is invalid,
record the blocker and stop before delivery work.

If state is blocked, enter Blocked Remediation Mode before normal delivery.
Hard stop before delivery if all phases are complete, status is completed, or
status is completed_pending_pause. For completed or stalled states, pause the
saved runner when `pause_saved_automation` is allowed, a context-specific
pause flag allows it, explicit human approval is present, or the context flag
is absent and default terminal safety pause applies; generated policies allow
completion and stalled-run safety pauses by default. Always record pause
readback evidence.

For the current phase only, extract objective, owned files, implementation
steps, acceptance criteria, required verification, non-goals, and stop
conditions. Create or reuse the correct phase branch when implementation work
is required. Verify saved runner model and reasoning against policy before
delivery. Make only phase-scoped changes, run required verification, update
state/log, write a fresh review, and advance only after the review verdict is
delivered.

Do not push or edit runner configuration unless a valid approval policy
explicitly allows the operation and readback evidence matches, except for the
narrow status-only completion/stall self-pause described above. Do not merge,
promote, delete branches, install global packages, or run destructive commands
without explicit human approval; approval modes never cover never-auto
operations.
After advancing state to the next phase, stop.
```
