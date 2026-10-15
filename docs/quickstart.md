# Quickstart

This quickstart is for a first local trial of roadmap delivery. It starts with
the repository demo fixture, then shows the dry-run scaffold path for a real
project. The safe demo path does not require network access, credentials,
published packages, or edits to a live Codex or Claude configuration.

Read `docs/who-this-is-for.md` first if you are deciding whether this workflow
fits your project.

## Start From The Local 0.3.0 Artifact

Use Python 3.12 and a POSIX environment. From the candidate source checkout,
build locally, then extract the entire skill into an isolated directory:

```bash
python3.12 scripts/build_release.py --output-dir dist --json
export TRIAL_HOME="$(mktemp -d)"
mkdir -p "$TRIAL_HOME/skill" "$TRIAL_HOME/project"
tar -xzf dist/roadmap-delivery-codex-skill-0.3.0.tar.gz \
  -C "$TRIAL_HOME/skill" --strip-components=1
export INSTALLED_SKILL="$TRIAL_HOME/skill"
cd "$TRIAL_HOME/project"
git init
python3.12 -I -S "$INSTALLED_SKILL/scripts/roadmap_delivery.py" version
python3.12 -I -S "$INSTALLED_SKILL/scripts/roadmap_delivery.py" scaffold \
  --repo-root . --roadmap-slug trial --approval-mode conservative --dry-run --json
python3.12 -I -S "$INSTALLED_SKILL/scripts/roadmap_delivery.py" scaffold \
  --repo-root . --roadmap-slug trial --approval-mode conservative --json
python3.12 -I -S "$INSTALLED_SKILL/scripts/roadmap_delivery.py" inspect \
  --repo-root . --roadmap-slug trial --json
python3.12 -I -S "$INSTALLED_SKILL/scripts/roadmap_delivery.py" validate \
  --repo-root . --roadmap-slug trial --json
```

For Claude, extract `roadmap-delivery-claude-plugin-0.3.0.tar.gz` instead and
set `INSTALLED_SKILL` to its `skills/roadmap-delivery-skill` directory. These
helpers need no pip, site packages, checkout imports or target-project schemas.
Validation can report expected setup warnings (missing runner and branch); it
does not prove phase delivery. Review planned artifacts before the writing
scaffold command. Keep this temporary install until you approve a live install.

Complete the roadmap's phase contracts, select/read back the real runner, and
validate the model policy before scheduling delivery. Configured model/reasoning
stay null until observed. Default stall threshold is two unique no-progress
runs; timestamps, logs and commits cannot count as progress. The terminal
controller writes an alert, requests status-only pause and confirms host readback
unless the corresponding context flag is explicitly false. See
`docs/autonomy-and-approval-policy.md` and `docs/migration-guide.md` for authority
and recovery. A prepared final review prompt does not mean review has run.

## Fit Check

This workflow fits projects where roadmap phases, approval boundaries,
verification commands, and review evidence need to be durable local artifacts.
It is a poor fit for small one-off edits, open-ended brainstorming, work that
requires credentials from the first step, or workflows that expect automatic
publication, promotion, or destructive git operations.

## Path 1: Safe Demo First

Start with Demo A, the normal evidence trail. Run these commands from the
repository root:

```bash
python3 -m roadmap_delivery.cli validate \
  --repo-root examples/demo-roadmap \
  --roadmap-slug demo-roadmap \
  --json

python3 -m roadmap_delivery.cli inspect \
  --repo-root examples/demo-roadmap \
  --roadmap-slug demo-roadmap \
  --json
```

If the package is not installed in your shell, use the checkout source path:

```bash
PYTHONPATH=src python3 -m roadmap_delivery.cli validate \
  --repo-root examples/demo-roadmap \
  --roadmap-slug demo-roadmap \
  --json
```

The demo fixture should show file-backed roadmap state, current phase status,
model-policy readback, approval decisions, and any validation warnings. It may
warn that no live saved automation config exists in your home directory. That
is acceptable for the fixture because the smoke tests use a temporary home and
the committed sample config under `examples/demo-roadmap/automation-config/`.

