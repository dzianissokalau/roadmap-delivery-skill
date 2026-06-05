# Autonomy And Approval Policy

Roadmap delivery automation can do local delivery work without weakening the
human approval boundary for publication, destructive changes, credentials, or
repository administration. This policy defines the durable contract that later
schemas, setup UX, validation, and runtime gates must implement.

The compatibility baseline is conservative. Existing automations without an
approval policy behave as if `conservative` is selected.

## Approval Modes

Approval mode is per roadmap automation. The selected mode must be stored in a
repository artifact, echoed in delivery state, and validated before any
automatic action relies on it.

| Mode | Intent | Allowed without new approval |
|---|---|---|
| `conservative` | Preserve current behavior. | Edit phase-owned files, write local state/log/review artifacts, create or switch the current phase branch, run verification, and perform terminal status-only self-pause by default. Ask before runner retargets, ordinary automation config edits, pushes, commits if not explicitly enabled, publication, promotion, installed-skill sync, external side effects, or destructive git. |
| `delegated_local` | Let the automation finish local delivery loops. | Everything in `conservative`, plus local commits for delivered phase-owned changes when state enables local commits, saved automation retargeting for model/reasoning when policy and readback agree, and saved automation pause on completion or stall threshold. |
| `delegated_delivery` | Allow routine branch publication while preserving high-risk approval gates. | Everything in `delegated_local`, plus pushing the current phase branch when the branch name, remote, and policy match, and updating saved automation config fields already covered by policy. |
| `custom` | Explicit operation map. | Only operations set to allow in the durable custom policy. Missing entries default to deny. |

An implementation must treat mode names as policy identifiers, not as prompt
advice. If the stored policy is missing, malformed, or not validated, fall back
to `conservative` and record the reason.

## Choosing A Mode

Choose the lowest mode that covers the operation you want the automation to do
without another prompt:

| Need | Mode to start with | Why |
|---|---|---|
| Local phase edits and verification only | `conservative` | This is the legacy fallback and keeps saved automation config, commits, pushes, and retarget operations ask-first while allowing terminal status-only self-pause by default. |
| Unattended local delivery and closeout | `delegated_local` | Allows local commits, saved model/reasoning retargets, and completion or stall pauses when readback proves the result. |
| Routine phase branch publication | `delegated_delivery` | Adds current phase branch push approval while keeping promotion, release publication, and destructive operations forbidden. |
| A narrower exception set | `custom` | Every allowed operation is named explicitly; missing entries stay denied. |

Review `examples/autonomy-controls/approval-policy-examples.json` before
switching an existing automation. For existing roadmaps, migrate through
`conservative` first so validation can prove the effective policy before any
delegated operation is enabled.

## Operation Boundary

The following operations can be pre-approved by mode or custom policy when the
operation is phase-scoped and every readback check passes:

| Operation | Conservative | Delegated local | Delegated delivery | Required evidence |
|---|---:|---:|---:|---|
| Edit phase-owned files | yes | yes | yes | Roadmap phase owns the path. |
| Write state, logs, reviews, alerts | yes | yes | yes | Artifact path is under the current automation directory. |
| Create or switch current phase branch | yes | yes | yes | Branch name is `codex/<roadmap-slug>-phase-<n>`. |
| Run verification | yes | yes | yes | Command is roadmap-required or targeted to changed behavior. |
| Commit delivered phase locally | ask unless state enables | yes | yes | Only phase-owned files and bookkeeping are staged by explicit path. |
| Retarget saved automation model/reasoning | ask | yes | yes | Required model/reasoning come from policy and saved config reads back matching values. |
| Pause saved automation on completion or stall | yes unless explicit flag disables it | yes | yes | Completion or stall state is recorded, only status is changed, and pause readback confirms `PAUSED`. |
| Push current phase branch | ask | ask | yes | Remote, branch name, and push policy match; no force push. |

Pre-approval never removes the requirement to record evidence. State, delivery
log, review output, and inspection reports must show what was done and which
policy allowed it.

## Never-Auto Operations

These operations require explicit human approval every time, in every mode:

