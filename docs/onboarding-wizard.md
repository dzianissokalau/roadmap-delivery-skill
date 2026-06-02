# Onboarding Wizard Contract

This document defines the setup wizard command contract. The Phase 1 contract
adds a repository-local `wizard` command that can preview or write starter
roadmap automation artifacts without creating a live host automation.

The wizard should guide a user from an empty or existing checkout to a validated
starter roadmap automation contract. It must support a safe demo path before it
offers real-project writes.

## Target Commands

The command surface is explicit about whether it is planning or writing local
files:

```bash
python3 -m roadmap_delivery.cli wizard \
  --repo-root "$PWD" \
  --roadmap-slug example-roadmap \
  --automation-id example-roadmap-delivery \
  --dry-run \
  --json

python3 -m roadmap_delivery.cli wizard \
  --repo-root "$PWD" \
  --roadmap-slug example-roadmap \
  --automation-id example-roadmap-delivery \
  --write \
  --json
```

`--dry-run` is the default mode for first use. `--write` creates
repository-local artifacts only. The wizard must not edit a live Codex or
Claude home, push branches, publish artifacts, promote work, or activate saved
automations.

## Required Inputs

The wizard must collect or derive:

- roadmap title
- roadmap slug
- automation id
- repository root
- optional roadmap path
- initial phase name
- approval mode
- default model
- default reasoning effort
- execution environment label
- cadence recommendation
- host target label
- branch prefix

The wizard should default to conservative approval mode and local execution.
Delegated approval modes require an explicit `--approval-mode` selection and
are recorded in the generated `approval_policy.json`.

## Optional Inputs

The wizard may ask for:

- branch prefix, defaulting to `codex/`
- finalization model and reasoning effort
- alert mode, defaulting to local alert files
- provider-role config path
- existing roadmap path
- existing automation directory
- paths to copy from the demo fixture
- whether to create placeholder review and alert directories

Optional values must be visible in the JSON output. Missing optional values
must not be guessed silently.

## Generated Files

For a new roadmap automation, the wizard should generate or plan:

```text
roadmaps/not_started_<roadmap_slug>_roadmap.md
automation/<roadmap_slug>/automation_guide.md
automation/<roadmap_slug>/delivery_state.json
automation/<roadmap_slug>/delivery_log.md
automation/<roadmap_slug>/review_fix_state.json
automation/<roadmap_slug>/review_fix_log.md
automation/<roadmap_slug>/phase_model_policy.json
automation/<roadmap_slug>/approval_policy.json
automation/<roadmap_slug>/automation_run_log.jsonl
automation/<roadmap_slug>/reviews/.gitkeep
automation/<roadmap_slug>/alerts/.gitkeep
```

Generated state must include `schema_version: 1`, the roadmap path, current
phase, review iteration limits, model/readback fields, approval policy
readback, run/stall counters, completion fields, and blocked-remediation fields
used by the validators.

Generated approval policy must be valid against
`schemas/approval_policy.schema.json`. Generated model policy must be valid
against `schemas/phase_model_policy.schema.json`.

The generated state records the selected local runner target so the starter
artifacts can pass repository validation before saved automation creation. A
saved Codex or Claude automation readback should replace those configured
fields before activation.

## Validation Contract

Every wizard result must include the next validation commands:

```bash
python3 -m roadmap_delivery.cli validate \
  --repo-root "$PWD" \
  --roadmap-slug <roadmap-slug> \
  --automation-id <automation-id> \
  --strict \
  --allow-warning missing_automation_config \
  --allow-warning current_branch_name_mismatch \
  --allow-warning empty_review_dir \
  --allow-warning worktree_dirty \
  --allow-warning git_branch_failed \
  --allow-warning git_status_failed \
  --json

python3 -m roadmap_delivery.cli inspect \
  --repo-root "$PWD" \
  --roadmap-slug <roadmap-slug> \
  --automation-id <automation-id> \
  --json
```

The wizard should explain warnings as setup evidence. Missing automation
config and empty review directory warnings are expected before the separate
saved-automation setup step. The wizard must not mark a phase delivered or
advance the roadmap.

After `--write`, the command immediately runs validation and inspection
readback against the generated repository-local artifacts. Expected setup
warnings are kept in the JSON readback evidence; validation or inspection
errors make the wizard command fail.

## Safety Warnings

The wizard must warn before any path that would:

- write outside the selected repository root
- overwrite an existing roadmap or automation directory
- depend on credentials
- edit a live saved automation config
- install or sync global tools
- commit, push, merge, promote, publish, or delete branches
- run destructive filesystem or git operations

For existing files, the wizard emits a conflict report and stops unless
`--force` is explicitly selected. `--force` only overwrites the planned
repository-local wizard artifacts.

## Output Shape

JSON output should be stable enough for tests and demos:

```json
{
  "command": "wizard",
  "status": "planned",
  "dry_run": true,
  "write": false,
  "repo_root": "/path/to/repo",
  "roadmap_slug": "example-roadmap",
  "automation_id": "example-roadmap-delivery",
  "approval_mode": "conservative",
  "model_policy": {
    "default_model": "gpt-5.5",
    "default_reasoning_effort": "xhigh",
    "phase_overrides": {
      "0": {
        "model": "gpt-5.5",
        "reasoning_effort": "xhigh"
      },
      "finalization": {
        "model": "gpt-5.5",
        "reasoning_effort": "xhigh"
      }
    }
  },
  "artifact_groups": {
    "automation": [
      "/path/to/repo/automation/example_roadmap/approval_policy.json",
      "/path/to/repo/automation/example_roadmap/delivery_state.json"
    ],
    "docs": [
      "/path/to/repo/roadmaps/not_started_example_roadmap_roadmap.md",
      "/path/to/repo/automation/example_roadmap/automation_guide.md"
    ]
  },
  "planned_paths": [],
  "would_create": [],
  "live_automation": {
    "created": false,
    "edited": false,
    "activated": false
  },
  "warnings": [],
  "errors": [],
  "readback": {
    "ran": false,
    "status": "not_run"
  },
  "next_commands": []
}
```

In write mode, `created` records files that were written and `readback` records
compact validation and inspection summaries. Text output may be friendlier, but
it must be derived from the same structured result so tests can verify the
contract.

## Demo Requirements

The wizard should offer a demo route before real-project writes:

- Demo A: validate and inspect `examples/demo-roadmap` so the user can see a
  normal evidence trail with one delivered phase, one current phase, approval
  operations, model policy, saved automation readback, and no required blocked
  remediation.
- Demo B: run the model-policy mismatch fixture in a temporary home, confirm
  validation blocks advancement with `automation_model_mismatch` and
  `automation_reasoning_mismatch`, repair only the temporary saved config, and
  confirm strict validation returns `status: ok`.
- Wizard preview: run `wizard --dry-run --json` in a temporary repository and
  verify `planned_create` matches `would_create` while
  `live_automation.created` remains false.
- Wizard write: run `wizard --write --json` in a temporary git checkout and
  verify readback records expected setup warnings without creating live host
  automation.
- Scaffold dry run: run `scaffold --dry-run --json` and confirm it writes
  nothing.

The demo route must not require a live host binary. If a host binary is present,
live checks may be offered as optional follow-up only.

Executable recipes live in `examples/demo-roadmap/README.md` and
`examples/onboarding-wizard/README.md`.
