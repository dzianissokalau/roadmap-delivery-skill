# Onboarding Wizard Demo

This directory records the local first-use wizard demos. The commands are
designed for a clean checkout and temporary directories only; they do not edit
a live Codex or Claude home.

## Demo A: Preview Starter Artifacts

Use dry-run mode to see the files and policies the wizard would create:

```bash
DEMO_REPO="$(mktemp -d)/wizard-preview"
mkdir -p "$DEMO_REPO"

python3 -m roadmap_delivery.cli wizard \
  --repo-root "$DEMO_REPO" \
  --roadmap-slug demo-onboarding \
  --automation-id demo-onboarding-delivery \
  --dry-run \
  --json
```

The report should have `status: planned`, `dry_run: true`,
`live_automation.created: false`, and `planned_create` matching
`would_create`. No files are written.

## Demo B: Write And Read Back Locally

Use write mode in a temporary git checkout to create schema-valid starter
artifacts and immediately run validation and inspection readback:

```bash
DEMO_REPO="$(mktemp -d)/wizard-write"
mkdir -p "$DEMO_REPO"
git -C "$DEMO_REPO" init -b main

python3 -m roadmap_delivery.cli wizard \
  --repo-root "$DEMO_REPO" \
  --roadmap-slug demo-onboarding \
  --automation-id demo-onboarding-delivery \
  --roadmap-title "Demo Onboarding" \
  --write \
  --json
```

Expected setup warnings are recorded in `readback.validate.warning_codes` and
`readback.inspect.warning_codes`. They are setup evidence, not a phase delivery
claim. The wizard still leaves `live_automation.created: false`.

## Safety Boundary

These demos may create files under the selected temporary repository root.
They must not:

- edit saved app automation config
- use credentials or network access
- push, publish, merge, promote, or delete branches
- install or sync global tools
- write outside the selected repository root