```text
force push
git reset --hard
delete branches or tags
merge or promote to main
publish releases or package registry artifacts
use credentials not already available to the runner
change repository visibility, secrets, permissions, or billing
install or sync global tools outside the approved scope
perform destructive filesystem operations outside phase-owned paths
```

If a phase appears to require a never-auto operation, the automation must stop,
set or keep the state blocked, classify the blocker, and ask for the missing
human action. It must not infer approval from mode name, cadence, or prior
successful delivery.

## Adaptive Model Policy

Adaptive model policy reacts to run quality by changing the next run through
the runner or saved automation config. Prompt text alone does not change the
active model.

Run quality classifications:

| Classification | Meaning | Default next-run behavior |
|---|---|---|
| `flawless` | Phase delivered with required verification and delivered review, with no fixes. | Keep current model/reasoning. Optional de-escalation can occur only after a configured streak and within policy floors. |
| `delivered_with_fixes` | Review or verification found current-phase issues that were fixed before delivery. | Escalate within policy caps or keep current settings if already at cap. |
| `verification_failed` | Required verification failed because of a phase bug. | Escalate within policy caps after recording failed command evidence. |
| `review_needs_fix` | Fresh review verdict was `needs-fix`. | Escalate within policy caps if the run stops unresolved or after fixes are delivered. |
| `blocked_local_repairable` | A stale path, branch drift, malformed bookkeeping, or generated artifact issue can be repaired locally. | Repair first when allowed; escalation is optional and should be policy-driven. |
| `blocked_human_required` | Credentials, product decision, publication, destructive git, or unapproved config mutation is required. | Do not escalate for quality. Ask for the human action. |
| `stalled` | Durable progress signature repeats until the stall threshold is reached. | Pause or request pause, write an alert, and escalate only if policy says a better model can resolve local non-progress. |
| `retarget_failed` | Required next-run model/reasoning update failed or readback mismatched. | Keep blocked, write an alert, and ask for repair or approval. |
| `completion_closeout_failed` | Completion alert, pause, or final closeout could not be verified. | Keep blocked or completed-pending-pause and ask for the missing action. |

Adaptive policy must define caps for model, reasoning effort, provider, and
cost class. It must also define floors before any de-escalation is allowed.
When policy and saved config disagree, delivery stops before implementation.

## Self-Pause Policy

Self-pause is a safety operation. It prevents completed or stalled automations
from continuing to consume runs after there is no safe phase work to perform.

Self-pause is allowed only when all of these are true:

1. The durable state is `completed`, `completed_pending_pause`, or blocked by a
   stall threshold that policy says should pause.
2. The selected approval mode or custom policy allows pause for that condition,
   the context-specific pause flag is absent and default terminal safety pause
   applies, or the operator explicitly approves the pause.
3. A local alert file has been written with the reason and next human action.
4. The saved automation config is updated only for the pause operation.
5. Readback confirms `status = "PAUSED"` and the result is recorded in state,
   delivery log, and inspection output.

If readback fails or still shows `ACTIVE`, the automation must keep durable
evidence of the failed closeout and stop. It must not start a new phase while
completion or stall pause handling is unresolved.

## Example Artifacts

The repository includes offline examples that can be inspected without
credentials or live automation access:

- `examples/autonomy-controls/approval-policy-examples.json` compares
  conservative, delegated local, delegated delivery, and custom policies.
- `examples/autonomy-controls/adaptive-escalation-trace.json` shows a
  non-flawless run escalating the next run within policy caps.
- `examples/autonomy-controls/completion-self-pause-state.json` shows completed
  state with a completed alert and `PAUSED` readback.
- `examples/autonomy-controls/stall-self-pause-run-log.jsonl` shows the audit
  line for stall-threshold pause handling.
- `examples/demo-roadmap/scenarios/delegated-local/approval_policy.json` can be
  copied into the demo fixture to inspect delegated local decisions.

## Implementation Notes

Schemas, validators, inspectors, setup output, adapter packages, and helper
scripts consume the durable JSON artifacts directly. They must not parse prose
from this document as policy.
