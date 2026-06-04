# Codex Phase-Gated Delivery Automation Template

Status: Project template
Created: 2026-05-20

## Purpose

Use this template to run Codex against a phased roadmap with a controlled
deliver-review-fix loop.

The automation should:

```text
read the selected roadmap
deliver exactly one phase
verify the result
review the delivered diff or artifacts in a fresh context
route review findings back for fixes
repeat until clean or blocked
repair resolvable blockers before retrying delivery
advance only after a clean phase gate
```

## Canonical Core Sources

This template is the Codex-facing automation template. Host-neutral workflow
sources live under:

```text
core/references/
core/templates/
core/prompts/
```

Codex skill reference files under `skill/roadmap-delivery-skill/references/`
must either have a matching canonical source in `core/references/` or an
explicit adapter-only reason covered by tests. The Codex package remains the
installable snapshot until adapter generation is introduced by a later phase.

## Project Defaults

```text
ROADMAP_SLUG=<short lowercase slug>
PHASE_N=<current phase number or label>
STATE_FILE=automation/<roadmap_slug>/delivery_state.json
DELIVERY_LOG=automation/<roadmap_slug>/delivery_log.md
REVIEW_DIR=automation/<roadmap_slug>/reviews
MAX_REVIEW_ITERATIONS=3
MAX_STALLED_RUNS=3
CADENCE=manual until the roadmap is review-clean
```

If this workspace is initialized as a git repository later, add:

```text
BRANCH_PREFIX=codex/
BRANCH_NAME=codex/<roadmap-slug>-phase-<phase-n>
```

Until then, keep `branch` nullable in state and rely on file-backed state,
append-only logs, and fresh review artifacts.

## Core Rule

Codex may implement, test, review, and fix within the current phase.

Codex must not advance to the next phase unless all of these are true:

```text
[ ] current phase acceptance criteria are satisfied
[ ] required verification passed
[ ] fresh reviewer verdict is delivered
[ ] roadmap status is updated
[ ] delivery log is updated
[ ] delivery state is updated
```

## State Files

Recommended files:

```text
automation/<roadmap_slug>/delivery_state.json
automation/<roadmap_slug>/delivery_log.md
automation/<roadmap_slug>/review_fix_state.json
automation/<roadmap_slug>/review_fix_log.md
automation/<roadmap_slug>/reviews/<roadmap_slug>-phase-<phase-n>-review-iteration-<m>.md
```

Suggested state:

```json
{
  "schema_version": 1,
  "roadmap": "<path to the roadmap markdown file>",
  "roadmap_slug": "ROADMAP_SLUG",
  "current_phase": "PHASE_N",
  "branch": null,
  "status": "not_started",
  "review_iterations": 0,
  "max_review_iterations": 3,
  "last_verification": null,
  "last_review": null,
  "blocked_reason": null,
  "last_blocker_repair": null,
  "run_count": 0,
  "stalled_run_count": 0,
  "max_stalled_runs": 3,
  "last_progress_signature": null,
  "last_progress_at": null,
  "updated_at": null
}
```

Suggested statuses:

```text
not_started
delivering
verifying
reviewing
fixing
delivered
blocked
```

`blocked` is a remediation state, not a retry loop. The next run must classify
and repair local or already-authorized automation blockers before attempting
normal phase advancement again.

## Delivery Log

The delivery log should be concise and append-only.

Suggested entry format:

```markdown
## Phase PHASE_N - YYYY-MM-DD - Delivery Pass M

Status: delivering | reviewing | fixing | delivered | blocked
Branch: `BRANCH_NAME` or `not available`

### Scope

- ...

### Changes

- ...

### Tests And Verification

- `command`: passed | failed | not run

### Review

- Review file: `automation/.../reviews/...`
- Verdict: delivered | needs-fix | blocked | pending

### Residual Risks

- ...

### Next Action

- ...
```

## Delivery Agent Prompt