For a strict run with saved automation readback in a temporary home, follow
`examples/demo-roadmap/README.md#demo-a-normal-evidence-trail`. The fields to
look for are `current_phase`, `last_delivered_phase`, `allowed_operations`,
`required_model`, `required_reasoning_effort`,
`configured_automation_model`, and `blocked_remediation_required: false`.

Then run Demo B, the policy-mismatch recovery path:

```bash
less examples/demo-roadmap/README.md
```

Demo B intentionally validates a temporary saved automation config with the
wrong model and reasoning effort, then repairs only that temporary config. The
first report should include `automation_model_mismatch` and
`automation_reasoning_mismatch`; the repaired strict validation should return
`status: ok` with no findings.

Use the runtime checklist when you want a fuller offline exercise:

```bash
less examples/demo-roadmap/runtime-checklist.md
```

The checklist copies the demo into a temporary directory, stages generated
Codex and Claude package snapshots in temporary homes, and triggers blocked-run
and model-policy mismatch scenarios without changing a live install.

The setup wizard has its own safe local fixture recipes:

```bash
less examples/onboarding-wizard/README.md
```

Those commands preview or write starter artifacts inside temporary repository
roots and leave live host automation creation disabled.

To see the measured proof artifact for the local fixtures:

```bash
python3 -m roadmap_delivery.cli benchmark \
  --repo-root . \
  --json \
  --output /tmp/roadmap-delivery-evidence-benchmark.json
```

The benchmark copies fixture data into temporary repositories, creates
temporary saved automation configs, and reports exactly which invalid
advancement scenarios were caught. Treat it as local fixture evidence, not a
claim about every possible roadmap or release.

## Path 2: Real-Project Scaffold Dry Run

After the demo fixture is understandable, plan artifacts for a real project
without writing files:

```bash
python3 -m roadmap_delivery.cli scaffold \
  --repo-root "$PWD" \
  --roadmap-slug example-roadmap \
  --automation-id example-roadmap-delivery \
  --approval-mode conservative \
  --dry-run \
  --json
```

Review the planned paths and approval policy before running without
`--dry-run`. The scaffold command plans a roadmap, automation directory,
delivery state, delivery log, review/fix state, review directory, alert
directory, run log, model policy, and approval policy.

When you are ready to create starter files in a project checkout:

```bash
python3 -m roadmap_delivery.cli scaffold \
  --repo-root "$PWD" \
  --roadmap-slug example-roadmap \
  --automation-id example-roadmap-delivery \
  --approval-mode conservative \
  --json
```

Then validate the created artifacts:

```bash
python3 -m roadmap_delivery.cli validate \
  --repo-root "$PWD" \
  --roadmap-slug example-roadmap \
  --automation-id example-roadmap-delivery \
  --strict \
  --allow-warning missing_automation_config \
  --allow-warning current_branch_name_mismatch \
  --allow-warning worktree_dirty \
  --json
```

Use the warnings as setup work, not as delivery evidence. A real phase should
not be advanced until its roadmap acceptance criteria, required verification,
fresh review verdict, state file, delivery log, and branch all agree.

## First Run Expectations

The first useful run should make these facts visible:

- the current roadmap phase and expected phase branch
- the approval mode and allowed operations
- the required model and reasoning effort from `phase_model_policy.json`
- the saved automation model and reasoning readback when available
- the validation warnings that must be resolved before delivery claims
- the local files that record state, logs, reviews, run logs, and alerts

The workflow intentionally adds ceremony. That ceremony is worthwhile only when
phase boundaries, review evidence, approval gates, and recovery from blockers
matter more than a one-off task transcript.

## Safety Boundary

The safe demo path must stay local:

- no network access
- no credentials
- no live Codex or Claude home mutation
- no branch push
- no package or release publication
- no promotion to `main`
- no destructive git operation

If any first-use step appears to require one of those operations, stop and
inspect the command, repository path, and approval policy before continuing.