```text
Deliver Phase PHASE_N of the roadmap recorded in DELIVERY_STATE.

Use this phase-gated delivery template:
automation/codex_phase_gated_delivery_automation_template.md

Work only on Phase PHASE_N. Do not start the next phase.

Before editing:
- Read DELIVERY_STATE and resolve the current roadmap path from its `roadmap`
  field.
- Extract the phase scope.
- Extract acceptance criteria.
- Identify non-goals.
- Identify implementation slices.
- Identify required tests and verification commands.
- If DELIVERY_STATE has `status: blocked`, enter Blocked Remediation Mode
  before normal phase delivery.
- If blocked only because a lifecycle rename would otherwise require a saved
  automation prompt edit, continue with local lifecycle repair when the saved
  prompt resolves the roadmap from DELIVERY_STATE. Require saved prompt retarget
  approval only when the prompt hardcodes the old lifecycle path and lacks the
  state-resolved guard.

Blocked Remediation Mode:
- classify the blocker as local-repairable, automation-config,
  permission-gated, external-decision, or destructive-risk
- before recording a generic automation status blocker, check the normal
  paused-setup to active-run transition; if durable setup artifacts still say
  PAUSED but saved readback is ACTIVE and model/reasoning, cwd, state-first
  prompt, hard-stop guard, and blocked-remediation guard all match, accept it
  immediately as operator/manual activation rather than forcing one blocked
  run
- repair local-repairable blockers and already-authorized automation-config
  blockers before retrying phase delivery
- if setup expected PAUSED but saved automation now reads ACTIVE, accept that
  as operator/manual activation when it is the only drift and model/reasoning,
  prompt path, cwd, hard-stop guard, and blocked-remediation guard all match;
  then record `last_activation` and `last_blocker_repair`, update durable
  status surfaces to ACTIVE, clear `blocked_reason` after validation, and
  resume the current phase
- rerun reconciliation and validation after repair
- clear `blocked_reason` only after the repair is verified
- keep state blocked and ask for the missing human action when credentials,
  product decisions, destructive git, publication, promotion, or unapproved
  automation edits are required
- do not write another blocked review for the same issue until remediation has
  been attempted

During delivery:
- Keep changes scoped to this phase.
- Preserve unrelated user changes.
- Add or update tests for behavior changed.
- Update DELIVERY_LOG with scope, changes, tests, known gaps, and next action.

Verification:
- Run the roadmap's required verification commands.
- Run targeted tests for changed behavior.
- If verification cannot run, record why and stop as blocked.

At the end:
- Report changed files.
- Report verification results.
- Report known risks.
- Do not claim the phase is delivered until a fresh review verdict is delivered.
- If the phase is blocked, state the blocker classification and whether it is
  repairable by the next run.
```

## Reviewer Prompt

```text
Review the delivered Phase PHASE_N changes against the roadmap recorded in
DELIVERY_STATE.

Use this phase-gated delivery template:
automation/codex_phase_gated_delivery_automation_template.md

Take a skeptical code-review stance. Lead with findings.

Treat the roadmap phase scope, implementation notes, and exit criteria as the
source of truth. Review:
- changed files or artifacts
- relevant surrounding docs or code
- tests and verification evidence
- delivery log
- state file

Look for:
- missed acceptance criteria
- bugs or regressions
- weak or missing tests
- unsafe behavior
- unclear operator workflow
- docs or roadmap claims that overstate delivery
- scope creep into later phases

Output:
- Findings ordered by severity with file/line references when applicable
- Missing tests
- Residual risks
- Verdict: delivered, needs-fix, or blocked

Evaluate delivered behavior only. Do not give credit for intent.
```

## Blocker Conditions

Stop and ask the human operator when:

- credentials or external service access are required
- tests cannot run for environmental reasons
- destructive operations are needed
- product decisions are not answered by the roadmap
- implementation requires broad refactoring outside the current phase
- review/fix loop reaches the maximum iteration count
- roadmap, state, log, and automation guide disagree
- blocked remediation requires credentials, a product decision, destructive
  git, publication, promotion, or unapproved automation config changes
Read the current roadmap path from `STATE_FILE`; the `roadmap` field in
`delivery_state.json` is authoritative across lifecycle renames. Do not make a
saved automation prompt retarget mandatory for a `not_started_` to
`in_progress_` or `in_progress_` to `delivered_` rename when the prompt still
points at the stable state and guide files.
